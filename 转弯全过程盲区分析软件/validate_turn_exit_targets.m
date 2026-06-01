function report = validate_turn_exit_targets(scenario_csv, target_csv, web_log_csv, tolerance_m, warmup_ignore_s, strategy_cfg_json)
%VALIDATE_TURN_EXIT_TARGETS  用 MATLAB 复算转弯全过程盲区分析软件的边界点 Poly 判定。
%
%   report = validate_turn_exit_targets(scenario_csv, target_csv)
%   report = validate_turn_exit_targets(scenario_csv, target_csv, web_log_csv)
%   report = validate_turn_exit_targets(scenario_csv, target_csv, web_log_csv, tolerance_m)
%   report = validate_turn_exit_targets(scenario_csv, target_csv, web_log_csv, tolerance_m, warmup_ignore_s)
%   report = validate_turn_exit_targets(scenario_csv, target_csv, web_log_csv, tolerance_m, warmup_ignore_s, strategy_cfg_json)
%
%   用途：
%     1. 读取转弯全过程盲区分析软件导出的目标点 CSV。
%     2. 对每一帧做一次在线 PolyW/A/I 预测，alpha 一阶保持；若传入 CFG，则按状态机启用分状态窗口。
%     3. 对每个目标点记录 MATLAB 版 first_PolyW/A/I 与 lead_W。
%     4. 若提供软件日志 CSV，则按 target 对比 Web 与 MATLAB 的 first_PolyW/lead_W。
%
%   注意：
%     - 为与网页软件一致，统计判定使用 segment_swept：相邻预测步右边缘
%       形成小扫掠四边形逐段判内，而不是整窗大多边形。
%     - 目标点 CSV 至少需要 x_m,y_m；若有 true_contact_time_s 则直接使用，
%       否则用逐帧 BodyNow 重新寻找真实接触时间。
%     - 全过程边界测试点常位于扫掠边界线上；默认 tolerance_m=0.05，
%       表示距离多边形边界 5 cm 内也按命中处理。
%     - 默认 warmup_ignore_s=2.0，将 t<2s 的起始截断点单独标为
%       STARTUP_TRUNCATED，不参与“盲区点”判断。

    if nargin < 1 || isempty(scenario_csv)
        [fn, fp] = uigetfile('*.csv', '选择场景 CSV');
        if isequal(fn, 0), error('validate_turn_exit_targets:NoScenario', '未选择场景 CSV。'); end
        scenario_csv = fullfile(fp, fn);
    end
    if nargin < 2 || isempty(target_csv)
        [fn, fp] = uigetfile('*.csv', '选择全过程盲区分析目标点 CSV');
        if isequal(fn, 0), error('validate_turn_exit_targets:NoTargets', '未选择目标 CSV。'); end
        target_csv = fullfile(fp, fn);
    end
    if nargin < 3
        web_log_csv = '';
    end
    if nargin < 4 || isempty(tolerance_m)
        tolerance_m = 0.05;
    end
    if nargin < 5 || isempty(warmup_ignore_s)
        warmup_ignore_s = 2.0;
    end
    if nargin < 6
        strategy_cfg_json = '';
    end

    script_dir = fileparts(mfilename('fullpath'));
    algo_dir = fullfile(fileparts(script_dir), '正交路口出弯状态机仿真');
    addpath(algo_dir);

    scenario = load_pid_scenario(scenario_csv);
    target_tbl = readtable(target_csv, 'TextType', 'string');
    p = vehicle_params(scenario.params);

    t = scenario.time_s;
    v = scenario.inputs.v_mps;
    alpha = scenario.inputs.alpha_rad;
    phi = scenario.inputs.phi_rad;
    truth = [scenario.states.xB_m, scenario.states.yB_m, scenario.states.theta_rad, phi];
    strategy_cfg = local_load_strategy_cfg(strategy_cfg_json);
    phase = local_phase_from_cfg(scenario.states.theta_rad, alpha, phi, t, strategy_cfg);

    targets = local_read_targets(target_tbl);
    n_targets = size(targets.xy, 1);
    n = numel(t);

    fprintf('\n[VALIDATE] 场景: %s\n', string(scenario.file_name));
    fprintf('[VALIDATE] 目标数: %d\n', n_targets);
    fprintf('[VALIDATE] CFG: %s, hit_method=segment_swept, tol=%.3fm, warmup_ignore=%.2fs\n', ...
        strategy_cfg.name, tolerance_m, warmup_ignore_s);

    first_W_idx = nan(n_targets, 1);
    first_A_idx = nan(n_targets, 1);
    first_I_idx = nan(n_targets, 1);

    for k = 1:n
        s0 = truth(k, :);
        strat = local_strategy_for_phase(strategy_cfg, phase(k));
        edgeW = local_predict_right_edge_sequence(s0, alpha(k), v(k), p, strat.T_h_W, strat.dt_pred);
        edgeA = local_predict_right_edge_sequence(s0, alpha(k), v(k), p, strat.T_h_A, strat.dt_pred);
        edgeI = local_predict_right_edge_sequence(s0, alpha(k), v(k), p, strat.T_h_I, strat.dt_pred);

        pending_W = isnan(first_W_idx);
        pending_A = isnan(first_A_idx);
        pending_I = isnan(first_I_idx);

        idxs = find(pending_W).';
        for j = idxs
            if local_point_in_swept_segments_tol(targets.xy(j,:), edgeW, tolerance_m)
                first_W_idx(j) = k;
            end
        end
        idxs = find(pending_A).';
        for j = idxs
            if local_point_in_swept_segments_tol(targets.xy(j,:), edgeA, tolerance_m)
                first_A_idx(j) = k;
            end
        end
        idxs = find(pending_I).';
        for j = idxs
            if local_point_in_swept_segments_tol(targets.xy(j,:), edgeI, tolerance_m)
                first_I_idx(j) = k;
            end
        end
    end

    true_contact_time = targets.true_contact_time_s;
    missing_contact = isnan(true_contact_time);
    for j = find(missing_contact).'
        true_contact_time(j) = local_first_body_contact_time(targets.xy(j,:), t, truth, p, tolerance_m);
    end

    first_W_s = local_idx_to_time(first_W_idx, t);
    first_A_s = local_idx_to_time(first_A_idx, t);
    first_I_s = local_idx_to_time(first_I_idx, t);
    lead_W_s = true_contact_time - first_W_s;

    threshold_s = 1.0;
    event = strings(n_targets, 1);
    for j = 1:n_targets
        if true_contact_time(j) < warmup_ignore_s
            event(j) = "STARTUP_TRUNCATED";
        elseif isnan(first_W_s(j))
            event(j) = "POLYW_NO_HIT";
        elseif lead_W_s(j) < threshold_s
            event(j) = "BLINDSPOT_REACTION_INSUFFICIENT";
        else
            event(j) = "REACTION_TIME_SUFFICIENT";
        end
    end

    first_W_phase = strings(n_targets, 1);
    for j = 1:n_targets
        if isnan(first_W_idx(j))
            first_W_phase(j) = "";
        else
            first_W_phase(j) = local_phase_name(phase(first_W_idx(j)));
        end
    end

    report_tbl = table( ...
        targets.name, targets.xy(:,1), targets.xy(:,2), true_contact_time, ...
        first_W_s, first_A_s, first_I_s, lead_W_s, first_W_phase, event, ...
        'VariableNames', {'target','x_m','y_m','true_contact_time_s', ...
        'first_PolyW_s','first_PolyA_s','first_PolyI_s','lead_W_s','first_PolyW_phase','event'});

    stamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    run_dir = fullfile(script_dir, 'logs', ['matlab_validate_', stamp]);
    if ~exist(run_dir, 'dir'), mkdir(run_dir); end
    writetable(report_tbl, fullfile(run_dir, 'matlab_validation_log.csv'), 'Encoding', 'UTF-8');

    summary_tbl = local_make_summary_table(report_tbl);
    writetable(summary_tbl, fullfile(run_dir, 'matlab_validation_summary.csv'), 'Encoding', 'UTF-8');

    cmp_tbl = table();
    if ~isempty(web_log_csv) && exist(web_log_csv, 'file')
        web_tbl = readtable(web_log_csv, 'TextType', 'string');
        cmp_tbl = local_compare_web_log(report_tbl, web_tbl);
        writetable(cmp_tbl, fullfile(run_dir, 'web_vs_matlab_compare.csv'), 'Encoding', 'UTF-8');
    end

    n_late = sum(event == "BLINDSPOT_REACTION_INSUFFICIENT");
    n_ok = sum(event == "REACTION_TIME_SUFFICIENT");
    n_miss = sum(event == "POLYW_NO_HIT");
    fprintf('[VALIDATE] MATLAB 分类: 盲区点=%d, 反应充足=%d, 未命中=%d\n', n_late, n_ok, n_miss);
    fprintf('[VALIDATE] 输出目录: %s\n\n', run_dir);

    report = struct();
    report.table = report_tbl;
    report.summary = summary_tbl;
    report.compare = cmp_tbl;
    report.run_dir = run_dir;
    report.params = p;
    report.phase = phase;
    report.strategy_cfg = strategy_cfg;
    report.hit_method = "segment_swept";
    report.tolerance_m = tolerance_m;
    report.warmup_ignore_s = warmup_ignore_s;
end


function summary_tbl = local_make_summary_table(report_tbl)
    event_names = ["BLINDSPOT_REACTION_INSUFFICIENT"; "REACTION_TIME_SUFFICIENT"; "POLYW_NO_HIT"; "STARTUP_TRUNCATED"];
    label = ["盲区点"; "反应充足"; "未命中"; "起始截断"];
    count = zeros(numel(event_names), 1);
    min_lead_W_s = nan(numel(event_names), 1);
    mean_lead_W_s = nan(numel(event_names), 1);
    max_lead_W_s = nan(numel(event_names), 1);
    first_target = strings(numel(event_names), 1);
    first_true_contact_time_s = nan(numel(event_names), 1);
    first_PolyW_s = nan(numel(event_names), 1);

    for i = 1:numel(event_names)
        idx = find(string(report_tbl.event) == event_names(i));
        count(i) = numel(idx);
        if isempty(idx)
            continue;
        end

        leads = report_tbl.lead_W_s(idx);
        min_lead_W_s(i) = min(leads, [], 'omitnan');
        mean_lead_W_s(i) = mean(leads, 'omitnan');
        max_lead_W_s(i) = max(leads, [], 'omitnan');

        [~, ord] = sort(report_tbl.true_contact_time_s(idx));
        first_idx = idx(ord(1));
        first_target(i) = string(report_tbl.target(first_idx));
        first_true_contact_time_s(i) = report_tbl.true_contact_time_s(first_idx);
        first_PolyW_s(i) = report_tbl.first_PolyW_s(first_idx);
    end

    summary_tbl = table(event_names, label, count, min_lead_W_s, mean_lead_W_s, ...
        max_lead_W_s, first_target, first_true_contact_time_s, first_PolyW_s, ...
        'VariableNames', {'event','label','count','min_lead_W_s','mean_lead_W_s', ...
        'max_lead_W_s','first_target','first_true_contact_time_s','first_PolyW_s'});
end


function targets = local_read_targets(tbl)
    names = tbl.Properties.VariableNames;
    if ismember('x_m', names) && ismember('y_m', names)
        xy = [tbl.x_m, tbl.y_m];
    elseif ismember('x', names) && ismember('y', names)
        xy = [tbl.x, tbl.y];
    else
        error('validate_turn_exit_targets:BadTargetCsv', '目标 CSV 需要 x_m,y_m 或 x,y 列。');
    end

    if ismember('target', names)
        target_name = string(tbl.target);
    else
        target_name = "B" + string((1:height(tbl)).');
    end

    if ismember('true_contact_time_s', names)
        true_contact_time_s = tbl.true_contact_time_s;
    else
        true_contact_time_s = nan(height(tbl), 1);
    end

    targets = struct();
    targets.name = target_name;
    targets.xy = xy;
    targets.true_contact_time_s = true_contact_time_s;
end


function out = local_idx_to_time(idx, t)
    out = nan(size(idx));
    valid = ~isnan(idx);
    out(valid) = t(idx(valid));
end


function t_contact = local_first_body_contact_time(target, t, truth, p, tolerance_m)
    t_contact = NaN;
    for k = 1:numel(t)
        body_now = local_make_current_trailer_body(truth(k,:), p);
        if local_point_in_poly_tol(target, body_now, tolerance_m)
            t_contact = t(k);
            return;
        end
    end
end


function inside = local_point_in_poly_tol(point, poly, tolerance_m)
    inside = point_in_poly(point(1), point(2), poly);
    if inside || tolerance_m <= 0 || isnan(tolerance_m)
        return;
    end
    if isequal(poly(1, :), poly(end, :))
        poly2 = poly(1:end-1, :);
    else
        poly2 = poly;
    end
    n = size(poly2, 1);
    for i = 1:n
        j = i + 1;
        if j > n, j = 1; end
        if local_point_segment_distance(point, poly2(i,:), poly2(j,:)) <= tolerance_m
            inside = true;
            return;
        end
    end
end


function d = local_point_segment_distance(p, a, b)
    v = b - a;
    w = p - a;
    len2 = dot(v, v);
    if len2 <= eps
        d = norm(p - a);
        return;
    end
    u = max(0, min(1, dot(w, v) / len2));
    proj = a + u * v;
    d = norm(p - proj);
end


function body_poly = local_make_current_trailer_body(s, p)
    d = derive_points(s, p);
    half_w = 0.5 * p.width;
    right_normal = [sin(d.theta_t), -cos(d.theta_t)];
    left_normal = -right_normal;

    H_right = d.H + half_w * right_normal;
    T_right = d.T + half_w * right_normal;
    T_left = d.T + half_w * left_normal;
    H_left = d.H + half_w * left_normal;
    body_poly = [H_right; T_right; T_left; H_left; H_right];
end


function cmp_tbl = local_compare_web_log(mat_tbl, web_tbl)
    if ~ismember('target', web_tbl.Properties.VariableNames)
        error('validate_turn_exit_targets:BadWebLog', '软件日志缺少 target 列。');
    end

    web_targets = string(web_tbl.target);
    n = height(mat_tbl);
    web_firstW = nan(n, 1);
    web_leadW = nan(n, 1);
    web_event = strings(n, 1);

    for j = 1:n
        idx = find(web_targets == string(mat_tbl.target(j)), 1, 'first');
        if isempty(idx), continue; end
        if ismember('time_s', web_tbl.Properties.VariableNames)
            web_firstW(j) = web_tbl.time_s(idx);
        end
        if ismember('lead_s', web_tbl.Properties.VariableNames)
            web_leadW(j) = web_tbl.lead_s(idx);
        elseif ismember('ttc_s', web_tbl.Properties.VariableNames)
            web_leadW(j) = web_tbl.ttc_s(idx);
        end
        if ismember('event', web_tbl.Properties.VariableNames)
            web_event(j) = string(web_tbl.event(idx));
        end
    end

    cmp_tbl = table( ...
        mat_tbl.target, web_firstW, mat_tbl.first_PolyW_s, ...
        web_firstW - mat_tbl.first_PolyW_s, web_leadW, mat_tbl.lead_W_s, ...
        web_leadW - mat_tbl.lead_W_s, web_event, mat_tbl.event, ...
        'VariableNames', {'target','web_first_PolyW_s','matlab_first_PolyW_s', ...
        'diff_first_PolyW_s','web_lead_W_s','matlab_lead_W_s','diff_lead_W_s', ...
        'web_event','matlab_event'});

    max_first_diff = max(abs(cmp_tbl.diff_first_PolyW_s), [], 'omitnan');
    max_lead_diff = max(abs(cmp_tbl.diff_lead_W_s), [], 'omitnan');
    mismatch = sum(cmp_tbl.web_event ~= "" & cmp_tbl.web_event ~= cmp_tbl.matlab_event);
    fprintf('[VALIDATE] Web vs MATLAB: max firstW diff=%.6fs, max lead diff=%.6fs, event mismatch=%d\n', ...
        max_first_diff, max_lead_diff, mismatch);
end


function name = local_phase_name(phase_id)
    labels = ["IDLE", "ENTRY", "MID", "EXIT", "DONE"];
    idx = max(1, min(numel(labels), double(phase_id) + 1));
    name = labels(idx);
end


function cfg = local_load_strategy_cfg(cfg_json)
    cfg = local_default_strategy_cfg();
    if nargin < 1 || isempty(cfg_json)
        return;
    end
    if isstring(cfg_json), cfg_json = char(cfg_json); end
    if exist(cfg_json, 'file')
        raw = jsondecode(fileread(cfg_json));
    else
        raw = jsondecode(cfg_json);
    end
    cfg = local_merge_strategy_cfg(cfg, raw);
end


function cfg = local_default_strategy_cfg()
    cfg = struct();
    cfg.name = "default_matlab_cfg";
    cfg.version = "1.0";
    cfg.state_machine = struct( ...
        'alpha_start_deg', 2.0, ...
        'mid_heading_delta_deg', 25.0, ...
        'exit_heading_delta_deg_min', 75.0, ...
        'exit_require_alpha_returning', true, ...
        'exit_phi_abs_deg_min', 4.0, ...
        'exit_hold_frames', 2, ...
        'done_alpha_abs_deg_max', 1.0, ...
        'done_phi_abs_deg_max', 2.0, ...
        'done_hold_frames', 10);
    base = struct('T_h_W', 2.0, 'T_h_A', 1.0, 'T_h_I', 0.3, ...
        'dt_pred', 0.02, 'alpha_mode', "hold", ...
        'safety_expand_m', 0.0, 'safety_expand_enabled', false);
    cfg.strategies = struct('default', base, 'EXIT', base);
end


function cfg = local_merge_strategy_cfg(cfg, raw)
    if isfield(raw, 'name'), cfg.name = string(raw.name); end
    if isfield(raw, 'version'), cfg.version = string(raw.version); end
    if isfield(raw, 'state_machine')
        cfg.state_machine = local_merge_struct(cfg.state_machine, raw.state_machine);
    end
    if isfield(raw, 'strategies')
        if isfield(raw.strategies, 'default')
            cfg.strategies.default = local_merge_struct(cfg.strategies.default, raw.strategies.default);
        end
        if isfield(raw.strategies, 'EXIT')
            cfg.strategies.EXIT = local_merge_struct(cfg.strategies.default, raw.strategies.EXIT);
        elseif isfield(raw.strategies, 'exit')
            cfg.strategies.EXIT = local_merge_struct(cfg.strategies.default, raw.strategies.exit);
        else
            cfg.strategies.EXIT = cfg.strategies.default;
        end
    end
end


function out = local_merge_struct(base, override)
    out = base;
    names = fieldnames(override);
    for i = 1:numel(names)
        out.(names{i}) = override.(names{i});
    end
end


function phase = local_phase_from_cfg(theta, alpha, phi, t, cfg)
    n = numel(theta);
    phase = zeros(n, 1);
    if n == 0, return; end
    sm = cfg.state_machine;
    state = 0;
    start_theta = theta(1);
    exit_count = 0;
    done_count = 0;
    theta_unwrap = unwrap(theta(:));
    alpha = alpha(:);
    phi = phi(:);
    t = t(:);

    for k = 2:n
        a = alpha(k);
        ap = alpha(k-1);
        ph = phi(k);
        dt = max(1e-6, t(k) - t(k-1));
        alpha_dot = (a - ap) / dt;

        if state == 0 && abs(a) > deg2rad(sm.alpha_start_deg)
            state = 1;
            start_theta = theta_unwrap(k);
        end
        if state == 1
            hdg = abs(local_wrap_pi(theta_unwrap(k) - start_theta));
            if hdg > deg2rad(sm.mid_heading_delta_deg)
                state = 2;
            end
        end
        if state == 2
            hdg = abs(local_wrap_pi(theta_unwrap(k) - start_theta));
            returning = abs(a) < abs(ap) || a * alpha_dot < 0;
            phi_lag = abs(ph) > deg2rad(sm.exit_phi_abs_deg_min);
            require_returning = ~isfield(sm, 'exit_require_alpha_returning') || sm.exit_require_alpha_returning;
            exit_ok = hdg >= deg2rad(sm.exit_heading_delta_deg_min) && ...
                ((require_returning && returning) || phi_lag || ~require_returning);
            if exit_ok
                exit_count = exit_count + 1;
            else
                exit_count = 0;
            end
            if exit_count >= sm.exit_hold_frames
                state = 3;
            end
        end
        if state == 3
            done_ok = abs(a) < deg2rad(sm.done_alpha_abs_deg_max) && ...
                abs(ph) < deg2rad(sm.done_phi_abs_deg_max);
            if done_ok
                done_count = done_count + 1;
            else
                done_count = 0;
            end
            if done_count >= sm.done_hold_frames
                state = 4;
            end
        end
        phase(k) = state;
    end
end


function strat = local_strategy_for_phase(cfg, phase_id)
    if double(phase_id) == 3
        strat = cfg.strategies.EXIT;
    else
        strat = cfg.strategies.default;
    end
end


function edge_seq = local_predict_right_edge_sequence(s0, alpha_now, v_now, p, T_h, dt_pred)
    M = max(1, floor(T_h / dt_pred));
    s = s0;
    edge_seq = struct('H', cell(M+1, 1), 'T', cell(M+1, 1));
    half_w = 0.5 * p.width;
    for i = 1:(M+1)
        d = derive_points(s, p);
        right_normal = [sin(d.theta_t), -cos(d.theta_t)];
        edge_seq(i).H = d.H + half_w * right_normal;
        edge_seq(i).T = d.T + half_w * right_normal;
        if i <= M
            s = kinematics_step(s, alpha_now, v_now, p, dt_pred);
        end
    end
end


function inside = local_point_in_swept_segments_tol(point, edge_seq, tolerance_m)
    inside = false;
    if numel(edge_seq) < 2, return; end
    for i = 1:(numel(edge_seq)-1)
        quad = [edge_seq(i).H; edge_seq(i+1).H; edge_seq(i+1).T; edge_seq(i).T; edge_seq(i).H];
        if local_point_in_poly_tol(point, quad, tolerance_m)
            inside = true;
            return;
        end
    end
end


function a = local_wrap_pi(a)
    a = atan2(sin(a), cos(a));
end
