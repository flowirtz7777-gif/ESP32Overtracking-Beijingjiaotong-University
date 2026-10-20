function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot) %#ok<INUSD>
%PREDICT_SWEPT alpha扇形包络仿真: temporal union of local convex edge covers.
%   N-by-2 output contains NaN-separated filled pieces, interpreted with OR.
%   Use point_in_poly / plot_swept_region / swept_polyshape for this output.
%   Includes degenerate edges; no connected component is discarded by size.
%   Local covers are conservative for linear endpoint interpolation only.

    rate     = deg2rad(25);   % 方向盘转向速率上限 (rad/s)，与方案 B 回正速率同量级
    N_branch = 7;             % 锥形内采样分支数 (含上/下界与中线)

    % 分支系数 in [-1, 1]：-1=下界(全力反打), 0=保持, +1=上界(全力同向打)
    ks = linspace(-1, 1, N_branch);

    pieces = cell(N_branch, 1);
    for b = 1:N_branch
        kb = ks(b);
        alpha_fun = @(tau) alpha_now + kb * rate * tau;
        pieces{b} = local_one_branch(s0, alpha_fun, v_now, p, T_h, dt_pred);
    end
    poly = pieces{1};
    for branch = 2:numel(pieces)
        poly = [poly; NaN NaN; pieces{branch}]; %#ok<AGROW>
    end
end


function bnd = local_one_branch(s0, alpha_fun, v_now, p, T_h, dt_pred)
%LOCAL_ONE_BRANCH  单条 α(τ) 分支下的右外缘边界点。
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
