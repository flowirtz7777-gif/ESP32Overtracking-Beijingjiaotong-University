% MATLAB Simulation: 半挂车轨迹仿真 (最终版：ICCT+TF内轮差 + 右侧外缘扫掠区域 + 红色斜杠裁剪)
% 核心：
% 1) 主仿真：时序自洽 + 严格几何约束（|H-T|=L），无漂移
% 2) 内轮差（按你的定义）：
%    ICCT = 挂车后轴T的瞬时转弯中心
%    直线 (T-ICCT) 与牵引车后轴中心轨迹 B(·) 的折线相交于 F
%    TF = |T-F| 为内轮差
%    关键修复：交点判定用"整条直线"（不限制 t_line ∈[0,1]），仅限制交点在B折线段上 u_seg∈[0,1]
% 3) 右侧车身外缘扫掠：用四边形片元栅格化 + 红色斜杠严格裁剪在黄色区域内

clear; clc; close all;

%% ====================== 1. 核心参数 ======================
v_A = 3;               % 牵引车前轮速度 (m/s)
l = 4.0;               % 牵引车轴距 (m)：前轮A ↔ 后轮B
l_h = 1.8;             % 后悬长度 (m)：后轮B ↔ 牵引销H
L = 13.5;              % 挂车轴距 (m)：牵引销H ↔ 挂车后轮T

T_end = 35;            % 总仿真时间 (s)
dt = 0.02;             % 时间步长 (s)
t = 0:dt:T_end;        % 时间向量
N = length(t);         % 总步数

% PID控制器参数
Kp_theta = 0.8;    Ki_theta = 0.02;    Kd_theta = 0.02;  % 外环：航向
Kp_phi   = 0.3;    Ki_phi   = 0.01;    Kd_phi   = 0.01;  % 内环：铰接角

% 物理限幅（硬限幅）
alpha_limit   = 30*pi/180;     % 转向角最大±30°
phi_safe_limit= 15*pi/180;     % 铰接角硬限幅±25°

% 低通滤波参数（用于 H 点角速度估计，可选）
omega_filter_alpha = 0.2;
prev_omega = 0;

%% ====================== 2. 数组初始化 ======================
x_A = zeros(1, N); y_A = zeros(1, N); % 牵引车前轮A
x_B = zeros(1, N); y_B = zeros(1, N); % 牵引车后轮B
theta = zeros(1, N);                  % 牵引车航向角

x_H = zeros(1, N); y_H = zeros(1, N); % 牵引销H
x_T = zeros(1, N); y_T = zeros(1, N); % 挂车后轮T
phi = zeros(1, N);                    % 铰接角
theta_t = zeros(1, N);                % 挂车航向角

alpha = zeros(1, N);                  % 转向角
theta_ref = zeros(1, N);              % 参考航向角

e_theta = zeros(1, N);
e_phi = zeros(1, N);
integral_theta = 0;
integral_phi = 0;
prev_e_theta = 0;
prev_e_phi = 0;

%% ====================== 3. 初始状态 ======================
x_B(1) = 0;  y_B(1) = 0;
x_A(1) = 0;  y_A(1) = l;
theta(1) = pi/2;

x_H(1) = x_B(1) + l_h*cos(theta(1));
y_H(1) = y_B(1) + l_h*sin(theta(1));

phi(1) = 0;

theta_t(1) = theta(1) - phi(1);
x_T(1) = x_H(1) - L*cos(theta_t(1));
y_T(1) = y_H(1) - L*sin(theta_t(1));

%% ====================== 4. 参考航向规划（t2可调） ======================
t1 = 3; t2 = 15; % 8=急，15=中，20=缓
for k = 1:N
    if t(k) <= t1
        theta_ref(k) = pi/2;
    elseif t(k) <= t2
        theta_ref(k) = pi/2 * (1 - (t(k)-t1)/(t2-t1));
    else
        theta_ref(k) = 0;
    end
end

%% ====================== 5. 主仿真循环 ======================
for k = 1:N-1
    % Step 1: 当前航向
    theta_k = atan2(y_A(k)-y_B(k), x_A(k)-x_B(k));
    theta(k) = theta_k;
    theta_t(k) = theta_k - phi(k);

    % Step 2: PID 求 alpha
    err_theta = atan2(sin(theta_ref(k) - theta_k), cos(theta_ref(k) - theta_k));
    e_theta(k) = err_theta;

    integral_theta = integral_theta + err_theta*dt;
    integral_theta = max(min(integral_theta, 0.4), -0.4);
    derivative_theta = (err_theta - prev_e_theta)/dt;

    alpha1 = Kp_theta*err_theta + Ki_theta*integral_theta + Kd_theta*derivative_theta;

    err_phi = 0 - phi(k);
    e_phi(k) = err_phi;

    integral_phi = integral_phi + err_phi*dt;
    integral_phi = max(min(integral_phi, 0.2), -0.2);
    derivative_phi = (err_phi - prev_e_phi)/dt;

    delta_alpha = Kp_phi*err_phi + Ki_phi*integral_phi + Kd_phi*derivative_phi;

    if k == 1
        alpha_k = alpha1 + delta_alpha;
    else
        alpha_k = 0.95*alpha(k-1) + 0.05*(alpha1 + delta_alpha);
    end
    alpha_k = max(min(alpha_k, alpha_limit), -alpha_limit);
    alpha(k) = alpha_k;

    % Step 3: 更新 A/B（后轴纯滚动）
    vB = v_A*cos(alpha_k);
    vBx = vB*cos(theta_k);  vBy = vB*sin(theta_k);
    vAx = v_A*cos(theta_k + alpha_k);
    vAy = v_A*sin(theta_k + alpha_k);

    x_A(k+1) = x_A(k) + vAx*dt;
    y_A(k+1) = y_A(k) + vAy*dt;
    x_B(k+1) = x_B(k) + vBx*dt;
    y_B(k+1) = y_B(k) + vBy*dt;

    % Step 4: theta_next
    theta_next = atan2(y_A(k+1)-y_B(k+1), x_A(k+1)-x_B(k+1));
    theta(k+1) = theta_next;

    % Step 5: 更新 phi（硬限幅）
    dphi_dt = (v_A*sin(alpha_k)/l) - (vB*sin(phi(k))/L);
    phi(k+1) = phi(k) + dphi_dt*dt;
    phi(k+1) = max(min(phi(k+1), phi_safe_limit), -phi_safe_limit);

    % Step 6: 更新 H
    x_H(k+1) = x_B(k+1) + l_h*cos(theta_next);
    y_H(k+1) = y_B(k+1) + l_h*sin(theta_next);

    % Step 7: （可选）估计 omega
    omega_raw = (theta_next - theta_k)/dt;
    omega = omega_filter_alpha*omega_raw + (1-omega_filter_alpha)*prev_omega;
    prev_omega = omega; %#ok<NASGU>

    % Step 8: 严格几何约束更新 T（无漂移）
    theta_t_next = theta_next - phi(k+1);
    theta_t(k+1) = theta_t_next;

    x_T(k+1) = x_H(k+1) - L*cos(theta_t_next);
    y_T(k+1) = y_H(k+1) - L*sin(theta_t_next);

    % Step 9: 缓存
    prev_e_theta = err_theta;
    prev_e_phi = err_phi;
end
alpha(N) = alpha(N-1);

%% ====================== 6. 轨迹可视化 ======================
set(0,'DefaultFigureColor','white');

figure('Position',[100,100,1000,600]);
plot(x_A,y_A,'r-','LineWidth',3,'DisplayName','牵引车前轮(A)'); hold on;
grid on; grid minor; axis equal;
plot(x_B,y_B,'b-','LineWidth',3,'DisplayName','牵引车后轮(B)');
plot(x_T,y_T,'g-','LineWidth',3,'DisplayName','挂车后轮(T)');
plot(x_H,y_H,'k--','LineWidth',1.5,'DisplayName','牵引销(H)');
scatter(x_A(1),y_A(1),100,'r','filled','DisplayName','起始点');
scatter(x_T(end),y_T(end),100,'g','filled','DisplayName','终点');
xlabel('X (m)'); ylabel('Y (m)');
title(sprintf('半挂车转弯轮迹（t2=%.0fs）',t2),'FontSize',14,'FontWeight','bold');
legend('Location','best');

figure('Position',[100,700,1000,400]);
subplot(1,2,1);
plot(t,rad2deg(phi),'m-','LineWidth',2); grid on;
xlabel('t (s)'); ylabel('\phi (deg)'); title('铰接角变化'); ylim([-30,30]);
subplot(1,2,2);
plot(t,rad2deg(alpha),'b-','LineWidth',2); grid on;
xlabel('t (s)'); ylabel('\alpha (deg)'); title('牵引车转向角输出 (PID)'); ylim([-32,32]);

%% ====================== 7. ICCT + TF 内轮差（关键修复版） ======================
ICCT_x = nan(1,N); ICCT_y = nan(1,N);
off_TF = nan(1,N);
Fx = nan(1,N); Fy = nan(1,N);

% vT（差分）
vTx = nan(1,N); vTy = nan(1,N);
vTx(2:N) = diff(x_T)/dt;
vTy(2:N) = diff(y_T)/dt;
vTx(1) = vTx(2); vTy(1) = vTy(2);
vT = hypot(vTx, vTy);
vT = smoothdata(vT,'movmean',7);

% omega_t = d(theta_t)/dt
omega_t = nan(1,N);
omega_t(2:N) = diff(theta_t)/dt;
omega_t(1) = omega_t(2);
omega_t = smoothdata(omega_t,'movmean',7);

eps_om = 1e-4;          % 近直行阈值
eps_det = 1e-12;        % 线线求交退化阈值

for k = 2:N
    if abs(omega_t(k)) < eps_om || vT(k) < 1e-6
        % 近直行：TF几何不稳定 -> 用 NaN（避免整条曲线被0拉平）
        off_TF(k) = NaN;
        continue;
    end

    % ICCT（挂车后轴T的瞬时转弯中心）
    Rt_signed = vT(k)/omega_t(k);
    tht = theta_t(k);
    nLx = -sin(tht); nLy = cos(tht);

    ICCT_x(k) = x_T(k) + Rt_signed*nLx;
    ICCT_y(k) = y_T(k) + Rt_signed*nLy;

    % 直线：T + t*d （注意：这是整条直线，不限制t）
    Px = x_T(k); Py = y_T(k);
    dx = ICCT_x(k) - Px;
    dy = ICCT_y(k) - Py;

    if hypot(dx,dy) < 1e-9
        off_TF(k) = NaN;
        continue;
    end

    bestDist = inf; bestFx = nan; bestFy = nan;

    % 与 B 轨迹折线求交（用历史 1..k）
    for i = 1:k-1
        Qx = x_B(i);   Qy = y_B(i);
        Rx = x_B(i+1) - x_B(i);
        Ry = y_B(i+1) - y_B(i);

        % 解： P + t*d = Q + u*R
        detM = dx*(-Ry) - dy*(-Rx);
        if abs(detM) < eps_det
            continue;
        end

        rhsx = Qx - Px;
        rhsy = Qy - Py;

        t_line = ( rhsx*(-Ry) - rhsy*(-Rx) ) / detM;
        u_seg  = ( dx*rhsy - dy*rhsx ) / detM;

        % 关键修复：只限制交点在 B 的线段上（u_seg∈[0,1]）
        % 不再限制 t_line（允许交点在整条直线上，通常会出现 t_line<0 的情况）
        if (u_seg >= 0) && (u_seg <= 1)
            ix = Px + t_line*dx;
            iy = Py + t_line*dy;

            distTF = hypot(ix - Px, iy - Py); % |TF|
            if distTF < bestDist
                bestDist = distTF;
                bestFx = ix; bestFy = iy;
            end
        end
    end

    if isfinite(bestDist)
        Fx(k) = bestFx; Fy(k) = bestFy;
        off_TF(k) = bestDist;
    else
        off_TF(k) = NaN;
    end
end

validTF = isfinite(off_TF);
fprintf('\n===== 你的定义（ICCT + TF）内轮差统计 =====\n');
fprintf('有效点数: %d / %d\n', sum(validTF), N);
if any(validTF)
    fprintf('最大 TF 内轮差: %.3f m\n', max(off_TF(validTF)));
    fprintf('平均 TF 内轮差: %.3f m\n', mean(off_TF(validTF)));
else
    fprintf('未找到有效交点，请检查轨迹是否足够长或eps_om设置是否过大。\n');
end

figure('Name','内轮差（你的定义：TF）');
plot(t, off_TF,'LineWidth',2); grid on;
xlabel('t (s)'); ylabel('TF (m)');
title('挂车内轮差（你的定义：ICCT，TF 为内轮差）');

figure('Name','ICCT轨迹（挂车ICC）','Position',[200 120 900 650]);
hold on; grid on; grid minor; axis equal;
plot(x_B,y_B,'b-','LineWidth',2,'DisplayName','牵引车后轴 B 轨迹');
plot(x_T,y_T,'g-','LineWidth',2,'DisplayName','挂车后轴 T 轨迹');
plot(ICCT_x,ICCT_y,'m--','LineWidth',2,'DisplayName','ICCT 轨迹');
xlabel('X (m)'); ylabel('Y (m)');
title('挂车 ICCT 轨迹（由 vT / \omega_t 计算）');
legend('Location','best');

% 最大TF时刻示意
if any(validTF)
    [~, idx] = max(off_TF(validTF));
    idxList = find(validTF);
    idx = idxList(idx);

    figure('Name','最大TF时刻几何示意','Position',[220 140 900 650]);
    hold on; grid on; axis equal;
    plot(x_B,y_B,'b-','LineWidth',2,'DisplayName','B轨迹');
    plot(x_T,y_T,'g-','LineWidth',2,'DisplayName','T轨迹');
    scatter(x_T(idx),y_T(idx),80,'g','filled','DisplayName','T@max');
    scatter(ICCT_x(idx),ICCT_y(idx),80,'m','filled','DisplayName','ICCT@max');
    scatter(Fx(idx),Fy(idx),80,'r','filled','DisplayName','F@max');
    plot([x_T(idx), ICCT_x(idx)],[y_T(idx), ICCT_y(idx)],'m-','LineWidth',2,'DisplayName','T-ICCT');
    plot([x_T(idx), Fx(idx)],[y_T(idx), Fy(idx)],'r-','LineWidth',3,'DisplayName','TF');
    title(sprintf('最大TF=%.2fm at t=%.2fs', off_TF(idx), t(idx)),'FontWeight','bold');
    legend('Location','best');
end

%% ====================== 8. 右侧车身外缘扫掠区域 + 红色斜杠（严格裁剪） ======================
track = 2.0; half_track = track/2;

% 右侧边界轨迹：H_right、T_right
x_Hr = zeros(1,N); y_Hr = zeros(1,N);
x_Tr = zeros(1,N); y_Tr = zeros(1,N);

for k = 1:N
    tht = theta_t(k);
    nRx =  sin(tht);
    nRy = -cos(tht);

    x_Hr(k) = x_H(k) + half_track*nRx;
    y_Hr(k) = y_H(k) + half_track*nRy;

    x_Tr(k) = x_T(k) + half_track*nRx;
    y_Tr(k) = y_T(k) + half_track*nRy;
end

% 网格参数
res = 0.05; margin = 2;
minX = min([x_Hr x_Tr x_A x_B x_T x_H]) - margin;
maxX = max([x_Hr x_Tr x_A x_B x_T x_H]) + margin;
minY = min([y_Hr y_Tr y_A y_B y_T y_H]) - margin;
maxY = max([y_Hr y_Tr y_A y_B y_T y_H]) + margin;

xg = minX:res:maxX;
yg = minY:res:maxY;
nx = numel(xg); ny = numel(yg);
occ = false(ny,nx);

% 四边形片元扫掠（Hr-Tr 随时间形成的带状区域）
for k = 1:N-1
    px = [x_Hr(k), x_Tr(k), x_Tr(k+1), x_Hr(k+1)];
    py = [y_Hr(k), y_Tr(k), y_Tr(k+1), y_Hr(k+1)];

    if polyarea(px,py) < 1e-10
        continue;
    end

    xmin = min(px); xmax = max(px);
    ymin = min(py); ymax = max(py);

    ix1 = max(1, floor((xmin-minX)/res)+1);
    ix2 = min(nx, ceil((xmax-minX)/res)+1);
    iy1 = max(1, floor((ymin-minY)/res)+1);
    iy2 = min(ny, ceil((ymax-minY)/res)+1);

    [X,Y] = meshgrid(xg(ix1:ix2), yg(iy1:iy2));
    in = inpolygon(X,Y,px,py);
    occ(iy1:iy2, ix1:ix2) = occ(iy1:iy2, ix1:ix2) | in;
end

swept_area = nnz(occ)*res^2;
fprintf('右侧车身外缘(Hr-Tr)扫掠面积 ≈ %.3f m^2 (res=%.2fm)\n', swept_area, res);

% 可视化
figure('Position',[120,120,1100,650]);
imagesc(xg, yg, occ); set(gca,'YDir','normal');
hold on; axis equal; grid on;
colormap([1 1 1; 1 0.85 0.25]);

plot(x_A,y_A,'r-','LineWidth',2.2,'DisplayName','牵引前轮A');
plot(x_B,y_B,'b-','LineWidth',2.2,'DisplayName','牵引后轮B(中心)');
plot(x_T,y_T,'g-','LineWidth',2.2,'DisplayName','挂车后轮T(中心)');
plot(x_H,y_H,'k--','LineWidth',1.1,'DisplayName','牵引销H(中心)');
plot(x_Hr,y_Hr,'Color',[0.95 0.45 0],'LineWidth',2,'DisplayName','H\_right');
plot(x_Tr,y_Tr,'Color',[0 0.5 0],'LineStyle','--','LineWidth',2,'DisplayName','T\_right');

title(sprintf('右侧车身外缘扫掠区域（t2=%.0fs） track=%.1fm res=%.2fm', t2, track, res), ...
    'FontWeight','bold');
xlabel('X (m)'); ylabel('Y (m)');
legend('Location','best');

% 红色斜杠（严格裁剪到 occ 内）
hatch_spacing = 0.55;
hatch_angle = pi/4;
hatch_len = 1.20;
clip_step = max(res/3, 0.01);

xmin = min(xg); xmax = max(xg);
ymin = min(yg); ymax = max(yg);

dxh = cos(hatch_angle);
dyh = sin(hatch_angle);

[xs, ys] = meshgrid(xmin:hatch_spacing:xmax, ymin:hatch_spacing:ymax);
xs = xs(:); ys = ys(:);

for i = 1:numel(xs)
    ix0 = round((xs(i) - minX)/res) + 1;
    iy0 = round((ys(i) - minY)/res) + 1;
    if ~(ix0>=1 && ix0<=nx && iy0>=1 && iy0<=ny && occ(iy0, ix0))
        continue;
    end

    x1 = xs(i) - 0.5*hatch_len*dxh;
    y1 = ys(i) - 0.5*hatch_len*dyh;
    x2 = xs(i) + 0.5*hatch_len*dxh;
    y2 = ys(i) + 0.5*hatch_len*dyh;

    segLen = hypot(x2-x1, y2-y1);
    M = max(10, ceil(segLen/clip_step));

    xline = linspace(x1,x2,M);
    yline = linspace(y1,y2,M);

    inside = false(1,M);
    for m = 1:M
        ix = round((xline(m)-minX)/res)+1;
        iy = round((yline(m)-minY)/res)+1;
        if ix>=1 && ix<=nx && iy>=1 && iy<=ny
            inside(m) = occ(iy,ix);
        end
    end

    d = diff([false, inside, false]);
    sIdx = find(d==1);
    eIdx = find(d==-1)-1;

    for s = 1:numel(sIdx)
        a = sIdx(s); b = eIdx(s);
        if b-a < 2, continue; end
        plot(xline(a:b), yline(a:b), 'r-', 'LineWidth', 1.2, 'HandleVisibility','off');
    end
end