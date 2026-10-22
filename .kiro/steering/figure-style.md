---
inclusion: always
---

# 出图规范（所有图都用 nature-figure skill）

本项目所有图表一律按 `nature-figure` skill（https://github.com/jing1312/nature-figure-skill，MIT，已安装在 `~/.kiro/skills/nature-figure/`）的流程和规则绘制。开始画图前先用 disclose_context 载入该 skill，按其 SKILL.md 和 references 执行。

## 项目约定

- 后端：**Python（matplotlib）**。依据是本项目已有的出图工作流全部是 Python/matplotlib（skill 允许按"已有明确语言的工作流"确定后端）。若用户另行指定 R，以用户为准；否则 R 不用于本项目的任何出图、预览或导出。
- 解释器：`C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8 -B`。
- 共用样式：`申报与答辩/06_中期答辩临时训练/common/plotting.py`（`apply_style()` / `save()` / `panel_label()` / `PALETTE`）。新脚本直接复用，不另起一套样式。

## 每张图之前先写"图表契约"

1. 核心结论：一句话说明这张图要证明什么。
2. 证据链：每个子图对应结论的哪一部分；不能单独提供证据的子图删掉。
3. 类型：quantitative grid / schematic-led composite / image plate + quant / asymmetric mixed-modality。
4. 口径：数据来源、评分口径（v3 / 修正）、是否依赖接触标签、n 的定义（轨迹、作业、目标点都不是独立车辆试验）。

## 必须遵守的规则

- 字体：`font.family = sans-serif`。中文图用 `font.sans-serif = ["Microsoft YaHei", "Arial", "DejaVu Sans"]`（微软雅黑必须放第一位：matplotlib 的 PDF/SVG 导出不做逐字回退，Arial 在前会缺中文字形）；纯英文图可以 Arial 在前。`svg.fonttype = "none"`、`pdf.fonttype = 42`，保持文字可编辑。
- 只留左、下坐标轴线；图例无边框；默认不画网格。
- 色板用 skill 的 `PALETTE`（蓝 = 主推方法，红 = 代价/基线对照，灰 = 参考），一张图只用一个主色族；不用彩虹色图，红绿不能是唯一编码。
- 小写加粗面板标签 a、b、c 放在左上角；图例不要压在密集数据上，统计量放在轴外的无框统计条。
- 导出：SVG 为主，同时导出 PDF 和 PNG（预览）。超过约 1 万个点的散点图用 `rasterized=True`。
- 脚注写明数据口径。中期答辩临时训练相关的图沿用"中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产"的标注。
- 交付前对照 skill 的 `references/qa-contract.md` 自查：尺寸、字号、可编辑文字、色彩、图例、统计说明、源数据可追溯。
