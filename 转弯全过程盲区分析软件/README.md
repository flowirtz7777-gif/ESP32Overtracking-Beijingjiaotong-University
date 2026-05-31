# 转弯全过程盲区分析软件

用于分析半挂车右转全过程中，哪些右侧扫掠边界点在报警时已经没有充足反应时间。

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

桌面软件模式下，导出路径固定为：

```text
C:\Users\Admin\Desktop\小挑资料\转弯全过程盲区分析软件\目标点CSV
C:\Users\Admin\Desktop\小挑资料\转弯全过程盲区分析软件\边界点盲区日志
```

若直接用浏览器打开 `index.html`，由于浏览器不能直接写入固定本地目录，会退回普通下载。

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
```

若没有 `true_contact_time_s / true_contact_idx`，软件会根据当前场景轨迹自动估计目标首次接触帧。

日志字段接近 TTC 报警日志格式：

```text
time_s,target,risk,ttc_s,event,phase,source,x_m,y_m,true_contact_time_s,lead_s
```

主要事件：

```text
BLINDSPOT_REACTION_INSUFFICIENT  盲区点，报警时反应时间不足
REACTION_TIME_SUFFICIENT         反应时间充足
POLYW_NO_HIT                     PolyW 未命中
STARTUP_TRUNCATED                起始截断点
```

## MATLAB 校验

用 MATLAB 校验网页端判定：

```matlab
cd('C:/Users/Admin/Desktop/小挑资料/转弯全过程盲区分析软件')
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

校验脚本使用 `正交路口出弯状态机仿真/predict_swept.m`，包含 MATLAB `polyshape` 后处理，因此它应作为网页端轻量 JS 预测的裁判。输出位于：

```text
logs/matlab_validate_*/matlab_validation_log.csv
logs/matlab_validate_*/matlab_validation_summary.csv
logs/matlab_validate_*/web_vs_matlab_compare.csv
```

## 阈值扫描

用于统计不同反应时间阈值下，哪些边界点会被定义为盲区：

```matlab
cd('C:/Users/Admin/Desktop/小挑资料/转弯全过程盲区分析软件')
out = scan_ttc_threshold_blindspots();
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

