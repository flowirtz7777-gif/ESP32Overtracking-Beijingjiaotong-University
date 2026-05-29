function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%PREDICT_SWEPT  挂车右侧外缘在 [0, T_h] 扫过的区域 → 简单闭合多边形。
%
%   poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred)
%   poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%
%   输入：
%     s0        初始状态 [xB, yB, theta, phi]
%     alpha_now 当前前轮转向角 (rad)
%     v_now     当前车速 (m/s)
%     p         vehicle_params struct
%     T_h       预测时间窗 (s)
%     dt_pred   预测内部步长 (s)
%     alpha_dot (可选) 转向角速率，默认 0（α 短时保持）
%
%   输出：
%     poly  闭合简单多边形 (N×2)，最后一行 = 第一行
%
%   ===== 多边形构造（用户定义版） =====
%   只考虑挂车（H→T 段），忽略牵引车头扫掠。挂车右侧外缘是 H→T 这根直棍
%   向右法向偏移 W/2 后形成的两个端点：
%       H_right = H + (W/2) · (sin θ_t, -cos θ_t)
%       T_right = T + (W/2) · (sin θ_t, -cos θ_t)
%   挂车在每个时刻自身是直的 (H_right_t → T_right_t 一根直线)，所以扫掠区
%   有 4 条边：
%
%        H_right₀ ── (H_right 曲线) ── H_right_E
%             │                              │
%             │  起始车身右沿       结束车身右沿
%             │                              │
%        T_right₀ ── (T_right 曲线) ── T_right_E
%
%   顶点序列：
%       H_right₀ → ... → H_right_E → T_right_E → ... → T_right₀ → 闭合 H_right₀
%
%   说明：
%     - H_right 与 T_right 用挂车航向 θ_t = θ - φ 投影到右法向
%     - 不再使用之前的 A_right（牵引车前轮右），因为按用户指示忽略车头扫掠
%
%   TODO（已在 TODO.md 登记）：
%     - 左侧扫掠区（防左转 / 道路左侧目标）：把 +W/2 改成 -W/2 同样构造
%     - 双侧合并区域：左 + 右两个多边形

    if nargin < 7, alpha_dot = 0; end
    if isempty(alpha_dot) || ~isfinite(alpha_dot), alpha_dot = 0; end
    ALPHA_DOT_MAX = pi;
    if abs(alpha_dot) > ALPHA_DOT_MAX
        alpha_dot = sign(alpha_dot) * ALPHA_DOT_MAX;
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
            alpha_tau = alpha_now + alpha_dot * tau;
            alpha_tau = max(min(alpha_tau, deg2rad(40)), -deg2rad(40));
            s   = kinematics_step(s, alpha_tau, v_now, p, dt_pred);
            tau = tau + dt_pred;
        end
    end

    % 顶点顺序：
    %   H_right₀ → H_right₁ → ... → H_right_E
    %   → T_right_E → T_right_{E-1} → ... → T_right₀
    %   → 闭合回 H_right₀
    %
    % 4 类边：
    %   - H_right 曲线段：上沿（挂车前端右角的真实轨迹）
    %   - 结束车身右沿：H_right_E → T_right_E（直，t=T_h 挂车右沿）
    %   - T_right 反曲线段：下沿（挂车后端右角真实轨迹反向）
    %   - 起始车身右沿：T_right₀ → H_right₀（直，t=0 挂车右沿，由闭合自动产生）
    poly = [ H_right; ...                 % H_right₀ ... H_right_E   (M+1 点)
             flipud(T_right); ...         % T_right_E ... T_right₀   (M+1 点)
             H_right(1, :) ];             % 闭合
end
