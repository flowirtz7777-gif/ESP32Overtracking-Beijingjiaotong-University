function out = diagnose_R3_hold(csv_name)
%DIAGNOSE_R3_HOLD  复现 hold 基线下 canonical R3 的晚报，并归因 polyshape
%                  「取最大连通区域」是否误删了包含 R3 的内切危险区。
%
%   out = diagnose_R3_hold()                  % 默认 020804 工况
%   out = diagnose_R3_hold('pid_scenario_*.csv')
%
%   ⚠️ 本脚本**不改任何 alpha 模型**，只用 hold 假设（α(τ)=α_now）。
%      目的纯是把「R3 为什么晚报」这个事实复现清楚、并定位机理。
%
%   ===== 方法 =====
%   沿密集决策网格（每 ~0.1s 一次在线判断），对 canonical R3 在每个时间窗
%   (PolyW/A/I) 下计算三种「是否危险」的判定，用以隔离失分环节：
%
%     1) swept_truth : rollout 过程中，R3 是否落入**任一逐步挂车车身矩形**
%        （H_right-T_right-T_left-H_left）内。这是「车身外缘在该时间窗内
%        是否物理扫过 R3」的真值，不经过任何多边形后处理。
%     2) poly_union  : R3 是否落入 polyshape(Simplify) 后**所有区域的并集**。
%     3) poly_largest: R3 是否落入**仅保留的最大连通区域**（= 当前
%        predict_swept 实际返回、在线判警实际使用的多边形）。
%
%   归因逻辑：
%     - swept_truth=1 且 poly_largest=0  → 多边形管线漏掉了真实扫掠命中。
%         再看 poly_union：
%           poly_union=1 且 poly_largest=0 → **「取最大块」规则误删**（主嫌疑）。
%           poly_union=0                   → 偶奇规则/边界构造阶段就丢了（另一类）。
%     - 另对比 BodyNow（当前车身占用）首次覆盖时刻，给出物理接触参照。
%
%   输出 out (struct)：固定目标集、三种判定的首次命中时刻、物理接触时刻、
%   提前量、归档目录；并出诊断图。

    if nargin < 1 || isempty(csv_name)
        csv_name = 'pid_scenario_20260530_020804.csv';
    end

    here = fileparts(mfilename('fullpath'));
    repo = fileparts(here);
    base = fullfile(repo, 'alpha一阶保持仿真');   % 公共函数 + CSV 来源
    addpath(base);
    addpath(here);

    csv_full = fullfile(base, 'scenarios', csv_name);
    if ~exist(csv_full, 'file')
        error('diag:csv', 'CSV 未找到: %s', csv_full);
    end
    scenario = load_pid_scenario(csv_full);
    p = vehicle_params(scenario.params);

    t   = scenario.time_s;
    dt  = scenario.dt_s;
    v   = scenario.inputs.v_mps;
    alpha = scenario.inputs.alpha_rad;
    truth = [scenario.states.xB_m, scenario.states.yB_m, ...
             scenario.states.theta_rad, scenario.inputs.phi_rad];
    N = numel(t);

    % ---------- 时间尺度（与主 demo 一致） ----------
    T_h = struct('W', 2.0, 'A', 1.0, 'I', 0.3);
    dt_pred = 0.01;
    tiers = {'W', 'A', 'I'};

    % ---------- 固定目标集（canonical，冻结） ----------
    tg = canonical_targets();
    n_tgt = numel(tg);
    P = reshape([tg.xy], 2, []).';   % n_tgt × 2

    % ---------- 决策网格 ----------
    scan_dt = 0.10;
    step = max(1, round(scan_dt/dt));
    scan = unique([1:step:N, N]);
    n_scan = numel(scan);

    % ---------- 物理接触时刻：BodyNow 首次覆盖 ----------
    contact = NaN(1, n_tgt);
    for jj = 1:n_scan
        k = scan(jj);
        bn = body_rect(truth(k,:), p);
        in = point_in_poly(P(:,1), P(:,2), bn);
        newly = in(:).' & isnan(contact);
        contact(newly) = t(k);
    end

    % ---------- 主扫描：三种判定 × 三层 × 每个决策时刻 ----------
    % hit.(tier).(kind)  : [n_tgt × n_scan] 逻辑
    kinds = {'swept_truth', 'poly_union', 'poly_largest'};
    hit = struct();
    for ti = 1:numel(tiers)
        for ki = 1:numel(kinds)
            hit.(tiers{ti}).(kinds{ki}) = false(n_tgt, n_scan);
        end
    end

    % 额外记录：R3 在 PolyA 窗下「被丢弃区域」命中的决策时刻（用于出图）
    dropped_frames = [];   % 记录 scan 索引

    for jj = 1:n_scan
        k  = scan(jj);
        s0 = truth(k, :);
        for ti = 1:numel(tiers)
            th = T_h.(tiers{ti});
            [bnd, body_stack] = rollout_hold(s0, alpha(k), v(k), p, th, dt_pred);

            % --- swept_truth：任一逐步车身矩形覆盖 ---
            st = false(n_tgt, 1);
            for m = 1:size(body_stack, 3)
                st = st | point_in_poly(P(:,1), P(:,2), body_stack(:,:,m));
            end
            hit.(tiers{ti}).swept_truth(:, jj) = st;

            % --- polyshape 拆区 ---
            [ps_all, ps_largest] = simplify_regions(bnd);
            in_union   = region_inside(P, ps_all);
            in_largest = region_inside(P, ps_largest);
            hit.(tiers{ti}).poly_union(:, jj)   = in_union;
            hit.(tiers{ti}).poly_largest(:, jj) = in_largest;

            % R3(第1个目标) 在 A 层：union 命中但 largest 丢 → 记录
            if strcmp(tiers{ti}, 'A') && in_union(1) && ~in_largest(1)
                dropped_frames(end+1) = jj; %#ok<AGROW>
            end
        end
    end

    % ---------- 首次命中时刻 + 提前量 ----------
    first = struct();
    lead  = struct();
    for ti = 1:numel(tiers)
        for ki = 1:numel(kinds)
            fa = NaN(1, n_tgt);
            H = hit.(tiers{ti}).(kinds{ki});
            for j = 1:n_tgt
                f = find(H(j,:), 1, 'first');
                if ~isempty(f), fa(j) = t(scan(f)); end
            end
            first.(tiers{ti}).(kinds{ki}) = fa;
            lead.(tiers{ti}).(kinds{ki})  = contact - fa;
        end
    end

    % ---------- 控制台报告 ----------
    fprintf('\n================ R3 hold-基线 诊断 ================\n');
    fprintf('工况: %s   平均车速 %.2f m/s\n', csv_name, mean(v));
    fprintf('canonical R3 = (%.4f, %.4f)\n', P(1,1), P(1,2));
    fprintf('R3 物理接触时刻 (BodyNow 首次覆盖) = %.2f s\n\n', contact(1));

    fprintf('---- R3 三种判定的首次命中时刻 / 提前量 (s) ----\n');
    fprintf('%-6s | %-22s | %-22s | %-22s\n', 'tier', 'swept_truth', 'poly_union', 'poly_largest');
    for ti = 1:numel(tiers)
        T = tiers{ti};
        fprintf('%-6s | t=%6.2f lead=%6.2f   | t=%6.2f lead=%6.2f   | t=%6.2f lead=%6.2f\n', ...
            ['Poly' T], ...
            first.(T).swept_truth(1), lead.(T).swept_truth(1), ...
            first.(T).poly_union(1),  lead.(T).poly_union(1), ...
            first.(T).poly_largest(1),lead.(T).poly_largest(1));
    end

    % ---------- 归因结论 ----------
    fprintf('\n---- 归因 (以 PolyA 层 R3 为准) ----\n');
    st_A  = first.A.swept_truth(1);
    un_A  = first.A.poly_union(1);
    lg_A  = first.A.poly_largest(1);
    n_drop = numel(unique(dropped_frames));
    if ~isnan(st_A) && (isnan(lg_A) || lg_A > st_A + 1e-9)
        fprintf('• 真实扫掠 (swept_truth) 在 t=%.2f 就该报，但 largest 区在 t=%.2f 才报（或从未报）。\n', st_A, lg_A);
        if ~isnan(un_A) && (isnan(lg_A) || un_A < lg_A - 1e-9)
            fprintf('• poly_union 在 t=%.2f 命中而 poly_largest 在 t=%.2f → 「取最大连通区域」规则确实误删了含 R3 的区域。\n', un_A, lg_A);
            fprintf('  → 在 %d 个决策时刻，R3 落在被丢弃的非最大区域内。证据成立。\n', n_drop);
        else
            fprintf('• 但 poly_union 与 poly_largest 命中时刻一致 → 丢失发生在更早的偶奇规则/边界构造，而非「取最大块」。\n');
        end
    else
        fprintf('• 在 PolyA 层，largest 区的命中时刻与真实扫掠一致 → 「取最大块」未造成 R3 晚报；\n');
        fprintf('  晚报机理需转向 horizon 覆盖 / alpha 假设方向（留待下一步，本轮不改 alpha）。\n');
    end

    % ---------- 出图 ----------
    run_dir = make_run_dir(here, csv_name);
    plot_diag(scenario, truth, p, P, tg, scan, t, alpha, v, dt_pred, ...
              dropped_frames, contact, run_dir);

    % ---------- 输出 ----------
    out = struct();
    out.csv = csv_name;
    out.targets = tg;
    out.contact = contact;
    out.first = first;
    out.lead = lead;
    out.hit = hit;
    out.scan_t = t(scan);
    out.dropped_frames_A = unique(dropped_frames);
    out.run_dir = run_dir;
    write_summary(run_dir, csv_name, P, contact, first, lead, tiers, unique(dropped_frames), t, scan);
    fprintf('\n[R3-DIAG] 完成，结果 + 图 + summary 已存到:\n  %s\n\n', run_dir);
end


% ===================================================================
function [bnd, body_stack] = rollout_hold(s0, alpha_now, v_now, p, T_h, dt_pred)
%ROLLOUT_HOLD  hold 假设下右外缘边界点 + 每步车身矩形堆栈。
    half_w = 0.5 * p.width;
    M = floor(T_h / dt_pred);
    H_right = zeros(M+1, 2);
    T_right = zeros(M+1, 2);
    body_stack = zeros(5, 2, M+1);   % 每步闭合矩形 (5×2)
    s = s0(:);
    for k = 1:M+1
        d = derive_points(s, p);
        cTt = cos(d.theta_t); sTt = sin(d.theta_t);
        rn = [sTt, -cTt];
        H_right(k,:) = d.H + half_w*rn;
        T_right(k,:) = d.T + half_w*rn;
        body_stack(:,:,k) = [d.H+half_w*rn; d.T+half_w*rn; d.T-half_w*rn; d.H-half_w*rn; d.H+half_w*rn];
        if k <= M
            s = kinematics_step(s, alpha_now, v_now, p, dt_pred);  % α 保持
        end
    end
    bnd = [H_right; flipud(T_right)];
end


function [ps_all, ps_largest] = simplify_regions(bnd)
%SIMPLIFY_REGIONS  对原始（可能自相交）边界做 polyshape 简化，
%   返回 (全部区域 polyshape, 仅最大连通区域 polyshape)。
    warning('off', 'MATLAB:polyshape:repairedBySimplify');
    ps_all = polyshape(bnd(:,1), bnd(:,2), 'Simplify', true);
    warning('on', 'MATLAB:polyshape:repairedBySimplify');
    if ps_all.NumRegions <= 1
        ps_largest = ps_all;
        return;
    end
    regs = regions(ps_all);
    a = arrayfun(@area, regs);
    [~, idx] = max(a);
    ps_largest = regs(idx);
end


function in = region_inside(P, ps)
%REGION_INSIDE  点是否在 polyshape 内（用 isinterior），返回 n×1 逻辑。
    if isempty(ps) || ps.NumRegions < 1
        in = false(size(P,1), 1);
        return;
    end
    in = isinterior(ps, P(:,1), P(:,2));
end


function r = body_rect(s, p)
%BODY_RECT  当前挂车车身矩形（H-T 按车宽扩展），闭合 5×2。
    d = derive_points(s, p);
    half_w = 0.5*p.width;
    rn = [sin(d.theta_t), -cos(d.theta_t)];
    r = [d.H+half_w*rn; d.T+half_w*rn; d.T-half_w*rn; d.H-half_w*rn; d.H+half_w*rn];
end


function run_dir = make_run_dir(here, csv_name)
    root = fullfile(here, 'runs');
    if ~exist(root,'dir'), mkdir(root); end
    [~, stem] = fileparts(csv_name);
    run_dir = fullfile(root, sprintf('%s__%s', datestr(now,'yyyymmdd_HHMMSS'), stem));
    if ~exist(run_dir,'dir'), mkdir(run_dir); end
end


function plot_diag(scenario, truth, p, P, tg, scan, t, alpha, v, dt_pred, dropped_frames, contact, run_dir)
%PLOT_DIAG  画两张图：
%   fig1: 一个「最大块误删」代表帧的 raw边界 / 全区域 / 最大块 / R3 对比
%   fig2: R3 接触窗附近若干决策帧的 PolyA largest 多边形 + R3
    set(0,'DefaultFigureColor','white');
    df = unique(dropped_frames);

    % --- fig1: 代表帧拆解 ---
    fig1 = figure('Name','R3 诊断 — polyshape 拆区', 'Position',[60 80 1400 460]);
    if ~isempty(df)
        rep = df(round(numel(df)/2));   % 取中间一个被丢帧
    else
        % 没有被丢帧：取 R3 接触前 1s 那帧
        [~, rep] = min(abs(t(scan) - (contact(1)-1.0)));
    end
    k = scan(rep);
    [bnd, ~] = rollout_hold(truth(k,:), alpha(k), v(k), p, 1.0, dt_pred);
    [ps_all, ps_largest] = simplify_regions(bnd);

    subplot(1,3,1);
    plot(bnd(:,1), bnd(:,2), '-', 'Color',[0.5 0.5 0.5], 'LineWidth',1.0); hold on;
    scatter(P(1,1), P(1,2), 90, [0.9 0.2 0.2], 'filled', 'MarkerEdgeColor','k');
    text(P(1,1)+0.2, P(1,2), 'R3'); axis equal; grid on;
    title(sprintf('原始边界 (自相交) @ t=%.2fs', t(k)));
    xlabel('X (m)'); ylabel('Y (m)');

    subplot(1,3,2);
    plot(ps_all, 'FaceColor',[0.3 0.6 0.9], 'FaceAlpha',0.25, 'EdgeColor',[0.2 0.4 0.7]); hold on;
    scatter(P(1,1), P(1,2), 90, [0.9 0.2 0.2], 'filled', 'MarkerEdgeColor','k');
    text(P(1,1)+0.2, P(1,2), 'R3'); axis equal; grid on;
    title(sprintf('polyshape 全部区域 (NumRegions=%d)', ps_all.NumRegions));
    xlabel('X (m)'); ylabel('Y (m)');

    subplot(1,3,3);
    plot(ps_largest, 'FaceColor',[0.9 0.55 0.15], 'FaceAlpha',0.30, 'EdgeColor',[0.7 0.4 0.1]); hold on;
    scatter(P(1,1), P(1,2), 90, [0.9 0.2 0.2], 'filled', 'MarkerEdgeColor','k');
    text(P(1,1)+0.2, P(1,2), 'R3'); axis equal; grid on;
    in_lg = region_inside(P, ps_largest);
    title(sprintf('仅最大区域 (当前用) — R3 in=%d', in_lg(1)));
    xlabel('X (m)'); ylabel('Y (m)');

    sgtitle('R3 归因：原始边界 → 全区域并集 → 仅最大块（看 R3 是否在被丢弃区域里）', 'FontWeight','bold');
    saveas(fig1, fullfile(run_dir, '01_polyshape_breakdown.png'));

    % --- fig2: 接触窗附近 PolyA largest 叠加 ---
    fig2 = figure('Name','R3 诊断 — 接触窗 PolyA', 'Position',[100 120 900 720]);
    plot(scenario.points.H(:,1), scenario.points.H(:,2), '-', 'Color',[0.2 0.4 0.85], 'LineWidth',1.0); hold on;
    plot(scenario.points.T(:,1), scenario.points.T(:,2), '-', 'Color',[0.2 0.65 0.3], 'LineWidth',1.0);
    grid on; axis equal;
    win = find(t(scan) >= contact(1)-2.2 & t(scan) <= contact(1)+0.2);
    cmap = parula(max(1,numel(win)));
    for ii = 1:numel(win)
        jj = win(ii); k = scan(jj);
        [bnd,~] = rollout_hold(truth(k,:), alpha(k), v(k), p, 1.0, dt_pred);
        [~, ps_lg] = simplify_regions(bnd);
        if ps_lg.NumRegions >= 1
            plot(ps_lg, 'FaceColor', cmap(ii,:), 'FaceAlpha',0.10, 'EdgeColor', cmap(ii,:));
        end
    end
    scatter(P(:,1), P(:,2), 90, 'r', 'filled', 'MarkerEdgeColor','k');
    for j=1:size(P,1), text(P(j,1)+0.15, P(j,2), tg(j).name, 'FontWeight','bold'); end
    title({'接触窗附近各决策帧的 PolyA (仅最大区域)', sprintf('R3 物理接触 t=%.2fs', contact(1))}, 'FontWeight','bold');
    xlabel('X (m)'); ylabel('Y (m)');
    saveas(fig2, fullfile(run_dir, '02_polyA_around_contact.png'));
end


function write_summary(run_dir, csv_name, P, contact, first, lead, tiers, df, t, scan) %#ok<INUSL>
    fid = fopen(fullfile(run_dir,'summary.txt'),'w','n','UTF-8');
    if fid<0, return; end
    cu = onCleanup(@() fclose(fid));
    fprintf(fid,'================ R3 hold-基线 诊断摘要 ================\n\n');
    fprintf(fid,'生成时间 : %s\n', datestr(now,'yyyy-mm-dd HH:MM:SS'));
    fprintf(fid,'工况     : %s\n', csv_name);
    fprintf(fid,'canonical R3 = (%.6f, %.6f)\n', P(1,1), P(1,2));
    fprintf(fid,'R3 物理接触时刻 (BodyNow 首次覆盖) = %.2f s\n\n', contact(1));
    fprintf(fid,'---- R3 三种判定首次命中时刻 t / 提前量 lead (s) ----\n');
    fprintf(fid,'%-7s | %-20s | %-20s | %-20s\n','tier','swept_truth','poly_union','poly_largest');
    for ti=1:numel(tiers)
        T=tiers{ti};
        fprintf(fid,'%-7s | t=%6.2f lead=%6.2f | t=%6.2f lead=%6.2f | t=%6.2f lead=%6.2f\n', ...
            ['Poly' T], first.(T).swept_truth(1),lead.(T).swept_truth(1), ...
            first.(T).poly_union(1),lead.(T).poly_union(1), ...
            first.(T).poly_largest(1),lead.(T).poly_largest(1));
    end
    fprintf(fid,'\nPolyA 层 R3 落入「被丢弃非最大区域」的决策帧数 = %d\n', numel(df));
    if ~isempty(df)
        fprintf(fid,'被丢帧时刻 (s): %s\n', strjoin(arrayfun(@(x) sprintf('%.2f',t(scan(x))), df,'UniformOutput',false), ', '));
    end
    fprintf(fid,'\n说明: swept_truth=逐步车身矩形真值扫掠; poly_union=全区域并集; poly_largest=当前在线用的仅最大区域。\n');
    fprintf(fid,'      若 swept_truth 早于 poly_largest 且 poly_union 与之一致 → 「取最大块」规则误删内切危险区。\n');
end
