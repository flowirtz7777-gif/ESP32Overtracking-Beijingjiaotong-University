function s2 = kinematics_step(s, alpha, v, p, dt)
%KINEMATICS_STEP  半挂车一步严格运动学（含鞍座偏置 l_h 耦合）。
%
%   s2 = kinematics_step(s, alpha, v, p, dt)
%
%   输入：
%     s     状态向量 [xB, yB, theta, phi]
%             xB, yB    : 牵引车后轴中心位置 (m)
%             theta     : 牵引车航向角 (rad)
%             phi       : 铰接角 (rad), 牵引车减挂车航向
%     alpha 前轮转向角 (rad)
%     v     牵引车前轮速度 (m/s)；这里假定 v 沿前轮指向，纵向分量 vB = v*cos(alpha)
%     p     vehicle_params 结构体
%     dt    步长 (s)
%
%   输出：
%     s2    下一时刻状态 [xB, yB, theta, phi]，与输入维度一致
%
%   核心方程（与 C++ Predictor::step 字字对齐，与 CLAUDE.md / AGENTS.md 一致）：
%
%       omega1 = v * sin(alpha) / l                     % 牵引车横摆率
%       vB     = v * cos(alpha)                         % 牵引车后轴中心纵向速度
%
%       v_Hx_t =  vB*cos(phi) + l_h*omega1*sin(phi)     % 鞍座 H 在挂车体系下纵向速度
%       v_Hy_t = -vB*sin(phi) + l_h*omega1*cos(phi)     %                       横向速度
%       omega2 = v_Hy_t / L                             % 挂车横摆率（关键耦合项）
%
%       xB    += vB*cos(theta)*dt
%       yB    += vB*sin(theta)*dt
%       theta += omega1*dt
%       phi   += (omega1 - omega2)*dt
%       phi    = clamp(phi, -phi_max, +phi_max)
%
%   ⚠️ 旧版 guacheweixianqu.m 漏了 omega2 中的 l_h*omega1 耦合项；新代码统一使用此函数。

    if numel(s) ~= 4
        error('kinematics_step:BadState', 'state 向量必须为 4 维 [xB,yB,theta,phi]');
    end

    xB    = s(1);
    yB    = s(2);
    theta = s(3);
    phi   = s(4);

    l   = p.l;
    l_h = p.l_h;
    L   = p.L;

    % ---------- 牵引车 ----------
    omega1 = v * sin(alpha) / l;
    vB     = v * cos(alpha);

    % ---------- 鞍座 H 在挂车体系下的速度（耦合关键） ----------
    cphi = cos(phi);
    sphi = sin(phi);
    v_Hx_t =  vB*cphi + l_h*omega1*sphi;
    v_Hy_t = -vB*sphi + l_h*omega1*cphi;

    % ---------- 挂车横摆率 ----------
    omega2 = v_Hy_t / L;

    % ---------- 欧拉积分 ----------
    xB_n    = xB    + vB*cos(theta)*dt;
    yB_n    = yB    + vB*sin(theta)*dt;
    theta_n = theta + omega1*dt;
    phi_n   = phi   + (omega1 - omega2)*dt;

    % ---------- 铰接角硬限幅 ----------
    if isfield(p, 'phi_max') && isfinite(p.phi_max) && p.phi_max > 0
        phi_n = max(min(phi_n, p.phi_max), -p.phi_max);
    end

    s2 = [xB_n; yB_n; theta_n; phi_n];
    if isrow(s)
        s2 = s2.';
    end
end
