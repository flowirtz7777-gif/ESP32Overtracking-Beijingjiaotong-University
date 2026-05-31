# runs/ — 对比结果自动归档

`compare_alpha_schemes` 每次运行在此创建 `<时间戳>__<csv名>/` 子目录，内含：

- `01_polyW_overlay.png` — 5 方案 PolyW 几何叠加
- `02_swept_area_bar.png` — 平均扫掠面积柱状
- `03_alarm_advance.png` — PolyA 报警提前量对比
- `summary.txt` — 面积 / 接触时刻 / 报警时刻 / 提前量数表

子目录已被 `.gitignore`（`**/runs/*`）忽略，仅本 README 入库占位。
