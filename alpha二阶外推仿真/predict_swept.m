function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot, alpha_ddot)
%PREDICT_SWEPT  [方案 D · 二阶外推] 挂车右侧外缘扫过区域 → 闭合多边形。
%
%   α 演化假设：α(τ) = α_now + alpha_dot·τ + ½·alpha_ddot·τ²
%   调用方须传入 **LPF 后** 的 alpha_dot / alpha_ddot（见 estimate_alpha_derivs.m）。
%   两者都为 0 时退化为方案 0（恒定保持）。
%
%   poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot, alpha_ddot)
%
%   输入：
%     s0        初始状态 [xB, yB, theta, phi]
%     alpha_now 当前前轮转向角 (rad)
%     v_now     当前车速 (m/s)
%     p         vehicle_params struct
%     T_h       预测时间窗 (s)
%     dt_pred   预测内部步长 (s)
%     alpha_dot  LPF 后一阶变化率 (rad/s)
%     alpha_ddot LPF 后二阶变化率 (rad/s²)
%
%   输出：
%     poly  闭合简单多边形 (N×2)，最后一行 = 第一行
%
%   多边形构造与基线一致，区别仅在 α(τ) 的二阶外推。

    if nargin < 7, alpha_dot = 0; end
    if nargin < 8, alpha_ddot = 0; end
    if isempty(alpha_dot)  || ~isfinite(alpha_dot),  alpha_dot = 0;  end
    if isempty(alpha_ddot) || ~isfinite(alpha_ddot), alpha_ddot = 0; end
    ALPHA_DOT_MAX  = pi;        % rad/s
    ALPHA_DDOT_MAX = 2*pi;      % rad/s²
    if abs(alpha_dot) > ALPHA_DOT_MAX
        alpha_dot = sign(alpha_dot) * ALPHA_DOT_MAX;
    end
    if abs(alpha_ddot) > ALPHA_DDOT_MAX
        alpha_ddot = sign(alpha_ddot) * ALPHA_DDOT_MAX;
    end

    half_w = 0.5 * p.width;
    M      = floor(T_h / dt_pred);

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
            % [方案 D] 二阶外推：α(τ) = α₀ + α̇·τ + ½·α̈·τ²
            alpha_tau = alpha_now + alpha_dot * tau + 0.5 * alpha_ddot * tau^2;
            alpha_tau = max(min(alpha_tau, deg2rad(40)), -deg2rad(40));
            s   = kinematics_step(s, alpha_tau, v_now, p, dt_pred);
            tau = tau + dt_pred;
        end
    end

    % ===== B2: 自相交多边形拆分，只保留"朝弯心方向"的区域 =====
    % 用 polyshape 用偶奇规则自动消除自相交、剔除外甩三角。
    % 物理依据：后轮没有转向能力，转弯时挂车后端往弯心外甩，
    %           T_right 弧与终点车身边交叉形成的"外甩三角"是车
    %           离开过的空地，不会撞到行人，应从危险区中排除。
    %
    %   原始构造的多边形（自相交）：
    %     Hr_0 → ... → Hr_M → Tr_M → ... → Tr_0 → 闭合
    %   起点车身边 Tr_0→Hr_0 与终点车身边 Hr_M→Tr_M 在右转激烈时
    %   会交叉，产生 X 形 / 漏斗形。
    %
    %   polyshape 用偶奇规则把它分成多个区域，"外甩三角"会被识别
    %   为独立区域。我们保留**面积最大**的区域作为有效危险区。

    boundary_pts = [H_right; flipud(T_right)];

    try
        % 'Simplify' = true 让 polyshape 自动消除自相交
        warning('off', 'MATLAB:polyshape:repairedBySimplify');
        ps = polyshape(boundary_pts(:,1), boundary_pts(:,2), 'Simplify', true);
        warning('on',  'MATLAB:polyshape:repairedBySimplify');

        if ps.NumRegions >= 1
            if ps.NumRegions == 1
                bx = ps.Vertices(:,1);
                by = ps.Vertices(:,2);
                bx = bx(~isnan(bx));
                by = by(~isnan(by));
            else
                % 多区域：选面积最大的一块（外甩三角通常较小）
                regs  = regions(ps);
                areas = arrayfun(@area, regs);
                [~, idx_max] = max(areas);
                bx = regs(idx_max).Vertices(:,1);
                by = regs(idx_max).Vertices(:,2);
                bx = bx(~isnan(bx));
                by = by(~isnan(by));
            end

            if numel(bx) >= 3
                poly = [bx, by];
                if ~isequal(poly(1,:), poly(end,:))
                    poly = [poly; poly(1,:)];   % 闭合
                end
            else
                % 退化（面积太小），回退到原始构造
                poly = [boundary_pts; boundary_pts(1,:)];
            end
        else
            poly = [boundary_pts; boundary_pts(1,:)];
        end
    catch ME
        % polyshape 异常时回退到原始多边形（不丢可用性）
        warning('predict_swept:polyshapeFallback', ...
            'polyshape 处理失败 (%s)，回退到原始自相交多边形', ME.message);
        poly = [boundary_pts; boundary_pts(1,:)];
    end
end
