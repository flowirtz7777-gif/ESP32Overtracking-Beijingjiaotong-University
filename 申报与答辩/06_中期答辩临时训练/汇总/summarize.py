"""汇总：准入总表、总图、模型独立加载验证、描述性图表。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common.config import HEADER, TIER_A  # noqa: E402
from common.monitor import run_main  # noqa: E402
from common.plotting import TIER_COLOR, footnote, plt, save  # noqa: E402

OUT = Path(__file__).resolve().parent
FAMILIES = ["M1_核心预测方法", "M2a_观测扰动与预处理", "M2b_状态估计筛选", "M3_二级处理联合", "M4_趋势增益精化"]


def work(mon):
    tiers = []
    for f in FAMILIES:
        p = ROOT / f / "results" / "tiers.csv"
        if p.exists():
            tiers.append(pd.read_csv(p))
        else:
            mon.line(f"缺少 {f} 的结果")
    mon.tick(1, "读取各模型族分档")
    t = pd.concat(tiers, ignore_index=True)
    keep = ["family", "target_label", "task", "kind", "label_dep", "model", "tier", "main_skill", "main_R2", "main_AUC",
            "external_skill", "reason"]
    t[keep].to_csv(OUT / "准入总表.csv", index=False, encoding="utf-8-sig")
    lines = [f"# 准入总表", "", HEADER, "",
             f"A 档：主方案 skill ≥ {TIER_A['skill']}、R² ≥ {TIER_A['r2']}（分类 AUC ≥ {TIER_A['auc']}），且所有验证方案都优于基线。",
             "B 档：优于基线但未达 A 档。C 档：不优于基线。", "",
             "| 模型族 | 目标 | 口径 | 最优模型 | 档 | 主方案 skill | R² / AUC | 外部 skill | 说明 |", "|---|---|---|---|---|---:|---:|---:|---|"]
    for _, r in t.iterrows():
        q = r.main_R2 if r.kind == "reg" else r.main_AUC
        ext = "" if pd.isna(r.external_skill) else f"{r.external_skill:+.3f}"
        lines.append(f"| {r.family} | {r.target_label} | {r.label_dep} | {r.model} | {r.tier} | {r.main_skill:+.3f} | {q:.3f} | {ext} | {r.reason} |")
    counts = t.tier.value_counts().to_dict()
    lines += ["", f"合计：A {counts.get('A', 0)}，B {counts.get('B', 0)}，C {counts.get('C', 0)}，共 {len(t)} 个任务。"]
    (OUT / "准入总表.md").write_text("\n".join(lines), encoding="utf-8")
    mon.tick(1, "写准入总表")

    fig, ax = plt.subplots(figsize=(max(12, 0.42 * len(t)), 5.2))
    x = np.arange(len(t))
    ax.bar(x, t.main_skill, color=[TIER_COLOR[v] for v in t.tier])
    ext = t.external_skill.to_numpy(float)
    ax.scatter(x[~np.isnan(ext)], ext[~np.isnan(ext)], marker="D", color="k", s=18, zorder=3, label="外部检验 skill（M3）")
    ax.axhline(0, color="k", lw=0.8)
    ax.axhline(TIER_A["skill"], color="#2ca02c", ls=":", lw=1)
    ax.set_xticks(x, [f"{a} · {b}" for a, b in zip(t.family, t.target_label)], rotation=75, ha="right", fontsize=7)
    ax.set_ylabel("主方案相对基线的改善 skill")
    ax.set_title("全部代理模型的准入情况（绿 A / 橙 B / 红 C）")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    footnote(fig, HEADER + " 回归 skill=1−MAE/MAE基线；分类 skill=1−Brier/Brier基线。", y=-0.38)
    save(fig, OUT / "fig11_全部模型准入总图.png")
    mon.tick(1, "总图")

    mon.set_stage("独立进程加载验证")
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", str(OUT / "verify_models.py")], capture_output=True, text=True, encoding="utf-8")
    mon.line("模型加载验证：" + (r.stdout.strip() or r.stderr.strip()[-500:]))
    mon.tick(1)

    mon.set_stage("描述性图表")
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", str(ROOT / "描述性图表" / "make_figures.py")], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("描述性图表失败：" + r.stderr[-1500:])
    mon.tick(1)
    mon.set_stage("汇集全部图表")
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", str(OUT / "collect_figures.py")], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("汇集图表失败：" + r.stderr[-1500:])
    mon.line(r.stdout.strip())
    mon.line("")
    for line in lines[8:]:
        mon.line(line)
    return {"tiers": counts}


if __name__ == "__main__":
    sys.exit(run_main("SUM", 5, work))
