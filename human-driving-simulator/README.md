# 人工驾驶半挂车工况仿真器

当前版本：**M1 + M2 + M3 + M4 — 浏览器人工驾驶、数据导出、Replay 与 Electron 开发入口**。

仿真器核心使用纯 HTML、CSS 和 JavaScript 实现，不依赖前端框架；既可直接在浏览器中打开，也可通过项目已有的 Electron 开发依赖启动独立桌面窗口。它用于通过 WASD 人工驾驶半挂车，并将每个固定时间步的真实车辆状态导出为 PID 工况兼容 CSV。

## M1 已实现

- 可编辑的车辆几何参数与人工驾驶参数；
- W/S 油门和制动控制；
- A/D 左右转向、转向限幅与松键自动回正；
- W 与 S 同时按下时刹车优先；
- 固定时间步长主循环，默认 `dt = 0.02 s`（50 Hz）；
- 含 `l_h` 鞍座偏置耦合项的半挂车运动学；
- A/B/H/T 四个关键点实时推导；
- 车速不小于 0，当前不支持倒车；
- 实时 HUD：时间、速度、加速度、α、φ、牵引车/挂车航向、B 点位置、按键和运行状态；
- Canvas 坐标网格、牵引车、挂车、关键点、朝向箭头和 B 点历史轨迹；
- 画面以 B 点为中心跟随，并根据车辆总长自动选择显示比例；
- 开始驾驶、结束驾驶和重置操作。

## M2 已实现

- 从点击“开始驾驶”起，按固定仿真步长逐帧记录真实状态；
- 记录 `t = 0` 初始帧，以及之后每个运动学积分帧；
- 导出 PID 工况兼容的 29 列 CSV；
- 文件名格式：`human_scenario_YYYYMMDD_HHMMSS.csv`；
- 页面显示记录行数、预计文件名、最近一行摘要和最近 8 行预览；
- 结束驾驶后仍可导出；
- 没有数据时点击导出会提示“暂无数据可导出”；
- 重置会清空全部 CSV 记录并生成新的预计文件名。

## M3 已实现

- 自动识别 `idle`、`accelerate`、`brake`、`left_turn`、`right_turn`、`straight`、`coast` 驾驶阶段；
- 阶段变化时自动关闭上一阶段并开启新阶段，记录起止时间、数据行、速度、转向角和铰接角；
- 同时记录大纲中的正交转弯五相 `IDLE / ENTRY / MID / EXIT / DONE` 及切换事件；
- 导出与当前工况共用时间戳的 `human_phase_log_YYYYMMDD_HHMMSS.csv`；
- 加载 M2 导出的本地 `human_scenario_*.csv`，检查关键字段并显示明确错误；
- Replay 支持播放、暂停、停止回到开头、进度拖动以及 `0.5x / 1x / 2x` 倍速；
- 回放直接使用 CSV 中的 A/B/H/T、航向、车速、转向角和铰接角，不重新积分，也不会写入 M2 驾驶记录；
- 人工驾驶与 Replay 相互隔离；重置会停止并清除 Replay、主 CSV 记录和 phase_log。

## M4 Electron 开发入口

- 新增独立主进程入口 `human-desktop-main.js`；
- `npm.cmd run human:dev` 打开“人工驾驶仿真软件”桌面窗口；
- 优先加载 `human-driving-simulator/人工驾驶仿真软件.html`，仅在该文件不存在时回退到旧的 `index.html`；
- PID 桌面版仍由原来的 `desktop-main.js` 和 `desktop:dev` 启动；
- 网页版和桌面版复用同一份 HTML，因此 M1/M2/M3 逻辑保持一致。

## 网页版打开方法

直接双击 `human-driving-simulator/人工驾驶仿真软件.html`，使用 Chrome、Edge 或其他现代浏览器打开即可。无需启动服务器，也无需安装依赖。

建议先保留默认参数，点击“开始驾驶”，再把焦点留在当前页面中进行操作。

## Electron 桌面版开发模式

在项目根目录打开 PowerShell 或命令提示符，首次使用先安装依赖：

```powershell
npm.cmd install
```

安装完成后，可以直接双击项目根目录中的：

```text
启动人工驾驶仿真软件.bat
```

BAT 会以自身所在目录作为项目根目录，检查 Node.js、`npm.cmd` 和 `node_modules`，然后执行 `npm.cmd run human:dev`。如果环境未安装完整或启动失败，窗口会保留并显示中文错误提示。

启动人工驾驶桌面版：

```powershell
npm.cmd run human:dev
```

原 PID 工况仿真导出器桌面版仍使用：

```powershell
npm.cmd run desktop:dev
```

PID 桌面版原有的一键启动脚本仍是：

```text
启动PID工况导出器.bat
```

可选打包命令已配置为：

```powershell
npm.cmd run human:pack
```

`human:pack` 当前只作为后续打包入口，本阶段不要求打包成功，也不需要执行。驾驶测试仍建议先切换到英文输入法（EN）。

## CSV 记录与导出

1. 切换到英文输入法（EN）。
2. 点击“开始驾驶”；程序立即记录初始帧，并在每个固定时间步追加一行。
3. 使用 WASD 完成人工驾驶。
4. 点击“结束驾驶”。
5. 检查“CSV 数据状态”中的行数、最近一行和预览。
6. 点击“导出 CSV”，浏览器会下载 `human_scenario_YYYYMMDD_HHMMSS.csv`。

CSV 字段顺序：

```text
time_s,dt_s,v_input_mps,l_m,l_h_m,L_m,width_m,phi_max_rad,
theta_ref_rad,theta_ref_deg,theta_rad,theta_deg,theta_t_rad,theta_t_deg,
alpha_rad,alpha_deg,phi_rad,phi_deg,e_theta_rad,e_phi_rad,
xA_m,yA_m,xB_m,yB_m,xH_m,yH_m,xT_m,yT_m,accel_mps2
```

- `rad` 字段单位为弧度，`deg` 字段单位为角度；
- 坐标单位为 m，速度单位为 m/s，加速度单位为 m/s²；
- `v_input_mps` 是当前帧真实车速，`accel_mps2` 是当前帧实际加速度；
- 人工驾驶没有参考航向，因此 `theta_ref_rad = theta_rad`、`theta_ref_deg = theta_deg`；
- `e_theta_rad = 0`、`e_phi_rad = 0`；
- 额外的 `accel_mps2` 位于原 PID 兼容字段之后，现有按字段名读取的工具可以忽略该列。

## MATLAB / CSV 读取验证

### 直接使用 readtable

下面的示例读取人工驾驶 CSV 的时间、车速、转向角、铰接角和 A/B/H/T 坐标，并绘制 B 点轨迹：

```matlab
csv_path = fullfile('alpha一阶保持仿真', 'scenarios', ...
    'human_scenario_YYYYMMDD_HHMMSS.csv');
data = readtable(csv_path);

t = data.time_s;
v = data.v_input_mps;
alpha_deg = data.alpha_deg;
phi_deg = data.phi_deg;

A = [data.xA_m, data.yA_m];
B = [data.xB_m, data.yB_m];
H = [data.xH_m, data.yH_m];
T = [data.xT_m, data.yT_m];

fprintf('读取 %d 行，时间 %.2f–%.2f s，最大车速 %.3f m/s。\n', ...
    height(data), t(1), t(end), max(v));

figure('Name', '人工驾驶 B 点轨迹');
plot(B(:, 1), B(:, 2), 'LineWidth', 1.8);
grid on;
axis equal;
xlabel('x_B / m');
ylabel('y_B / m');
title('human\_scenario：牵引车后轴 B 点轨迹');
```

人工驾驶没有独立参考航向，因此每行满足：

```text
theta_ref_rad = theta_rad
theta_ref_deg = theta_deg
e_theta_rad = 0
e_phi_rad = 0
```

### 使用 load_pid_scenario

当前仓库的函数签名为：

```matlab
scenario = load_pid_scenario(csv_path)
```

`csv_path` 可以是完整路径，也可以是加载器同级 `scenarios/` 目录中的文件名；省略参数时会打开文件选择框。推荐流程：

1. 将 `human_scenario_*.csv` 复制到加载器所在方案目录的 `scenarios/`。
2. 进入该方案目录并按文件名读取。
3. 从返回结构的 `inputs / states / points` 分组访问数据。

当前仓库已将原来的 `Matlab/` 方案目录重组为多个 alpha 预测方案。因此基线加载器的实际推荐目录是：

```text
alpha一阶保持仿真/scenarios/
```

旧版目录布局或仍使用 `Matlab/load_pid_scenario.m` 的副本时，对应目录就是 `Matlab/scenarios/`。加载器始终根据自身文件位置查找同级 `scenarios/`，不依赖当前工作目录。

示例：

```matlab
cd('alpha一阶保持仿真');
scenario = load_pid_scenario('human_scenario_YYYYMMDD_HHMMSS.csv');

t = scenario.time_s;
v = scenario.inputs.v_mps;
alpha_deg = scenario.inputs.alpha_deg;
phi_deg = scenario.inputs.phi_deg;
A = scenario.points.A;
B = scenario.points.B;
H = scenario.points.H;
T = scenario.points.T;

figure('Name', 'load\_pid\_scenario：B 点轨迹');
plot(B(:, 1), B(:, 2), 'LineWidth', 1.8);
grid on;
axis equal;
xlabel('x_B / m');
ylabel('y_B / m');
```

### 兼容性结论

`load_pid_scenario.m` 要求 25 个核心字段。人工驾驶导出的 29 列包含全部核心字段，并额外提供：

- `phi_max_rad`：加载器识别并写入 `scenario.params.phi_max_rad`；
- `e_theta_rad`、`e_phi_rad`：保留 PID 同格式语义；
- `accel_mps2`：额外加速度列，`readtable` 会保留，加载器可安全忽略。

因此 `human_scenario` 在字段和读取结构上兼容 `load_pid_scenario.m`，无需修改加载器或 CSV 表头。仓库中的 `run_phase1_demo.m` 也能通过该加载器读取人工驾驶 CSV。

需要注意：`run_phase1_demo` 的严格 `< 1 mm` 重积分门控最初针对 PID 导出器的采样时序设计，假定第 `k` 行输入用于推进第 `k → k+1` 个区间。人工驾驶 CSV 记录的是每次固定步完成后的当前状态与当前输入；在油门或转向持续变化时，可能出现一个采样步的输入对齐差异。因此“成功读取”代表格式兼容，但人工驾驶数据不保证直接通过该 PID 专用的 1 mm 重积分门控。

### M4-3 下游兼容性实测

已使用相对路径 `scenarios/human_scenario_20260803_091503.csv` 完成一次 MATLAB 下游链路实测，结果如下：

- `readtable` 成功读取，共 1655 行、29 个字段，表头完整；
- `load_pid_scenario` 成功加载并生成分组后的 `scenario` 结构；
- `run_phase1_demo('scenarios/human_scenario_20260803_091503.csv')` 成功运行；
- demo 完成轨迹回放、误差报告和三层扫掠预测，并生成三幅图和 `summary.txt`；
- demo 最终完成，但未通过 PID 专用的 `< 1 mm` 重积分门控。

实测最大误差：

| 状态量 | 最大误差 |
|---|---:|
| `xB` | 0.071541 m |
| `yB` | 0.106706 m |
| `theta` | 0.012228 rad |
| `phi` | 0.009619 rad |

位置最大误差约为 106.7055 mm。该结果应分为三个层次理解：

1. **可读取**：29 列 CSV 与 `readtable`、`load_pid_scenario` 的字段接口兼容；
2. **可运行**：`run_phase1_demo` 可以完成现有 MATLAB 回放、报告、绘图和预测流程；
3. **未通过 PID 1 mm 门控**：该门控验证的是 PID 导出采样时序下的严格重积分一致性，不等同于人工驾驶 CSV 的格式或下游接口是否有效。

因此，人工驾驶 CSV 可以用于 MATLAB 下游链路联调、数据结构验证、轨迹可视化和预测流程测试，但不应把 `run_phase1_demo` 的 `< 1 mm` PID 专用门控作为人工驾驶 CSV 的严格通过标准。

本次 `predict_swept` 运行期间出现了 `polyshape` 空多边形警告，表示部分预测帧可能生成退化或空的预测多边形。警告没有阻止 demo 完成；但在后续正式接入目标判内、风险分级或报警算法前，需要进一步定位对应帧并检查多边形顶点、车速、转向角和几何退化条件。

## phase_log 记录与导出

1. 点击“开始驾驶”，phase_log 与主工况 CSV 同时开始记录。
2. 驾驶过程中可在“phase_log 状态”查看当前阶段、阶段数量、持续时间和最近阶段。
3. 点击“结束驾驶”关闭最后一个阶段。
4. 点击“导出 phase_log”下载日志。无阶段数据时页面会提示“暂无 phase_log 可导出”。

主工况与阶段日志复用同一时间戳，例如：

```text
human_scenario_20260802_153000.csv
human_phase_log_20260802_153000.csv
```

phase_log 字段：

```text
phase_id,phase_name,start_time_s,end_time_s,duration_s,start_row,end_row,
start_v_mps,end_v_mps,start_alpha_deg,end_alpha_deg,start_phi_deg,end_phi_deg,note,
time_s,phase,event,alpha_deg,phi_deg,heading_delta_deg
```

前 14 个字段描述人工驾驶控制阶段；后 6 个字段兼容大纲中的正交路口相位日志。其中 `phase` 为 `IDLE / ENTRY / MID / EXIT / DONE`，`event` 包括 `FIRST_ENTRY / ENTER_MID / ENTER_EXIT / ENTER_DONE`。

## Replay 使用方法

1. 确保当前没有正在进行的人工驾驶。
2. 在 Replay 区点击“加载 CSV”，选择 M2 导出的 `human_scenario_YYYYMMDD_HHMMSS.csv`。
3. 加载成功后核对文件名、行数和起止时间。
4. 点击“播放”，可使用暂停、停止/回到开头、进度条和倍速选择。
5. HUD、车辆、挂车、A/B/H/T、B 点轨迹会显示当前回放帧。
6. 缺少关键字段、数值无效或时间倒序时，页面显示错误且不会崩溃。

Replay 只读本地文件，不上传数据，不修改已存在的 M2 记录。加载 Replay 后如需重新人工驾驶，请点击“重置”。

## WASD 控制

推荐使用英文输入法（EN）进行驾驶测试。中文输入法/IME 可能拦截 W/A/S/D，导致按键不响应；中文输入法下方向键也不保证稳定。如果按键无效，请先切换到英文输入法，然后点击画布再测试。

| 按键 | 功能 | 行为 |
|---|---|---|
| W | 油门 | 按住时油门为 1，车辆加速 |
| S | 刹车 | 按住时制动为 1，只减速、不倒车 |
| A | 左转 | α 按设定转向速率向正方向变化 |
| D | 右转 | α 按设定转向速率向负方向变化 |

方向键仍保留为备用尝试：`↑` 等同 W、`↓` 等同 S、`←` 等同 A、`→` 等同 D；但 M1 操作与演示推荐统一使用英文输入法下的 WASD。

输入法限制不影响 M1 的车辆运动学、HUD、轨迹绘制，也不影响后续 CSV 的字段和数据结构。M1 验收以英文输入法下 WASD 能正常控制车辆为准；Caps Lock 开启或关闭均不影响验收。

- 松开 A/D 后，α 按 `returnRateDeg` 自动回到 0。
- A 与 D 同时按下时视为无转向输入并回正。
- W 与 S 同时按下时采用刹车优先。
- 浏览器窗口失去焦点时会释放所有按键，防止按键状态卡住。

## 当前未实现

- 目标点导入与在线判警：属于 M4/可选扩展；
- TTC 与盲区风险算法：属于后续功能；
- 人工驾驶桌面版的正式安装包、签名和发布流程尚未实现。

## M1 测试清单

- [ ] 直接双击 HTML 后页面正常显示，无外部资源加载错误；
- [ ] 默认参数下点击“开始驾驶”，HUD 状态变为“驾驶中”；
- [ ] 切换到英文输入法（EN）后，W/A/S/D 均可正常控制；
- [ ] Caps Lock 开启和关闭时，英文输入法下 WASD 均可正常控制；
- [ ] 若按键无效，先切换到英文输入法，再点击画布重试；
- [ ] 中文输入法下方向键只作为备用尝试，不列入 M1 验收要求；
- [ ] 输入法限制不影响车辆运动学、HUD、轨迹绘制和后续 CSV 数据结构；
- [ ] 按住 W 后速度增加，松开后受阻力逐渐下降；
- [ ] 按住 S 后车辆减速，速度不会低于 0；
- [ ] 同时按 W 和 S 时制动优先；
- [ ] 按 A 时 α 为正、车辆逆时针左转；
- [ ] 按 D 时 α 为负、车辆顺时针右转；
- [ ] 松开 A/D 后 α 自动回正；
- [ ] α 与 φ 均不超过配置限幅；
- [ ] Canvas 中 A/B/H/T 位置、牵引车与挂车姿态连续变化；
- [ ] B 点轨迹不会在每帧刷新时被清除；
- [ ] 离开浏览器窗口后 WASD 状态被释放；
- [ ] 点击“结束驾驶”后时间和车辆状态停止更新；
- [ ] 点击“重置”后参数和车辆状态恢复默认值。

## M2 测试清单

- [ ] 点击“开始驾驶”后记录行数从 1 开始增长；
- [ ] 英文输入法下 W/S/A/D 控制仍然正常；
- [ ] 最近一行的时间、速度、α、φ 与 HUD 对应；
- [ ] 点击“结束驾驶”后行数停止增长，但仍可导出；
- [ ] 点击“重置”后记录行数归零；
- [ ] 无数据时点击“导出 CSV”会显示明确提示；
- [ ] 导出文件名符合 `human_scenario_YYYYMMDD_HHMMSS.csv`；
- [ ] CSV 第一行与本文列出的 29 列字段顺序完全一致；
- [ ] CSV 包含初始帧和多行驾驶数据；
- [ ] `theta_ref` 等于同一行 `theta`，两个误差字段均为 0；

## M3 测试清单

- [ ] 开始驾驶后 phase_log 当前阶段和持续时间实时更新；
- [ ] 分别使用 W、S、A、D 及松键滑行，阶段按预期切换；
- [ ] 结束驾驶后最后阶段被关闭，导出文件含表头和多行阶段；
- [ ] scenario CSV 与 phase_log 文件名使用相同时间戳；
- [ ] 重置后主记录、phase_log 和 Replay 状态均被清空；
- [ ] Replay 能加载刚导出的 M2 CSV，显示文件名、行数、时间范围和当前帧；
- [ ] 播放、暂停、停止回到开头、进度拖动和 0.5x/1x/2x 正常；
- [ ] Replay 画面使用 CSV 中的 A/B/H/T，并随帧更新 HUD 和轨迹；
- [ ] Replay 期间 M2 记录行数不增加；
- [ ] 缺少任一关键字段的 CSV 会显示错误，页面仍可继续操作；
- [ ] 英文输入法下 M1 的 WASD、回正、运动学、HUD 和画布仍正常；
- [ ] M2 主 CSV 的 29 列字段及顺序保持不变。

## M4 Electron 开发模式测试清单

- [ ] 首次使用前在项目根目录执行 `npm.cmd install`；
- [ ] 双击 `启动人工驾驶仿真软件.bat` 后出现人工驾驶桌面窗口；
- [ ] 临时缺少 `node_modules` 时，BAT 显示安装提示并等待确认，不直接关闭；
- [ ] 在项目根目录运行 `npm.cmd run human:dev` 后出现独立桌面窗口；
- [ ] 窗口标题为“人工驾驶仿真软件”，页面内容来自新的中文 HTML 入口；
- [ ] 切换英文输入法（EN）后，W/S/A/D 驾驶与自动回正正常；
- [ ] `human_scenario_*.csv` 可以导出并包含 M2 的 29 列表头；
- [ ] `human_phase_log_*.csv` 可以导出且与主 CSV 时间戳对应；
- [ ] Replay 可以加载 CSV，并完成播放、暂停和停止；
- [ ] 重置会清空驾驶记录、phase_log 和 Replay；
- [ ] PID 一键启动仍使用原 `启动PID工况导出器.bat`；
- [ ] `npm.cmd run desktop:dev` 仍能启动原 PID 桌面版。

## 运动学一致性

M1 使用的核心方程与项目 MATLAB `kinematics_step.m` 保持一致：

```text
omega1 = v * sin(alpha) / l
vB     = v * cos(alpha)
omega2 = (vB * sin(phi) + l_h * omega1 * cos(phi)) / L
dphi   = omega1 - omega2
```

其中 `l_h * omega1 * cos(phi)` 为必须保留的鞍座偏置耦合项。所有内部角度使用弧度，HUD 再转换为角度显示。
