function out = compare_alpha_schemes(csv_name)
%COMPARE_ALPHA_SCHEMES  同一 CSV 工况下横向对比 5 种 alpha 预测方案。
%
%   out = compare_alpha_schemes()              % 默认用 pid_scenario_20260530_020804.csv
%   out = compare_alpha_schemes(csv_name)      % 指定 scenarios 目录下的 CSV 文件名
%
%   被对比的 5 个方案（各自独立文件夹，predict_swept 签名一致）：
%     0  alpha一阶保持仿真     hold    α(τ)=α_now                （基线）
%     A  alpha线性外推仿真     linear  α(τ)=α_now+α̇·τ
%     B  alpha多假设并集仿真   union   保持∪继续打∪回正 三假设并集  ⭐主推
%     C  alpha扇形包络仿真     fan     α(τ)∈[α₀-rate·τ, α₀+rate·τ] 包络（上界）
%     D  alpha二阶外推仿真     quad    α(τ)=α₀+α̇·τ+½α̈·τ²
%
%   对比维度：
%     1) 几何：同一关键帧下 5 个方案的 PolyW 叠加（看谁更大/更保守）
%     2) 面积：各方案 PolyW / PolyA 的平均扫掠面积（柱状）
%     3) 报警提前量：对一组固定雷达目标，每个方案"首次把目标判入 PolyA"
%        的时刻——越早 = 提前量越大 = 越安全（但要权衡误报）
%
%   语义说明：
%     - 目标在世界坐标系中固定，5 个方案评估完全相同的目标，保证公平。
%     - "首次报警时刻"沿关键帧时间轴扫描，取最早把目标纳入对应 tier 的关键帧时间。
%     - 基线(hold)通常报警最晚（α̇=0 假设在弯道收尾提前量不足，即 v1.0.1 的 R3 反例）。
%
%   输出 out (struct)：每个方案的多边形、面积、命中时刻矩阵 + 归档目录。

    if nargin < 1 || isempty(csv_name)
        csv_name = 'pid_scenario_20260530_020804.csv';
    end

    repo_root = fileparts(mfilename('fullpath'));
    repo_root = fileparts(repo_root);   % 上一级 = 仓库根

    schemes = struct( ...
        'tag',    {'hold', 'linear', 'union', 'fan', 'quad'}, ...
        'folder', {'alpha一阶保持仿真', 'alpha线性外推仿真', 'alpha多假设并集仿真', ...
                   'alpha扇形包络仿真', 'alpha二阶外推仿真'}, ...
        'label',  {'0·保持(基线)', 'A·线性外推', 'B·多假设并集', 'C·扇形包络', 'D·二阶外推'} );
    n_scheme = numel(schemes);

    % ---------- 时间尺度（与各方案 demo 保持一致） ----------
    T_h_W = 2.0; T_h_A = 1.0; T_h_I = 0.3;
    dt_pred = 0.01;
    n_keyframes = 20;

    % ---------- 加载工况（用基线文件夹的 loader，全路径无歧义） ----------
    base_dir = fullfile(repo_root, schemes(1).folder);
    % 把基线文件夹加入路径：point_in_poly/derive_points/kinematics_step/
    % vehicle_params/load_pid_scenario 各方案完全一致，全局可用即可；
    % predict_swept 各异，但 cd 进方案目录时"当前目录函数"优先于路径，不冲突。
    addpath(base_dir);
    csv_full = fullfile(base_dir, 'scenarios', csv_name);
    if ~exist(csv_full, 'file')
        error('compare:csvNotFound', 'CSV 未找到: %s', csv_full);
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

    keyframes = unique(round(linspace(1, N, n_keyframes)));
    n_kf = numel(keyframes);

    % 报警提前量用的密集决策网格（每 ~0.15s 做一次预测判内），
    % 否则关键帧(~1.4s 间隔)太粗，PolyA(1s≈3m) 来不及在车身到达前抓到目标，
    % 五个方案会被 BodyNow(物理到达时刻) 拉平、显示不出差异。
    scan_dt   = 0.15;
    scan_step = max(1, round(scan_dt / dt));
    scan_idx  = unique([1:scan_step:N, N]);

    % ---------- 固定雷达目标（世界系，方案无关，保证公平） ----------
    targets = local_make_fixed_targets(truth, keyframes, p);
    n_tgt = size(targets, 1);

    % ---------- 物理接触时刻（方案无关）：BodyNow 首次覆盖目标 ----------
    % 作为"报警提前量"的参照零点：lead = contact_time - first_alarm_time。
    contact_time = NaN(1, n_tgt);
    for ii = 1:numel(scan_idx)
        k = scan_idx(ii);
        body_now = local_body_now(truth(k, :), p);
        inb = point_in_poly(targets(:,1), targets(:,2), body_now);
        newly = inb(:).' & isnan(contact_time);
        contact_time(newly) = t(k);
    end

    fprintf('\n========== alpha 方案横向对比 ==========\n');
    fprintf('工况 CSV     : %s\n', csv_name);
    fprintf('车型         : l=%.2f l_h=%.2f L=%.2f W=%.2f phi_max=%.1f°\n', ...
        p.l, p.l_h, p.L, p.width, rad2deg(p.phi_max));
    fprintf('关键帧       : %d 帧, 平均车速 %.2f m/s\n', n_kf, mean(v));
    fprintf('固定雷达目标 : %d 个\n', n_tgt);
    fprintf('时间窗       : PolyW=%.1fs PolyA=%.1fs PolyI=%.1fs, dt_pred=%.3fs\n\n', ...
        T_h_W, T_h_A, T_h_I, dt_pred);

    % ---------- 逐方案计算 ----------
    results = cell(1, n_scheme);
    for si = 1:n_scheme
        sc = schemes(si);
        fprintf('[%d/%d] 运行方案 %s (%s) ...\n', si, n_scheme, sc.label, sc.folder);
        results{si} = local_run_scheme(repo_root, sc, alpha, v, dt, truth, ...
            keyframes, scan_idx, targets, T_h_W, T_h_A, T_h_I, dt_pred, p);
        fprintf('       PolyW 平均面积 = %7.3f m²   PolyA 平均面积 = %7.3f m²\n', ...
            results{si}.areaW_mean, results{si}.areaA_mean);
    end

    % ---------- 归档目录 ----------
    run_dir = local_make_run_dir(repo_root, csv_name);
    fprintf('\n[对比] 归档目录: %s\n', run_dir);

    % ---------- 可视化 ----------
    scheme_colors = [0.45 0.45 0.45;   % 0 灰
                     0.20 0.55 0.85;   % A 蓝
                     0.90 0.30 0.25;   % B 红 (主推)
                     0.95 0.65 0.15;   % C 橙
                     0.45 0.30 0.70];  % D 紫
    labels = {schemes.label};

    set(0, 'DefaultFigureColor', 'white');

    % --- Figure 1: 同关键帧 PolyW 叠加（3 个代表帧）---
    rep_kf = unique(round(linspace(round(n_kf*0.4), round(n_kf*0.8), 3)));
    fig1 = figure('Name', '方案对比 — PolyW 几何叠加', 'Position', [60 80 1500 480]);
    for r = 1:numel(rep_kf)
        subplot(1, numel(rep_kf), r);
        plot(scenario.points.H(:,1), scenario.points.H(:,2), '-', 'Color', [0.2 0.4 0.85], 'LineWidth', 1.0); hold on;
        plot(scenario.points.T(:,1), scenario.points.T(:,2), '-', 'Color', [0.2 0.65 0.3], 'LineWidth', 1.0);
        grid on; axis equal;
         kf = rep_kf(r);
        hh = gobjects(1, n_scheme);
        for si = 1:n_scheme
            pw = results{si}.polyW{kf};
            hh(si) = plot(pw(:,1), pw(:,2), '-', 'Color', scheme_colors(si,:), ...
                'LineWidth', 1.6, 'DisplayName', labels{si});
        end
        scatter(targets(:,1), targets(:,2), 50, [0.1 0.1 0.1], 'filled', 'HandleVisibility', 'off');
        title(sprintf('关键帧 t=%.2fs 的 PolyW (T_h=2s)', t(keyframes(kf))), 'FontWeight', 'bold');
        xlabel('X (m)'); ylabel('Y (m)');
        if r == 1, legend(hh, 'Location', 'best', 'FontSize', 8, 'Box', 'off'); end
    end
    sgtitle('5 方案 PolyW 几何对比：扇形包络(C)最大、基线(0)最小', 'FontWeight', 'bold');

    % --- Figure 2: 平均扫掠面积柱状 ---
    fig2 = figure('Name', '方案对比 — 平均扫掠面积', 'Position', [100 120 900 520]);
    areaW = cellfun(@(r) r.areaW_mean, results);
    areaA = cellfun(@(r) r.areaA_mean, results);
    bar_data = [areaW(:), areaA(:)];
    hb = bar(bar_data, 'grouped'); grid on;
    hb(1).FaceColor = [0.95 0.75 0.20];
    hb(2).FaceColor = [0.90 0.45 0.20];
    set(gca, 'XTickLabel', labels, 'XTickLabelRotation', 15);
    ylabel('平均扫掠面积 (m²)');
    legend({'PolyW (T_h=2.0s)', 'PolyA (T_h=1.0s)'}, 'Location', 'northwest');
    title('各方案平均扫掠面积（越大越保守，误报风险越高）', 'FontWeight', 'bold');
    for si = 1:n_scheme
        text(si-0.15, areaW(si)+0.3, sprintf('%.1f', areaW(si)), 'FontSize', 8, 'HorizontalAlignment','center');
        text(si+0.15, areaA(si)+0.3, sprintf('%.1f', areaA(si)), 'FontSize', 8, 'HorizontalAlignment','center');
    end

    % --- Figure 3: 报警提前量（PolyA 预测命中早于物理接触多少秒）---
    % lead(si, j) = contact_time(j) - first_alarm_time(si, j)
    %   越大 = 越早预测到 = 提前量越大 = 越安全。NaN=该方案对该目标从未报警。
    first_alarm = NaN(n_scheme, n_tgt);   % 首次报警的绝对时刻 (s)
    lead = NaN(n_scheme, n_tgt);          % 提前量 (s)
    for si = 1:n_scheme
        fa_idx = results{si}.first_alarm_idx;
        for j = 1:n_tgt
            if ~isnan(fa_idx(j))
                first_alarm(si, j) = t(fa_idx(j));
                if ~isnan(contact_time(j))
                    lead(si, j) = contact_time(j) - first_alarm(si, j);
                end
            end
        end
    end

    fig3 = figure('Name', '方案对比 — PolyA 报警提前量', 'Position', [140 80 1100 560]);
    valid_tgt = find(any(~isnan(lead), 1));
    if isempty(valid_tgt)
        annotation('textbox', [0.2 0.45 0.6 0.1], 'String', ...
            '所有固定目标在所有方案下均未触发 PolyA（可调目标位置或工况）', ...
            'FontSize', 12, 'HorizontalAlignment', 'center', 'EdgeColor', 'none');
    else
        plot_data = lead(:, valid_tgt).';   % [n_valid × n_scheme]
        plot_data(isnan(plot_data)) = 0;    % 未报警的画 0 高度（柱缺失）
        hb3 = bar(plot_data, 'grouped'); grid on;
        for si = 1:n_scheme
            hb3(si).FaceColor = scheme_colors(si, :);
        end
        set(gca, 'XTickLabel', arrayfun(@(j) sprintf('R%d', j), valid_tgt, 'UniformOutput', false));
        xlabel('雷达目标'); ylabel('PolyA 报警提前量 (s)  = 物理接触时刻 - 首次报警时刻');
        legend(labels, 'Location', 'best', 'FontSize', 8, 'Box', 'off');
        title({'PolyA 报警提前量对比：柱越高 = 越早预测到危险 = 越安全', ...
               '(柱高 0 = 该方案对该目标未提前报警)'}, 'FontWeight', 'bold');
    end

    % ---------- 输出 + 归档 ----------
    out = struct();
    out.csv_name    = csv_name;
    out.schemes     = schemes;
    out.keyframes   = keyframes;
    out.t           = t;
    out.targets     = targets;
    out.results     = results;
    out.first_alarm = first_alarm;
    out.lead        = lead;
    out.contact_time = contact_time;
    out.areaW       = areaW;
    out.areaA       = areaA;
    out.run_dir     = run_dir;

    saveas(fig1, fullfile(run_dir, '01_polyW_overlay.png'));
    saveas(fig2, fullfile(run_dir, '02_swept_area_bar.png'));
    saveas(fig3, fullfile(run_dir, '03_alarm_advance.png'));
    local_write_summary(run_dir, csv_name, p, schemes, labels, areaW, areaA, ...
                        first_alarm, lead, contact_time, valid_tgt);

    fprintf('\n[对比] 完成。三幅图 + summary.txt 已保存到:\n  %s\n\n', run_dir);
end


% ======================================================================
function res = local_run_scheme(repo_root, sc, alpha, v, dt, truth, ...
        keyframes, scan_idx, targets, T_h_W, T_h_A, T_h_I, dt_pred, p)
%LOCAL_RUN_SCHEME  cd 进方案文件夹，按其 predict_swept 计算多边形/面积/命中。
%   靠 MATLAB"当前目录函数优先于路径"的规则保证调用到本方案的 predict_swept。
%
%   两套计算：
%     - keyframes 上：算 PolyW/A/I 用于几何叠加图 + 面积统计（粗，画图够用）
%     - scan_idx 上：只算 PolyA，密集扫描，求每个目标"首次被 PolyA 抓到"的
%       时刻 = 在线预测提前量（不含 BodyNow 兜底，确保比的是"预测能力"）

    old_dir = pwd;
    cu = onCleanup(@() cd(old_dir));
    cd(fullfile(repo_root, sc.folder));
    rehash;

    n_kf  = numel(keyframes);
    n_tgt = size(targets, 1);

    polyW = cell(1, n_kf);
    polyA = cell(1, n_kf);
    polyI = cell(1, n_kf);
    areaW = zeros(1, n_kf);
    areaA = zeros(1, n_kf);

    hitW = false(n_tgt, n_kf);
    hitA = false(n_tgt, n_kf);
    hitI = false(n_tgt, n_kf);

    for ii = 1:n_kf
        k  = keyframes(ii);
        s0 = truth(k, :);
        [aW, aA, aI] = local_predict_tiers(sc, s0, alpha, v, dt, k, ...
            T_h_W, T_h_A, T_h_I, dt_pred, p);

        polyW{ii} = aW; polyA{ii} = aA; polyI{ii} = aI;
        areaW(ii) = local_poly_area(aW);
        areaA(ii) = local_poly_area(aA);

        % 命中判定（含 BodyNow 兜底，与 demo 一致）— 用于几何图标注
        body_now = local_body_now(truth(k, :), p);
        inb = point_in_poly(targets(:,1), targets(:,2), body_now);
        hitW(:, ii) = point_in_poly(targets(:,1), targets(:,2), aW) | inb;
        hitA(:, ii) = point_in_poly(targets(:,1), targets(:,2), aA) | inb;
        hitI(:, ii) = point_in_poly(targets(:,1), targets(:,2), aI) | inb;
    end

    % ===== 密集网格：求 PolyA 首次预测命中时刻（不含 BodyNow） =====
    first_alarm_idx = NaN(1, n_tgt);
    for jj = 1:numel(scan_idx)
        k = scan_idx(jj);
        [~, aA, ~] = local_predict_tiers(sc, truth(k,:), alpha, v, dt, k, ...
            T_h_W, T_h_A, T_h_I, dt_pred, p);
        inA = point_in_poly(targets(:,1), targets(:,2), aA);
        newly = inA(:).' & isnan(first_alarm_idx);
        first_alarm_idx(newly) = k;
    end

    res = struct();
    res.tag        = sc.tag;
    res.label      = sc.label;
    res.polyW      = polyW;
    res.polyA      = polyA;
    res.polyI      = polyI;
    res.areaW_mean = mean(areaW);
    res.areaA_mean = mean(areaA);
    res.hitW       = hitW;
    res.hitA       = hitA;
    res.hitI       = hitI;
    res.first_alarm_idx = first_alarm_idx;   % CSV 行索引 (NaN=未报警)
end


function [aW, aA, aI] = local_predict_tiers(sc, s0, alpha, v, dt, k, ...
        T_h_W, T_h_A, T_h_I, dt_pred, p)
%LOCAL_PREDICT_TIERS  按方案 tag 分派 predict_swept，返回三层多边形。
    switch sc.tag
        case {'hold', 'fan'}
            aW = predict_swept(s0, alpha(k), v(k), p, T_h_W, dt_pred, 0);
            aA = predict_swept(s0, alpha(k), v(k), p, T_h_A, dt_pred, 0);
            aI = predict_swept(s0, alpha(k), v(k), p, T_h_I, dt_pred, 0);
        case {'linear', 'union'}
            ad = estimate_alpha_dot(alpha, k, dt, 0.25);
            aW = predict_swept(s0, alpha(k), v(k), p, T_h_W, dt_pred, ad);
            aA = predict_swept(s0, alpha(k), v(k), p, T_h_A, dt_pred, ad);
            aI = predict_swept(s0, alpha(k), v(k), p, T_h_I, dt_pred, ad);
        case 'quad'
            [ad, add] = estimate_alpha_derivs(alpha, k, dt, 0.35);
            aW = predict_swept(s0, alpha(k), v(k), p, T_h_W, dt_pred, ad, add);
            aA = predict_swept(s0, alpha(k), v(k), p, T_h_A, dt_pred, ad, add);
            aI = predict_swept(s0, alpha(k), v(k), p, T_h_I, dt_pred, ad, add);
        otherwise
            error('compare:unknownTag', '未知方案 tag: %s', sc.tag);
    end
end


function a = local_poly_area(poly)
%LOCAL_POLY_AREA  闭合多边形面积（鞋带公式，取绝对值）。
    if size(poly, 1) < 3, a = 0; return; end
    x = poly(:, 1); y = poly(:, 2);
    if isequal(poly(1,:), poly(end,:))
        x = x(1:end-1); y = y(1:end-1);
    end
    a = abs(sum(x .* circshift(y, -1) - circshift(x, -1) .* y)) / 2;
end


function body_poly = local_body_now(s, p)
%LOCAL_BODY_NOW  当前挂车矩形占用区（H-T 线段按车宽扩展）。
    cT = cos(s(3)); sT = sin(s(3));
    theta_t = s(3) - s(4);
    H = [s(1) + p.l_h*cT, s(2) + p.l_h*sT];
    T = [H(1) - p.L*cos(theta_t), H(2) - p.L*sin(theta_t)];
    half_w = 0.5 * p.width;
    rn = [sin(theta_t), -cos(theta_t)];
    body_poly = [H+half_w*rn; T+half_w*rn; T-half_w*rn; H-half_w*rn; H+half_w*rn];
end


function targets = local_make_fixed_targets(truth, keyframes, p)
%LOCAL_MAKE_FIXED_TARGETS  沿挂车后端 T 的未来轨迹布置固定目标（世界系）。
%   策略：在中后段若干关键帧，取该帧的挂车右沿中点稍向弯心偏移，
%         使大多数方案都能命中，便于对比"谁报得早"。确定性，可复现。
    rng(7);
    n_kf = numel(keyframes);
    pick = unique(round(linspace(round(n_kf*0.35), round(n_kf*0.85), 6)));
    targets = zeros(numel(pick), 2);
    half_w = 0.5 * p.width;
    N = size(truth, 1);
    for i = 1:numel(pick)
        k = keyframes(pick(i));
        cT = cos(truth(k,3)); sT = sin(truth(k,3));
        theta_t = truth(k,3) - truth(k,4);
        H = [truth(k,1)+p.l_h*cT, truth(k,2)+p.l_h*sT];
        T = [H(1)-p.L*cos(theta_t), H(2)-p.L*sin(theta_t)];
        rn = [sin(theta_t), -cos(theta_t)];
        mid = (H + T) / 2 + half_w * rn;     % 右沿中点
        % 朝弯心轻微内移，让目标更可能被各方案覆盖
        targets(i, :) = mid - 0.25 * rn;
    end
end


function run_dir = local_make_run_dir(repo_root, csv_name)
    runs_root = fullfile(repo_root, 'alpha方案对比', 'runs');
    if ~exist(runs_root, 'dir'), mkdir(runs_root); end
    [~, stem, ~] = fileparts(csv_name);
    run_dir = fullfile(runs_root, sprintf('%s__%s', datestr(now,'yyyymmdd_HHMMSS'), stem));
    if ~exist(run_dir, 'dir'), mkdir(run_dir); end
end


function local_write_summary(run_dir, csv_name, p, schemes, labels, areaW, areaA, ...
                             first_alarm, lead, contact_time, valid_tgt)
    fid = fopen(fullfile(run_dir, 'summary.txt'), 'w', 'n', 'UTF-8');
    if fid < 0, return; end
    cu = onCleanup(@() fclose(fid));
    fprintf(fid, '========================================\n');
    fprintf(fid, '  alpha 方案横向对比摘要\n');
    fprintf(fid, '========================================\n\n');
    fprintf(fid, '生成时间 : %s\n', datestr(now, 'yyyy-mm-dd HH:MM:SS'));
    fprintf(fid, '工况 CSV : %s\n', csv_name);
    fprintf(fid, '车型     : l=%.2f l_h=%.2f L=%.2f W=%.2f phi_max=%.1f°\n\n', ...
        p.l, p.l_h, p.L, p.width, rad2deg(p.phi_max));

    fprintf(fid, '---- 平均扫掠面积 (m²) ----\n');
    fprintf(fid, '%-16s %12s %12s\n', '方案', 'PolyW', 'PolyA');
    for si = 1:numel(schemes)
        fprintf(fid, '%-16s %12.3f %12.3f\n', labels{si}, areaW(si), areaA(si));
    end
    fprintf(fid, '\n');

    fprintf(fid, '---- 物理接触时刻 (s, BodyNow 首次覆盖) ----\n');
    for j = valid_tgt
        fprintf(fid, '  R%d : %.2f\n', j, contact_time(j));
    end
    fprintf(fid, '\n');

    fprintf(fid, '---- PolyA 首次报警时刻 (s, "-"=未报警) ----\n');
    fprintf(fid, '%-16s', '方案');
    for j = valid_tgt, fprintf(fid, ' %8s', sprintf('R%d', j)); end
    fprintf(fid, '\n');
    for si = 1:numel(schemes)
        fprintf(fid, '%-16s', labels{si});
        for j = valid_tgt
            fa = first_alarm(si, j);
            if isnan(fa), fprintf(fid, ' %8s', '-');
            else,         fprintf(fid, ' %8.2f', fa); end
        end
        fprintf(fid, '\n');
    end
    fprintf(fid, '\n');

    fprintf(fid, '---- PolyA 报警提前量 lead = 接触时刻 - 首次报警 (s) ----\n');
    fprintf(fid, '%-16s', '方案');
    for j = valid_tgt, fprintf(fid, ' %8s', sprintf('R%d', j)); end
    fprintf(fid, '\n');
    for si = 1:numel(schemes)
        fprintf(fid, '%-16s', labels{si});
        for j = valid_tgt
            lv = lead(si, j);
            if isnan(lv), fprintf(fid, ' %8s', '-');
            else,         fprintf(fid, ' %8.2f', lv); end
        end
        fprintf(fid, '\n');
    end
    fprintf(fid, '\n说明: lead 越大 = 越早预测到危险 = 提前量越大。基线(hold)通常最小。\n');
    fprintf(fid, '      首次报警时刻只用 PolyA 预测命中，不含 BodyNow 兜底，比的是预测能力。\n');
end
