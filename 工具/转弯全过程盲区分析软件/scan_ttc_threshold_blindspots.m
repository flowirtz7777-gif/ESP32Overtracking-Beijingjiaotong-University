function out = scan_ttc_threshold_blindspots(scenario_csv, opts)
%SCAN_TTC_THRESHOLD_BLINDSPOTS  扫描不同反应时间阈值下的全过程盲区点分布。
%
%   out = scan_ttc_threshold_blindspots()
%   out = scan_ttc_threshold_blindspots(scenario_csv)
%   out = scan_ttc_threshold_blindspots(scenario_csv, opts)
%
% 默认参数按当前讨论口径：
%   sampling_spacing_m = 0.1
%   tolerance_m        = 0.05
%   max_boundary_points = 2000
%   warmup_ignore_s    = 2.0
%   thresholds_s       = 0.1:0.1:3.0
%
% 盲区点定义：
%   对阈值 threshold_s，若点不是起始截断点，且
%     - PolyW 从未命中；或
%     - lead_W = true_contact_time_s - first_PolyW_s < threshold_s
%   则该点在该阈值下记为盲区点。

    script_dir = fileparts(mfilename('fullpath'));
    repo_dir = fileparts(script_dir);
    algo_dir = fullfile(repo_dir, '正交路口出弯状态机仿真');
    addpath(algo_dir);

    if nargin < 1 || isempty(scenario_csv)
        scenario_csv = fullfile(algo_dir, 'scenarios', 'pid_scenario_20260530_020804.csv');
    end
    if nargin < 2 || isempty(opts)
        opts = struct();
    end

    opts = local_defaults(opts);

    scenario = load_pid_scenario(scenario_csv);
    p = vehicle_params(scenario.params);
    if ~isfield(scenario.params,'phi_max_rad'), p.phi_max=deg2rad(15); end

    t = scenario.time_s;
    v = scenario.inputs.v_mps;
    alpha = scenario.inputs.alpha_rad;
    phi = scenario.inputs.phi_rad;
    truth = [scenario.states.xB_m, scenario.states.yB_m, scenario.states.theta_rad, phi];
    strategy_cfg = normalize_steering_config(local_load_strategy_cfg(opts.strategy_cfg_json));
    phase = local_phase_from_cfg(scenario.states.theta_rad, alpha, phi, t, strategy_cfg);

    fprintf('\n[SCAN] 场景: %s\n', string(scenario.file_name));
    threshold_text = strjoin(compose('%.2g',opts.thresholds_s),',');
    fprintf('[SCAN] 参数: spacing=%.2fm, tolerance=%.2fm, max_points=%d, warmup=%.2fs, thresholds=%s, CFG=%s, hit=segment_convex_union\n', ...
        opts.sampling_spacing_m, opts.tolerance_m, opts.max_boundary_points, opts.warmup_ignore_s, ...
        threshold_text, strategy_cfg.name);

    if ~isempty(opts.target_csv)
        targets=readtable(opts.target_csv,'TextType','string');
        if ~ismember('sample_group',targets.Properties.VariableNames)
            targets.sample_group=repmat("imported",height(targets),1);
        end
        idx=first_trailer_contacts([targets.x_m,targets.y_m],scenario,p,opts.tolerance_m);
        targets.true_contact_idx=idx;
        targets.true_contact_time_s=nan(height(targets),1);
        valid=isfinite(idx); targets.true_contact_time_s(valid)=t(idx(valid));
    elseif strcmp(opts.target_mode,'boundary')
        targets=local_generate_boundary_targets(scenario,p,opts);
        targets.sample_group=repmat("boundary",height(targets),1);
    else
        generation_opts=opts; generation_opts.save_outputs=false;
        targets=generate_evaluation_targets(scenario,generation_opts);
    end
    fprintf('[SCAN] 评价目标点: %d\n', height(targets));

    hit = local_compute_first_polyw_hits(targets, t, v, alpha, truth, p, opts, phase, strategy_cfg);
    result_tbl = targets;
    result_tbl.nearest_contact_edge=nearest_contact_edges([targets.x_m,targets.y_m],targets.true_contact_idx,scenario,p);
    result_tbl.is_front_contact_ignored=isfinite(result_tbl.true_contact_time_s) & result_tbl.nearest_contact_edge=="FRONT";
    result_tbl.first_PolyW_s = hit.first_PolyW_s;
    result_tbl.lead_W_s = result_tbl.true_contact_time_s - result_tbl.first_PolyW_s;
    result_tbl.is_startup_truncated = result_tbl.true_contact_time_s < opts.warmup_ignore_s & ~result_tbl.is_front_contact_ignored;
    result_tbl.is_no_warning = isfinite(result_tbl.true_contact_time_s) & isnan(result_tbl.first_PolyW_s) & ~result_tbl.is_front_contact_ignored;
    result_tbl.first_PolyW_horizon_s=hit.first_PolyW_horizon_s;
    result_tbl.event=classify_warning_events(result_tbl.true_contact_time_s,result_tbl.first_PolyW_s, ...
        hit.first_PolyW_horizon_s,t(end),opts.warmup_ignore_s,opts.reaction_threshold_s,result_tbl.nearest_contact_edge);
    result_tbl.contact_phase = strings(height(result_tbl), 1);
    for i = 1:height(result_tbl)
        if isfinite(result_tbl.true_contact_idx(i))
            result_tbl.contact_phase(i) = local_phase_name(phase(result_tbl.true_contact_idx(i)));
        end
    end

    thresholds = opts.thresholds_s(:);
    counts=zeros(numel(thresholds),1); late_count=counts; miss_count=counts;
    false_positive_count=counts; true_negative_count=counts; positive_count=counts;
    negative_count=counts; end_truncated_count=counts; front_ignored_count=counts;
    for i=1:numel(thresholds)
        events=classify_warning_events(result_tbl.true_contact_time_s,result_tbl.first_PolyW_s, ...
            hit.first_PolyW_horizon_s,t(end),opts.warmup_ignore_s,thresholds(i),result_tbl.nearest_contact_edge);
        late_count(i)=nnz(events=="BLINDSPOT_REACTION_INSUFFICIENT");
        miss_count(i)=nnz(events=="POLYW_NO_HIT"); counts(i)=late_count(i)+miss_count(i);
        false_positive_count(i)=nnz(events=="FALSE_POSITIVE");
        true_negative_count(i)=nnz(events=="CORRECT_REJECTION");
        positive_count(i)=counts(i)+nnz(events=="REACTION_TIME_SUFFICIENT");
        negative_count(i)=false_positive_count(i)+true_negative_count(i);
        end_truncated_count(i)=nnz(events=="END_TRUNCATED");
        front_ignored_count(i)=nnz(events=="FRONT_CONTACT_IGNORED");
    end
    blindspot_rate=counts./positive_count; false_positive_rate=false_positive_count./negative_count;
    count_tbl=table(thresholds,counts,late_count,miss_count,false_positive_count,true_negative_count, ...
        positive_count,negative_count,end_truncated_count,blindspot_rate,false_positive_rate,front_ignored_count, ...
        'VariableNames',{'reaction_threshold_s','blindspot_count','late_count','miss_count', ...
        'false_positive_count','true_negative_count','positive_count','negative_count', ...
        'end_truncated_count','blindspot_rate','false_positive_rate','front_ignored_count'});

    critical_threshold_s = nan(height(result_tbl), 1);
    for j = 1:height(result_tbl)
        if ~isfinite(result_tbl.true_contact_time_s(j)) || result_tbl.is_startup_truncated(j) || result_tbl.is_front_contact_ignored(j)
            continue;
        end
        if result_tbl.is_no_warning(j)
            critical_threshold_s(j) = opts.thresholds_s(1);
        else
            idx = find(opts.thresholds_s > result_tbl.lead_W_s(j), 1, 'first');
            if ~isempty(idx)
                critical_threshold_s(j) = opts.thresholds_s(idx);
            end
        end
    end
    result_tbl.critical_threshold_s = critical_threshold_s;

    stamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss_SSS'));
    out_dir = fullfile(script_dir, 'logs', ['threshold_scan_', stamp]);
    if ~exist(out_dir, 'dir'), mkdir(out_dir); end

    writetable(result_tbl, fullfile(out_dir, 'threshold_scan_points.csv'), 'Encoding', 'UTF-8');
    writetable(count_tbl, fullfile(out_dir, 'threshold_scan_counts.csv'), 'Encoding', 'UTF-8');
    writetable(summarize_contact_edges(result_tbl),fullfile(out_dir,'contact_edge_summary.csv'),'Encoding','UTF-8');

    fig = local_plot_scan(result_tbl, count_tbl, scenario, opts);
    png_path = fullfile(out_dir, 'threshold_blindspot_overlay.png');
    fig_path = fullfile(out_dir, 'threshold_blindspot_overlay.fig');
    exportgraphics(fig, png_path, 'Resolution', 220);
    savefig(fig, fig_path);

    fprintf('[SCAN] 输出目录: %s\n', out_dir);
    fprintf('[SCAN] 叠加图: %s\n\n', png_path);

    out = struct();
    out.points = result_tbl;
    out.counts = count_tbl;
    out.out_dir = out_dir;
    out.figure = fig;
    out.png_path = png_path;
    out.strategy_cfg = strategy_cfg;
end


function opts = local_defaults(opts)
    opts = local_set_default(opts, 'sampling_spacing_m', 0.1);
    opts = local_set_default(opts, 'tolerance_m', 0.05);
    opts = local_set_default(opts, 'max_boundary_points', 7000);
    opts = local_set_default(opts, 'warmup_ignore_s', 2.0);
    opts = local_set_default(opts, 'thresholds_s', 0.1:0.1:3.0);
    opts = local_set_default(opts, 'T_h_W', 2.0);
    opts = local_set_default(opts, 'dt_pred', 0.02);
    opts = local_set_default(opts, 'strategy_cfg_json', '');
    opts = local_set_default(opts, 'target_mode', 'mixed');
    opts = local_set_default(opts, 'target_csv', '');
    opts = local_set_default(opts, 'boundary_band_m', 0.2);
    opts = local_set_default(opts, 'negative_margin_m', 0.5);
    opts = local_set_default(opts, 'reaction_threshold_s', 1.0);
    validateattributes(opts.thresholds_s,{'numeric'},{'vector','finite','real','nonnegative','nonempty'});
    opts.thresholds_s=sort(unique(opts.thresholds_s));
end


function s = local_set_default(s, name, value)
    if ~isfield(s, name) || isempty(s.(name))
        s.(name) = value;
    end
end


function targets = local_generate_boundary_targets(scenario, p, opts)
    t = scenario.time_s;
    dt = scenario.dt_s;
    v_avg = mean(scenario.inputs.v_mps, 'omitnan');
    step_k = max(1, round(opts.sampling_spacing_m / max(0.01, v_avg * dt)));
    lateral_step = max(0.08, opts.sampling_spacing_m / max(3, ceil(p.L / opts.sampling_spacing_m)));

    xy_raw = zeros(0, 2);
    contact_idx_raw = zeros(0, 1);
    for k = 1:step_k:numel(t)
        H = scenario.points.H(k, :);
        T = scenario.points.T(k, :);
        theta_t = scenario.states.theta_t_rad(k);
        right_normal = [sin(theta_t), -cos(theta_t)];
        for dist = 0:lateral_step:p.L
            u = dist / p.L;
            mid = H + (T - H) .* u;
            xy_raw(end+1, :) = mid + 0.5 * p.width * right_normal; %#ok<AGROW>
            contact_idx_raw(end+1, 1) = k; %#ok<AGROW>
        end
    end

    key = round(xy_raw ./ opts.sampling_spacing_m);
    [~, ia] = unique(key, 'rows', 'stable');
    xy = xy_raw(ia, :);
    contact_idx = contact_idx_raw(ia);

    stride = max(1, ceil(size(xy, 1) / opts.max_boundary_points));
    pick = 1:stride:size(xy, 1);
    pick = pick(1:min(numel(pick), opts.max_boundary_points));
    xy = xy(pick, :);
    contact_idx = contact_idx(pick);

    refined_idx=first_trailer_contacts(xy,scenario,p,opts.tolerance_m);
    times=nan(numel(refined_idx),1); valid=isfinite(refined_idx); times(valid)=t(refined_idx(valid));
    target="B"+string((1:size(xy,1)).');
    targets=table(target,xy(:,1),xy(:,2),times,refined_idx, ...
        'VariableNames',{'target','x_m','y_m','true_contact_time_s','true_contact_idx'});
end


function hit = local_compute_first_polyw_hits(targets, t, v, alpha, truth, p, opts, phase, strategy_cfg)
    rates_cache=make_steering_rate_cache(alpha,t,strategy_cfg);
    n_targets = height(targets);
    first_idx = nan(n_targets, 1);
    first_horizon = nan(n_targets, 1);
    points = [targets.x_m, targets.y_m];

    for k = 1:numel(t)
        pending = find(isnan(first_idx));
        if isempty(pending)
            break;
        end
        strat = local_strategy_for_phase(strategy_cfg, phase(k));
        rates=rates_cache.default; if double(phase(k))==3, rates=rates_cache.EXIT; end
        edgeW=predict_steering_edges(truth(k,:),alpha(k),v(k),p,strat.T_h_W,strat,rates.dot(k),rates.ddot(k));
        inside = points_in_swept_cover(points(pending, :), edgeW, opts.tolerance_m);
        first_idx(pending(inside)) = k;
        first_horizon(pending(inside)) = strat.T_h_W;
        if mod(k, 100) == 0
            fprintf('[SCAN] PolyW replay %.1f%%, pending=%d\n', 100*k/numel(t), nnz(isnan(first_idx)));
        end
    end

    first_s = nan(n_targets, 1);
    valid = ~isnan(first_idx);
    first_s(valid) = t(first_idx(valid));
    hit = struct('first_PolyW_idx', first_idx, 'first_PolyW_s', first_s, 'first_PolyW_horizon_s', first_horizon);
end


function blind = local_blind_mask(tbl, threshold_s)
    valid = isfinite(tbl.true_contact_time_s) & ~tbl.is_startup_truncated & ~tbl.is_front_contact_ignored;
    blind = valid & (tbl.is_no_warning | tbl.lead_W_s < threshold_s);
end


function fig = local_plot_scan(tbl, count_tbl, scenario, opts)
    fig = figure('Name', 'TTC threshold blindspot overlay', 'Color', 'white', ...
        'Position', [80 80 1450 820]);
    tiledlayout(fig, 1, 2, 'Padding', 'compact', 'TileSpacing', 'compact');

    ax = nexttile(1);
    hold(ax, 'on'); grid(ax, 'on'); axis(ax, 'equal');
    plot(ax, scenario.points.H(:,1), scenario.points.H(:,2), '-', 'Color', [0.45 0.65 0.90], 'LineWidth', 1.0);
    plot(ax, scenario.points.T(:,1), scenario.points.T(:,2), '-', 'Color', [0.36 0.70 0.44], 'LineWidth', 1.0);

    positive = isfinite(tbl.true_contact_time_s) & ~tbl.is_front_contact_ignored;
    startup = tbl.is_startup_truncated;
    no_warn = ~startup & tbl.is_no_warning;
    never_blind = positive & ~startup & ~tbl.is_no_warning & isnan(tbl.critical_threshold_s);
    blind = positive & ~startup & ~isnan(tbl.critical_threshold_s) & ~tbl.is_no_warning;

    if any(startup)
        scatter(ax, tbl.x_m(startup), tbl.y_m(startup), 12, [0.45 0.55 0.70], 'filled', ...
            'MarkerFaceAlpha', 0.25, 'DisplayName', 'STARTUP_TRUNCATED');
    end
    if any(never_blind)
        scatter(ax, tbl.x_m(never_blind), tbl.y_m(never_blind), 12, [0.65 0.65 0.65], 'filled', ...
            'MarkerFaceAlpha', 0.18, 'DisplayName', '扫描阈值范围内充足');
    end
    if any(no_warn)
        scatter(ax, tbl.x_m(no_warn), tbl.y_m(no_warn), 24, 'k', 'x', ...
            'LineWidth', 1.0, 'DisplayName', 'PolyW未命中');
    end
    if any(blind)
        scatter(ax, tbl.x_m(blind), tbl.y_m(blind), 18, tbl.critical_threshold_s(blind), ...
            'filled', 'MarkerFaceAlpha', 0.78, 'DisplayName', '盲区点临界阈值');
    end

    fp=tbl.event=="FALSE_POSITIVE"; tn=tbl.event=="CORRECT_REJECTION"; censored=tbl.event=="END_TRUNCATED";
    if any(fp), scatter(ax,tbl.x_m(fp),tbl.y_m(fp),24,[0.6 0.3 0.65],'x','DisplayName','误报'); end
    if any(tn), scatter(ax,tbl.x_m(tn),tbl.y_m(tn),10,[0.3 0.55 0.6],'o','DisplayName','正确排除'); end
    if any(censored), scatter(ax,tbl.x_m(censored),tbl.y_m(censored),15,[0.45 0.45 0.45],'+','DisplayName','结束截断'); end
    colormap(ax, parula);
    cb = colorbar(ax);
    cb.Label.String = '首次成为盲区的反应时间阈值 / s';
    if numel(opts.thresholds_s) >= 2 && opts.thresholds_s(end) > opts.thresholds_s(1)
        clim(ax, [opts.thresholds_s(1), opts.thresholds_s(end)]);
    else
        clim(ax, opts.thresholds_s(1) + [-0.05, 0.05]);
    end
    xlabel(ax, 'X (m)');
    ylabel(ax, 'Y (m)');
    title(ax, {'不同反应时间阈值下盲区点叠加分布', ...
        sprintf('spacing=%.2fm, tol=%.2fm, max_points=%d, warmup=%.1fs', ...
        opts.sampling_spacing_m, opts.tolerance_m, opts.max_boundary_points, opts.warmup_ignore_s)}, ...
        'FontWeight', 'bold');
    legend(ax, 'Location', 'bestoutside');

    ax2 = nexttile(2);
    plot(ax2, count_tbl.reaction_threshold_s, count_tbl.blindspot_count, '-o', ...
        'Color', [0.85 0.20 0.18], 'MarkerFaceColor', [0.85 0.20 0.18], 'LineWidth', 1.5);
    grid(ax2, 'on');
    xlabel(ax2, '反应时间阈值 / s');
    ylabel(ax2, '盲区点数量');
    title(ax2, '阈值-盲区点数量曲线', 'FontWeight', 'bold');
end


function inside = local_points_in_poly_tol(points, poly, tolerance_m)
    inside = point_in_poly(points(:,1), points(:,2), poly);
    if tolerance_m <= 0 || all(inside)
        return;
    end

    if isequal(poly(1,:), poly(end,:))
        poly2 = poly(1:end-1, :);
    else
        poly2 = poly;
    end

    pending = find(~inside);
    min_d2 = inf(numel(pending), 1);
    pnt = points(pending, :);
    n = size(poly2, 1);
    for i = 1:n
        j = i + 1;
        if j > n, j = 1; end
        a = poly2(i, :);
        b = poly2(j, :);
        v = b - a;
        len2 = dot(v, v);
        if len2 <= eps
            d2 = sum((pnt - a).^2, 2);
        else
            u = ((pnt(:,1)-a(1))*v(1) + (pnt(:,2)-a(2))*v(2)) ./ len2;
            u = max(0, min(1, u));
            proj = a + u .* v;
            d2 = sum((pnt - proj).^2, 2);
        end
        min_d2 = min(min_d2, d2);
    end
    inside(pending) = min_d2 <= tolerance_m^2;
end


function inside = local_points_in_swept_segments_tol(points, edge_seq, tolerance_m)
    inside = false(size(points, 1), 1);
    if numel(edge_seq) < 2 || isempty(points)
        return;
    end
    for i = 1:(numel(edge_seq)-1)
        pending = find(~inside);
        if isempty(pending), break; end
        quad = swept_step_hull([edge_seq(i).H; edge_seq(i+1).H; edge_seq(i+1).T; edge_seq(i).T]);
        inside(pending) = local_points_in_poly_tol(points(pending, :), quad, tolerance_m);
    end
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
        'enter_hold_frames', 2, ...
        'mid_heading_delta_deg', 25.0, ...
        'exit_heading_delta_deg_min', 75.0, ...
        'exit_require_alpha_returning', true, ...
        'exit_phi_abs_deg_min', 4.0, ...
        'exit_hold_frames', 2, ...
        'done_heading_delta_deg_min', 88.0, ...
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
    enter_count = 0;
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

        if state == 0
            if abs(a) >= deg2rad(sm.alpha_start_deg)
                enter_count = enter_count + 1;
                if enter_count >= sm.enter_hold_frames
                    state = 1;
                    start_theta = theta_unwrap(k);
                end
            else
                enter_count = 0;
            end
        end
        if state == 1
            hdg = abs(local_wrap_pi(theta_unwrap(k) - start_theta));
            if hdg >= deg2rad(sm.mid_heading_delta_deg)
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
            hdg = abs(local_wrap_pi(theta_unwrap(k) - start_theta));
            done_ok = hdg >= deg2rad(sm.done_heading_delta_deg_min) && ...
                abs(a) <= deg2rad(sm.done_alpha_abs_deg_max) && ...
                abs(ph) <= deg2rad(sm.done_phi_abs_deg_max);
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


function a = local_wrap_pi(a)
    a = atan2(sin(a), cos(a));
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


function name = local_phase_name(phase_id)
    labels = ["IDLE", "ENTRY", "MID", "EXIT", "DONE"];
    idx = max(1, min(numel(labels), double(phase_id) + 1));
    name = labels(idx);
end
