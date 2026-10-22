"""每个模型族的标准图。中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FEATURE_LABEL, HEADER, SAFETY_RECALL, target_label
from .plotting import MODEL_COLOR, TIER_COLOR, footnote, plt, save


def _key_tasks(fam, tiers, kind=None):
    ok = [t.target for t in fam.tasks if t.key and (kind is None or t.kind == kind) and t.target in set(tiers.task)]
    if not ok:
        ok = [t for t in tiers.task if kind is None or tiers.set_index("task").at[t, "kind"] == kind][:4]
    return ok[:4]


def family_figures(fam, scores, tiers, imp, oof, ext, cls, lc_rows, pdp_store, segs):
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
    fig, ax = plt.subplots(figsize=(max(9, 1.15 * len(tasks)), 4.8))
    x = np.arange(len(tasks))
    w = 0.8 / max(1, len(models))
    for k, m in enumerate(models):
        v = [main[(main.task == t) & (main.model == m)].skill.mean() for t in tasks]
        ax.bar(x + (k - (len(models) - 1) / 2) * w, v, w, color=MODEL_COLOR.get(m, "#999"), label=f"{m}（{fam.main_scheme}）")
    marks = {s: mk for s, mk in zip([s for s in scores.scheme.unique() if s != fam.main_scheme], ["D", "^", "s", "v"])}
    for s, mk in marks.items():
        sub = scores[scores.scheme == s]
        v = [sub[(sub.task == t) & (sub.model == best_of[t])].skill.mean() for t in tasks]
        ax.scatter(x, v, marker=mk, color="k", s=22, zorder=3, label=f"最优模型 · {s}")
    ax.axhline(0, color="k", lw=0.8)
    ax.axhline(0.3, color="#2ca02c", ls=":", lw=1)
    ax.set_xticks(x, [f"{target_label(t)}\n[{tier_of[t]}]" for t in tasks], fontsize=7, rotation=30, ha="right")
    for lbl, t in zip(ax.get_xticklabels(), tasks):
        lbl.set_color(TIER_COLOR[tier_of[t]])
    ax.set_ylabel("相对基线的改善 skill")
    ax.set_ylim(min(-0.3, np.nanmin(main.skill) - 0.05), 1.0)
    ax.set_title(f"{fam.name} {fam.title}：各任务的模型对比（[ ] 内为临时模型表现分档）")
    ax.legend(fontsize=7, ncol=2, loc="lower left")
    ax.grid(axis="y", alpha=0.3)
    footnote(fig, foot + " 虚线为 A 档 skill 阈值 0.3；回归 skill=1−MAE/MAE基线，分类 skill=1−Brier/Brier基线。"
                         "柱为开发集交叉验证成绩，最优模型类别按同一成绩选出，略偏乐观；分档只衡量对纠错前评分的预测能力，不是科研准入。", y=-0.12)
    save(fig, fig_dir / "fig01_模型对比与分档.png")

    # 2 预测 vs 实际（主方案折外）
    reg_keys = _key_tasks(fam, tiers, "reg")
    if reg_keys:
        fig, axes = plt.subplots(1, len(reg_keys), figsize=(4.2 * len(reg_keys), 4), squeeze=False)
        for ax, t in zip(axes[0], reg_keys):
            d = oof[t][fam.main_scheme]
            ax.scatter(d.y_true, d.y_pred, s=5, alpha=0.35, color=TIER_COLOR[tier_of[t]])
            lim = [min(d.y_true.min(), d.y_pred.min()), max(d.y_true.max(), d.y_pred.max())]
            ax.plot(lim, lim, "k--", lw=0.8)
            r = tiers.set_index("task").loc[t]
            ax.set_title(f"{target_label(t)}\n{r.model} R²={r.main_R2:.2f} [{r.tier}]", fontsize=9)
            ax.set_xlabel("仿真实际值")
            ax.grid(alpha=0.3)
        axes[0, 0].set_ylabel("留出轨迹预测值")
        footnote(fig, foot + f" {fam.main_scheme} 折外预测。", y=-0.06)
        save(fig, fig_dir / "fig02_预测vs实际_折外.png")

        # 3 残差诊断
        fig, axes = plt.subplots(2, len(reg_keys), figsize=(4.2 * len(reg_keys), 7), squeeze=False)
        for j, t in enumerate(reg_keys):
            d = oof[t][fam.main_scheme]
            res = d.y_true - d.y_pred
            axes[0, j].scatter(d.y_pred, res, s=5, alpha=0.35)
            axes[0, j].axhline(0, color="k", lw=0.8)
            axes[0, j].set_title(target_label(t), fontsize=9)
            axes[0, j].set_xlabel("预测值")
            axes[1, j].hist(res, bins=50, color="#55a868")
            axes[1, j].set_xlabel(f"残差（偏度 {pd.Series(res).skew():.2f}）")
        axes[0, 0].set_ylabel("残差 = 实际 − 预测")
        axes[1, 0].set_ylabel("行数")
        footnote(fig, foot, y=-0.03)
        save(fig, fig_dir / "fig03_残差诊断.png")

        # 4 分段误差
        if not segs.empty:
            seg_names = [s for s in ("condition", "template", "variant", "config_id") if s in set(segs.segment)]
            fig, axes = plt.subplots(len(reg_keys), len(seg_names), figsize=(5 * len(seg_names), 3 * len(reg_keys)), squeeze=False)
            fig.subplots_adjust(wspace=0.75, hspace=0.45)
            for i, t in enumerate(reg_keys):
                for j, s in enumerate(seg_names):
                    d = segs[(segs.task == t) & (segs.segment == s)].sort_values("MAE")
                    axes[i, j].barh([str(v)[:26] for v in d.value], d.MAE, color="#4c72b0")
                    axes[i, j].tick_params(axis="y", labelsize=6)
                    if i == 0:
                        axes[i, j].set_title(f"按 {s} 分段", fontsize=9)
                    if j == 0:
                        axes[i, j].set_ylabel(target_label(t), fontsize=8)
                    axes[i, j].set_xlabel("MAE", fontsize=8)
            footnote(fig, foot + " 主方案折外误差按分段统计；最难预测的前 10 个轨迹×条件见 results/segment_errors.csv。", y=-0.01)
            save(fig, fig_dir / "fig04_分段误差.png")

    # 5 置换重要性
    keys = _key_tasks(fam, tiers)
    if keys and not imp.empty:
        fig, axes = plt.subplots(1, len(keys), figsize=(4.8 * len(keys), 4.8), squeeze=False)
        fig.subplots_adjust(wspace=0.85)
        for ax, t in zip(axes[0], keys):
            d = imp[imp.task == t].sort_values("importance_mean")
            d = d[d.importance_mean.abs() > 1e-12]
            ax.barh(d.label, d.importance_mean, xerr=d.importance_fold_std, capsize=2,
                    color=np.where(d.is_group, "#dd8452", "#4c72b0"))
            ax.set_title(f"{target_label(t)}\n{best_of[t]} [{tier_of[t]}]", fontsize=9)
            ax.set_xlabel("置换后误差增加量", fontsize=8)
            ax.tick_params(axis="y", labelsize=7)
            ax.grid(axis="x", alpha=0.3)
        footnote(fig, foot + " 橙色为成组置换；在留出折上计算，误差线为跨折标准差。C 档任务的重要性不作解释。", y=-0.04)
        save(fig, fig_dir / "fig05_置换重要性.png")

    # 6 分类：混淆矩阵与 ROC/PR
    if cls:
        names = list(cls)
        fig, axes = plt.subplots(len(names), 2, figsize=(8, 3.6 * len(names)), squeeze=False)
        fig.subplots_adjust(hspace=0.6)
        for i, t in enumerate(names):
            for j, (tname, v) in enumerate(cls[t]["confusion"].items()):
                cm = np.array(v["matrix"])
                axes[i, j].imshow(cm, cmap="Blues")
                for a in range(2):
                    for b in range(2):
                        axes[i, j].text(b, a, str(cm[a, b]), ha="center", va="center", fontsize=11,
                                        color="white" if cm[a, b] > cm.max() / 2 else "black")
                axes[i, j].set_xticks([0, 1], ["预测否", "预测是"])
                axes[i, j].set_yticks([0, 1], ["实际否", "实际是"])
                lo, hi = v.get("threshold_range", [v["threshold"], v["threshold"]])
                thr_txt = f"{v['threshold']:.3f}" if abs(hi - lo) < 1e-9 else f"{lo:.3f}–{hi:.3f}"
                axes[i, j].set_title(f"{target_label(t)} · {tname}\n阈值 {thr_txt}  召回 {v['recall']:.2f}  精确率 {v['precision']:.2f}", fontsize=8)
        footnote(fig, foot + f" 数据来源：{cls[names[0]]['source']}。安全优先阈值的目标召回为 {SAFETY_RECALL:.0%}，"
                             "阈值从不在被评估的同一批预测上选择，因此实际召回可能低于目标。", y=-0.01)
        save(fig, fig_dir / "fig06_混淆矩阵.png")

        from sklearn.metrics import auc, precision_recall_curve, roc_curve
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
        for t in names:
            y, p = cls[t]["y"], cls[t]["p"]
            if len(np.unique(y)) < 2:
                continue
            fpr, tpr, _ = roc_curve(y, p)
            pr, rc, _ = precision_recall_curve(y, p)
            axes[0].plot(fpr, tpr, label=f"{target_label(t)} AUC={auc(fpr, tpr):.2f}")
            axes[1].plot(rc, pr, label=f"{target_label(t)} 正例比例={y.mean():.2f}")
        axes[0].plot([0, 1], [0, 1], "k--", lw=0.8)
        axes[0].set(xlabel="假阳性率", ylabel="真阳性率（召回）", title="ROC 曲线")
        axes[1].set(xlabel="召回", ylabel="精确率", title="PR 曲线")
        for ax in axes:
            ax.legend(fontsize=7)
            ax.grid(alpha=0.3)
        footnote(fig, foot + f" 数据来源：{cls[names[0]]['source']}。", y=-0.04)
        save(fig, fig_dir / "fig07_ROC_PR.png")

    # 7 外部检验
    if ext:
        ks = [t for t in reg_keys if t in ext]
        if ks:
            fig, axes = plt.subplots(1, len(ks), figsize=(4.3 * len(ks), 4.2), squeeze=False)
            for ax, t in zip(axes[0], ks):
                d = ext[t]
                cases = sorted(d.case_id.unique())
                cmap = plt.get_cmap("tab20")
                for c_i, c in enumerate(cases):
                    s = d[d.case_id == c]
                    ax.scatter(s.y_true, s.y_pred, s=6, alpha=0.5, color=cmap(c_i % 20), label=c if t == ks[0] else None)
                lim = [min(d.y_true.min(), d.y_pred.min()), max(d.y_true.max(), d.y_pred.max())]
                ax.plot(lim, lim, "k--", lw=0.8)
                r = scores[(scores.task == t) & (scores.scheme.str.startswith("外部检验"))].iloc[0]
                ax.set_title(f"{target_label(t)}\n外部 skill={r.skill:+.2f} R²={r.R2:.2f}", fontsize=9)
                ax.set_xlabel("仿真实际值")
                ax.grid(alpha=0.3)
            axes[0, 0].set_ylabel("预测值（模型从未见过这些轨迹）")
            fig.legend(fontsize=6, ncol=6, loc="lower center", bbox_to_anchor=(0.5, -0.16))
            footnote(fig, foot + " 用 27 条开发轨迹训练，在 12 条选择轨迹上只评一次；颜色区分轨迹。", y=-0.2)
            save(fig, fig_dir / "fig08_外部检验_预测vs实际.png")

    # 8 学习曲线
    if lc_rows:
        lc = pd.DataFrame(lc_rows)
        ts = lc.task.unique().tolist()
        fig, axes = plt.subplots(1, len(ts), figsize=(4 * len(ts), 3.8), squeeze=False)
        for ax, t in zip(axes[0], ts):
            d = lc[lc.task == t]
            col = "MAE_group_equal" if "MAE_group_equal" in d and d["MAE_group_equal"].notna().any() else "Brier"
            g = d.groupby("n_traj")[col].agg(["mean", "min", "max"])
            ax.plot(g.index, g["mean"], marker="o", label=f"{d.model.iloc[0]}")
            ax.fill_between(g.index, g["min"], g["max"], alpha=0.2)
            bcol = "baseline_MAE_group_equal" if col == "MAE_group_equal" else "baseline_Brier"
            gb = d.groupby("n_traj")[bcol].mean()
            ax.plot(gb.index, gb.values, ls="--", color="#999", label="基线")
            ax.set_title(target_label(t), fontsize=9)
            ax.set_xlabel("每折训练用轨迹数")
            ax.set_ylabel(f"开发集留出折 {'每轨迹等权 MAE' if col == 'MAE_group_equal' else 'Brier'}")
            ax.legend(fontsize=7)
            ax.grid(alpha=0.3)
        footnote(fig, foot + f" 学习曲线只在开发集内部完成（{fam.main_scheme}，每折从训练轨迹中抽样），外部集不参与；"
                             "模型类别与超参数与最终模型一致。每个规模抽 2 次，阴影为最小–最大。曲线变平表示再加同类轨迹收益有限。", y=-0.05)
        save(fig, fig_dir / "fig09_学习曲线.png")

    # 9 PDP
    if pdp_store:
        ts = list(pdp_store)
        feats = [f for f in ("EXIT_W_s", "margin_m", "confirmation_s", "noise_level") if any(f in pdp_store[t] for t in ts)]
        fig, axes = plt.subplots(len(ts), len(feats) + 1, figsize=(3.4 * (len(feats) + 1), 2.9 * len(ts)), squeeze=False)
        for i, t in enumerate(ts):
            for j, f in enumerate(feats):
                if f in pdp_store[t]:
                    axes[i, j].plot(pdp_store[t][f]["grid"], pdp_store[t][f]["avg"], marker="o")
                if i == len(ts) - 1:
                    axes[i, j].set_xlabel(FEATURE_LABEL.get(f, f))
                axes[i, j].grid(alpha=0.3)
            axes[i, 0].set_ylabel(target_label(t), fontsize=8)
            two = pdp_store[t].get("margin_m×confirmation_s")
            if two:
                im = axes[i, -1].imshow(np.array(two["avg"]).T, origin="lower", cmap="viridis", aspect="auto")
                axes[i, -1].set_xticks(range(len(two["grid"][0])), [f"{v:g}" for v in two["grid"][0]])
                axes[i, -1].set_yticks(range(len(two["grid"][1])), [f"{v:g}" for v in two["grid"][1]])
                for a in range(len(two["grid"][0])):
                    for b in range(len(two["grid"][1])):
                        axes[i, -1].text(a, b, f"{two['avg'][a][b]:.2f}", ha="center", va="center", fontsize=7, color="w")
                if i == len(ts) - 1:
                    axes[i, -1].set_xlabel("膨胀 (m) × 确认 (s)")
        footnote(fig, foot + " 部分依赖图：其他输入保持数据中的分布，只改变横轴变量时模型预测的平均值；描述模型学到的规律，不等于因果效应。", y=-0.02)
        save(fig, fig_dir / "fig10_部分依赖_后处理.png")
