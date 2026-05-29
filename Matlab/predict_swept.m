function poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%PREDICT_SWEPT  从当前状态 s0 向前推 T_h 秒，构造右侧车身扫掠多边形。
%
%   poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred)
%   poly = predict_swept(s0, alpha_now, v_now, p, T_h, dt_pred, alpha_dot)
%
%   输入：
%     s0        初始状态 [xB, yB, theta, phi]
%     alpha_now 当前前轮转向角 (rad)
%     v_now     当前车速 (m/s)
%     p         vehicle_params struct
%     T_h       预测时间窗 (s)，建议 0.3 / 1.0 / 2.0 三档
%     dt_pred   预测内部步长 (s)，建议 0.01
%     alpha_dot (可选) 转向角速率 (rad/s)；建议默认 0（短时保持假设）
%
%   输出：
%     poly  闭合简单多边形顶点 (N×2)，最后一行 = 第一行
%           **凸包**，保证不自相交
%
%   构造方法（修订版，2026-05-30）：
%     旧逻辑用 [A_right(0..M); T_right(M..0); close] 构造一个"梯形包络"，
%     但车体右沿是 V 形折线 (H 处因 φ 折弯)，把它当直线连导致两端线段交叉，
%     形成漏斗 / 蝴蝶结自相交多边形。
%
%     新逻辑：每时刻收集 4 个右半车体关键点 (A_right, B, T, T_right) 的位置，
%     再对所有时刻所有点取凸包。凸包数学上保证简单多边形 (无自相交)。
%     B、T 在车体中心线上，A_right、T_right 在外右沿，4 点合起来覆盖
%     "车体右半边"，凸包包络整个右半边在 t∈[0,T_h] 占据的空间。
%
%   性能：
%     T_h=2.0, dt_pred=0.01 → M=200, 4*(M+1)=804 候选点
%     凸包后顶点 ~30-60 个 (取决于转弯激烈程度)，远低于 ESP32 端 64 顶点上限

    if nargin < 7, alpha_dot = 0; end
    if isempty(alpha_dot) || ~isfinite(alpha_dot), alpha_dot = 0; end
    ALPHA_DOT_MAX = pi;
    if abs(alpha_dot) > ALPHA_DOT_MAX
        alpha_dot = sign(alpha_dot) * ALPHA_DOT_MAX;
    end

    half_w = 0.5 * p.width;
    M      = floor(T_h / dt_pred);

    % 每个时间步收集 4 个右半车体关键点
    pts_pool = zeros((M+1) * 4, 2);

    s   = s0(:);
    tau = 0;
    idx = 1;
    for k = 1:M+1
        d   = derive_points(s, p);
        cT  = cos(s(3));         sT  = sin(s(3));
        cTt = cos(d.theta_t);    sTt = sin(d.theta_t);

        pts_pool(idx,   :) = d.A + half_w * [ sT,  -cT ];     % A_right (前轮右)
        pts_pool(idx+1, :) = d.B;                              % B (后轴中心)
        pts_pool(idx+2, :) = d.T;                              % T (挂车后轴中心)
        pts_pool(idx+3, :) = d.T + half_w * [ sTt, -cTt ];    % T_right (挂车后轮右)
        idx = idx + 4;

        if k <= M
            alpha_tau = alpha_now + alpha_dot * tau;
            alpha_tau = max(min(alpha_tau, deg2rad(40)), -deg2rad(40));
            s   = kinematics_step(s, alpha_tau, v_now, p, dt_pred);
            tau = tau + dt_pred;
        end
    end

    % 凸包（自动闭合：convhull 返回的索引序列首尾相同）
    K    = convhull(pts_pool(:,1), pts_pool(:,2));
    poly = pts_pool(K, :);
end
