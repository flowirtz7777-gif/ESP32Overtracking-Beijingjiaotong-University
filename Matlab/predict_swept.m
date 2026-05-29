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
%     dt_pred   预测内部步长 (s)，建议 0.05
%     alpha_dot (可选) 转向角速率 (rad/s)。
%               若提供：α(τ) = α0 + α_dot * τ，并夹紧到 [−π/2, π/2]
%               若省略或为 NaN：α(τ) = α0 (保持不变)
%
%   输出：
%     poly  闭合多边形顶点 (N×2)，逆时针走向：
%             [A_right(0..k_end)] -> [T_right(k_end..0)]
%           最后一行与第一行相同以闭合
%
%   说明：
%     - 主循环每步用 kinematics_step 推进
%     - 每一步取 A、T 两点的右侧法向偏移 (+W/2) 得到右沿点
%       A 用 牵引车航向 theta；T 用 挂车航向 theta_t (= theta - phi)
%     - 这样形成的多边形包络从车头到挂车尾的整段右侧扫掠区域
%     - B、H 落在 A-T 的连线附近（同一刚体），无需重复加入边界
%
%   设计权衡：
%     - 顶点数 = 2*(k+1)，其中 k = ceil(T_h/dt_pred)；T_h=2.0, dt_pred=0.05 时 ≈ 82 顶点
%     - 用包络法替代栅格化，保证 ESP32 端 point_in_poly 复杂度 O(N)

    if nargin < 7
        alpha_dot = 0;
    end
    if isempty(alpha_dot) || ~isfinite(alpha_dot)
        alpha_dot = 0;
    end

    half_w = 0.5 * p.width;
    N      = floor(T_h / dt_pred);     % 步数
    M      = N + 1;                    % 包含起点

    A_right = zeros(M, 2);
    T_right = zeros(M, 2);

    s = s0(:);   % 列向量
    tau = 0;
    for k = 1:M
        % 派生几何点
        pts = derive_points(s, p);

        % A 用牵引车航向的右法向 ( sinθ, -cosθ )
        cT = cos(s(3));
        sT = sin(s(3));
        A_right(k, :) = pts.A + half_w * [ sT, -cT ];

        % T 用挂车航向的右法向 ( sinθ_t, -cosθ_t )
        cTt = cos(pts.theta_t);
        sTt = sin(pts.theta_t);
        T_right(k, :) = pts.T + half_w * [ sTt, -cTt ];

        % 推进到 τ + dt
        if k < M
            alpha_tau = alpha_now + alpha_dot * tau;
            % 物理限幅（与硬件 α 量程一致）
            alpha_tau = max(min(alpha_tau, deg2rad(40)), -deg2rad(40));
            s   = kinematics_step(s, alpha_tau, v_now, p, dt_pred);
            tau = tau + dt_pred;
        end
    end

    % 包络多边形：A_right 正向 + T_right 反向 + 闭合
    poly = [ A_right; flipud(T_right); A_right(1, :) ];
end
