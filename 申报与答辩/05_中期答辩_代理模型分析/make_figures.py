"""P1/P2 图表：已有实验的规律 + 代理模型结果 + 标签区间旁证。

每张图的标题或脚注都写明数据口径（标签无关 / 纠错前配对差 / 纠错前绝对值）。
作者标记：Kiro。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import (
    DEEPSEEK_BOUNDS, FEATURE_LABEL, FIGURES, METHOD_LABEL, TABLES, ensure_dirs, setup_matplotlib,
)

plt = setup_matplotlib()

METHOD_COLOR = {"hold": "#7f7f7f", "linear": "#1f77b4", "damped_linear": "#2ca02c", "bounded_second_order": "#d62728"}
CONFIG_ORDER = (
    ["hold"]
    + [f"linear_g{g}" for g in ("050", "075", "100", "125", "150", "200")]
    + [f"damped_d{d}" for d in ("0125", "0250", "0500", "1000", "2000", "4000")]
    + [f"second_a{a}" for a in ("0050", "0100", "0200", "0250", "0500", "1000")]
)
FOOT_PRE = "数据：S1，27 条轨迹（转角峰值均为 10°），接触标签纠错前评分"
FOOT_FREE = "数据：S1，27 条轨迹（转角峰值均为 10°）；端点误差与接触标签无关"


def config_method(cfg: str) -> str:
    return {"hold": "hold", "linear": "linear", "damped": "damped_linear", "second": "bounded_second_order"}[cfg.split("_")[0]]


def footnote(fig, text, y=-0.02):
    fig.text(0.01, y, text, fontsize=8, color="#555555", ha="left", va="top")


def fig_geom_error(s1):
    fig, ax = plt.subplots(figsize=(11, 4.2))
    data = [s1.loc[s1.config_id == c, "geom_2.0_mean"].to_numpy() for c in CONFIG_ORDER]
    bp = ax.boxplot(data, patch_artist=True, widths=0.6, showfliers=False)
    for patch, c in zip(bp["boxes"], CONFIG_ORDER):
        patch.set_facecolor(METHOD_COLOR[config_method(c)])
        patch.set_alpha(0.6)
    ax.set_xticks(range(1, len(CONFIG_ORDER) + 1), CONFIG_ORDER, rotation=45, ha="right")
    ax.set_ylabel("2 s 右缘端点误差均值 (m)")
    ax.set_title("预测误差随外推强度变化：适度外推最小，过强外推回升")
    handles = [plt.Rectangle((0, 0), 1, 1, color=METHOD_COLOR[m], alpha=0.6) for m in METHOD_COLOR]
    ax.legend(handles, [METHOD_LABEL[m] for m in METHOD_COLOR], ncol=4, loc="upper left")
    ax.grid(axis="y", alpha=0.3)
    footnote(fig, FOOT_FREE + "；箱体为 27 条轨迹的分布", y=-0.2)
    fig.savefig(FIGURES / "fig01_端点误差_各配置.png")
    plt.close(fig)


def fig_paired_right(s1):
    d = s1[s1.method != "hold"]
    order = [c for c in CONFIG_ORDER if c != "hold"]
    g = d.groupby("config_id")["d_right_pct"]
    mean, lo, hi = g.mean()[order], g.min()[order], g.max()[order]
    better = d.groupby("config_id")["d_right_pct"].apply(lambda x: int((x < 0).sum()))[order]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    x = np.arange(len(order))
    ax.bar(x, mean, color=[METHOD_COLOR[config_method(c)] for c in order], alpha=0.7)
    ax.errorbar(x, mean, yerr=[mean - lo, hi - mean], fmt="none", ecolor="k", capsize=3, lw=0.8)
    for xi, b in enumerate(better):
        ax.text(xi, 0.32, f"{b}/27", ha="center", va="bottom", fontsize=7.5,
                color="k" if b == 27 else "#d62728")
    ax.set_ylim(lo.min() - 0.2, 0.6)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x, order, rotation=45, ha="right")
    ax.set_ylabel("RIGHT 不足率 − 保持 (pp)")
    ax.set_title("同一轨迹下与保持基线的配对差：数字为优于保持的轨迹数")
    ax.grid(axis="y", alpha=0.3)
    footnote(fig, FOOT_PRE + "；柱为均值，误差线为 27 条轨迹的最小–最大；RIGHT 不足 = 窗口漏报或提前量 < 1 s", y=-0.2)
    fig.savefig(FIGURES / "fig02_配对迟报差_相对保持.png")
    plt.close(fig)


def fig_tradeoff(s1):
    d = s1.groupby("config_id").agg(r=("right_pct", "mean"), fp=("negative_fp_pct", "mean"),
                                   fpw=("negative_fp_pct", "max")).loc[CONFIG_ORDER]
    label_only = {"hold", "damped_d0125", "damped_d0250", "damped_d1000", "linear_g050",
                  "linear_g125", "linear_g150", "linear_g200", "second_a0200", "second_a1000"}
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for cfg, row in d.iterrows():
        m = config_method(cfg)
        ax.scatter(row.fp, row.r, s=55, color=METHOD_COLOR[m], edgecolor="k", lw=0.5, zorder=3)
        if cfg in label_only:
            ax.annotate(cfg, (row.fp, row.r), fontsize=7, xytext=(4, 4), textcoords="offset points")
    for m in METHOD_COLOR:
        sub = d[[config_method(c) == m for c in d.index]]
        if len(sub) > 1:
            ax.plot(sub.fp, sub.r, color=METHOD_COLOR[m], lw=1, alpha=0.6)
    ax.set_xlabel("近场点误报率均值 (%)")
    ax.set_ylabel("RIGHT 不足率均值 (%)")
    ax.set_title("迟报与误报的权衡：没有同时最优的配置")
    handles = [plt.Line2D([], [], marker="o", ls="", color=METHOD_COLOR[m]) for m in METHOD_COLOR]
    ax.legend(handles, [METHOD_LABEL[m] for m in METHOD_COLOR], loc="upper right")
    ax.grid(alpha=0.3)
    footnote(fig, FOOT_PRE + "；绝对值仅作描述；每种方法内沿参数增大连线，部分点未标注以免重叠")
    fig.savefig(FIGURES / "fig03_迟报误报权衡.png")
    plt.close(fig)


def fig_drive_heatmap(s1):
    d = s1[s1.config_id == "damped_d1000"]
    vmin = d["d_right_pct"].min()
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    names = {"symmetric": "对称动作", "fast_entry": "较快入弯", "fast_return": "较快回正"}
    for ax, tpl in zip(axes, ("symmetric", "fast_entry", "fast_return")):
        p = d[d.template == tpl].pivot_table(index="v_B_mps", columns="base_rate_deg_s", values="d_right_pct")
        im = ax.imshow(p.to_numpy(), cmap="Greens_r", vmin=vmin, vmax=0, origin="lower")
        ax.set_xticks(range(p.shape[1]), [f"{c:g}" for c in p.columns])
        ax.set_yticks(range(p.shape[0]), [f"{v:g}" for v in p.index])
        for i in range(p.shape[0]):
            for j in range(p.shape[1]):
                ax.text(j, i, f"{p.iat[i, j]:.2f}", ha="center", va="center", fontsize=9)
        ax.set_title(names[tpl])
        ax.set_xlabel("基准转角速率 r (°/s)")
    axes[0].set_ylabel("车速 v_B (m/s)")
    fig.colorbar(im, ax=axes, shrink=0.85, label="衰减线性 τ=1 s − 保持 (pp)")
    fig.suptitle("趋势外推的收益随车速和转向速率增大", x=0.43, y=1.02)
    footnote(fig, FOOT_PRE + "；越负表示相对保持基线迟报越少")
    fig.savefig(FIGURES / "fig04_驾驶因素_配对收益热图.png")
    plt.close(fig)


def fig_s2_noise(s2):
    pre_label = {"raw": "原始输入", "alpha_lp": "仅转角低通", "age_hold": "按测量年龄前推（无延迟时同原始）"}
    pre_color = {"raw": "#1f77b4", "alpha_lp": "#2ca02c", "age_hold": "#ff7f0e"}
    pre_style = {"raw": dict(ls="-", lw=3, alpha=0.5), "alpha_lp": dict(ls="-"), "age_hold": dict(ls="--")}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    noise = s2[(s2.delay_ms == 0)]
    for pre in ("raw", "alpha_lp", "age_hold"):
        g = noise[noise.preprocessing == pre].groupby("noise_level")["negative_fp_pct"]
        axes[0].plot(g.mean().index, g.mean(), marker="o", color=pre_color[pre], label=pre_label[pre], **pre_style[pre])
        if pre != "age_hold":
            axes[0].fill_between(g.mean().index, g.min(), g.max(), color=pre_color[pre], alpha=0.12)
    axes[0].axhline(5, color="r", ls="--", lw=1, label="研究预算 5%")
    axes[0].set_xlabel("噪声倍率（α 0.15°、φ 0.25°、v 0.04 m/s 为 1 倍）")
    axes[0].set_ylabel("近场点误报率 (%)")
    axes[0].set_title("误报主要由输入噪声决定")
    axes[0].legend(fontsize=8)
    delay = s2[(s2.noise_level == 0)]
    for pre in ("raw", "alpha_lp", "age_hold"):
        g = delay[delay.preprocessing == pre].groupby("delay_ms")["right_pct"]
        axes[1].plot(g.mean().index, g.mean(), marker="o", color=pre_color[pre], label=pre_label[pre].split("（")[0])
    axes[1].set_xlabel("纯延迟 (ms)")
    axes[1].set_ylabel("RIGHT 不足率均值 (%)")
    axes[1].set_title("延迟主要推高迟报")
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.3)
    footnote(fig, "数据：S2，6 条代表轨迹 × 3 方法，噪声各 3 个种子；接触标签纠错前评分，绝对值仅作描述；阴影为最小–最大")
    fig.savefig(FIGURES / "fig05_噪声与延迟响应.png")
    plt.close(fig)


def fig_model_skill(scores):
    tasks = scores.task.unique().tolist()
    models = ["Ridge(二阶交互)", "随机森林", "梯度提升"]
    colors = ["#9467bd", "#8c564b", "#17becf"]
    main = scores[scores.scheme.isin(["按轨迹5折", "留一轨迹"])]
    alt = scores[scores.scheme == "留一动作模板"]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    x = np.arange(len(tasks))
    w = 0.26
    for k, (m, c) in enumerate(zip(models, colors)):
        v = main[main.model == m].set_index("task").loc[tasks, "skill_vs_baseline"]
        ax.bar(x + (k - 1) * w, v, w, color=c, label=f"{m}（按轨迹留出）")
        a = alt[alt.model == m].set_index("task").reindex(tasks)["skill_vs_baseline"]
        ax.scatter(x + (k - 1) * w, a, marker="D", s=18, color="k", zorder=3,
                   label="留一动作模板" if k == 0 else None)
    labels = main[main.model == "均值基线"].set_index("task").loc[tasks]
    ax.set_xticks(x, [f"{t}\n({labels.at[t, 'label_dependency']})" for t in tasks], fontsize=7.5)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("相对均值基线的 MAE 改善\n1 − MAE/MAE基线（每条轨迹等权）")
    ax.set_title("代理模型在未见轨迹上的表现")
    ax.legend(fontsize=8, ncol=2, loc="lower left")
    ax.grid(axis="y", alpha=0.3)
    footnote(fig, "S1：27 条轨迹，GroupKFold 5 折 + 留一动作模板；S2：6 条轨迹留一轨迹。固定超参数，未做自动调参")
    fig.savefig(FIGURES / "fig06_代理模型_相对基线改善.png")
    plt.close(fig)


def fig_oof(oof, best, scores):
    show = ["S1_geom2s_mean", "S1_d_right_pct", "S1_d_negative_fp_pct", "S2_negative_fp_pct"]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.9))
    for ax, t in zip(axes, show):
        scheme = "按轨迹5折" if t.startswith("S1") else "留一轨迹"
        d = oof[(oof.task == t) & (oof.model == best[t]) & (oof.scheme == scheme)]
        ax.scatter(d.y_true, d.y_pred, s=8, alpha=0.5)
        lim = [min(d.y_true.min(), d.y_pred.min()), max(d.y_true.max(), d.y_pred.max())]
        ax.plot(lim, lim, "k--", lw=0.8)
        r = scores[(scores.task == t) & (scores.model == best[t]) & (scores.scheme == scheme)].iloc[0]
        ax.set_title(f"{r.target}\n{best[t]}  R²={r.R2_oof:.2f}", fontsize=9)
        ax.set_xlabel("仿真实际值")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("留出轨迹预测值")
    footnote(fig, "均为留出轨迹上的预测（out-of-fold）；端点误差标签无关，配对差为纠错前评分，S2 误报为纠错前绝对值")
    fig.savefig(FIGURES / "fig07_留出预测_对比实际.png")
    plt.close(fig)


def fig_importance(imp, scores):
    show = ["S1_geom2s_mean", "S1_d_right_pct", "S1_d_negative_fp_pct", "S2_negative_fp_pct"]
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.2))
    fig.subplots_adjust(wspace=0.75)
    for ax, t in zip(axes, show):
        d = imp[imp.task == t].sort_values("importance_mean")
        d = d[d.importance_mean.abs() > 0]
        ax.barh([FEATURE_LABEL.get(f, f) for f in d.feature], d.importance_mean,
                xerr=d.importance_fold_std, color="#4c72b0", alpha=0.8, capsize=2)
        target = scores[scores.task == t].iloc[0].target
        ax.set_title(f"{target}\n（{d.model.iloc[0]}）", fontsize=9)
        ax.set_xlabel("置换后 MAE 增加量")
        ax.grid(axis="x", alpha=0.3)
    footnote(fig, "在留出轨迹上计算的置换重要性，误差线为跨折标准差；动作模板由入弯/回正速率唯一确定，单独置换时重要性近 0；"
                  "转角峰值等固定量未参与排序")
    fig.savefig(FIGURES / "fig08_置换重要性.png")
    plt.close(fig)


def fig_label_interval():
    d = pd.read_csv(DEEPSEEK_BOUNDS)
    lo_hi = d["paired_pct"].str.split(r"\.\.", regex=True, expand=True).astype(float)
    d["lo"], d["hi"] = lo_hi[0], lo_hi[1]
    d = d.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8, 6))
    name = {"damped_linear_g1000_d1000": "衰减线性 τ=1 s", "linear_g0500_d0500": "线性 g=0.5"}
    for i, r in d.iterrows():
        color = "#2ca02c" if r.hi < 0 else "#7f7f7f"
        ax.plot([r.lo, r.hi], [i, i], color=color, lw=4, solid_capstyle="butt")
        ax.plot([r.lo, r.hi], [i, i], "|", color="k", ms=8)
        if r.hi - r.lo < 1e-9:  # 区间宽度为 0：两种方法的 RIGHT 不足完全相同
            ax.plot([r.lo], [i], "o", color=color, ms=5)
            ax.annotate("恰为 0", (r.lo, i), xytext=(6, -3), textcoords="offset points", fontsize=7)
    ax.set_yticks(range(len(d)), [f"{r.condition} · {name.get(r.method_A, r.method_A)}" for _, r in d.iterrows()],
                  fontsize=8)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("RIGHT 不足率配对差 A − 保持 (pp)，区间为标签不确定性下的上下界")
    ax.set_title("标签不确定性对配对结论的影响\n绿色：区间全在 0 以下（结论不受标签影响）；灰色：跨 0")
    ax.grid(axis="x", alpha=0.3)
    footnote(fig, "数据：DeepSeek 正向区间评分，v2_r2_symmetric 一条轨迹、70000 点、1854 帧，独立核验尚未进行")
    fig.savefig(FIGURES / "fig09_标签区间旁证.png")
    plt.close(fig)


def main():
    ensure_dirs()
    s1 = pd.read_csv(TABLES / "s1_rows.csv")
    s2 = pd.read_csv(TABLES / "s2_rows.csv")
    scores = pd.read_csv(TABLES / "model_scores.csv")
    oof = pd.read_csv(TABLES / "oof_predictions.csv")
    imp = pd.read_csv(TABLES / "permutation_importance.csv")
    best = pd.read_json(TABLES / "best_models.json", typ="series")["best_model_by_task"]
    fig_geom_error(s1)
    fig_paired_right(s1)
    fig_tradeoff(s1)
    fig_drive_heatmap(s1)
    fig_s2_noise(s2)
    fig_model_skill(scores)
    fig_oof(oof, best, scores)
    fig_importance(imp, scores)
    fig_label_interval()
    print("figures:", sorted(p.name for p in FIGURES.glob("*.png")))


if __name__ == "__main__":
    main()
