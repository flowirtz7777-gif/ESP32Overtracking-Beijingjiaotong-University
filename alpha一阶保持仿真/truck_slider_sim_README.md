# truck_slider_sim.py 复盘说明

`truck_slider_sim.py` 是 Phase 1 的 Python 复盘/可视化工具，不是实车在线主判警程序。

## 用途

- 读取 `Matlab/scenarios/pid_scenario_20260530_020804.csv`。
- 用滑动条回放半挂车运动。
- 显示当前时刻由 `(v, alpha, phi)` 预测得到的三层右外缘扫掠窗口：
  - `PolyW`: 2.0 s
  - `PolyA`: 1.0 s
  - `PolyI`: 0.3 s
- 标记 R1-R5 目标中心点，目标不带宽度。
- 用完整 CSV 真值轨迹做后验 TTC 复盘，检查主预测判警是否足够提前。

## 参数与目标点来源

程序启动时会先给出菜单：

```text
1) Use default scenario CSV and MATLAB demo targets
2) Import another scenario CSV
3) Use built-in exporter default simulation
```

车辆参数优先从场景 CSV 表头字段读取：

```text
l_m, l_h_m, L_m, width_m, v_input_mps, phi_max_rad, time_s
```

若选择内置仿真，则使用 `pid工况仿真导出器.html` 当前默认参数：

```text
l=4.0, l_h=1.8, L=13.5, width=2.0, speed=3.0, totalTime=35, dt=0.02
thetaStart=90 deg, thetaEnd=0 deg, t1=3, t2=15
PID gains and limits copied from the exporter defaults
```

随后会询问目标点来源：

```text
1) Use default/demo targets for this scenario
2) Import target CSV
3) Type target centers manually
```

目标 CSV 支持以下任一列名组合：

```text
x,y
x_m,y_m
target_x_m,target_y_m
```

手工输入格式示例：

```text
1.03,9.06; 5.16,24.04; 15.16,34.26
```

当前默认场景的 R1-R5 目标点来自 MATLAB `run_phase1_demo.m` 实际输出，坐标固定为：

```text
R1 (1.034546627,  9.064921825)
R2 (5.165832032, 24.046315542)
R3 (15.162112188, 34.264469347)
R4 (25.335459623, 36.779763982)
R5 (41.480453564, 38.856137380)
```

## 颜色含义

当前 Python 图中的目标颜色按复盘 TTC 显示：

```text
绿色: true TTC >= 2.0 s 或无碰撞
黄色: true TTC < 2.0 s
橙色: true TTC < 1.0 s
红色: true TTC < 0.3 s 或当前已经被挂车车身覆盖
```

这里的 true TTC 是基于已知完整 CSV 轨迹计算的后验量，因此只能用于复盘、验证和找漏报风险，不能直接作为实车在线主算法。

## 与在线主算法的边界

实车在线端没有完整未来真值轨迹，只能使用当前传感器输入 `(v, alpha, phi)` 做短时预测。在线主算法应保持：

```text
1. BodyNow 当前挂车车身占用区命中 => Risk 3
2. 否则用 predict_swept 生成 PolyI / PolyA / PolyW
3. 目标中心点落入 PolyI => Risk 3
4. 目标中心点落入 PolyA => Risk 2
5. 目标中心点落入 PolyW => Risk 1
6. 否则 Risk 0
```

`truck_slider_sim.py` 中的 true TTC 复盘逻辑不要搬到 `ArduinoIDE/risk_eval.{h,cpp}` 作为在线判警替代方案。

## R3 反例

在 `pid_scenario_20260530_020804.csv` 中，R3 位于：

```text
(15.162112188, 34.264469347)
```

后验真值显示挂车车身在约 `16.24 s - 18.12 s` 覆盖 R3。该例用于评估在线 Poly 预测的提前量是否足够，不用于证明在线算法可以知道未来真实轨迹。

## 运行

```powershell
cd C:\Users\Admin\Desktop\小挑资料\Matlab
py truck_slider_sim.py
```

打开图窗后，用底部滑动条控制回放时间；关闭图窗即可退出。
