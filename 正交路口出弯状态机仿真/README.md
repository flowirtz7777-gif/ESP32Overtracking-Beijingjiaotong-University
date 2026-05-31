# 正交路口出弯状态机仿真

基于 `alpha一阶保持仿真` 的独立实验分支。

## 目的

验证一种新的在线预测策略：

```text
十字正交路口转弯
→ 用航向累计角 + alpha/phi 辅助量识别出弯阶段
→ 出弯阶段扩大 PolyW / PolyA / PolyI 预测时间窗
→ alpha 仍保持一阶保持，不引入 alpha 外推
```

该分支用于讨论 R3 类出弯目标报警偏晚问题，不直接替代主程序。

## 状态机

`orthogonal_turn_phase.m` 输出：

```text
0 IDLE   未转弯
1 ENTRY  入弯
2 MID    转弯中
3 EXIT   出弯
4 DONE   转弯结束
```

当前没有真实转向灯输入，暂用 `|alpha| > 2°` 作为开始转弯触发。进入 EXIT 的主要依据：

```text
累计航向变化 >= 75°
并且 alpha 正在回正 或 phi 仍有滞后
```

状态机含简单计数滞回，避免阈值附近抖动。

## 预测窗口策略

普通阶段：

```text
PolyW = 2.0 s
PolyA = 1.0 s
PolyI = 0.3 s
```

EXIT 出弯阶段：

```text
PolyW = 3.0 s
PolyA = 1.5 s
PolyI = 0.5 s
```

安全膨胀接口已在 `run_phase1_demo.m` 中预留但注释掉，当前不启用：

```matlab
% if keyframe_phase(ii) == 3
%     polys.W{ii} = inflate_poly(polys.W{ii}, 0.30);
%     polys.A{ii} = inflate_poly(polys.A{ii}, 0.20);
% end
```

## 固定目标集 CSV

`run_phase1_demo` 支持第二个参数作为固定目标集：

```matlab
out = run_phase1_demo('pid_scenario_20260530_020804.csv', 'targets_exit.csv');
```

目标 CSV 支持列名：

```text
x,y
x_m,y_m
target_x_m,target_y_m
```

若只传文件名，会优先从本文件夹 `targets/` 下寻找。

如果不传第二个参数，程序会弹出文件选择框，要求选择固定目标集 CSV。此分支不再允许自动生成目标点，因为自动目标会导致 R2/R3/R4 含义漂移，无法做跨方案对比。

本文件夹内置一个示例目标集：

```text
targets/canonical_R1_R5.csv
```

## 验收重点

1. 固定 canonical R3 或出弯目标集，不再自动换目标。
2. 检查 EXIT 首次触发时间是否早于 R3 风险窗口。
3. 比较扩大窗口前后 PolyW / PolyA / PolyI 首次命中时间。
4. 若仍晚报，优先排查 `polyshape` 后处理是否误删包含目标的小 region。

## 命中日志

每次运行会在结果目录额外输出：

```text
04_hit_log.csv
```

日志已改为接近 `TTC预警复盘软件` 的报警日志格式：一行只表示一个事件，前 5 列固定为：

```text
time_s,target,risk,ttc_s,event
```

后续列补充：

```text
phase,source,x_m,y_m,true_contact_time_s,lead_s,
hit_PolyW,hit_PolyA,hit_PolyI,hit_BodyNow_keyframe
```

主要事件含义：

- `TRUE_CONTACT`：目标中心点被逐帧真值 `BodyNow` 首次覆盖，即实际接触时间。
- `NO_CONTACT`：该目标在整段真值轨迹中没有实际接触。
- `FIRST_POLYW` / `FIRST_POLYA` / `FIRST_POLYI`：目标首次进入对应预测扫掠窗口。
- `NO_POLYW_HIT` / `NO_POLYA_HIT` / `NO_POLYI_HIT`：对应窗口全程未命中。
- `FIRST_BODYNOW_KEYFRAME`：目标在仿真关键帧中首次进入当前车身占用区。
- `FRAME_HIT`：每个命中关键帧的详细记录，`source` 会用 `PolyW|PolyA|PolyI|BodyNow_keyframe` 标出命中来源。

`ttc_s` 和 `lead_s` 在本离线日志里均表示相对真实接触的提前量：`true_contact_time_s - time_s`。若目标没有真实接触或该层未命中，则为空值。
