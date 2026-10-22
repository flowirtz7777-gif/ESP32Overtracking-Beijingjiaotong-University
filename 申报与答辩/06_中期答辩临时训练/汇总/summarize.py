"""汇总：临时模型表现分档总表、总图、模型独立加载验证、描述性图表、汇集全部图表。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。
任一模型族缺结果或未正常完成、模型加载验证失败、描述性图表或图表汇集失败，汇总都会以失败退出，
不会把不完整的结果报成完成。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common.config import HEADER, LOGS, TIER_A  # noqa: E402
from common.monitor import run_main  # noqa: E402
from common.plotting import TIER_COLOR, footnote, plt, save  # noqa: E402
from common.provenance import run_record, sha256  # noqa: E402

OUT = Path(__file__).resolve().parent
FAMILIES = [("M1", "M1_核心预测方法"), ("M2a", "M2a_观测扰动与预处理"), ("M2b", "M2b_状态估计筛选"),
            ("M3", "M3_二级处理联合"), ("M4", "M4_趋势增益精化")]


def check_families():
    """每个模型族必须：状态文件为 done、tiers.csv 存在、任务数与 train.py 定义一致。"""
    import runpy
    problems, tiers = [], []
    for code, folder in FAMILIES:
        st = LOGS / f"{code}.status.json"
        state = json.loads(st.read_text(encoding="utf-8")).get("state") if st.exists() else "missing"
        if state != "done":
            problems.append(f"{code}: 训练状态为 {state}，不是 done")
        p = ROOT / folder / "results" / "tiers.csv"
        if not p.exists():
            problems.append(f"{code}: 缺少 results/tiers.csv")
            continue
        t = pd.read_csv(p)
        defined = [x.target for x in runpy.run_path(str(ROOT / folder / "train.py"))["fam"].tasks]
        missing = sorted(set(defined) - set(t.task))
        if missing:
            problems.append(f"{code}: 定义了 {len(defined)} 个任务，结果只有 {len(t)} 个，缺 {missing}")
        tiers.append(t)
    return problems, tiers


def run_sub(script: Path, what: str, mon):
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", str(script)], capture_output=True, text=True, encoding="utf-8")
    mon.line(f"{what}：" + (r.stdout.strip()[-800:] or "(无输出)"))
    if r.returncode != 0:
        raise RuntimeError(f"{what}失败（退出码 {r.returncode}）：{(r.stderr or r.stdout)[-1500:]}")


def work(mon):
    problems, tiers = check_families()
    if problems:
        for p in problems:
            mon.line("  ✗ " + p)
        raise RuntimeError(f"有 {len(problems)} 项检查未通过，汇总中止，不生成“完成”结论")
    mon.tick(1, "读取各模型族分档")
    t = pd.concat(tiers, ignore_index=True)
    keep = ["family", "target_label", "task", "kind", "label_dep", "model", "tier", "main_skill", "main_R2", "main_AUC",
            "external_skill", "reason"]
    t[keep].to_csv(OUT / "临时模型表现分档总表.csv", index=False, encoding="utf-8-sig")
    lines = ["# 临时模型表现分档总表", "", HEADER, "",
             "分档只衡量代理模型对**当前（接触标签纠错前）评分**的预测能力，不代表评分正确、实验完成或安全性通过，与正式科研准入分开。", "",
             f"A 档：主方案 skill ≥ {TIER_A['skill']}、R² ≥ {TIER_A['r2']}（分类 AUC ≥ {TIER_A['auc']}），且所有验证方案都优于基线。",
             "B 档：优于基线但未达 A 档。C 档：不优于基线。", "",
             "“主方案 skill”是开发集交叉验证成绩；最优模型类别按同一外层成绩选出，略偏乐观。M3 的“外部 skill”来自 12 条从未参与训练、调参、阈值选择和学习曲线的选择轨迹，每个任务只评一次，没有这项偏差。", "",
             "| 模型族 | 目标 | 口径 | 最优模型 | 档 | 主方案 skill | R² / AUC | 外部 skill | 说明 |", "|---|---|---|---|---|---:|---:|---:|---|"]
    for _, r in t.iterrows():
        q = r.main_R2 if r.kind == "reg" else r.main_AUC
        ext = "" if pd.isna(r.external_skill) else f"{r.external_skill:+.3f}"
        lines.append(f"| {r.family} | {r.target_label} | {r.label_dep} | {r.model} | {r.tier} | {r.main_skill:+.3f} | {q:.3f} | {ext} | {r.reason} |")
    counts = t.tier.value_counts().to_dict()
    lines += ["", f"合计：A {counts.get('A', 0)}，B {counts.get('B', 0)}，C {counts.get('C', 0)}，共 {len(t)} 个任务。"]
    (OUT / "临时模型表现分档总表.md").write_text("\n".join(lines), encoding="utf-8")
    for old in ("准入总表.md", "准入总表.csv"):
        (OUT / old).unlink(missing_ok=True)
    mon.tick(1, "写分档总表")

    fig, ax = plt.subplots(figsize=(max(12, 0.42 * len(t)), 5.2))
    x = np.arange(len(t))
    ax.bar(x, t.main_skill, color=[TIER_COLOR[v] for v in t.tier])
    ext = t.external_skill.to_numpy(float)
    ax.scatter(x[~np.isnan(ext)], ext[~np.isnan(ext)], marker="D", color="k", s=18, zorder=3, label="外部检验 skill（M3，只评一次）")
    ax.axhline(0, color="k", lw=0.8)
    ax.axhline(TIER_A["skill"], color="#2ca02c", ls=":", lw=1)
    ax.set_xticks(x, [f"{a} · {b}" for a, b in zip(t.family, t.target_label)], rotation=75, ha="right", fontsize=7)
    ax.set_ylabel("主方案相对基线的改善 skill")
    ax.set_title("全部代理模型的临时表现分档（绿 A / 橙 B / 红 C）")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    footnote(fig, HEADER + " 回归 skill=1−MAE/MAE基线；分类 skill=1−Brier/Brier基线。柱为开发集交叉验证成绩（含模型类别选择，略偏乐观）；"
                           "分档只衡量对纠错前评分的预测能力，不是科研准入。", y=-0.38)
    for old in OUT.glob("fig11_*.png"):
        old.unlink()
    save(fig, OUT / "fig11_全部模型临时表现分档总图.png")
    mon.tick(1, "总图")

    mon.set_stage("独立进程加载验证")
    run_sub(OUT / "verify_models.py", "模型加载验证", mon)
    mon.tick(1)
    mon.set_stage("描述性图表")
    run_sub(ROOT / "描述性图表" / "make_figures.py", "描述性图表", mon)
    mon.tick(1)
    mon.set_stage("汇集全部图表")
    run_sub(OUT / "collect_figures.py", "汇集全部图表", mon)
    mon.tick(1)

    manifests = {code: json.loads((ROOT / folder / "results" / "run_manifest.json").read_text(encoding="utf-8"))
                 for code, folder in FAMILIES}
    rec = run_record({"header": HEADER, "tiers": counts, "tasks": int(len(t)),
                      "family_code_aggregate_sha256": {k: v["code_aggregate_sha256"] for k, v in manifests.items()},
                      "family_data_sha256": {k: v["data_sha256"] for k, v in manifests.items()},
                      "verification": json.loads((OUT / "model_load_verification.json").read_text(encoding="utf-8"))["all_ok"],
                      "summary_table_sha256": sha256(OUT / "临时模型表现分档总表.md")})
    same_code = len({v for v in rec["family_code_aggregate_sha256"].values()}) == 1
    rec["all_families_same_code"] = same_code
    (OUT / "run_manifest.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    if not same_code:
        mon.line("  ! 注意：各模型族训练时的代码指纹不一致（中途改过代码），见 汇总/run_manifest.json")
    mon.line("")
    for line in lines[10:]:
        mon.line(line)
    return {"tiers": counts}


if __name__ == "__main__":
    sys.exit(run_main("SUM", 6, work))
