function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%PREDICT_SWEPT alpha线性外推仿真: temporal union of local convex edge covers.
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

    half_w = 0.5 * p.width;
    validateattributes(T_h, {'numeric'}, {'scalar', 'real', 'finite', 'nonnegative'});
    validateattributes(dt_pred, {'numeric'}, {'scalar', 'real', 'finite', 'positive'});
    times = (0:floor(T_h / dt_pred)) * dt_pred;
    if times(end) < T_h, times(end+1) = T_h; end
    M = numel(times) - 1;

    H_right = zeros(M+1, 2);
    T_right = zeros(M+1, 2);

    s   = s0(:);
    tau = 0;
    for k = 1:M+1
        d   = derive_points(s, p);
        cTt = cos(d.theta_t);
        sTt = sin(d.theta_t);

        H_right(k, :) = d.H + half_w * [ sTt, -cTt ];
        T_right(k, :) = d.T + half_w * [ sTt, -cTt ];

        if k <= M
            alpha_tau = alpha_now + alpha_dot * tau;
            alpha_tau = max(min(alpha_tau, deg2rad(40)), -deg2rad(40));
            s   = kinematics_step(s, alpha_tau, v_now, p, times(k+1)-times(k));
            tau = times(k+1);
        end
    end

    poly = swept_segments(H_right, T_right);
end
