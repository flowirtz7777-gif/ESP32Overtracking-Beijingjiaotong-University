# CFG 扩窗算法一致性说明

本文记录 `CFG` 状态机扩窗算法在各程序中的统一口径，避免网页、MATLAB、复盘工具各自采用不同判定逻辑。

## 统一算法口径

当前权威口径为：

```text
输入：当前帧 (v, alpha, phi, xB, yB, theta) + CFG
1. 用 CFG state_machine 因果判定 IDLE / ENTRY / MID / EXIT / DONE。
2. 按当前状态选择策略：
   - 非 EXIT：strategies.default
   - EXIT：strategies.EXIT
3. alpha_mode 当前只执行 hold，即 alpha(tau)=alpha_now。
4. safety_expand_m / safety_expand_enabled 只记录，不启用几何膨胀。
5. 统计命中必须使用 segment_swept：
   将预测窗口拆成相邻预测步右边缘形成的小扫掠四边形逐段判内。
```

`segment_swept` 的原因：整段预测窗口拼成一个大 Poly 后，长窗口可能自交或退化，导致 3s 扩窗反而漏掉 2s 已覆盖点，破坏扩窗单调性。逐段扫掠只会随时间窗增加更多小四边形，因此扩窗结果应满足首报不晚于默认策略。

`转弯全过程盲区分析软件/index.html` 的在线预测区已经加入显示模式开关：

```text
segment_swept 判定区  默认，逐段绘制真正参与日志/统计判定的小扫掠四边形
Poly 大多边形参考     旧版大 Poly 轮廓，仅作可视化参考
```

实时命中点也跟随该开关切换口径；日志与盲区数量始终使用 `segment_swept`。

## 必须统一的程序

| 程序 | 角色 | 当前口径 |
|---|---|---|
| `转弯全过程盲区分析软件/index.html` | 主分析软件 | 已使用 CFG 状态机、分状态窗口、`segment_swept` 统计命中 |
| `转弯全过程盲区分析软件/validate_turn_exit_targets.m` | MATLAB 校验裁判 | 已支持第 6 参数 `strategy_cfg_json`，并使用 `segment_swept` |
| `转弯全过程盲区分析软件/scan_ttc_threshold_blindspots.m` | 阈值扫描工具 | 已支持 `opts.strategy_cfg_json`，并使用 `segment_swept` |
| `正交路口出弯状态机仿真/run_phase1_demo.m` | MATLAB 可视化/对照 demo | 已支持第 3 参数 `strategy_cfg_json`；状态机、EXIT 窗口和统计命中均使用同一 CFG + `segment_swept` |
| `正交路口出弯状态机仿真/orthogonal_turn_phase.m` | 正交路口状态机 | 已支持第 5 参数 `state_machine`，默认值与 CFG 口径对齐 |
| `CFG配置生成器/index.html` | CFG 生成工具 | 只生成配置，不参与判定；字段必须与主分析软件一致 |

## 可视化参考程序

| 程序 | 角色 | 说明 |
|---|---|---|
| `TTC预警复盘软件/index.html` | 后验 true-TTC 复盘 | 主要用未来真实车身占用计算 TTC；显示的 PolyW/A/I 目前是固定窗口可视化参考，不作为 CFG 扩窗统计裁判 |
| `alpha一阶保持仿真/truck_slider_sim.py` | Python TTC 复盘 | 主要用于 true-TTC 复盘和交互查看；若后续要比较 CFG 扩窗，应迁移同一套 `segment_swept` 判定 |

## 正交路口 demo 的边界

`正交路口出弯状态机仿真/run_phase1_demo.m` 现在已经统一读取 CFG，并且目标统计命中使用 `segment_swept`。MATLAB 图形暂不改成网页端的 `segment_swept / Poly` 双模式开关，仍按关键帧绘制 PolyW/A/I 大多边形作为形状参考；若要产出盲区数量、阈值扫描、跨 CFG 统计结论，仍以 `转弯全过程盲区分析软件/index.html`、`validate_turn_exit_targets.m`、`scan_ttc_threshold_blindspots.m` 的逐帧裁判链为准。

示例：

```matlab
cd('C:/Users/Admin/Desktop/小挑资料/正交路口出弯状态机仿真')
out = run_phase1_demo( ...
    'C:/path/to/pid_scenario.csv', ...
    'C:/path/to/targets.csv', ...
    'C:/Users/Admin/Desktop/小挑资料/转弯全过程盲区分析软件/CFG配置/exit_window_test_cfg.json');
```

## 历史对照程序

以下目录用于 alpha 行为对照或历史方案，不作为当前 CFG 扩窗结论的裁判：

```text
alpha一阶保持仿真/
alpha线性外推仿真/
alpha二阶外推仿真/
alpha多假设并集仿真/
alpha扇形包络仿真/
alpha方案对比/
```

如果未来要把某个历史方案纳入 CFG 对比，必须先补齐：

```text
CFG 状态机读取
分状态 T_h_W / T_h_A / T_h_I / dt_pred
segment_swept 统计命中
日志字段 hit_method / cfg_name / T_h_* / dt_pred
```

## MATLAB 调用示例

校验某个 CFG：

```matlab
cd('C:/Users/Admin/Desktop/小挑资料/转弯全过程盲区分析软件')
report = validate_turn_exit_targets( ...
    'C:/path/to/pid_scenario.csv', ...
    'C:/path/to/targets.csv', ...
    '', ...
    0.05, ...
    2.0, ...
    'C:/Users/Admin/Desktop/小挑资料/转弯全过程盲区分析软件/CFG配置/exit_window_test_cfg.json');
```

阈值扫描使用 CFG：

```matlab
opts = struct();
opts.strategy_cfg_json = 'C:/Users/Admin/Desktop/小挑资料/转弯全过程盲区分析软件/CFG配置/exit_window_test_cfg.json';
out = scan_ttc_threshold_blindspots('C:/path/to/pid_scenario.csv', opts);
```
