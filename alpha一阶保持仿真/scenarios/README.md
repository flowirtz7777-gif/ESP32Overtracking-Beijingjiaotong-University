# Matlab/scenarios/

PID 工况 CSV 文件统一存放目录。

## 来源

由 [`pid工况仿真导出器.html`](../../pid工况仿真导出器.html) 导出。
- Web 版（直接双击 HTML）：浏览器下载到默认 Downloads 文件夹，需手动移到这里
- Electron 版（双击 `启动PID工况导出器.bat` 或桌面快捷方式）：保存对话框默认就指向本目录

## 使用

```matlab
% 1. 弹文件框（默认打开本目录）
out = run_phase1_demo();

% 2. 直接传文件名（自动到本目录找）
out = run_phase1_demo('pid_scenario_20260530_010000.csv');

% 3. 传完整路径（向后兼容）
out = run_phase1_demo('C:\anywhere\pid_scenario.csv');
```

## 命名约定

`pid_scenario_<YYYYMMDD>_<HHMMSS>.csv` （HTML 导出器自动按时间戳命名）

## Git

CSV 是纯文本，体积小，默认随仓库一起提交。
如不希望提交某些大型测试 CSV，可把它命名为 `pid_scenario_*.local.csv`（已在 .gitignore 排除）。
