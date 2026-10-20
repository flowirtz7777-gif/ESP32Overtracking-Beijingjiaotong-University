# PID工况仿真导出器

用于生成平滑、可控的车辆转向工况，并导出包含 `t / v / alpha / phi` 等字段的 CSV，供各MATLAB预测工具作为虚拟传感器输入。

## 启动

双击 `启动PID工况导出器.bat`。也可以直接用浏览器打开 `pid工况仿真导出器.html`。

## 目录

- `pid工况仿真导出器.html`：主界面。
- `desktop-main.js`、`package.json`：Electron桌面包装。
- `Matlab/`：MATLAB加载辅助文件和导出的工况目录。
- `logs/`：运行调试日志。
- `历史版本/`：整理前保留的早期实现，不参与当前启动。

桌面模式导出的CSV默认写入 `Matlab/scenarios/`。这些CSV是仿真输入，不是实车采集数据。
