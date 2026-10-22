% MATLAB Simulation: 初始航向角pi/2(90°) → 稳态航向角0°
clear; clc; close all;

%% ====================== 1. 参数设置 ======================
v_A = 3;               % 前轮速度 (m/s)
l = 9;                 % 轴距 (m)
T = 35;                % 仿真总时间 (s)
dt = 0.01;             % 时间步长 (s)
t = 0:dt:T;            % 时间向量
N = length(t);         % 时间步数

% PID控制器参数（无震荡最优值）
Kp = 0.9;              % 比例增益
Ki = 0.02;             % 积分增益
Kd = 0.03;             % 微分增益
alpha_limit = 20*pi/180;   % 车轮转向角限幅(20°) - 设定值
integral_limit = 0.5;  % 积分项限幅（防止饱和）

%% ====================== 2. 数组初始化 ======================
x_A = zeros(1, N); y_A = zeros(1, N);  % 前轮A坐标
x_B = zeros(1, N); y_B = zeros(1, N);  % 后轮B坐标
alpha_t = zeros(1, N);                 % 车轮转向角
theta = zeros(1, N);                   % 实际航向角 (rad)
theta_ref = zeros(1, N);               % 参考航向角 (rad)
e = zeros(1, N);                       % 航向偏差
integral_e = 0;                        % 积分项
prev_e = 0;                            % 上一时刻偏差

% 初始位置：后轮B(0,0)，前轮A(0,l) → 初始航向角=pi/2(90°，竖直向上)
x_A(1) = 0; y_A(1) = l;
x_B(1) = 0; y_B(1) = 0;

%% ====================== 3. 参考航向角规划 ======================
t1 = 3; t2 = 20;  % 收敛时间节点
for k = 1:N
    if t(k) <= t1
        theta_ref(k) = pi/2;  % 0~3s：保持初始航向90°
    elseif t(k) <= t2
        % 3~20s：线性收敛到0°
        theta_ref(k) = pi/2 * (1 - (t(k)-t1)/(t2-t1));
    else
        theta_ref(k) = 0;  % 20s后：保持水平0°
    end
end

%% ====================== 4. 全时段PID控制 ======================
for k = 1:N-1
    % 当前坐标
    xA = x_A(k); yA = y_A(k);
    xB = x_B(k); yB = y_B(k);
    
    % 计算实际航向角
    AB_x = xA - xB;
    AB_y = yA - yB;
    theta(k) = atan2(AB_y, AB_x);  % 初始值=pi/2(90°)
    
    % 计算航向偏差：参考航向 - 实际航向
    e(k) = theta_ref(k) - theta(k);
    
    % PID核心计算（积分限幅）
    integral_e = integral_e + e(k)*dt;
    integral_e = max(min(integral_e, integral_limit), -integral_limit);
    derivative_e = (e(k) - prev_e)/dt;
    alpha_pid = Kp*e(k) + Ki*integral_e + Kd*derivative_e;
    
    % 转向角限幅
    alpha_pid = max(min(alpha_pid, alpha_limit), -alpha_limit);
    
    % 更新转向角和上一偏差
    alpha_t(k) = alpha_pid;
    prev_e = e(k);
    
    % 速度计算（正alpha对应顺时针偏转，向右转弯）
    w2x = AB_x / l;
    w2y = AB_y / l;
    w1x = w2x*cos(alpha_t(k)) - w2y*sin(alpha_t(k));
    w1y = w2x*sin(alpha_t(k)) + w2y*cos(alpha_t(k));
    
    % 前轮/后轮速度
    vAx = v_A * w1x;
    vAy = v_A * w1y;
    vB = v_A * cos(alpha_t(k));
    vBx = vB * w2x;
    vBy = vB * w2y;
    
    % 更新坐标
    x_A(k+1) = xA + vAx * dt;
    y_A(k+1) = yA + vAy * dt;
    x_B(k+1) = xB + vBx * dt;
    y_B(k+1) = yB + vBy * dt;
    
    % 轴距修正（确保轴距始终为l）
    current_l = sqrt((x_A(k+1)-x_B(k+1))^2 + (y_A(k+1)-y_B(k+1))^2);
    delta_l = current_l - l;
    if abs(delta_l) > 1e-5
        adjust_x = (x_A(k+1)-x_B(k+1))/current_l * delta_l;
        adjust_y = (y_A(k+1)-y_B(k+1))/current_l * delta_l;
        x_B(k+1) = x_B(k+1) + adjust_x;
        y_B(k+1) = y_B(k+1) + adjust_y;
    end
end

%% ====================== 5. 计算实际最大转向角（关键新增） ======================
alpha_limit_set = rad2deg(alpha_limit);  % 设定的转向角上限（20°）
actual_max_alpha = max(abs(rad2deg(alpha_t)));  % 实际输出的最大转向角

%% ====================== 6. 可视化设置（白色背景+黑色图框） ======================
% 全局基础设置
set(0, 'DefaultFigureColor', 'white');        % 图表背景白
set(0, 'DefaultAxesColor', 'white');          % 坐标轴背景白
set(0, 'DefaultTextColor', 'black');          % 文字黑色
set(0, 'DefaultLineColor', 'blue');           % 默认线条蓝色
set(0, 'DefaultAxesBox', 'on');               % 显示坐标轴边框
set(0, 'DefaultAxesLineWidth', 1.5);          % 边框线条加粗

%% ---------------------- 图1：轮迹曲线（单独输出） ----------------------
figure('Position', [100, 100, 800, 600], 'Name', '车辆轮迹曲线');
plot(x_A, y_A, 'r-', 'LineWidth', 3, 'DisplayName', '前轮A');
hold on;
plot(x_B, y_B, 'b-', 'LineWidth', 3, 'DisplayName', '后轮B');
% ========== 最终绝对精准版：稳态水平直线 ==========
% 1. 设置判断阈值
angle_threshold = 0.1;  % 航向角变化阈值（°）
window_size = 100;      % 连续判断的点数

% 2. 初始化稳态标记
steady_flag = false(1, N);

% 3. 计算航向角的变化率（绝对值）
theta_diff = abs([0, diff(rad2deg(theta))]);

% 4. 滑动窗口判断稳态阶段
for k = window_size:N
    if max(theta_diff(k-window_size+1:k)) < angle_threshold
        steady_flag(k) = true;
    end
end

% 5. 提取稳态段的坐标
first_steady_idx = find(steady_flag, 1, 'first');
last_steady_idx = find(steady_flag, 1, 'last');

if ~isempty(first_steady_idx) && ~isempty(last_steady_idx)
    steady_y = mean(y_A(last_steady_idx - 99 : last_steady_idx));
    % 关键：直接用稳态段的x坐标范围，不往前延伸
    line_start_x = x_A(first_steady_idx);
    line_end_x = max(x_A) + 10;
else
    steady_idx = t > 20;
    steady_y = mean(y_A(steady_idx));
    line_start_x = x_A(find(t>20, 1, 'first'));
    line_end_x = max(x_A) + 10;
end

% 6. 绘制精准对齐的稳态水平直线
plot([line_start_x, line_end_x], [steady_y, steady_y], 'k--', 'LineWidth', 2, 'DisplayName', '稳态水平直线');
% 标记初始位置
scatter(x_A(1), y_A(1), 100, 'r', 'filled', 'DisplayName', '前轮初始位置');
scatter(x_B(1), y_B(1), 100, 'b', 'filled', 'DisplayName', '后轮初始位置');
% 格式设置
xlabel('x / m', 'FontSize', 14);
ylabel('y / m', 'FontSize', 14);
title('车辆行驶轮迹（初始90°→稳态0°）', 'FontSize', 16, 'FontWeight', 'bold');
grid on; grid minor;  % 细网格
axis equal;  % 等比例显示
legend('Location', 'best', 'FontSize', 12);
set(gca, 'FontSize', 12);
% 核心修改：黑色图框+浅灰网格
ax1 = gca;
ax1.GridColor = [0.8,0.8,0.8];    % 浅灰色网格（不刺眼）
ax1.XColor = 'black';             % x轴刻度/文字黑色
ax1.YColor = 'black';             % y轴刻度/文字黑色
ax1.LineWidth = 1.5;              % 边框加粗
ax1.Box = 'on';                   % 显示图框

%% ====================== 7. ICC 与内轮差计算（后处理） ======================
ICC_x = nan(1, N);
ICC_y = nan(1, N);
R_A = nan(1, N);
R_B = nan(1, N);
d_inner = nan(1, N);     % 内轮差：R_A - R_B

% 为了求速度，使用差分（与主循环一致的 dt）
vAx = nan(1, N); vAy = nan(1, N);
vBx = nan(1, N); vBy = nan(1, N);

% 速度差分（后向差分；第1点无法算速度）
for k = 2:N
    vAx(k) = (x_A(k) - x_A(k-1)) / dt;
    vAy(k) = (y_A(k) - y_A(k-1)) / dt;
    vBx(k) = (x_B(k) - x_B(k-1)) / dt;
    vBy(k) = (y_B(k) - y_B(k-1)) / dt;
end

% 计算 ICC：用"速度法线交点"
% 法线方向 n = rot90(v) = [-vy, vx]
eps_det = 1e-10;  % 判断两条法线是否近平行
for k = 2:N
    Ax = x_A(k); Ay = y_A(k);
    Bx = x_B(k); By = y_B(k);

    vA = [vAx(k); vAy(k)];
    vB = [vBx(k); vBy(k)];

    % 若速度太小（几乎静止），跳过
    if norm(vA) < 1e-9 || norm(vB) < 1e-9
        continue;
    end

    nA = [-vA(2); vA(1)];
    nB = [-vB(2); vB(1)];

    % 解交点： A + s*nA = B + t*nB
    M = [nA, -nB];
    rhs = [Bx - Ax; By - Ay];

    if abs(det(M)) < eps_det
        % 法线近平行：曲率中心在无穷远（近似直行）
        continue;
    end

    st = M \ rhs;
    s = st(1);

    Ox = Ax + s*nA(1);
    Oy = Ay + s*nA(2);

    ICC_x(k) = Ox;
    ICC_y(k) = Oy;

    % 半径
    R_A(k) = hypot(Ax - Ox, Ay - Oy);
    R_B(k) = hypot(Bx - Ox, By - Oy);

    % 你要求的"连到ICC的线段长度差"作为内轮差
    d_inner(k) = R_A(k) - R_B(k);
end

% 去掉 nan，便于统计
valid = ~isnan(d_inner);
fprintf('\n===== ICC / 内轮差统计 =====\n');
fprintf('有效采样点数: %d / %d\n', sum(valid), N);
fprintf('最大内轮差: %.4f m\n', max(d_inner(valid)));
fprintf('平均内轮差: %.4f m\n', mean(d_inner(valid)));
fprintf('设定转向角上限: %.2f °\n', alpha_limit_set);  % 新增打印
fprintf('实际最大转向角: %.2f °\n', actual_max_alpha);  % 新增打印

% ========== 在轨迹图上添加车辆信息（含内轮差，兼容所有MATLAB版本） ==========
% 1. 计算内轮差的最大/平均值（此时d_inner已计算完成）
if exist('d_inner', 'var') && sum(~isnan(d_inner)) > 0
    max_inner_diff = max(d_inner(~isnan(d_inner)));  % 最大内轮差
    mean_inner_diff = mean(d_inner(~isnan(d_inner)));% 平均内轮差
else
    max_inner_diff = 0;
    mean_inner_diff = 0;
end

% 2. 准备要显示的信息文本（关键修改：新增实际最大转向角）
info_text = {
    ['车辆轴距: ', num2str(l), ' m'],
    ['前轮速度: ', num2str(v_A), ' m/s'],
    ['设定转向角上限: ', num2str(alpha_limit_set), ' °'],  % 设定值
    ['实际最大转向角: ', sprintf('%.2f', actual_max_alpha), ' °'],  % 实际值
    ['仿真总时长: ', num2str(T), ' s'],
    ['最大内轮差: ', sprintf('%.4f', max_inner_diff), ' m'],
    ['平均内轮差: ', sprintf('%.4f', mean_inner_diff), ' m']
};

% 3. 添加可拖动的文本（兼容所有版本）
h = text(max(x_A)*0.65, max(y_A)*0.9, info_text, ...
    'BackgroundColor', 'white', ...
    'EdgeColor', 'black', ...
    'FontSize', 10, ...
    'LineWidth', 1, ...
    'HorizontalAlignment', 'left');

% 4. 允许手动拖动文本框
set(h, 'ButtonDownFcn', @(obj,event) dragText(obj));

% 拖动函数
function dragText(obj)
    fig = gcf;
    pos = get(obj, 'Position');
    start_pt = get(fig, 'CurrentPoint');
    offset = pos(1:2) - start_pt(1,1:2);
    set(fig, 'WindowButtonMotionFcn', @(src,evnt) moveText(src, evnt, obj, offset));
    set(fig, 'WindowButtonUpFcn', @(src,evnt) stopDrag(src, evnt));
end

function moveText(src, evnt, obj, offset)
    pt = get(src, 'CurrentPoint');
    set(obj, 'Position', [pt(1,1)+offset(1), pt(1,2)+offset(2), 0]);
end

function stopDrag(src, evnt)
    set(src, 'WindowButtonMotionFcn', []);
    set(src, 'WindowButtonUpFcn', []);
end

%% ---------------------- 图2：ICC轨迹（单独输出） ----------------------
figure('Position', [950, 100, 800, 600], 'Name', 'ICC轨迹图');
% 绘制轮迹作为背景
plot(x_A, y_A, 'r-', 'LineWidth', 2, 'DisplayName', '前轮A');
hold on;
plot(x_B, y_B, 'b-', 'LineWidth', 2, 'DisplayName', '后轮B');
% 绘制ICC轨迹和散点
plot(ICC_x(valid), ICC_y(valid), 'g--', 'LineWidth', 2, 'DisplayName', 'ICC轨迹');
scatter(ICC_x(valid), ICC_y(valid), 10, 'k', 'filled', 'DisplayName', 'ICC离散点');
% 格式设置
xlabel('x / m', 'FontSize', 14);
ylabel('y / m', 'FontSize', 14);
title('ICC轨迹（瞬时转弯中心）', 'FontSize', 16, 'FontWeight', 'bold');
grid on; grid minor;
axis equal;
legend('Location', 'best', 'FontSize', 12);
set(gca, 'FontSize', 12);
% 保持边框样式不变
ax_icc = gca;
ax_icc.GridColor = [0.8,0.8,0.8];
ax_icc.XColor = 'black';
ax_icc.YColor = 'black';
ax_icc.LineWidth = 1.5;
ax_icc.Box = 'on';

%% ---------------------- 图3：内轮差+其余5张小图（合并输出） ----------------------
figure('Position', [100, 750, 1200, 800], 'Name', '内轮差+航向角+转向角+位移');

% 子图1：内轮差随时间变化
subplot(2, 3, 1);
plot(t, d_inner, 'b-', 'LineWidth', 2);
xlabel('Time / s', 'FontSize', 10);
ylabel('内轮差 d = R_A - R_B (m)', 'FontSize', 10);
title('内轮差随时间变化', 'FontSize', 12, 'FontWeight', 'bold');
grid on;
set(gca, 'FontSize', 10);
ax3_1 = gca;
ax3_1.GridColor = [0.8,0.8,0.8];
ax3_1.XColor = 'black';
ax3_1.YColor = 'black';
ax3_1.LineWidth = 1.5;
ax3_1.Box = 'on';

% 子图2：航向角跟踪
subplot(2, 3, 2);
plot(t, rad2deg(theta), 'r-', 'LineWidth', 2, 'DisplayName', '实际航向角');
hold on;
plot(t, rad2deg(theta_ref), 'k--', 'LineWidth', 2, 'DisplayName', '参考航向角');
xlabel('Time / s', 'FontSize', 10);
ylabel('航向角 / °', 'FontSize', 10);
title('航向角跟踪', 'FontSize', 12, 'FontWeight', 'bold');
grid on; legend('Location', 'best', 'FontSize', 10);
set(gca, 'FontSize', 10);
ax3_2 = gca;
ax3_2.GridColor = [0.8,0.8,0.8];
ax3_2.XColor = 'black';
ax3_2.YColor = 'black';
ax3_2.LineWidth = 1.5;
ax3_2.Box = 'on';

% 子图3：航向偏差
subplot(2, 3, 3);
plot(t, abs(rad2deg(e)), 'm-', 'LineWidth', 2);
xlabel('Time / s', 'FontSize', 10);
ylabel('航向偏差 / °', 'FontSize', 10);
title('航向偏差', 'FontSize', 12, 'FontWeight', 'bold');
grid on;
set(gca, 'FontSize', 10);
ax3_3 = gca;
ax3_3.GridColor = [0.8,0.8,0.8];
ax3_3.XColor = 'black';
ax3_3.YColor = 'black';
ax3_3.LineWidth = 1.5;
ax3_3.Box = 'on';

% 子图4：车轮转向角（绝对值）
subplot(2, 3, 4);
plot(t, abs(rad2deg(alpha_t)), 'g-', 'LineWidth', 2);
xlabel('Time / s', 'FontSize', 10);
ylabel('转向角（绝对值） / °', 'FontSize', 10);
title('车轮转向角大小', 'FontSize', 12, 'FontWeight', 'bold');
grid on;
set(gca, 'FontSize', 10);
ax3_4 = gca;
ax3_4.GridColor = [0.8,0.8,0.8];
ax3_4.XColor = 'black';
ax3_4.YColor = 'black';
ax3_4.LineWidth = 1.5;
ax3_4.Box = 'on';

% 子图5：x方向位移
subplot(2, 3, 5);
plot(t, x_A, 'c-', 'LineWidth', 2);
xlabel('Time / s', 'FontSize', 10);
ylabel('x位移 / m', 'FontSize', 10);
title('水平前进位移', 'FontSize', 12, 'FontWeight', 'bold');
grid on;
set(gca, 'FontSize', 10);
ax3_5 = gca;
ax3_5.GridColor = [0.8,0.8,0.8];
ax3_5.XColor = 'black';
ax3_5.YColor = 'black';
ax3_5.LineWidth = 1.5;
ax3_5.Box = 'on';

% 子图6：y方向位移
subplot(2, 3, 6);
plot(t, y_A, 'LineWidth', 2, 'Color', '#FF7F00');
xlabel('Time / s', 'FontSize', 10);
ylabel('y位移 / m', 'FontSize', 10);
title('竖直方向位移', 'FontSize', 12, 'FontWeight', 'bold');
grid on;
set(gca, 'FontSize', 10);
ax3_6 = gca;
ax3_6.GridColor = [0.8,0.8,0.8];
ax3_6.XColor = 'black';
ax3_6.YColor = 'black';
ax3_6.LineWidth = 1.5;
ax3_6.Box = 'on';
