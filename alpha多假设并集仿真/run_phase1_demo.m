function out = run_phase1_demo(csv_path)
%RUN_PHASE1_DEMO  Phase 1 验证主入口：CSV → 运动学回放 → 三层扫掠预测 → 误差报告。
%
%   out = run_phase1_demo()              % 弹文件选择框
%   out = run_phase1_demo(csv_path)      % 直接加载指定 CSV
%
%   时间尺度（与 CLAUDE.md / AGENTS.md 一致）：
%     T_h_W = 2.0 s     PolyW  黄色警告     最远预测窗口
%     T_h_A = 1.0 s     PolyA  红色报警     中距
%     T_h_I = 0.3 s     PolyI  立即危险     最近
%     dt_pred = 0.05 s  预测内部积分步长（每个 T_h 切成 N 段）
%     主循环 (ESP32 端) 节拍 = 20 ms / 50 Hz （此 demo 在 MATLAB 端按等时间间隔取关键帧近似）
%
%   流程：
%     1. 用 load_pid_scenario 读 CSV (输入 v(t), alpha(t)；真值 xB, yB, theta, phi 等)
%     2. 用 kinematics_step 从 t=0 起逐步推演，得到"我们重写的运动学"轨迹
%     3. 与 CSV 真值轨迹做差，输出最大/RMS 误差（验收门控：< 1mm 视为通过）
%     4. 在均匀分布的关键时刻调 predict_swept 得到三层扫掠多边形 (PolyW/PolyA/PolyI)
%     5. 画图：
%          Figure 1: 轨迹叠加（CSV 真值 vs MATLAB 重算）
%          Figure 2: 状态误差 (xB, yB, theta, phi)
%          Figure 3: 三层扫掠多边形 + 几个虚拟雷达目标 + 判内结果
%     6. 自动归档到 Matlab/runs/<timestamp>__<csv_name>/
%
%   输出 out (struct)：
%     scenario      : load_pid_scenario 原始返回
%     params        : vehicle_params struct
%     replay        : 重算的轨迹 [N×4]
%     error_max     : 各分量最大绝对误差
%     error_rms     : 各分量 RMS 误差
%     polys         : 关键时刻的多边形 cell{tier}{frame}
%     pass_gate     : 是否通过 < 1mm 验收门控
%     run_dir       : 本次结果归档目录绝对路径

    if nargin < 1 || isempty(csv_path)
        scenario = load_pid_scenario();
    else
        scenario = load_pid_scenario(csv_path);
    end

    p = vehicle_params(scenario.params);

    % ---------- 时间尺度参数（集中在此） ----------
    T_h_W   = 2.0;     % 黄色警告：未来 2 秒车身扫过区域
    T_h_A   = 1.0;     % 红色报警：未来 1 秒
    T_h_I   = 0.3;     % 立即危险：未来 0.3 秒
    dt_pred = 0.01;    % 预测内部积分步长 (s) — 与 ESP32 主循环 50 Hz 兼容
    n_keyframes = 20;  % 演示用：取均匀分布的 20 个时刻画扫掠多边形

    % ---------- 准备归档目录 ----------
    run_dir = local_make_run_dir(scenario.file_name);
    fprintf('\n[PHASE-1] 输出归档目录: %s\n', run_dir);
    fprintf('[PHASE-1] 车型参数: l=%.2f  l_h=%.2f  L=%.2f  W=%.2f  phi_max=%.1f°\n', ...
        p.l, p.l_h, p.L, p.width, rad2deg(p.phi_max));

    % ---------- 时间尺度解释（每次都打印一遍，避免遗忘） ----------
    fprintf('\n[PHASE-1] 时间尺度配置：\n');
    fprintf('  PolyW (黄)  T_h = %.2fs    dt_pred=%.3fs   步数=%d\n', T_h_W, dt_pred, round(T_h_W/dt_pred));
    fprintf('  PolyA (橙)  T_h = %.2fs    dt_pred=%.3fs   步数=%d\n', T_h_A, dt_pred, round(T_h_A/dt_pred));
    fprintf('  PolyI (红)  T_h = %.2fs    dt_pred=%.3fs   步数=%d\n', T_h_I, dt_pred, round(T_h_I/dt_pred));
    v_avg = mean(scenario.inputs.v_mps);
    fprintf('  本工况平均车速 = %.2f m/s (%.1f km/h)\n', v_avg, v_avg*3.6);
    fprintf('  对应纵向覆盖距离: PolyW≈%.1fm  PolyA≈%.1fm  PolyI≈%.2fm\n', ...
        v_avg*T_h_W, v_avg*T_h_A, v_avg*T_h_I);
    fprintf('  ESP32 主循环 = 20ms (50Hz) → 每 20ms 重做一次完整 predict + 判内\n');
    fprintf('  本 demo 在 MATLAB 端只取 %d 个关键帧画图（避免多边形重叠）\n', n_keyframes);

    %% ---------------------- 1) 运动学回放 ----------------------
    t        = scenario.time_s;
    dt       = scenario.dt_s;
    v        = scenario.inputs.v_mps;
    alpha    = scenario.inputs.alpha_rad;

    xB_csv   = scenario.states.xB_m;
    yB_csv   = scenario.states.yB_m;
    th_csv   = scenario.states.theta_rad;
    phi_csv  = scenario.inputs.phi_rad;       % CSV 的 phi 是状态量，HTML 把它放在 inputs
    N        = numel(t);

    replay   = zeros(N, 4);
    replay(1, :) = [xB_csv(1), yB_csv(1), th_csv(1), phi_csv(1)];

    s = replay(1, :).';
    for k = 1:N-1
        s = kinematics_step(s, alpha(k), v(k), p, dt);
        replay(k+1, :) = s.';
    end

    % CSV 真值
    truth = [xB_csv, yB_csv, th_csv, phi_csv];

    err     = replay - truth;
    err_max = max(abs(err), [], 1);
    err_rms = sqrt(mean(err.^2, 1));

    fprintf('\n[PHASE-1] 轨迹回放误差 (MATLAB kinematics_step vs CSV 真值)\n');
    fprintf('              max abs        RMS\n');
    fprintf('  xB    : %12.6f m %12.6f m\n', err_max(1), err_rms(1));
    fprintf('  yB    : %12.6f m %12.6f m\n', err_max(2), err_rms(2));
    fprintf('  theta : %12.6f rad %10.6f rad\n', err_max(3), err_rms(3));
    fprintf('  phi   : %12.6f rad %10.6f rad\n', err_max(4), err_rms(4));

    pos_tol = 1e-3;     % 1 mm
    pass_gate = (err_max(1) < pos_tol) && (err_max(2) < pos_tol);
    if pass_gate
        fprintf('  ✅ 位置最大误差 < 1mm，通过 Phase 1 验收门控\n');
    else
        fprintf('  ⚠️ 位置最大误差 ≥ 1mm，请检查积分方案 / dt 与 HTML 端是否一致\n');
    end

    %% ---------------------- 2) 三层扫掠多边形（均匀关键帧） ----------------------
    % 用等时间间隔取关键帧，演示"每隔一段时间预测一次"的语义
    keyframes = round(linspace(1, N, n_keyframes));
    keyframes = unique(keyframes);

    horizons = struct('W', T_h_W, 'A', T_h_A, 'I', T_h_I);

    polys = struct('W', {cell(1, numel(keyframes))}, ...
                   'A', {cell(1, numel(keyframes))}, ...
                   'I', {cell(1, numel(keyframes))});

    for ii = 1:numel(keyframes)
        k  = keyframes(ii);
        s0 = truth(k, :);
        % [方案 B · 多假设并集] α̇ 用 LPF 估计，传入 predict_swept 作为"继续打"假设。
        % predict_swept 内部再叠加"保持"和"回正"两个假设，取扫掠区并集。
        alpha_dot = estimate_alpha_dot(alpha, k, dt, 0.25);
        polys.W{ii} = predict_swept(s0, alpha(k), v(k), p, horizons.W, dt_pred, alpha_dot);
        polys.A{ii} = predict_swept(s0, alpha(k), v(k), p, horizons.A, dt_pred, alpha_dot);
        polys.I{ii} = predict_swept(s0, alpha(k), v(k), p, horizons.I, dt_pred, alpha_dot);
    end

    %% ---------------------- 3) 可视化 ----------------------
    set(0, 'DefaultFigureColor', 'white');

    % --- Figure 1: 轨迹叠加 ---
    fig1 = figure('Name', 'Phase 1 — 轨迹回放对照', 'Position', [80 80 980 620]);
    plot(scenario.points.A(:,1), scenario.points.A(:,2), '-',  'LineWidth', 2, 'Color', [0.85 0.20 0.20], 'DisplayName', 'CSV: A 前轮'); hold on; grid on; axis equal;
    plot(scenario.points.B(:,1), scenario.points.B(:,2), '-',  'LineWidth', 2, 'Color', [0.20 0.40 0.85], 'DisplayName', 'CSV: B 后轴中心');
    plot(scenario.points.T(:,1), scenario.points.T(:,2), '-',  'LineWidth', 2, 'Color', [0.20 0.65 0.30], 'DisplayName', 'CSV: T 挂车后轮');
    plot(replay(:,1),            replay(:,2),            '--', 'LineWidth', 2, 'Color', [0.10 0.10 0.10], 'DisplayName', 'MATLAB 重算: B');
    xlabel('X (m)'); ylabel('Y (m)');
    title(sprintf('CSV 真值 vs MATLAB kinematics\\_step 重算（max |err| = %.4f mm）', max(err_max(1:2))*1000), 'FontWeight', 'bold');
    legend('Location', 'best');

    % --- Figure 2: 状态误差 ---
    fig2 = figure('Name', 'Phase 1 — 状态误差', 'Position', [120 120 980 620]);
    subplot(2,2,1); plot(t, err(:,1)*1000, 'LineWidth', 1.6); grid on;
    xlabel('t (s)'); ylabel('ΔxB (mm)'); title('xB 误差');

    subplot(2,2,2); plot(t, err(:,2)*1000, 'LineWidth', 1.6); grid on;
    xlabel('t (s)'); ylabel('ΔyB (mm)'); title('yB 误差');

    subplot(2,2,3); plot(t, rad2deg(err(:,3))*3600, 'LineWidth', 1.6); grid on;
    xlabel('t (s)'); ylabel('Δθ (arcsec)'); title('θ 误差');

    subplot(2,2,4); plot(t, rad2deg(err(:,4))*3600, 'LineWidth', 1.6); grid on;
    xlabel('t (s)'); ylabel('Δφ (arcsec)'); title('φ 误差');

    % --- Figure 3: 每个雷达目标各占一个子图，仅显示「抓到它」的那些预测帧 ---
    %
    % 设计动机:
    %   把所有 keyframes × 3 tiers 的多边形堆在一张图上，会把"哪几次判断
    %   抓到了 R1"这个语义信息淹没在视觉重叠里。
    %   改成：对每个目标，先扫描所有关键帧，记录「哪些帧的哪一层抓到它」，
    %   然后仅把这些帧的相应多边形画出来，并在标题里说出
    %   「R1 在 t=0.6s/0.8s/1.0s 三次判断中被 PolyA/PolyA/PolyW 抓到」。

    color_W = [1.00 0.85 0.25];   % 黄
    color_A = [1.00 0.55 0.15];   % 橙
    color_I = [0.95 0.20 0.20];   % 红
    color_body = [0.35 0.35 0.35]; % 当前挂车车身占用区

    % 雷达目标（车体右后方常见盲区，固定随机种子让结果可复现）
    rng(42);
    radar_targets = make_demo_targets(truth, keyframes(end), p, keyframes);
    n_targets = size(radar_targets, 1);

    % 对每个目标 × 每个关键帧 × 每一层，做判内标记
    % hits(j,ii,tier)  : 目标 j 是否被关键帧 ii 的 tier 抓到
    %   tier: 1=I, 2=A, 3=W (从最严重到最缓和)
    hits = false(n_targets, numel(keyframes), 3);
    for ii = 1:numel(keyframes)
        in_I = point_in_poly(radar_targets(:,1), radar_targets(:,2), polys.I{ii});
        in_A = point_in_poly(radar_targets(:,1), radar_targets(:,2), polys.A{ii});
        in_W = point_in_poly(radar_targets(:,1), radar_targets(:,2), polys.W{ii});
        % 兜底判定：若目标已经落在当前挂车矩形占用区内，说明右外缘
        % 已经扫过该点；此时不能只依赖"未来外缘扫掠带"。
        body_now = make_current_trailer_body(truth(keyframes(ii), :), p);
        in_body_now = point_in_poly(radar_targets(:,1), radar_targets(:,2), body_now);
        in_I = in_I | in_body_now;
        in_A = in_A | in_body_now;
        in_W = in_W | in_body_now;
        hits(:, ii, 1) = in_I;
        hits(:, ii, 2) = in_A;
        hits(:, ii, 3) = in_W;
    end

    % 全局风险（任一时刻任一层抓到，取最严重）
    risk = zeros(n_targets, 1);
    for j = 1:n_targets
        if any(any(hits(j, :, 1))),     risk(j) = 3;
        elseif any(any(hits(j, :, 2))), risk(j) = 2;
        elseif any(any(hits(j, :, 3))), risk(j) = 1;
        else,                            risk(j) = 0;
        end
    end

    risk_colors = [0.30 0.70 0.30;   % 0 安全 绿
                   1.00 0.85 0.25;   % 1 警告 黄
                   1.00 0.55 0.15;   % 2 报警 橙
                   0.95 0.20 0.20];  % 3 立即 红
    risk_label = {'安全', '警告', '报警', '立即危险'};

    % --- 子图布局：1 个全局图 + n_targets 个目标专图 ---
    n_cols = max(2, ceil((n_targets + 1)/2));
    fig3 = figure('Name', 'Phase 1 — 每个目标的命中预测帧', ...
                  'Position', [120 80 380*n_cols 720]);

    % 子图 1：全局总览（仅画 H 与 T 轨迹 + 目标点 + 风险颜色）
    subplot(2, n_cols, 1);
    plot(scenario.points.H(:,1), scenario.points.H(:,2), '-', 'LineWidth', 1.4, 'Color', [0.20 0.40 0.85], 'DisplayName', '挂车前端 H'); hold on;
    plot(scenario.points.T(:,1), scenario.points.T(:,2), '-', 'LineWidth', 1.4, 'Color', [0.20 0.65 0.30], 'DisplayName', '挂车后端 T');
    grid on; axis equal;

    % 风险等级"假"句柄用于图例
    h_risk = gobjects(1, 4);
    for r = 0:3
        h_risk(r+1) = scatter(NaN, NaN, 80, risk_colors(r+1,:), 'filled', ...
                              'MarkerEdgeColor', 'k', 'DisplayName', ...
                              sprintf('风险 %d = %s', r, risk_label{r+1}));
    end

    for j = 1:n_targets
        c = risk_colors(risk(j)+1, :);
        scatter(radar_targets(j,1), radar_targets(j,2), 110, c, 'filled', ...
                'MarkerEdgeColor', 'k', 'LineWidth', 0.8, 'HandleVisibility', 'off');
        n_hit_total_frames = numel(union(union(find(hits(j,:,1)), find(hits(j,:,2))), find(hits(j,:,3))));
        text(radar_targets(j,1)+0.25, radar_targets(j,2), ...
             sprintf('R%d (%d/%d)', j, n_hit_total_frames, numel(keyframes)), ...
             'FontSize', 9, 'Color', c*0.6, 'FontWeight', 'bold');
    end
    title({'总览：车体轨迹 + 雷达目标', '点颜色 = 整段最严重风险等级，括号 = 命中帧数/总帧数'}, ...
          'FontWeight', 'bold', 'FontSize', 10);
    xlabel('X (m)'); ylabel('Y (m)');
    legend('Location', 'best', 'FontSize', 7.5, 'Box', 'off');

    % --- 每个目标一个子图 ---
    for j = 1:n_targets
        subplot(2, n_cols, 1 + j);
        plot(scenario.points.H(:,1), scenario.points.H(:,2), '-', 'LineWidth', 1.0, 'Color', [0.45 0.55 0.85]); hold on;
        plot(scenario.points.T(:,1), scenario.points.T(:,2), '-', 'LineWidth', 1.0, 'Color', [0.45 0.70 0.50]);
        grid on; axis equal;

        % 找到所有抓到本目标的 (帧, 层) 组合
        hit_frames_I = find(hits(j, :, 1));
        hit_frames_A = find(hits(j, :, 2));
        hit_frames_W = find(hits(j, :, 3));

        n_hit_I = numel(hit_frames_I);
        n_hit_A = numel(hit_frames_A);
        n_hit_W = numel(hit_frames_W);
        n_total_frames = numel(keyframes);

        % 画 PolyW (最远，先画最底层) — 第一个保留 handle 给 legend
        h_W_legend = []; h_A_legend = []; h_I_legend = []; h_body_legend = [];
        for ii = hit_frames_W
            h_tmp = fill(polys.W{ii}(:,1), polys.W{ii}(:,2), color_W, ...
                 'FaceAlpha', 0.15, 'EdgeColor', color_W*0.7, 'LineWidth', 0.6);
            if isempty(h_W_legend), h_W_legend = h_tmp; else, set(h_tmp,'HandleVisibility','off'); end
        end
        for ii = hit_frames_A
            h_tmp = fill(polys.A{ii}(:,1), polys.A{ii}(:,2), color_A, ...
                 'FaceAlpha', 0.28, 'EdgeColor', color_A*0.7, 'LineWidth', 0.8);
            if isempty(h_A_legend), h_A_legend = h_tmp; else, set(h_tmp,'HandleVisibility','off'); end
        end
        for ii = hit_frames_I
            body_now = make_current_trailer_body(truth(keyframes(ii), :), p);
            h_body_tmp = fill(body_now(:,1), body_now(:,2), color_body, ...
                 'FaceAlpha', 0.16, 'EdgeColor', color_body, 'LineWidth', 0.8);
            if isempty(h_body_legend)
                h_body_legend = h_body_tmp;
            else
                set(h_body_tmp,'HandleVisibility','off');
            end

            h_tmp = fill(polys.I{ii}(:,1), polys.I{ii}(:,2), color_I, ...
                 'FaceAlpha', 0.42, 'EdgeColor', color_I*0.7, 'LineWidth', 1.0);
            if isempty(h_I_legend), h_I_legend = h_tmp; else, set(h_tmp,'HandleVisibility','off'); end
        end

        % 设置 legend DisplayName
        if ~isempty(h_W_legend), set(h_W_legend, 'DisplayName', sprintf('PolyW (T_h=2.0s, %d 次)', n_hit_W)); end
        if ~isempty(h_A_legend), set(h_A_legend, 'DisplayName', sprintf('PolyA (T_h=1.0s, %d 次)', n_hit_A)); end
        if ~isempty(h_I_legend), set(h_I_legend, 'DisplayName', sprintf('PolyI (T_h=0.3s, %d 次)', n_hit_I)); end
        if ~isempty(h_body_legend), set(h_body_legend, 'DisplayName', 'BodyNow 当前挂车车身'); end

        % 画所有关键帧的挂车前端 H 位置（小灰点），让"哪一帧"的位置更直观
        for ii = 1:numel(keyframes)
            k = keyframes(ii);
            scatter(scenario.points.H(k,1), scenario.points.H(k,2), 16, ...
                    [0.3 0.3 0.3], 'filled', 'HandleVisibility', 'off');
        end

        % 标记抓到的关键帧时间
        for ii = union(union(hit_frames_W, hit_frames_A), hit_frames_I)
            k = keyframes(ii);
            text(scenario.points.H(k,1), scenario.points.H(k,2), ...
                 sprintf(' t=%.2fs', t(k)), 'FontSize', 7.5, 'Color', [0.3 0.3 0.3]);
        end

        % 突出显示当前目标
        c = risk_colors(risk(j)+1, :);
        scatter(radar_targets(j,1), radar_targets(j,2), 130, c, 'filled', ...
                'MarkerEdgeColor', 'k', 'LineWidth', 1.0, 'HandleVisibility', 'off');
        text(radar_targets(j,1)+0.25, radar_targets(j,2), sprintf('R%d', j), ...
             'FontSize', 11, 'Color', c*0.5, 'FontWeight', 'bold');

        % 子图标题：命中次数统计 + 命中时间列表
        n_hit_total_frames = numel(union(union(hit_frames_W, hit_frames_A), hit_frames_I));
        title_lines = {sprintf('R%d  风险=%s  命中 %d/%d 帧 (PolyI:%d  PolyA:%d  PolyW:%d)', ...
            j, risk_label{risk(j)+1}, n_hit_total_frames, n_total_frames, n_hit_I, n_hit_A, n_hit_W)};
        if ~isempty(hit_frames_I)
            title_lines{end+1} = sprintf('PolyI 命中: t = %s s', ...
                strjoin(arrayfun(@(ii) sprintf('%.2f', t(keyframes(ii))), hit_frames_I, 'UniformOutput', false), ', '));
        end
        if ~isempty(hit_frames_A)
            title_lines{end+1} = sprintf('PolyA 命中: t = %s s', ...
                strjoin(arrayfun(@(ii) sprintf('%.2f', t(keyframes(ii))), hit_frames_A, 'UniformOutput', false), ', '));
        end
        if ~isempty(hit_frames_W)
            title_lines{end+1} = sprintf('PolyW 命中: t = %s s', ...
                strjoin(arrayfun(@(ii) sprintf('%.2f', t(keyframes(ii))), hit_frames_W, 'UniformOutput', false), ', '));
        end
        if numel(title_lines) == 1
            title_lines{end+1} = sprintf('所有 %d 个关键帧均未命中（车不会扫到）', numel(keyframes));
        end
        title(title_lines, 'FontWeight', 'normal', 'FontSize', 9);
        xlabel('X (m)'); ylabel('Y (m)');

        % 加图例（仅显示有命中的层）
        legend_handles = [h_W_legend, h_A_legend, h_I_legend, h_body_legend];
        legend_handles = legend_handles(~cellfun(@isempty, num2cell(legend_handles)));
        if ~isempty(legend_handles)
            legend(legend_handles, 'Location', 'best', 'FontSize', 7.5, 'Box', 'off');
        end
    end

    sgtitle({'三层扫掠预测 — 每个目标只显示抓到它的预测帧（PolyW/A/I）', ...
             '注：PolyW⊃PolyA⊃PolyI（嵌套），同一帧可能被多层同时抓到，故各层命中次数之和 ≥ 命中帧数'}, ...
            'FontWeight', 'bold', 'FontSize', 11);

    %% ---------------------- 输出 + 归档 ----------------------
    out = struct();
    out.scenario   = scenario;
    out.params     = p;
    out.replay     = replay;
    out.error_max  = err_max;
    out.error_rms  = err_rms;
    out.polys      = polys;
    out.keyframes  = keyframes;
    out.targets    = radar_targets;
    out.target_risk = risk;
    out.pass_gate  = pass_gate;
    out.figures    = [fig1 fig2 fig3];
    out.horizons   = horizons;
    out.dt_pred    = dt_pred;
    out.run_dir    = run_dir;

    % 保存三幅图
    saveas(fig1, fullfile(run_dir, '01_traj_replay.png'));
    saveas(fig2, fullfile(run_dir, '02_state_error.png'));
    saveas(fig3, fullfile(run_dir, '03_swept_polygons.png'));

    % 写 summary.txt
    local_write_summary(run_dir, scenario, p, horizons, dt_pred, ...
                        err_max, err_rms, pass_gate, keyframes, v_avg);

    fprintf('\n[PHASE-1] 演示完成。\n');
    fprintf('          三幅图与 summary.txt 已保存到:\n');
    fprintf('          %s\n\n', run_dir);
end


function body_poly = make_current_trailer_body(s, p)
%MAKE_CURRENT_TRAILER_BODY  当前挂车矩形占用区（H-T 线段按车宽扩展）。
    d = derive_points(s, p);
    half_w = 0.5 * p.width;
    right_normal = [sin(d.theta_t), -cos(d.theta_t)];
    left_normal = -right_normal;

    H_right = d.H + half_w * right_normal;
    T_right = d.T + half_w * right_normal;
    T_left  = d.T + half_w * left_normal;
    H_left  = d.H + half_w * left_normal;

    body_poly = [H_right; T_right; T_left; H_left; H_right];
end


function targets = make_demo_targets(truth, k_end, p, keyframes_idx)
%MAKE_DEMO_TARGETS  在车身右后方盲区生成 5 个虚拟雷达目标。
%
%   targets = make_demo_targets(truth, k_end, p, keyframes_idx)
%
%   策略（v9，B2 多边形配套，"扫掠区几何中心"版）：
%     v1-v8 各种偏移启发式都不可靠（命中数 0-2 不稳定）。
%     这次改用确定性策略：
%       1. 选 5 个 keyframe k_now
%       2. 内部小步快速 roll-forward 1 秒得到那一刻的挂车 H_right 和 T_right
%       3. target = H_right 与 T_right 的中点 (在 PolyW 几何中心附近)
%       4. 加少量 inward 抖动 0.0-0.3m，让 5 个 target 互不相同
%
%     好处：每个 target 必然落在该 KF 的 PolyW 内（中心位置），
%           PolyA 和 PolyI（更短预测）也大概率覆盖到。

    if nargin < 4 || isempty(keyframes_idx)
        N = size(truth, 1);
        last_idx = round(min(0.7*N, double(k_end)));
        sample_idx = round(linspace(round(0.15*N), last_idx, 5));
    else
        % 跳过完全直行的早期帧（KF1-2），从 KF3 开始
        n_kf = numel(keyframes_idx);
        pick = round(linspace(3, max(3, round(n_kf*0.7)), 5));
        pick = unique(pick);
        if numel(pick) < 5
            pick = round(linspace(3, max(3, round(n_kf*0.8)), 5));
        end
        sample_idx = keyframes_idx(pick(1:min(5, numel(pick))));
    end

    half_w = 0.5 * p.width;
    N = size(truth, 1);
    targets = zeros(numel(sample_idx), 2);

    for i = 1:numel(sample_idx)
        k_now = sample_idx(i);

        % 取 k_now 之后约 1 秒（50 步）的挂车姿态——位于 PolyW (T_h=2s) 中段
        future_k = min(N, k_now + 50);

        theta_t_f = truth(future_k, 3) - truth(future_k, 4);
        cT_f = cos(truth(future_k, 3));
        sT_f = sin(truth(future_k, 3));
        H_x = truth(future_k, 1) + p.l_h*cT_f;
        H_y = truth(future_k, 2) + p.l_h*sT_f;
        T_x = H_x - p.L*cos(theta_t_f);
        T_y = H_y - p.L*sin(theta_t_f);

        right_normal_f = [ sin(theta_t_f), -cos(theta_t_f)];

        % H_right 与 T_right 中点（挂车右沿中段，在 PolyW 中央）
        Hr = [H_x, H_y] + half_w * right_normal_f;
        Tr = [T_x, T_y] + half_w * right_normal_f;
        body_mid = (Hr + Tr) / 2;

        % 弯心方向
        if future_k < N
            theta_t_next = truth(future_k+1, 3) - truth(future_k+1, 4);
            d_theta_t = atan2(sin(theta_t_next - theta_t_f), cos(theta_t_next - theta_t_f));
        elseif future_k > 1
            theta_t_prev = truth(future_k-1, 3) - truth(future_k-1, 4);
            d_theta_t = atan2(sin(theta_t_f - theta_t_prev), cos(theta_t_f - theta_t_prev));
        else
            d_theta_t = 0;
        end
        if d_theta_t > 1e-4
            inward_dir = -right_normal_f;
        else
            inward_dir = right_normal_f;
        end

        % 小幅 inward 抖动（让目标看起来不在车身正下方）
        side_offset = -0.3 + 0.6 * rand();
        targets(i, :) = body_mid + side_offset * inward_dir;
    end
end


function run_dir = local_make_run_dir(csv_file_name)
%LOCAL_MAKE_RUN_DIR  在 Matlab/runs/ 下创建带时间戳和 CSV 名的子目录。
    this_file = mfilename('fullpath');
    matlab_dir = fileparts(this_file);
    runs_root = fullfile(matlab_dir, 'runs');
    if ~exist(runs_root, 'dir')
        mkdir(runs_root);
    end

    [~, csv_stem, ~] = fileparts(char(csv_file_name));
    if isempty(csv_stem)
        csv_stem = 'unnamed';
    end
    timestamp = datestr(now, 'yyyymmdd_HHMMSS');
    run_dir = fullfile(runs_root, sprintf('%s__%s', timestamp, csv_stem));
    if ~exist(run_dir, 'dir')
        mkdir(run_dir);
    end
end


function local_write_summary(run_dir, scenario, p, horizons, dt_pred, ...
                              err_max, err_rms, pass_gate, keyframes, v_avg)
%LOCAL_WRITE_SUMMARY  把本次测试的关键数据写成可读的 summary.txt
    fid = fopen(fullfile(run_dir, 'summary.txt'), 'w', 'n', 'UTF-8');
    if fid < 0, return; end
    cu = onCleanup(@() fclose(fid));

    fprintf(fid, '========================================\n');
    fprintf(fid, '  Phase 1 测试摘要\n');
    fprintf(fid, '========================================\n\n');

    fprintf(fid, '生成时间        : %s\n', datestr(now, 'yyyy-mm-dd HH:MM:SS'));
    fprintf(fid, '工况 CSV        : %s\n', char(scenario.file_name));
    fprintf(fid, '采样数          : %d\n', scenario.row_count);
    fprintf(fid, 'CSV dt          : %.4f s\n', scenario.dt_s);
    fprintf(fid, '总时长          : %.2f s\n', scenario.summary.duration_s);
    fprintf(fid, '平均车速        : %.2f m/s (%.1f km/h)\n', v_avg, v_avg*3.6);
    fprintf(fid, '\n');

    fprintf(fid, '---- 车型参数 ----\n');
    fprintf(fid, 'l       (牵引车轴距)    = %.3f m\n', p.l);
    fprintf(fid, 'l_h     (后悬长 B→H)    = %.3f m\n', p.l_h);
    fprintf(fid, 'L       (挂车轴距 H→T)  = %.3f m\n', p.L);
    fprintf(fid, 'width   (等效车宽)      = %.3f m\n', p.width);
    fprintf(fid, 'phi_max (铰接角限幅)    = %.2f°\n', rad2deg(p.phi_max));
    fprintf(fid, '\n');

    fprintf(fid, '---- 时间尺度 ----\n');
    fprintf(fid, 'PolyW T_h = %.2f s   纵向覆盖 ≈ %.2f m   含义=黄色警告\n', horizons.W, v_avg*horizons.W);
    fprintf(fid, 'PolyA T_h = %.2f s   纵向覆盖 ≈ %.2f m   含义=红色报警\n', horizons.A, v_avg*horizons.A);
    fprintf(fid, 'PolyI T_h = %.2f s   纵向覆盖 ≈ %.2f m   含义=立即危险\n', horizons.I, v_avg*horizons.I);
    fprintf(fid, 'dt_pred 预测内部步长     = %.3f s\n', dt_pred);
    fprintf(fid, 'ESP32 主循环 (硬件端)    = 0.020 s (50 Hz)\n');
    fprintf(fid, '本 demo 关键帧索引       = %s\n', mat2str(keyframes));
    fprintf(fid, '\n');

    fprintf(fid, '---- 运动学等价性误差 (MATLAB 重算 vs CSV 真值) ----\n');
    fprintf(fid, '              max abs        RMS\n');
    fprintf(fid, 'xB    : %12.6f m %12.6f m\n', err_max(1), err_rms(1));
    fprintf(fid, 'yB    : %12.6f m %12.6f m\n', err_max(2), err_rms(2));
    fprintf(fid, 'theta : %12.6f rad %10.6f rad\n', err_max(3), err_rms(3));
    fprintf(fid, 'phi   : %12.6f rad %10.6f rad\n', err_max(4), err_rms(4));
    fprintf(fid, '\n');

    fprintf(fid, '---- 验收门控 (Phase 1 Gate) ----\n');
    if pass_gate
        fprintf(fid, '位置最大误差 < 1 mm，✅ 通过\n');
    else
        fprintf(fid, '位置最大误差 ≥ 1 mm，⚠️ 未通过 — 请检查积分方案 (Euler vs RK4) / dt 一致性\n');
    end
end
