# CFG批量实验

## 转向方式实验（2026-10-13更新）

五种预测方式已经接入当前网页与MATLAB复算，安全膨胀仍未实现。
专用90组实验、7000点固定目标、方案和启动器在`steering_experiment/`。
本目录原`batch_plan.json`仍保留此前700点窗口比较，便于复现旧实验。
不指定evaluation时，批量脚本当前默认7000点和0.1米间距。

直接调用当前盲区分析网页的真实CFG导入、分析和导出入口，不另写一套预测算法。
软件本身支持CFG导入：左侧下滚到“4. CFG策略”，选择JSON文件。

## 运行

双击本目录的`运行CFG批量实验.bat`。默认自动打开后台Edge，运行内置工况700个固定目标，
比较EXIT阶段W窗口2、3、4秒。不会操作或关闭你正在使用的桌面软件/浏览器。

配置修改在`batch_plan.json`，每次运行会创建独立的`results/run_时间_随机标识/`。
所有相对路径都以实验计划文件所在目录为准。依赖Node.js、Playwright及本机Edge；
启动器优先使用本机Codex已提供的运行环境，不会联网安装依赖。

命令行预检与运行：

```powershell
.\run.ps1 -DryRun -NoPause
.\run.ps1 -Plan .\batch_plan.json -NoPause
.\run.ps1 -Plan .\batch_plan.json -Resume 'results\已有运行目录' -NoPause
```

恢复运行要求计划、生成的CFG、网页代码及输入文件没有变化；成功且结果文件校验通过的任务跳过。
失败会保存错误和截图并停止，以免后续任务使用不完整状态。之后可修复运行环境并恢复。

`integration_plan.json`另提供已有PID场景与700点CSV导入的两组CFG实验，可通过`-Plan`运行。

## 调整实验计划

- `base_cfg`：基准配置文件。`grid`按笛卡尔积生成不同参数组合。
- `cfg_files`：也可改为已有CFG文件路径数组；或使用`cfg_dir`扫描一个目录的JSON文件。
  三者只能选择一个，`cfg_files`/`cfg_dir`模式不使用`grid`。
- `scenarios`：多个工况，每个有唯一ASCII `id`、`csv`路径和可选`targets_csv`。
  `csv`为空使用网页内置工况；`targets_csv`为空则每个工况生成一次目标并冻结。
- `evaluation`：统一评价设置。导入目标CSV自带的容差等设置会被这里的固定设置覆盖。
- `max_configs`：组合数上限，避免误生成超大实验。`headless=false`可查看自动化过程。

已有工况示例，可替换`scenarios`内容：

```json
[
  {
    "id": "pid_020804",
    "csv": "../../alpha一阶保持仿真/scenarios/pid_scenario_20260530_020804.csv",
    "targets_csv": "../目标点CSV/mixed_targets_20261013_011540_873.csv"
  }
]
```

可扫描`strategies.default/EXIT`下的`T_h_W/T_h_A/T_h_I/dt_pred`及状态机阈值。
例如增加`"state_machine.exit_heading_delta_deg_min": [65, 75, 85]`会与窗口组合交叉。
要求I窗口不超过A窗口，A不超过W。当前网页也支持IDLE/ENTRY/MID/DONE策略。

当前网页预测器执行`hold/linear/quad/union/fan`。脚本仍拒绝非零/启用的安全膨胀，
以及未知字段或会被网页静默限幅的数值。转向参数包括filter_tau_s、return_rate_deg_s、
fan_rate_deg_s、fan_branches及alpha_limit_deg/alpha_dot_limit_deg_s/alpha_ddot_limit_deg_s2。
转角保持不变时，同一个CFG重复执行没有新的性能信息。

## 结果与公平性

- `summary.csv`、`summary.json`：逐配置/工况统计，比例为0到1；失败不填伪造的零指标。
- `configs/`：本次所有请求CFG。
- `scenarios/工况ID/`：实际使用的场景CSV、固定目标CSV及目标哈希和评价设置。
- `jobs/工况ID__配置ID/`：请求CFG、生效CFG、网页导出的`results.csv`及`report.json`。
- `manifest.json`：计划、输入和网页代码哈希。每个结果可追溯到其配置和目标集。
- `source/`：本次批量脚本、网页和目标模块的源码快照。

使用相同工况的相同目标坐标、接触真值和评价阈值，只改变CFG。前沿统一标记为
`FRONT_CONTACT_IGNORED`，不计入有效接触分母；右侧及角点保留，负样本误报单列。
原始工具CFG、已有CSV和历史输出都不覆盖。导出的日志与手动点击导出是同一套逻辑。

`analysis_wall_s`包含浏览器分析、渲染和导出开销，不是算法单帧耗时或单片机性能。
本脚本提供可复现批量对比，不自动宣称任何配置“最优”；应结合误报、晚报、不同工况及独立测试选型。
