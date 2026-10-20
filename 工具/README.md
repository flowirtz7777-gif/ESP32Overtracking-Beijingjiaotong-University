# 工具索引

所有工具均以本目录为共同父目录，因此需要互相调用的MATLAB工具仍可使用原有兄弟目录关系。

| 工具 | 入口 | 输入/配置 | 结果/日志 |
|---|---|---|---|
| PID工况仿真导出器 | `启动PID工况导出器.bat` | 页面参数 | `Matlab/scenarios/`、`logs/` |
| 人工驾驶仿真软件 | `启动人工驾驶仿真软件.bat` | WASD驾驶、导入回放CSV | `导出数据/`（桌面版） |
| TTC预警复盘软件 | `启动TTC预警复盘软件.bat` | 导入工况CSV | `报警日志/` |
| CFG配置生成器 | `启动CFG配置生成器.bat` | 页面参数 | `生成结果/` |
| 转弯全过程盲区分析软件 | `启动转弯全过程盲区分析软件.bat` | `目标点CSV/`、`CFG配置/` | `边界点盲区日志/`、`logs/` |
| 正交路口出弯状态机仿真 | `run_phase1_demo.m` | `scenarios/`、`targets/` | `runs/` |
| Alpha一阶保持仿真 | `run_phase1_demo.m` | `scenarios/` | `runs/` |
| Alpha线性外推仿真 | `run_phase1_demo.m` | `scenarios/` | `runs/` |
| Alpha二阶外推仿真 | `run_phase1_demo.m` | `scenarios/` | `runs/` |
| Alpha多假设并集仿真 | `run_phase1_demo.m` | `scenarios/` | `runs/` |
| Alpha扇形包络仿真 | `run_phase1_demo.m` | `scenarios/` | `runs/` |
| Alpha方案对比 | `compare_alpha_schemes.m` | 读取各Alpha方案 | `runs/` |
| R3诊断 | `diagnose_R3_hold.m` | `canonical_targets.m` | `runs/` |
| 验收目标集 | 由其他工具读取 | 两组冻结CSV | 本目录不生成结果 |

具体参数、调用示例和结果字段以各工具自己的 `README.md` 为准。
