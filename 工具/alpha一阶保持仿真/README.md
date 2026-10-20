# alpha 一阶保持仿真

本目录是 alpha 一阶保持策略的 MATLAB / Python 对照分支。

## MATLAB 入口

`run_phase1_demo.m` 支持固定目标集 CSV：

```matlab
cd('E:/大创内轮差项目/工具/alpha一阶保持仿真')

% 默认：弹出场景 CSV 选择框，目标点自动生成
out = run_phase1_demo();

% 指定场景 CSV，目标点自动生成
out = run_phase1_demo('C:/path/to/pid_scenario.csv');

% 指定场景 CSV + 固定目标集 CSV
out = run_phase1_demo( ...
    'C:/path/to/pid_scenario.csv', ...
    'C:/path/to/targets.csv');
```

目标 CSV 支持以下任一列名组合：

```text
x,y
x_m,y_m
target_x_m,target_y_m
```

若第二个参数只传文件名，程序会优先从本目录 `targets/` 下寻找。

## Python 入口

`truck_slider_sim.py` 是 TTC 后验复盘/可视化工具，运行后会在命令行询问场景来源和目标点来源，其中目标点支持导入 CSV 或手工输入。
> 2026-10-13 几何修正：MATLAB预测区现采用 `segment_convex_union`，对相邻预测时刻的右边缘端点构造局部凸包，并保留全部扫掠片。转向假设、运动学方程和铰接角限幅未改变。
>
> `predict_swept` 返回的N×2矩阵含NaN分隔，各片按OR判定，不再是单个简单多边形。请用 `point_in_poly` 判定、`plot_swept_region` 绘图、`area(swept_polyshape(poly))` 统计并集面积，不能直接使用鞋带公式、偶奇填充或删除NaN。退化线段与点也被保留，边界默认数值容差为1e-9米。
>
> 回归测试入口：相邻 `alpha一阶保持仿真/test_swept_geometry.m`。历史runs不覆盖；旧口径结论须重新实验。局部凸包仅是线性端点插值的保守覆盖，真实连续运动仍需步长收敛验证。

