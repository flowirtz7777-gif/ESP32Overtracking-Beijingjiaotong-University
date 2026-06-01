# alpha 一阶保持仿真

本目录是 alpha 一阶保持策略的 MATLAB / Python 对照分支。

## MATLAB 入口

`run_phase1_demo.m` 支持固定目标集 CSV：

```matlab
cd('C:/Users/Admin/Desktop/小挑资料/alpha一阶保持仿真')

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
