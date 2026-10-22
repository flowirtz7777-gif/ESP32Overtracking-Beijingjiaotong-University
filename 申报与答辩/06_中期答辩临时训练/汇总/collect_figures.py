"""把各步骤生成的图复制到 全部图表/，并生成带来源说明的 README.md。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。
图的说明按 train.py 中的任务定义与 results/tiers.csv 自动生成，重跑训练后再运行本脚本即可同步。
"""
from __future__ import annotations

import runpy
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from common.config import HEADER, target_label  # noqa: E402

DEST = ROOT / "全部图表"

FAMILIES = [
    ("M1", "M1_核心预测方法", "S1：27 条开发轨迹 × 19 个预测配置，clean，v3 评分口径"),
    ("M2a", "M2a_观测扰动与预处理", "S2：6 条代表轨迹 × 3 方法 × 16 观测条件 × 3 预处理，v3 评分口径"),
    ("M2b", "M2b_状态估计筛选", "S4 状态估计筛选：6 条轨迹 × 3 方法 × 8 条件 × 4 种输入处理，修正评分口径"),
    ("M3", "M3_二级处理联合", "S3 修正评分：27 条开发轨迹训练，12 条选择轨迹外部检验，2 方法 × 8 条件 × 12 后处理变体"),
    ("M4", "M4_趋势增益精化", "S4 联合精化：12 条选择轨迹 × 7 配置（g 0.375–1.25，含保持）× 8 条件 × 12 变体，修正评分口径"),
]

# 标“★”的是建议直接放进答辩材料的图
STAR = {
    ("02_描述性图表", n) for n in ("fig01", "fig02", "fig03", "fig04", "fig05", "fig06", "fig07", "fig12", "fig13", "fig14")
} | {("06_M3_二级处理联合", n) for n in ("fig06", "fig08", "fig09", "fig10")} | {("08_汇总", "fig11")} | {
    ("01_数据探索", "02_输入相关矩阵_D3"), ("01_数据探索", "03_输出相关矩阵_D3")}

P0_DATASETS = {
    "D1": "S1 方法对照（513 行，27 条轨迹，v3 口径）",
    "D2": "S2 观测扰动（864 行，6 条轨迹，v3 口径）",
    "D3": "S3 修正评分 + 保持基线（7800 行，39 条轨迹）",
    "D4": "S4 状态估计筛选（576 行，6 条轨迹）",
    "D5": "S4 联合精化（8064 行，12 条轨迹）",
}

DESCRIPTIVE = {
    "fig01": ("S1", "标签无关", "19 个预测配置在 27 条轨迹上的 2 s 右缘端点误差分布。看外推强度与几何误差的关系：适度外推误差最小，过强外推误差回升。"),
    "fig02": ("S1", "配对差", "同一轨迹下各配置相对保持基线的 RIGHT 不足率变化；数字为 27 条轨迹中优于保持的条数。"),
    "fig03": ("S1", "绝对值，仅描述", "各配置迟报与误报均值的散点；每种方法沿参数增大连线。看迟报与误报的此消彼长。"),
    "fig04": ("S1", "配对差", "衰减线性 τ=1 s 相对保持的收益随车速、转向速率、动作模板的变化热图。"),
    "fig05": ("S2 + S4 状态估计", "绝对值，仅描述", "左：噪声倍率与近场误报；中：纯延迟与迟报；右：四种状态估计的误报与窗口漏报对比。"),
    "fig06": ("S3 修正评分", "配对差", "窗口 × 膨胀 × 确认 12 种组合相对“无后处理”的平均变化（迟报、窗口漏报、近场误报、共同 2 s 误报）。"),
    "fig07": ("S4 联合精化", "绝对值，仅描述", "趋势增益细档（线性 0.375–0.625、衰减线性 0.75–1.25）与三种后处理下的迟报、漏报、误报曲线，并以保持为水平参考线。"),
    "fig12": ("DeepSeek 正向区间评分", "标签不确定性旁证", "一条轨迹 16 个配对的 RIGHT 不足率配对差上下界；绿色区间全在 0 以下表示方向不受标签影响。"),
    "fig13": ("S1 clean，v4_r8_fast_entry 一条轨迹；由冻结 v3 预测器逐帧重算", "a/c/d 几何与标签无关；a 中目标点按纠错前标签筛选",
              "案例图·方法改善了哪里：a 关键帧（入弯初期）在车身坐标系中叠加真实 2 s 右缘扫掠区、保持/线性/衰减线性三种预测区、"
              "保持漏掉而衰减线性补上的区域，以及因此被提前覆盖的目标点；b 全转弯轨迹与 70,000 个目标点；c 同一帧三种方法对未来转角的假设（机制）；"
              "d 全程漏覆盖面积：改善集中在入弯，回正阶段衰减线性反而略差。"),
    "fig14": ("同上；改善/失败案例从该轨迹 20,369 个 RIGHT 目标中按规则选出", "依赖纠错前接触标签",
              "案例图·提前了多少、为什么仍失败：a/b 改善案例的位置与报警—接触时间轴（保持提前 0.71 s → 衰减线性 1.01 s）；"
              "c/d 失败案例（接触距开始转向仅 0.74 s，任何只用历史数据的方法都不可能提前满 1 s）；"
              "e 全部 RIGHT 目标的提前量分布：衰减线性仍迟报的 512 个中 96% 的接触发生在开始转向后 1 s 内。重算报警与原作业结果逐点一致。"),
}

MODEL_FIGS = {
    "fig01": ("模型对比与分档", "主验证方案下各候选模型（Ridge/逻辑回归、随机森林、梯度提升）相对基线的 skill；黑色记号为最优模型在其他验证方案（及外部检验）上的 skill；横轴标签颜色为临时模型表现分档（绿 A / 橙 B / 红 C）。柱为开发集交叉验证成绩，最优模型类别按同一成绩选出，略偏乐观。", "all"),
    "fig02": ("预测 vs 实际（折外）", "主验证方案下留出轨迹的预测值与仿真值散点，越贴近对角线越好。", "reg"),
    "fig03": ("残差诊断", "上：残差 vs 预测值，看是否有系统偏差；下：残差分布与偏度。", "reg"),
    "fig04": ("分段误差", "按观测条件、动作模板、后处理变体、配置分段统计折外 MAE，看模型在哪些工况上最难预测；前 10 个最难工况见 results/segment_errors.csv。", "reg"),
    "fig05": ("置换重要性", "在留出折上打乱某个输入后误差增加多少；橙色为成组置换（转向动作、方法及参数、观测扰动、后处理）。只对 A 档任务作解释。", "imp"),
    "fig06": ("混淆矩阵", "分类任务在默认阈值 0.5 和“安全优先”阈值（目标召回 ≥ 90%）下的 2×2 混淆矩阵，含召回与精确率。阈值从不在被评估的同一批预测上选择：有外部集时只用开发集折外预测确定；无外部集时交叉拟合（每折阈值只用其余折确定），所以实际召回可能低于 90%。", "cls"),
    "fig07": ("ROC 与 PR 曲线", "分类任务的 ROC（含 AUC）和精确率–召回曲线。", "cls"),
    "fig08": ("外部检验：预测 vs 实际", "用 27 条开发轨迹训练、在 12 条从未见过的选择轨迹上只评一次的结果，颜色区分轨迹。", "reg"),
    "fig09": ("学习曲线", "只在开发集内部完成：沿用按轨迹 5 折，每折从训练轨迹中抽 5/10/15/20 条或全部训练，在留出轨迹上评估；外部集不参与。模型类别与超参数与最终模型一致。曲线变平说明再加同类轨迹收益有限。", "lc"),
    "fig10": ("部分依赖（后处理）", "其他输入保持数据分布不变时，只改变窗口、膨胀、确认、噪声，模型预测的平均变化；最右列为膨胀 × 确认的二维图。描述模型学到的规律，不等于因果效应。", "pdp"),
}


def key_tasks(fam, tiers, kind=None):
    names = set(tiers.task)
    ok = [t.target for t in fam.tasks if t.key and (kind is None or t.kind == kind) and t.target in names]
    if not ok:
        ok = [t for t in tiers.task if kind is None or tiers.set_index("task").at[t, "kind"] == kind][:4]
    return ok[:4]


def fmt_tasks(tasks, tiers):
    tr = tiers.set_index("task")
    parts = []
    for t in tasks:
        if t in tr.index:
            r = tr.loc[t]
            parts.append(f"{target_label(t)}（{r.model}，{r.tier} 档）")
    return "；".join(parts) if parts else "—"


def copy_dir(src: Path, sub: str) -> list[Path]:
    out = DEST / sub
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("*.png"))
    for f in files:
        shutil.copy2(f, out / f.name)
    return files


def star(sub, name):
    return "★ " if any(sub == s and name.startswith(n) for s, n in STAR) else ""


def main():
    if DEST.exists():
        for p in DEST.rglob("*.png"):
            p.unlink()
    DEST.mkdir(exist_ok=True)
    lines = [
        "# 全部图表", "", f"> {HEADER}", "",
        "本目录是各步骤生成图片的副本，按来源分子目录存放，原图仍保留在各步骤的 `figures/` 中。"
        "重跑训练后运行 `汇总/collect_figures.py`（汇总步骤会自动运行）即可同步。", "",
        "标 ★ 的是建议直接放进答辩材料的图。每张图的脚注都写了数据口径，引用时请保留。", "",
        "通用口径：",
        "- 全部轨迹转角峰值均为 10°，结论只适用于这一种转弯几何、2–4 m/s 低速、静态目标的运动学仿真。",
        "- S1、S2 为 v3 评分口径（误报类数值略高于修正口径），S3、S4 为修正评分口径。",
        "- 接触标签纠错尚未完成：端点误差与标签无关；配对差有区间旁证；绝对值只作描述。",
        "- 临时模型表现分档：A 档 = 主方案 skill ≥ 0.3 且 R² ≥ 0.5（分类 AUC ≥ 0.75），且所有验证方案都优于基线；B 档 = 优于基线但未达 A 档；C 档 = 不优于基线。"
        "分档只衡量模型对纠错前评分的预测能力，不代表评分正确、实验完成或安全性通过，与正式科研准入分开。",
        "- 主方案成绩是开发集交叉验证成绩，最优模型类别按同一成绩选出，略偏乐观；M3 外部检验（12 条选择轨迹，每任务只评一次，不参与调参、阈值和学习曲线）没有这项偏差。",
        "- skill = 1 − 模型误差 ÷ 基线误差（回归用每条轨迹等权 MAE，分类用 Brier 分数）。", "",
    ]

    # 01 数据探索
    sub = "01_数据探索"
    files = copy_dir(ROOT / "P0_数据整理" / "figures", sub)
    lines += [f"## {sub}", "", "来源：`P0_数据整理/build_all.py`，原图在 `P0_数据整理/figures/`。不涉及模型。", "",
              "| 图 | 数据 | 内容 |", "|---|---|---|"]
    for f in files:
        ds = f.stem.split("_")[-1]
        if f.stem.startswith("01_"):
            what = "8 个主要目标（迟报、漏报、提前量、三种误报、端点误差）的分布直方图；端点误差按作业去重。"
        elif f.stem.startswith("02_"):
            what = "输入之间的 Spearman 相关矩阵。全因子设计下各因素应接近不相关，说明效应可以分开估计；方法专属参数与方法类别天然相关。"
        elif f.stem.startswith("03_"):
            what = "各输出指标之间的 Spearman 相关矩阵，看哪些指标同涨同落、哪些此消彼长（不能合成单一分数的依据）。"
        elif f.stem.startswith("04_"):
            what = "39 条轨迹按 RIGHT 不足率、近场误报的指标向量做相关并聚类排序，看哪些工况表现相近（sel_ 开头为选择集）。"
        else:
            what = "开发集上各输入取值与 RIGHT 不足率、近场误报率的箱线图。"
        lines.append(f"| {star(sub, f.stem)}`{f.name}` | {P0_DATASETS.get(ds, ds)} | {what} |")
    lines.append("")

    # 02 描述性图表
    sub = "02_描述性图表"
    files = copy_dir(ROOT / "描述性图表", sub)
    lines += [f"## {sub}", "", "来源：`描述性图表/make_figures.py`，直接由评分数据画出，不依赖模型。", "",
              "| 图 | 数据 | 口径 | 内容 |", "|---|---|---|---|"]
    for f in files:
        d = DESCRIPTIVE.get(f.stem[:5], ("", "", ""))
        lines.append(f"| {star(sub, f.stem)}`{f.name}` | {d[0]} | {d[1]} | {d[2]} |")
    lines.append("")

    # 03–07 各模型族
    for i, (code, folder, data_desc) in enumerate(FAMILIES, start=3):
        sub = f"{i:02d}_{folder}"
        files = copy_dir(ROOT / folder / "figures", sub)
        fam = runpy.run_path(str(ROOT / folder / "train.py"))["fam"]
        tiers = pd.read_csv(ROOT / folder / "results" / "tiers.csv")
        counts = tiers.tier.value_counts().to_dict()
        schemes = "、".join(fam.schemes) + ("、外部检验（12 条选择轨迹）" if fam.external is not None else "")
        lines += [f"## {sub}", "",
                  f"来源：`{folder}/train.py`（训练引擎 `common/modeling.py`，出图 `common/figures.py`），原图在 `{folder}/figures/`。",
                  "", f"- 数据：{data_desc}。",
                  f"- 验证方案：{schemes}；主方案为 {fam.main_scheme}。",
                  f"- 任务 {len(tiers)} 个，临时模型表现分档 A {counts.get('A', 0)} / B {counts.get('B', 0)} / C {counts.get('C', 0)}，逐项见 `{folder}/results/tiers.csv`；训练记录（代码、依赖、数据哈希、最终参数）见 `{folder}/results/run_manifest.json`。", "",
                  "| 图 | 内容 | 图中展示的任务（最优模型，档） |", "|---|---|---|"]
        cls_tasks = [t for t in tiers.task if tiers.set_index("task").at[t, "kind"] == "cls"]
        for f in files:
            name, what, scope = MODEL_FIGS.get(f.stem[:5], (f.stem, "", "all"))
            if scope == "all":
                shown = f"全部 {len(tiers)} 个任务"
            elif scope == "reg":
                shown = fmt_tasks(key_tasks(fam, tiers, "reg"), tiers)
            elif scope == "imp":
                shown = fmt_tasks(key_tasks(fam, tiers), tiers)
            elif scope == "cls":
                src = "外部检验" if fam.external is not None else f"{fam.main_scheme} 折外预测"
                shown = fmt_tasks(cls_tasks, tiers) + f"；数据来源：{src}"
            elif scope == "lc":
                shown = fmt_tasks(fam.learning_curve, tiers)
            else:
                shown = fmt_tasks([t.target for t in fam.tasks if t.key], tiers)
            lines.append(f"| {star(sub, f.stem)}`{f.name}` | **{name}**：{what} | {shown} |")
        lines.append("")

    # 08 汇总
    sub = "08_汇总"
    files = copy_dir(ROOT / "汇总", sub)
    lines += [f"## {sub}", "", "来源：`汇总/summarize.py`，读取各模型族 `results/tiers.csv`。", "",
              "| 图 | 内容 |", "|---|---|"]
    for f in files:
        lines.append(f"| {star(sub, f.stem)}`{f.name}` | 全部任务主验证方案下的 skill，颜色为临时模型表现分档，黑色菱形为 M3 外部检验 skill；逐项数值见 `汇总/临时模型表现分档总表.md`。 |")
    lines.append("")

    n = len(list(DEST.rglob("*.png")))
    lines += ["## 统计", "", f"共 {n} 张图。"]
    (DEST / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"copied {n} figures -> {DEST}")


if __name__ == "__main__":
    main()
