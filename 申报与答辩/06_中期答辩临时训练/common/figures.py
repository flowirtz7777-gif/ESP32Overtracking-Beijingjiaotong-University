"""每个模型族的标准图（按 nature-figure skill 规范）。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

两种用法：
- 训练时由 common.modeling.run_family 调用 family_figures()；
- 不重新训练、直接用 results/ 中保存的结果重画：replot_from_results("M3_二级处理联合")，
  或在 06_中期答辩临时训练 目录下运行  python -m common.figures [模型族目录 ...]
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import FEATURE_LABEL, HEADER, ROOT, SAFETY_RECALL, target_label
from .plotting import (MODEL_COLOR, PALETTE, QUAL, SEQ_CMAP, TEMPLATE_COLOR, TEMPLATE_LABEL, TIER_COLOR,
                       apply_style, footnote, is_dark, panel_label, plt, save)

FAMILY_FOLDERS = ["M1_核心预测方法", "M2a_观测扰动与预处理", "M2b_状态估计筛选", "M3_二级处理联合", "M4_趋势增益精化"]
LETTERS = "abcdefghijklmnop"


def _key_tasks(fam, tiers, kind=None):
    ok = [t.target for t in fam.tasks if t.key and (kind is None or t.kind == kind) and t.target in set(tiers.task)]
    if not ok:
        ok = [t for t in tiers.task if kind is None or tiers.set_index("task").at[t, "kind"] == kind][:4]
    return ok[:4]


def _case_traits(case_id: str):
    """从选择集轨迹名（如 sel_v2.5_r3_fast_entry）解析车速与动作模板。"""
    m = re.match(r"^sel_v([\d.]+)_r(\d+)_(.+)$", str(case_id))
    return (float(m.group(1)), m.group(3)) if m else (np.nan, "")


def family_figures(fam, scores, tiers, imp, oof, ext, cls, lc_rows, pdp_store, segs):
    apply_style()
    fig_dir = fam.out / "figures"
    foot = f"{HEADER} {fam.score_note}"
    if tiers.empty:
        return
    tier_of = tiers.set_index("task")["tier"].to_dict()
    best_of = tiers.set_index("task")["model"].to_dict()

    # 1 模型对比
    tasks = tiers.task.tolist()
    models = [m for m in scores.model.unique() if m != "基线"]
    main = scores[scores.scheme == fam.main_scheme]
    fig, ax = plt.subplots(figsize=(max(7.2, 0.62 * len(tasks)), 3.6))
    x = np.arange(len(tasks))
    w = 0.8 / max(1, len(models))
    for k, m in enumerate(models):
        v = [main[(main.task == t) & (main.model == m)].skill.mean() for t in tasks]
        ax.bar(x + (k - (len(models) - 1) / 2) * w, v, w, color=MODEL_COLOR.get(m, PALETTE["neutral_mid"]),
               label=f"{m}（{fam.main_scheme}）")
    marks = {s: mk for s, mk in zip([s for s in scores.scheme.unique() if s != fam.main_scheme], ["D", "^", "s", "v"])}
    for s, mk in marks.items():
        sub = scores[scores.scheme == s]
        v = [sub[(sub.task == t) & (sub.model == best_of[t])].skill.mean() for t in tasks]
        ax.scatter(x, v, marker=mk, color=PALETTE["neutral_black"], s=14, zorder=3, label=f"最优模型 · {s}")
    ax.axhline(0, color=PALETTE["neutral_black"], lw=0.8)
    ax.axhline(0.3, color=TIER_COLOR["A"], ls=":", lw=1)
    ax.set_xticks(x, [f"{target_label(t)} [{tier_of[t]}]" for t in tasks], fontsize=6.5, rotation=40, ha="right")
    for lbl, t in zip(ax.get_xticklabels(), tasks):
        lbl.set_color(TIER_COLOR[tier_of[t]])
    ax.set_ylabel("相对基线的改善 skill")
    ax.set_ylim(min(-0.3, np.nanmin(main.skill) - 0.05), 1.0)
    ax.set_title(f"{fam.name} {fam.title}：各任务的模型对比（[ ] 内为临时模型表现分档）")
    ax.legend(fontsize=6.5, ncols=2, loc="lower left")
    footnote(fig, foot + " 虚线为 A 档 skill 阈值 0.3；回归 skill=1−MAE/MAE基线，分类 skill=1−Brier/Brier基线。"
                         "柱为开发集交叉验证成绩，最优模型类别按同一成绩选出，略偏乐观；分档只衡量对纠错前评分的预测能力，不是科研准入。", y=-0.02)
    save(fig, fig_dir / "fig01_模型对比与分档.png")

    # 2 预测 vs 实际（主方案折外）
    reg_keys = _key_tasks(fam, tiers, "reg")
    if reg_keys:
        fig, axes = plt.subplots(1, len(reg_keys), figsize=(1.85 * len(reg_keys) + 0.6, 2.4), squeeze=False)
        fig.subplots_adjust(wspace=0.45)
        for j, (ax, t) in enumerate(zip(axes[0], reg_keys)):
            d = oof[t][fam.main_scheme]
            ax.scatter(d.y_true, d.y_pred, s=3, alpha=0.35, lw=0, color=PALETTE["blue_main"], rasterized=len(d) > 3000)
            lim = [min(d.y_true.min(), d.y_pred.min()), max(d.y_true.max(), d.y_pred.max())]
            ax.plot(lim, lim, ls="--", color=PALETTE["neutral_dark"], lw=0.7)
            r = tiers.set_index("task").loc[t]
            ax.set_title(f"{target_label(t)}\n{r.model} R²={r.main_R2:.2f} [{r.tier}]", fontsize=7)
            ax.set_xlabel("仿真实际值")
            panel_label(ax, LETTERS[j], x=-0.28, y=1.02)
        axes[0, 0].set_ylabel("留出轨迹预测值")
        footnote(fig, foot + f" {fam.main_scheme} 折外预测：每个点都来自训练时没见过的轨迹；虚线为完美预测。", y=-0.08)
        save(fig, fig_dir / "fig02_预测vs实际_折外.png")

        # 3 残差诊断
        fig, axes = plt.subplots(2, len(reg_keys), figsize=(1.85 * len(reg_keys) + 0.6, 4.0), squeeze=False)
        fig.subplots_adjust(wspace=0.45, hspace=0.55)
        for j, t in enumerate(reg_keys):
            d = oof[t][fam.main_scheme]
            res = d.y_true - d.y_pred
            axes[0, j].scatter(d.y_pred, res, s=3, alpha=0.35, lw=0, color=PALETTE["blue_main"], rasterized=len(d) > 3000)
            axes[0, j].axhline(0, color=PALETTE["neutral_dark"], lw=0.7)
            axes[0, j].set_title(target_label(t), fontsize=7)
            axes[0, j].set_xlabel("预测值")
            axes[1, j].hist(res, bins=50, color=PALETTE["blue_secondary"])
            axes[1, j].set_xlabel(f"残差（偏度 {pd.Series(res).skew():.2f}）")
            panel_label(axes[0, j], LETTERS[j], x=-0.28, y=1.02)
        axes[0, 0].set_ylabel("残差 = 实际 − 预测")
        axes[1, 0].set_ylabel("行数")
        footnote(fig, foot + " 上：残差随预测值的分布（应围绕 0 且无明显趋势）；下：残差直方图。", y=-0.02)
        save(fig, fig_dir / "fig03_残差诊断.png")

        # 4 分段误差
        if not segs.empty:
            seg_names = [s for s in ("condition", "template", "variant", "config_id") if s in set(segs.segment)]
            seg_title = {"condition": "观测条件", "template": "动作模板", "variant": "后处理变体", "config_id": "预测配置"}
            fig, axes = plt.subplots(len(reg_keys), len(seg_names), figsize=(1.9 * len(seg_names) + 0.8, 1.75 * len(reg_keys) + 0.4),
                                     squeeze=False)
            fig.subplots_adjust(wspace=0.95, hspace=0.6)
            for i, t in enumerate(reg_keys):
                for j, s in enumerate(seg_names):
                    d = segs[(segs.task == t) & (segs.segment == s)].sort_values("MAE")
                    axes[i, j].barh([str(v)[:24] for v in d.value], d.MAE, color=PALETTE["blue_main"])
                    axes[i, j].tick_params(axis="y", labelsize=5)
                    axes[i, j].tick_params(axis="x", labelsize=6)
                    if i == 0:
                        axes[i, j].set_title(f"按{seg_title.get(s, s)}分段", fontsize=7)
                    if j == 0:
                        axes[i, j].set_ylabel(target_label(t), fontsize=6.5)
                        panel_label(axes[i, j], LETTERS[i], x=-1.0, y=1.0)
                    axes[i, j].set_xlabel("MAE", fontsize=6)
            footnote(fig, foot + " 主方案折外误差按分段统计；最难预测的前 10 个轨迹×条件见 results/segment_errors.csv。", y=-0.01)
            save(fig, fig_dir / "fig04_分段误差.png")

    # 5 置换重要性
    keys = _key_tasks(fam, tiers)
    if keys and not imp.empty:
        fig, axes = plt.subplots(1, len(keys), figsize=(2.1 * len(keys) + 0.8, 2.8), squeeze=False)
        fig.subplots_adjust(wspace=1.1)
        for j, (ax, t) in enumerate(zip(axes[0], keys)):
            d = imp[imp.task == t].sort_values("importance_mean")
            d = d[d.importance_mean.abs() > 1e-12]
            ax.barh(d.label, d.importance_mean, xerr=d.importance_fold_std, capsize=1.5,
                    error_kw={"elinewidth": 0.6, "capthick": 0.6},
                    color=np.where(d.is_group, PALETTE["orange"], PALETTE["blue_main"]))
            ax.set_title(f"{target_label(t)}\n{best_of[t]} [{tier_of[t]}]", fontsize=7)
            ax.set_xlabel("置换后误差增加量", fontsize=6.5)
            ax.tick_params(axis="y", labelsize=6)
            panel_label(ax, LETTERS[j], x=-0.75, y=1.02)
        footnote(fig, foot + " 橙色为成组置换（一次打乱一组相关输入）；在留出折上计算，误差线为跨折标准差。C 档任务的重要性不作解释。", y=-0.04)
        save(fig, fig_dir / "fig05_置换重要性.png")

    # 6 分类：混淆矩阵与 ROC/PR
    if cls:
        names = list(cls)
        fig, axes = plt.subplots(len(names), 2, figsize=(4.6, 2.2 * len(names)), squeeze=False)
        fig.subplots_adjust(hspace=0.75, wspace=0.55)
        cmap = plt.get_cmap("Blues")
        for i, t in enumerate(names):
            for j, (tname, v) in enumerate(cls[t]["confusion"].items()):
                cm = np.array(v["matrix"])
                axes[i, j].imshow(cm, cmap=cmap, vmin=0)
                for a in range(2):
                    for b in range(2):
                        axes[i, j].text(b, a, f"{cm[a, b]:,}", ha="center", va="center", fontsize=7.5,
                                        color="white" if is_dark(cmap(cm[a, b] / max(1, cm.max()))) else "black")
                axes[i, j].set_xticks([0, 1], ["预测否", "预测是"])
                axes[i, j].set_yticks([0, 1], ["实际否", "实际是"])
                lo, hi = v.get("threshold_range", [v["threshold"], v["threshold"]])
                thr_txt = f"{v['threshold']:.3f}" if abs(hi - lo) < 1e-9 else f"{lo:.3f}–{hi:.3f}"
                axes[i, j].set_title(f"{target_label(t)} · {tname}\n阈值 {thr_txt}  召回 {v['recall']:.2f}  精确率 {v['precision']:.2f}",
                                     fontsize=6)
                for sp in axes[i, j].spines.values():
                    sp.set_visible(False)
            panel_label(axes[i, 0], LETTERS[i], x=-0.55, y=1.05)
        footnote(fig, foot + f" 数据来源：{cls[names[0]]['source']}。安全优先阈值的目标召回为 {SAFETY_RECALL:.0%}，"
                             "阈值从不在被评估的同一批预测上选择，因此实际召回可能低于目标。", y=-0.01)
        save(fig, fig_dir / "fig06_混淆矩阵.png")

        from sklearn.metrics import auc, precision_recall_curve, roc_curve
        fig, axes = plt.subplots(1, 2, figsize=(5.6, 2.6))
        fig.subplots_adjust(wspace=0.35)
        for t, color in zip(names, QUAL):
            y, p = cls[t]["y"], cls[t]["p"]
            if len(np.unique(y)) < 2:
                continue
            fpr, tpr, _ = roc_curve(y, p)
            pr, rc, _ = precision_recall_curve(y, p)
            axes[0].plot(fpr, tpr, color=color, lw=1.1, label=f"{target_label(t)} AUC={auc(fpr, tpr):.2f}")
            axes[1].plot(rc, pr, color=color, lw=1.1, label=f"{target_label(t)} 正例比例={y.mean():.2f}")
        axes[0].plot([0, 1], [0, 1], ls="--", color=PALETTE["neutral_mid"], lw=0.7)
        axes[0].set(xlabel="假阳性率", ylabel="真阳性率（召回）", title="ROC 曲线")
        axes[1].set(xlabel="召回", ylabel="精确率", title="PR 曲线")
        for ax, lab in zip(axes, "ab"):
            ax.legend(fontsize=5.8, loc="lower right" if lab == "a" else "lower left")
            panel_label(ax, lab, x=-0.2, y=1.02)
        footnote(fig, foot + f" 数据来源：{cls[names[0]]['source']}。", y=-0.04)
        save(fig, fig_dir / "fig07_ROC_PR.png")

    # 7 外部检验：颜色 = 动作模板，形状 = 车速
    if ext:
        ks = [t for t in reg_keys if t in ext]
        if ks:
            fig, axes = plt.subplots(1, len(ks), figsize=(1.85 * len(ks) + 0.6, 2.6), squeeze=False)
            fig.subplots_adjust(wspace=0.45)
            markers = {2.5: "o", 3.5: "^"}
            for j, (ax, t) in enumerate(zip(axes[0], ks)):
                d = ext[t].copy()
                traits = d.case_id.map(_case_traits)
                d["speed"], d["template"] = traits.map(lambda x: x[0]), traits.map(lambda x: x[1])
                for (tpl, sp), s in d.groupby(["template", "speed"]):
                    ax.scatter(s.y_true, s.y_pred, s=4, alpha=0.45, lw=0, marker=markers.get(sp, "o"),
                               color=TEMPLATE_COLOR.get(tpl, PALETTE["neutral_mid"]), rasterized=True,
                               label=f"{TEMPLATE_LABEL.get(tpl, tpl)} · {sp:g} m/s" if j == 0 else None)
                lim = [min(d.y_true.min(), d.y_pred.min()), max(d.y_true.max(), d.y_pred.max())]
                ax.plot(lim, lim, ls="--", color=PALETTE["neutral_dark"], lw=0.7)
                r = scores[(scores.task == t) & (scores.scheme.str.startswith("外部检验"))].iloc[0]
                ax.set_title(f"{target_label(t)}\n外部 skill={r.skill:+.2f} R²={r.R2:.2f}", fontsize=7)
                ax.set_xlabel("仿真实际值")
                panel_label(ax, LETTERS[j], x=-0.28, y=1.02)
            axes[0, 0].set_ylabel("预测值（模型从未见过这些轨迹）")
            fig.legend(fontsize=6, ncols=6, loc="upper center", bbox_to_anchor=(0.5, -0.02), markerscale=3)
            footnote(fig, foot + " 用 27 条开发轨迹训练，在 12 条选择轨迹上每个任务只评一次；颜色为动作模板，形状为车速。", y=-0.12)
            save(fig, fig_dir / "fig08_外部检验_预测vs实际.png")

    # 8 学习曲线
    if lc_rows:
        lc = pd.DataFrame(lc_rows)
        ts = lc.task.unique().tolist()
        fig, axes = plt.subplots(1, len(ts), figsize=(1.85 * len(ts) + 0.6, 2.4), squeeze=False)
        fig.subplots_adjust(wspace=0.5)
        for j, (ax, t) in enumerate(zip(axes[0], ts)):
            d = lc[lc.task == t]
            col = "MAE_group_equal" if "MAE_group_equal" in d and d["MAE_group_equal"].notna().any() else "Brier"
            g = d.groupby("n_traj")[col].agg(["mean", "min", "max"])
            ax.plot(g.index, g["mean"], marker="o", ms=3, lw=1.1, color=PALETTE["blue_main"], label=f"{d.model.iloc[0]}")
            ax.fill_between(g.index, g["min"], g["max"], alpha=0.2, color=PALETTE["blue_main"], lw=0)
            bcol = "baseline_MAE_group_equal" if col == "MAE_group_equal" else "baseline_Brier"
            gb = d.groupby("n_traj")[bcol].mean()
            ax.plot(gb.index, gb.values, ls="--", lw=0.9, color=PALETTE["neutral_mid"], label="基线")
            ax.set_title(target_label(t), fontsize=7)
            ax.set_xlabel("每折训练用轨迹数")
            ax.set_ylabel(f"留出折 {'每轨迹等权 MAE' if col == 'MAE_group_equal' else 'Brier'}", fontsize=6.5)
            ax.legend(fontsize=6, loc="center right")
            panel_label(ax, LETTERS[j], x=-0.3, y=1.02)
        footnote(fig, foot + f" 学习曲线只在开发集内部完成（{fam.main_scheme}，每折从训练轨迹中抽样），外部集不参与；"
                             "模型类别与超参数与最终模型一致。每个规模抽 2 次，阴影为最小–最大。曲线变平表示再加同类轨迹收益有限。", y=-0.06)
        save(fig, fig_dir / "fig09_学习曲线.png")

    # 9 PDP
    if pdp_store:
        ts = list(pdp_store)
        feats = [f for f in ("EXIT_W_s", "margin_m", "confirmation_s", "noise_level") if any(f in pdp_store[t] for t in ts)]
        fig, axes = plt.subplots(len(ts), len(feats) + 1, figsize=(1.45 * (len(feats) + 1) + 0.6, 1.5 * len(ts) + 0.4),
                                 squeeze=False)
        fig.subplots_adjust(wspace=0.55, hspace=0.6)
        cmap = plt.get_cmap(SEQ_CMAP)
        for i, t in enumerate(ts):
            for j, f in enumerate(feats):
                if f in pdp_store[t]:
                    axes[i, j].plot(pdp_store[t][f]["grid"], pdp_store[t][f]["avg"], marker="o", ms=3, lw=1.0,
                                    color=PALETTE["blue_main"])
                if i == len(ts) - 1:
                    axes[i, j].set_xlabel(FEATURE_LABEL.get(f, f), fontsize=6.5)
                axes[i, j].tick_params(labelsize=5.5)
            axes[i, 0].set_ylabel(target_label(t), fontsize=6)
            panel_label(axes[i, 0], LETTERS[i], x=-0.75, y=1.0)
            two = pdp_store[t].get("margin_m×confirmation_s")
            ax2 = axes[i, -1]
            if two:
                vals = np.array(two["avg"])
                ax2.imshow(vals.T, origin="lower", cmap=cmap, aspect="auto")
                ax2.set_xticks(range(len(two["grid"][0])), [f"{v:g}" for v in two["grid"][0]], fontsize=5.5)
                ax2.set_yticks(range(len(two["grid"][1])), [f"{v:g}" for v in two["grid"][1]], fontsize=5.5)
                vmin, vmax = vals.min(), vals.max()
                for a in range(len(two["grid"][0])):
                    for b in range(len(two["grid"][1])):
                        frac = 0.5 if vmax == vmin else (vals[a][b] - vmin) / (vmax - vmin)
                        ax2.text(a, b, f"{vals[a][b]:.2f}", ha="center", va="center", fontsize=5.5,
                                 color="white" if is_dark(cmap(frac)) else "black")
                for sp in ax2.spines.values():
                    sp.set_visible(False)
                if i == len(ts) - 1:
                    ax2.set_xlabel("膨胀 (m) × 确认 (s)", fontsize=6.5)
            else:
                ax2.set_axis_off()
        footnote(fig, foot + " 部分依赖图：其他输入保持数据中的分布，只改变横轴变量时模型预测的平均值；最右列为膨胀 × 确认的二维部分依赖。"
                             "描述的是模型学到的规律，不等于因果效应。", y=-0.02)
        save(fig, fig_dir / "fig10_部分依赖_后处理.png")


def replot_from_results(folder: str | Path):
    """不重新训练：读取某个模型族 results/ 中保存的结果，重画该族的全部图。"""
    import runpy
    import shutil

    d = Path(folder) if Path(folder).is_absolute() else ROOT / folder
    fam = runpy.run_path(str(d / "train.py"), run_name="replot")["fam"]
    res = d / "results"
    scores = pd.read_csv(res / "scores.csv")
    tiers = pd.read_csv(res / "tiers.csv")
    imp = pd.read_csv(res / "permutation_importance.csv")
    segs = pd.read_csv(res / "segment_errors.csv") if (res / "segment_errors.csv").exists() else pd.DataFrame()
    oof_all = pd.read_csv(res / "oof_best_and_baseline.csv.gz", low_memory=False)
    oof = {t: {s: g.drop(columns=["task", "scheme"]).reset_index(drop=True) for s, g in gt.groupby("scheme")}
           for t, gt in oof_all.groupby("task")}
    ext = {}
    if (res / "external_predictions.csv").exists():
        e = pd.read_csv(res / "external_predictions.csv", low_memory=False)
        ext = {t: g.drop(columns=["task"]).reset_index(drop=True) for t, g in e.groupby("task")}
    cls = {}
    if (res / "confusion_matrices.json").exists():
        for t, v in json.loads((res / "confusion_matrices.json").read_text(encoding="utf-8")).items():
            src = ext[t] if t in ext else oof[t][fam.main_scheme]
            cls[t] = {"source": v["source"], "confusion": {k: x for k, x in v.items() if k != "source"},
                      "y": src.y_true.to_numpy().astype(int), "p": src.y_pred.to_numpy()}
    lc = pd.read_csv(res / "learning_curve.csv").to_dict("records") if (res / "learning_curve.csv").exists() else []
    pdp = json.loads((res / "pdp.json").read_text(encoding="utf-8")) if (res / "pdp.json").exists() else {}
    if (d / "figures").exists():
        shutil.rmtree(d / "figures")
    family_figures(fam, scores, tiers, imp, oof, ext, cls, lc, pdp, segs)
    return sorted((d / "figures").glob("*.png"))


if __name__ == "__main__":
    import sys

    for folder in sys.argv[1:] or FAMILY_FOLDERS:
        files = replot_from_results(folder)
        print(f"{folder}: {len(files)} 张图")
