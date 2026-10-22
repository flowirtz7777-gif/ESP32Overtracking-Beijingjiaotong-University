function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%PREDICT_SWEPT alpha多假设并集仿真: temporal union of local convex edge covers.
%   N-by-2 output contains NaN-separated filled pieces, interpreted with OR.
%   Use point_in_poly / plot_swept_region / swept_polyshape for this output.
%   Includes degenerate edges; no connected component is discarded by size.
%   Local covers are conservative for linear endpoint interpolation only.

    if nargin < 7, alpha_dot = 0; end
    if isempty(alpha_dot) || ~isfinite(alpha_dot), alpha_dot = 0; end
    ALPHA_DOT_MAX = pi;
    if abs(alpha_dot) > ALPHA_DOT_MAX
        alpha_dot = sign(alpha_dot) * ALPHA_DOT_MAX;
    end

    % 假设3 的回正速率：若当前几乎直行则不回正（避免符号抖动）
    return_rate = deg2rad(25);     % 25°/s 朝 0 回（典型驾驶员回方向速率量级）
    if abs(alpha_now) < deg2rad(1)
        sign_a = 0;
    else
        sign_a = sign(alpha_now);
    end

    % 三个假设的 α(τ) 函数句柄
    hypo = {
        @(tau) alpha_now;                                  % 假设1 保持
        @(tau) alpha_now + alpha_dot * tau;                % 假设2 继续打
        @(tau) alpha_now - sign_a * return_rate * tau      % 假设3 回正
    };

    pieces = cell(numel(hypo), 1);
    for h = 1:numel(hypo)
        pieces{h} = local_one_hypothesis(s0, hypo{h}, v_now, p, T_h, dt_pred);
    end
    poly = pieces{1};
    for branch = 2:numel(pieces)
        poly = [poly; NaN NaN; pieces{branch}]; %#ok<AGROW>
    end
end


function bnd = local_one_hypothesis(s0, alpha_fun, v_now, p, T_h, dt_pred)
%LOCAL_ONE_HYPOTHESIS  单个 α(τ) 假设下的右外缘边界点（未做 polyshape 简化）。
    half_w = 0.5 * p.width;
    validateattributes(T_h, {'numeric'}, {'scalar', 'real', 'finite', 'nonnegative'});
    validateattributes(dt_pred, {'numeric'}, {'scalar', 'real', 'finite', 'positive'});
    times = (0:floor(T_h / dt_pred)) * dt_pred;
    if times(end) < T_h, times(end+1) = T_h; end
    M = numel(times) - 1;
    H_right = zeros(M+1, 2);
    T_right = zeros(M+1, 2);
    s = s0(:);
    tau = 0;
    for k = 1:M+1
        d = derive_points(s, p);
        cTt = cos(d.theta_t); sTt = sin(d.theta_t);
        H_right(k, :) = d.H + half_w * [ sTt, -cTt ];
        T_right(k, :) = d.T + half_w * [ sTt, -cTt ];
        if k <= M
            alpha_tau = alpha_fun(tau);
            alpha_tau = max(min(alpha_tau, deg2rad(40)), -deg2rad(40));
            s = kinematics_step(s, alpha_tau, v_now, p, times(k+1)-times(k));
            tau = times(k+1);
        end
    end
    bnd = swept_segments(H_right, T_right);
end
