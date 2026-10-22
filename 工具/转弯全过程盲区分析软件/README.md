# 转弯全过程盲区分析软件

用于分析半挂车右转全过程中，哪些右侧扫掠边界点在报警时已经没有充足反应时间。

## 当前研究入口（2026-10-14）

此前`自动化批量实验/`全部旧轮次按用户要求封存，保留原路径和只读文件，完整快照及校验清单位于`实验封存/2026-10-14/`。
新实验从[科研实验_2026-10-14/实验总计划.md](科研实验_2026-10-14/实验总计划.md)重新开始；当前仅制定计划，尚未启动新实验。
先做可控车速/转向输入、独立真值和目标集验收，再比较核心方法、驾驶因素和二级处理联合效果。
以下2026-10-13实验入口和结果描述为历史记录，不应作为当前续跑指令。

## 转向预测实验更新（2026-10-13）

网页与MATLAB复算现支持hold、linear、quad、union、fan五种转向预测，新增因果滤波、回正速率、
扇形速率/分支数及限幅参数。union回正到零后停止，多分支扫掠分别取OR，不连成跨分支多边形。
默认目标上限改为7000、采样间距0.1米；可导入冻结目标，旧700点文件及历史实验保留。
非hold模式禁用旧大多边形参考显示，只显示与统计一致的逐段并集。

旧实验入口为`自动化批量实验/steering_experiment/运行转向方式实验.bat`，冻结方案见该目录
`实验计划.md`。25组主比较、55组单因素敏感性、10组独立固定反例；结果及检查点都在该目录。
安全膨胀仍未实现，不能开启；现有静态点指标不是实车安全证明。

## 当前评价范围（2026-10-13更新）

批量CFG对比入口：`自动化批量实验/运行CFG批量实验.bat`，说明见该目录`README.md`。
脚本通过当前网页真实导入/导出入口运行，支持参数网格、多个工况、固定目标及恢复执行。

首次接触边缘标记为`FRONT`的挂车前沿点全部排除评价，统一记录为
`FRONT_CONTACT_IGNORED`（前沿忽略），不计入漏报、晚报、反应充足或相应比例的分母。
前沿忽略优先于起始截断；右侧、角点和其他非前沿样例保持原判定，负样本误报统计不变。
网页摘要显示忽略数量，风险图和实时目标命中数不显示或计入被忽略点。
MATLAB校验、阈值扫描和过滤图采用相同范围。内部采样点不按来源一概删除。

目标坐标、真实接触时间和原始预测命中时间仍保留在导出日志中；旧CSV和历史结果不覆盖。
此调整是评价范围变化，不是预测能力提升，也不代表已实现完整车身碰撞预警。

## 盲区定义

本工具中的“盲区”不是单纯的静态视觉不可见区域，而是一个时间安全概念：

```text
盲区点 = 在线预测首次报警时，距离真实接触已经没有充足反应时间的点。
```

当前以 `lead_W = true_contact_time_s - first_PolyW_s` 作为提前量。若：

```text
lead_W < reaction_threshold_s
```

则记为：

```text
BLINDSPOT_REACTION_INSUFFICIENT
```

`reaction_threshold_s` 的具体取值仍待定义；界面当前默认使用 `1.0 s` 作为分析阈值，后续可按驾驶员反应时间、制动延迟、车速和比赛/论文口径再确定。

## 核心口径

- 边界测试点由整段 CSV 真值轨迹离线生成，只作为固定靶标。
- 判警过程只使用当前帧状态、当前 `alpha`、当前 `v` 做短时 PolyW/A/I 在线预测。
- 默认不启用 EXIT 扩窗，不启用安全膨胀，用于观察原始一阶保持 Poly 在全过程哪些点反应时间不足。
- 由于测试点常放在扫掠边界线上，判内默认使用 `0.05 m` 几何容差：点在多边形内部，或距离多边形边界不超过 5 cm，均视为命中。
- 默认将 `t < 2.0 s` 的起始截断点单独标为 `STARTUP_TRUNCATED`。这些点没有仿真开始前的历史预测窗口，应单独解释。

## 启动方式

```text
双击 启动转弯全过程盲区分析软件.bat
```

或者直接用浏览器打开：

```text
index.html
```

## CSV

界面提供：

- `导入固定目标点 CSV`
- `导出当前目标点 CSV`
- `导出 CSV`：导出当前盲区分析日志
- `按当前参数刷新分析`：导入固定目标点后，修改反应时间阈值、判内容差、起始截断等参数，再点击此按钮重新计算并刷新图表。
- `导入策略 CFG / JSON`：导入在线状态机和分状态预测窗口配置。
- `导出当前 CFG`：保存当前策略配置，桌面模式下写入 `CFG配置/`。

桌面软件模式下，导出路径固定为：

```text
E:\大创内轮差项目\工具\转弯全过程盲区分析软件\目标点CSV
E:\大创内轮差项目\工具\转弯全过程盲区分析软件\边界点盲区日志
E:\大创内轮差项目\工具\转弯全过程盲区分析软件\CFG配置
```

若直接用浏览器打开 `index.html`，由于浏览器不能直接写入固定本地目录，会退回普通下载。

场景 CSV 只应包含车辆运动与车辆参数相关信息，不应混入目标点。目标点 CSV 是独立输入；切换场景 CSV 或点击 `使用内置示例工况` 时，软件会保留已导入的目标点，并按新的车辆轨迹重新估计目标首次接触时刻和报警结果。

目标点 CSV 支持列名：

```text
x_m,y_m
x,y
target_x_m,target_y_m
```

可选列：

```text
target
true_contact_time_s
true_contact_idx
contact_phase
sampling_spacing_m
tolerance_m
max_boundary_points
warmup_ignore_s
```

若没有 `true_contact_time_s / true_contact_idx`，软件会根据当前场景轨迹自动估计目标首次接触帧。

导入目标点 CSV 时，软件会自动读取并回填以下界面配置：

```text
sampling_spacing_m    -> 采样间距
tolerance_m           -> 判内容差
max_boundary_points   -> 最大边界点数
warmup_ignore_s       -> 忽略起始截断
```

反应时间阈值 `reaction_threshold_s` 不属于目标点 CSV，目前仍保留为界面分析参数，需要手动设置。

日志字段接近 TTC 报警日志格式：

```text
time_s,target,risk,ttc_s,event,phase,state,source,hit_method,cfg_name,T_h_W_s,T_h_A_s,T_h_I_s,dt_pred_s,alpha_mode,safety_expand_m,safety_expand_enabled,x_m,y_m,true_contact_time_s,lead_s
```

主要事件：

```text
BLINDSPOT_REACTION_INSUFFICIENT  盲区点，报警时反应时间不足
REACTION_TIME_SUFFICIENT         反应时间充足
POLYW_NO_HIT                     PolyW 未命中
STARTUP_TRUNCATED                起始截断点
```

在线判定命中方法为 `segment_swept`：软件将预测窗口拆成相邻时刻右边缘形成的小扫掠四边形逐段判内，而不是把整个预测窗口拼成一个大多边形后一次性判内。这样扩展预测时间窗只会增加后续小扫掠段，避免长窗口多边形自交导致“扩窗反而漏报”的非单调问题。

在线预测区图提供“预测区显示模式”开关：

```text
segment_swept 判定区  默认模式，逐段绘制真正参与日志/统计判定的小扫掠四边形
Poly 大多边形参考     保留旧的大 Poly 可视化，用于观察整体轮廓
```

两种模式都会同步切换图内实时命中点的口径；盲区日志与数量始终以 `segment_swept` 为准。

## 策略 CFG

CFG 是 JSON 文件，用来定义在线状态机和不同状态下的预测策略。导入 CFG 后，软件会重新计算 `IDLE / ENTRY / MID / EXIT / DONE` 状态，并在刷新分析时按状态选择 PolyW/A/I 时间窗。

最小示例见：

```text
CFG配置/default_exit_window_cfg.json
```

核心结构：

```json
{
  "name": "default_exit_window_cfg",
  "state_machine": {
    "alpha_start_deg": 2.0,
    "mid_heading_delta_deg": 25.0,
    "exit_heading_delta_deg_min": 75.0,
    "exit_require_alpha_returning": true,
    "exit_phi_abs_deg_min": 4.0,
    "exit_hold_frames": 2
  },
  "strategies": {
    "default": {
      "T_h_W": 2.0,
      "T_h_A": 1.0,
      "T_h_I": 0.3,
      "dt_pred": 0.02,
      "alpha_mode": "hold",
      "safety_expand_m": 0.0,
      "safety_expand_enabled": false
    },
    "EXIT": {
      "T_h_W": 3.0,
      "T_h_A": 1.5,
      "T_h_I": 0.5,
      "dt_pred": 0.02,
      "alpha_mode": "hold",
      "safety_expand_m": 0.0,
      "safety_expand_enabled": false
    }
  }
}
```

注意：当前版本已经记录 `safety_expand_m / safety_expand_enabled`，但暂不启用几何膨胀；这是为后续策略评估预留的字段。`alpha_mode` 目前也只实现 `hold`，用于保持和主算法一致。

## MATLAB 校验

用 MATLAB 校验网页端判定：

```matlab
cd('E:/大创内轮差项目/工具/转弯全过程盲区分析软件')
report = validate_turn_exit_targets( ...
    'C:/path/to/pid_scenario.csv', ...
    'C:/path/to/turn_boundary_targets.csv', ...
    'C:/path/to/turn_boundary_log.csv');
```

若只想复算 MATLAB 版命中结果，也可以省略第三个参数：

```matlab
report = validate_turn_exit_targets('C:/path/to/pid_scenario.csv', 'C:/path/to/targets.csv');
```

第四个参数可选，用于指定 MATLAB 校验的判内容差，默认 `0.05 m`。第五个参数可选，用于指定起始截断忽略时间，默认 `2.0 s`：

```matlab
report = validate_turn_exit_targets(scenario_csv, target_csv, '', 0.05, 2.0);
```

第六个参数可选，用于指定策略 CFG。若传入 CFG，MATLAB 校验会使用与网页一致的状态机、分状态预测窗口和 `segment_swept` 命中口径：

```matlab
report = validate_turn_exit_targets(scenario_csv, target_csv, '', 0.05, 2.0, ...
    'E:/大创内轮差项目/工具/转弯全过程盲区分析软件/CFG配置/exit_window_test_cfg.json');
```

校验脚本使用 `工具/正交路口出弯状态机仿真/predict_swept.m`，包含 MATLAB `polyshape` 后处理，因此它应作为网页端轻量 JS 预测的裁判。输出位于：

```text
logs/matlab_validate_*/matlab_validation_log.csv
logs/matlab_validate_*/matlab_validation_summary.csv
logs/matlab_validate_*/web_vs_matlab_compare.csv
```

## 阈值扫描

用于统计不同反应时间阈值下，哪些边界点会被定义为盲区：

```matlab
cd('E:/大创内轮差项目/工具/转弯全过程盲区分析软件')
out = scan_ttc_threshold_blindspots();
```

如需用指定 CFG 扫描：

```matlab
opts = struct();
opts.strategy_cfg_json = 'E:/大创内轮差项目/工具/转弯全过程盲区分析软件/CFG配置/exit_window_test_cfg.json';
out = scan_ttc_threshold_blindspots('C:/path/to/pid_scenario.csv', opts);
```

当前默认参数：

```text
sampling_spacing_m = 0.1
tolerance_m = 0.05
max_boundary_points = 2000
warmup_ignore_s = 2.0
thresholds_s = 0.1:0.1:3.0
T_h_W = 2.0
dt_pred = 0.02
```

输出位于：

```text
logs/threshold_scan_*/
```

主要文件：

```text
threshold_scan_points.csv
threshold_scan_counts.csv
threshold_blindspot_overlay.png
```

叠加图颜色口径：越小的阈值越红/橙，表示更紧迫；只有在较高阈值下才出现的点偏蓝/紫。黑色 `x` 表示 `POLYW_NO_HIT`，浅灰点表示 `STARTUP_TRUNCATED`。

如需生成去掉高阈值点后的筛选图：

```matlab
out = plot_threshold_filtered_blindspots('C:/path/to/logs/threshold_scan_xxx', [2.0 1.5 1.0]);
```

会生成：

```text
threshold_blindspot_overlay_le_2.0s.png
threshold_blindspot_overlay_le_1.5s.png
threshold_blindspot_overlay_le_1.0s.png
```

> 2026-10-13 几何更新：默认逐段判定及对应显示已将每一步端点构造改为局部凸包，以避免相邻边缘交叉时的偶奇漏区。MATLAB核验、阈值扫描和正交状态机使用同样处理；新日志 `hit_method=segment_convex_union`。保留的“Poly大多边形参考”显示模式仍为旧轮廓参考，不应用于新版几何评价。该模式下实时点着色也仍为参考口径，统计日志使用新版逐段判定。
>
> 网页几何回归：`node tests/test_geometry.cjs`；可加MATLAB测试输出的 `web_parity_fixtures.json` 作为第二参数，验证跨语言判定。所有历史日志保留，不能混用旧口径与新口径数字。

> 2026-10-13目标集更新：默认使用mixed_v2综合采样（挂车内部、右边缘邻域、核验后的负样本），保留历史边缘模式。首次接触始终在整段当前记录中重算；新增误报、正确排除、结束截断，并按最近接触边缘分组。全挂车占用区与右侧危险区不是同一评价范围，不能把前端未命中都解释为右侧内轮差漏报。
>
> MATLAB生成入口：`generate_evaluation_targets(scene,opts)`；核验入口第七参数为反应阈值；扫描可用`opts.target_csv`冻结同一目标集，`opts.target_mode='boundary'`保留历史采样。详细用法、证据与算法候选见 `../../项目文档/04_使用说明/目标集升级与算法优化路线.md`。本次没有替换默认预测器，也没有启用安全膨胀。

