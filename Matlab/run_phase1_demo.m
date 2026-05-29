function out = run_phase1_demo(csv_path)
%RUN_PHASE1_DEMO  Phase 1 验证主入口：CSV → 运动学回放 → 三层扫掠预测 → 误差报告。
%
%   out = run_phase1_demo()              % 弹文件选择框
%   out = run_phase1_demo(csv_path)      % 直接加载指定 CSV
%
%   流程：
%     1. 用 load_pid_scenario 读 CSV (输入 v(t), alpha(t)；真值 xB, yB, theta, phi 等)
%     2. 用 kinematics_step 从 t=0 起逐步推演，得到"我们重写的运动学"轨迹
%     3. 与 CSV 真值轨迹做差，输出最大/RMS 误差（验收门控：< 1mm 视为通过）
%     4. 在若干关键时刻调 predict_swept 得到三层扫掠多边形 (PolyW/PolyA/PolyI)
%     5. 画图：
%          Figure 1: 轨迹叠加（CSV 真值 vs MATLAB 重算）
%          Figure 2: 状态误差 (xB, yB, theta, phi)
%          Figure 3: 三层扫掠多边形 + 几个虚拟雷达目标 + 判内结果
%
%   输出 out (struct)：
%     scenario      : load_pid_scenario 原始返回
%     params        : vehicle_params struct
%     replay        : 重算的轨迹 [N×4]
%     error_max     : 各分量最大绝对误差
%     error_rms     : 各分量 RMS 误差
%     polys         : 关键时刻的多边形 cell{tier}{frame}
%     pass_gate     : 是否通过 < 1mm 验收门控

    if nargin < 1 || isempty(csv_path)
        scenario = load_pid_scenario();
    else
        scenario = load_pid_scenario(csv_path);
    end

    p = vehicle_params(scenario.params);
    fprintf('\n[PHASE-1] 车型参数: l=%.2f  l_h=%.2f  L=%.2f  W=%.2f  phi_max=%.1f°\n', ...
        p.l, p.l_h, p.L, p.width, rad2deg(p.phi_max));

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

    %% ---------------------- 2) 三层扫掠多边形（关键帧） ----------------------
    % 选 5 个时间点：起始、转弯前、转弯峰值、稳定后、结束
    [~, idx_peak] = max(abs(alpha));
    keyframes = unique([1, ...
                        max(2, round(0.2*N)), ...
                        idx_peak, ...
                        max(2, round(0.7*N)), ...
                        N]);
    keyframes = keyframes(keyframes <= N);

    horizons = struct('W', 2.0, 'A', 1.0, 'I', 0.3);
    dt_pred  = 0.05;

    polys = struct('W', {cell(1, numel(keyframes))}, ...
                   'A', {cell(1, numel(keyframes))}, ...
                   'I', {cell(1, numel(keyframes))});

    for ii = 1:numel(keyframes)
        k  = keyframes(ii);
        s0 = truth(k, :);
        % α̇ 用前向差分估计；端点退化时置 0
        if k < N
            alpha_dot = (alpha(k+1) - alpha(k)) / dt;
        else
            alpha_dot = 0;
        end
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

    % --- Figure 3: 三层扫掠多边形 + 虚拟雷达目标 ---
    fig3 = figure('Name', 'Phase 1 — 三层扫掠预测 + 虚拟雷达目标', 'Position', [160 160 1100 700]);
    plot(scenario.points.B(:,1), scenario.points.B(:,2), '-', 'LineWidth', 1.5, 'Color', [0.5 0.5 0.5], 'DisplayName', 'CSV: B 轨迹'); hold on; grid on; axis equal;
    plot(scenario.points.T(:,1), scenario.points.T(:,2), '-', 'LineWidth', 1.5, 'Color', [0.5 0.5 0.5], 'HandleVisibility', 'off');

    color_W = [1.00 0.85 0.25];   % 黄
    color_A = [1.00 0.55 0.15];   % 橙
    color_I = [0.95 0.20 0.20];   % 红

    % 演示用虚拟雷达目标（车体右后方常见盲区）
    radar_targets = make_demo_targets(truth, keyframes(end), p);

    legend_added = false(1, 3);
    for ii = 1:numel(keyframes)
        k = keyframes(ii);

        % 由远到近画，让 PolyI 盖在最上面
        h_W = fill(polys.W{ii}(:,1), polys.W{ii}(:,2), color_W, 'FaceAlpha', 0.18, 'EdgeColor', color_W*0.7, 'LineWidth', 0.8);
        h_A = fill(polys.A{ii}(:,1), polys.A{ii}(:,2), color_A, 'FaceAlpha', 0.30, 'EdgeColor', color_A*0.7, 'LineWidth', 0.8);
        h_I = fill(polys.I{ii}(:,1), polys.I{ii}(:,2), color_I, 'FaceAlpha', 0.45, 'EdgeColor', color_I*0.7, 'LineWidth', 1.2);

        if ~legend_added(1)
            set(h_W, 'DisplayName', 'PolyW (T_h=2.0s 黄色警告)'); legend_added(1) = true;
        else, set(h_W, 'HandleVisibility', 'off'); end
        if ~legend_added(2)
            set(h_A, 'DisplayName', 'PolyA (T_h=1.0s 红色报警)'); legend_added(2) = true;
        else, set(h_A, 'HandleVisibility', 'off'); end
        if ~legend_added(3)
            set(h_I, 'DisplayName', 'PolyI (T_h=0.3s 立即危险)'); legend_added(3) = true;
        else, set(h_I, 'HandleVisibility', 'off'); end

        % 时间标签
        text(scenario.points.B(k,1), scenario.points.B(k,2), sprintf('  t=%.1fs', t(k)), ...
             'FontSize', 9, 'Color', [0.2 0.2 0.2]);
    end

    % 雷达目标 + 判内
    in_W = false(size(radar_targets,1), 1);
    in_A = false(size(radar_targets,1), 1);
    in_I = false(size(radar_targets,1), 1);
    for ii = 1:numel(keyframes)
        in_W = in_W | point_in_poly(radar_targets(:,1), radar_targets(:,2), polys.W{ii});
        in_A = in_A | point_in_poly(radar_targets(:,1), radar_targets(:,2), polys.A{ii});
        in_I = in_I | point_in_poly(radar_targets(:,1), radar_targets(:,2), polys.I{ii});
    end

    risk = zeros(size(radar_targets,1), 1);
    risk(in_W) = 1;
    risk(in_A) = 2;
    risk(in_I) = 3;

    risk_colors = [0.30 0.70 0.30;
                   1.00 0.85 0.25;
                   1.00 0.55 0.15;
                   0.95 0.20 0.20];

    for j = 1:size(radar_targets,1)
        c = risk_colors(risk(j)+1, :);
        scatter(radar_targets(j,1), radar_targets(j,2), 90, c, 'filled', ...
                'MarkerEdgeColor', 'k', 'LineWidth', 0.8, 'HandleVisibility', 'off');
        text(radar_targets(j,1)+0.2, radar_targets(j,2), sprintf('R%d (%d)', j, risk(j)), ...
             'FontSize', 8.5, 'Color', c*0.6);
    end

    xlabel('X (m)'); ylabel('Y (m)');
    title('三层扫掠多边形覆盖 + 虚拟雷达目标风险等级 (0=安全 / 1=黄 / 2=橙 / 3=红)', 'FontWeight', 'bold');
    legend('Location', 'best');

    %% ---------------------- 输出 ----------------------
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

    fprintf('\n[PHASE-1] 演示完成。三幅图已生成；out struct 已返回。\n\n');
end


function targets = make_demo_targets(truth, k_end, p)
%MAKE_DEMO_TARGETS  生成几个虚拟雷达目标，分布在车身右后方常见盲区。
    % 取整段轨迹中段的车体右侧若干点作为模拟"行人/电动车"位置
    N = size(truth, 1);
    sample_idx = round(linspace(round(0.4*N), min(N, k_end), 5));
    targets = zeros(numel(sample_idx), 2);
    for i = 1:numel(sample_idx)
        k = sample_idx(i);
        theta_t = truth(k, 3) - truth(k, 4);
        right_normal = [sin(theta_t), -cos(theta_t)];
        % 距 T 点 (0.8 ~ 1.6 m) 的右后方
        cT = cos(truth(k, 3));
        sT = sin(truth(k, 3));
        T_x = truth(k, 1) + p.l_h*cT - p.L*cos(theta_t);
        T_y = truth(k, 2) + p.l_h*sT - p.L*sin(theta_t);
        offset = 0.6 + 1.2*rand();
        back   = -0.5 + 1.0*rand();
        targets(i, :) = [T_x, T_y] + offset*right_normal + back*[cos(theta_t), sin(theta_t)];
    end
end
