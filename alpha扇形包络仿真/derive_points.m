function pts = derive_points(s, p)
%DERIVE_POINTS  从最小状态 [xB,yB,theta,phi] 派生所有车体几何点。
%
%   pts = derive_points(s, p)
%
%   输入：
%     s   状态 [xB, yB, theta, phi]
%     p   vehicle_params struct
%
%   输出 pts (struct)：
%     A   牵引车前轮中心 [x, y]
%     B   牵引车后轴中心 [x, y]
%     H   鞍座牵引销     [x, y]
%     T   挂车后轴中心   [x, y]
%     theta_t  挂车航向角 (rad)
%
%   几何关系（与 C++ Predictor::derive_points 对齐）：
%       A   = B + l*(cos θ, sin θ)
%       H   = B + l_h*(cos θ, sin θ)
%       θ_t = θ - φ
%       T   = H - L*(cos θ_t, sin θ_t)

    xB    = s(1);
    yB    = s(2);
    theta = s(3);
    phi   = s(4);

    cT = cos(theta);
    sT = sin(theta);

    pts.B = [xB,                yB];
    pts.A = [xB + p.l   * cT,   yB + p.l   * sT];
    pts.H = [xB + p.l_h * cT,   yB + p.l_h * sT];

    theta_t = theta - phi;
    pts.theta_t = theta_t;

    cTt = cos(theta_t);
    sTt = sin(theta_t);
    pts.T = [pts.H(1) - p.L * cTt,  pts.H(2) - p.L * sTt];
end
