"""描述性图表（不依赖模型；按 nature-figure skill 规范）。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

fig01–04 来自 S1（预测方法），fig05 来自 S2 与 S4 状态估计筛选，fig06 来自 S3（后处理），
fig07 来自 S4 联合精化（趋势增益），fig12 来自 DeepSeek 的标签区间评分。
直接运行本文件或调用 main() 即可重画全部 8 张图。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common.config import DATA, DEEPSEEK_BOUNDS, HEADER  # noqa: E402
from common.plotting import (DIV_CMAP, METHOD_COLOR, METHOD_LABEL, PALETTE, apply_style, footnote, is_dark,  # noqa: E402
                             panel_label, plt, save)

OUT = Path(__file__).resolve().parent
CONFIG_ORDER = (["hold"] + [f"linear_g{g}" for g in ("050", "075", "100", "125", "150", "200")]
                + [f"damped_d{d}" for d in ("0125", "0250", "0500", "1000", "2000", "4000")]
                + [f"second_a{a}" for a in ("0050", "0100", "0200", "0250", "0500", "1000")])
F_S1 = HEADER + " 数据 S1（v3 口径，误报类数值略高于修正口径），27 条轨迹，转角峰值均为 10°。"


def cm(cfg):
    return {"hold": "hold", "linear": "linear", "damped": "damped_linear", "second": "bounded_second_order"}[cfg.split("_")[0]]


def _legend_methods(ax, loc="upper left", **kw):
    hs = [plt.Rectangle((0, 0), 1, 1, color=METHOD_COLOR[m], alpha=0.75) for m in METHOD_COLOR]
    ax.legend(hs, [METHOD_LABEL[m] for m in METHOD_COLOR], loc=loc, **kw)


def fig01(s1):
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    data = [s1.loc[s1.config_id == c, "geom_2.0_mean"].to_numpy() for c in CONFIG_ORDER]
    bp = ax.boxplot(data, patch_artist=True, widths=0.6, showfliers=False,
                    medianprops=dict(color=PALETTE["neutral_black"], lw=0.9), whiskerprops=dict(lw=0.6), capprops=dict(lw=0.6))
    for patch, c in zip(bp["boxes"], CONFIG_ORDER):
        patch.set_facecolor(METHOD_COLOR[cm(c)]); patch.set_alpha(0.7); patch.set_linewidth(0.6)
    ax.set_xticks(range(1, len(CONFIG_ORDER) + 1), CONFIG_ORDER, rotation=45, ha="right", fontsize=6.5)
    ax.set_ylabel("2 s 右缘端点误差均值 (m)")
    ax.set_title("预测误差随外推强度变化：适度外推最小，过强外推回升（与接触标签无关）", fontsize=8)
    _legend_methods(ax, ncols=4)
    footnote(fig, F_S1 + " 每个箱体是 27 条轨迹的分布；端点误差 = 预测的 2 s 后挂车右缘两端点与真实位置的最大距离，按评分时段内各帧平均。", y=-0.12)
    save(fig, OUT / "fig01_端点误差_各配置.png")


def fig02(s1):
    d = s1[s1.method != "hold"]
    order = [c for c in CONFIG_ORDER if c != "hold"]
    g = d.groupby("config_id")["d_hold_right_pct"]
    mean, lo, hi = g.mean()[order], g.min()[order], g.max()[order]
    better = g.apply(lambda x: int((x < 0).sum()))[order]
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    x = np.arange(len(order))
    ax.bar(x, mean, color=[METHOD_COLOR[cm(c)] for c in order], alpha=0.8)
    ax.errorbar(x, mean, yerr=[mean - lo, hi - mean], fmt="none", ecolor=PALETTE["neutral_black"], capsize=2, lw=0.7)
    for xi, b in enumerate(better):
        ax.text(xi, 0.32, f"{b}/27", ha="center", va="bottom", fontsize=6,
                color=PALETTE["neutral_black"] if b == 27 else PALETTE["red_strong"])
    ax.set_ylim(lo.min() - 0.2, 0.6)
    ax.axhline(0, color=PALETTE["neutral_black"], lw=0.8)
    ax.set_xticks(x, order, rotation=45, ha="right", fontsize=6.5)
    ax.set_ylabel("RIGHT 不足率 − 保持 (pp)")
    ax.set_title("同一轨迹下相对保持基线的配对差（越负越好）：上方数字为 27 条轨迹中优于保持的条数", fontsize=8)
    footnote(fig, F_S1 + " 柱为 27 条轨迹的均值，误差线为最小–最大；RIGHT 不足 = 窗口漏报或提前量 < 1 s；配对差在同一轨迹、同一组目标点上计算。", y=-0.12)
    save(fig, OUT / "fig02_配对迟报差_相对保持.png")


def fig03(s1):
    d = s1.groupby("config_id").agg(r=("right_pct", "mean"), fp=("negative_fp_pct", "mean")).loc[CONFIG_ORDER]
    lab = {"hold", "damped_d0125", "damped_d0250", "damped_d1000", "linear_g050", "linear_g125", "linear_g150",
           "linear_g200", "second_a0200", "second_a1000"}
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    for m in METHOD_COLOR:
        sub = d[[cm(c) == m for c in d.index]]
        if len(sub) > 1:
            ax.plot(sub.fp, sub.r, color=METHOD_COLOR[m], lw=0.9, alpha=0.7)
    for cfg, row in d.iterrows():
        ax.scatter(row.fp, row.r, s=22, color=METHOD_COLOR[cm(cfg)], edgecolor=PALETTE["neutral_black"], lw=0.4, zorder=3)
        if cfg in lab:
            ax.annotate(cfg, (row.fp, row.r), fontsize=5.5, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("近场点误报率均值 (%)"); ax.set_ylabel("RIGHT 不足率均值 (%)")
    ax.set_title("迟报与误报的权衡：没有同时最优的配置", fontsize=8)
    hs = [plt.Line2D([], [], marker="o", ls="", ms=4, color=METHOD_COLOR[m]) for m in METHOD_COLOR]
    ax.legend(hs, [METHOD_LABEL[m] for m in METHOD_COLOR], loc="upper right")
    footnote(fig, F_S1 + " 每个点是一个配置在 27 条轨迹上的均值；同一方法内按参数增大连线，部分点未标注以免重叠。绝对值仅作描述。")
    save(fig, OUT / "fig03_迟报误报权衡.png")


def fig04(s1):
    d = s1[s1.config_id == "damped_d1000"]
    vmin = d["d_hold_right_pct"].min()
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.5), sharey=True)
    fig.subplots_adjust(wspace=0.12)
    names = {"symmetric": "对称动作", "fast_entry": "较快入弯", "fast_return": "较快回正"}
    cmap = plt.get_cmap("Greens_r")
    for k, (ax, tpl) in enumerate(zip(axes, names)):
        p = d[d.template == tpl].pivot_table(index="v_B_mps", columns="base_rate_deg_s", values="d_hold_right_pct")
        im = ax.imshow(p.to_numpy(), cmap=cmap, vmin=vmin, vmax=0, origin="lower")
        ax.set_xticks(range(p.shape[1]), [f"{c:g}" for c in p.columns])
        ax.set_yticks(range(p.shape[0]), [f"{v:g}" for v in p.index])
        for i in range(p.shape[0]):
            for j in range(p.shape[1]):
                val = p.iat[i, j]
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if is_dark(cmap((val - vmin) / (0 - vmin))) else "black")
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title(names[tpl], fontsize=8); ax.set_xlabel("基准转角速率 r (°/s)")
        panel_label(ax, "abc"[k], x=-0.12, y=1.04)
    axes[0].set_ylabel("车速 v_B (m/s)")
    fig.colorbar(im, ax=axes, shrink=0.85, label="衰减线性 τ=1 s − 保持 (pp)")
    fig.suptitle("趋势外推的收益随车速和转向速率增大（越负 = 比保持迟报越少）", x=0.43, y=1.04, fontsize=8.5)
    footnote(fig, F_S1 + " 每格是一条轨迹上衰减线性 τ=1 s 与保持的 RIGHT 不足率配对差。", y=-0.04)
    save(fig, OUT / "fig04_驾驶因素_配对收益热图.png")


def fig05(s2, s4p):
    pre_label = {"raw": "原始输入", "alpha_lp": "仅转角低通", "age_hold": "按测量年龄前推（无延迟时同原始）"}
    pre_color = {"raw": PALETTE["neutral_dark"], "alpha_lp": PALETTE["blue_main"], "age_hold": PALETTE["teal"]}
    style = {"raw": dict(ls="-", lw=2.2, alpha=0.45), "alpha_lp": dict(ls="-", lw=1.1), "age_hold": dict(ls="--", lw=1.1)}
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7))
    fig.subplots_adjust(wspace=0.55)
    noise = s2[s2.delay_ms == 0]
    for p in ("raw", "alpha_lp", "age_hold"):
        g = noise[noise.processor == p].groupby("noise_level")["negative_fp_pct"]
        axes[0].plot(g.mean().index, g.mean(), marker="o", ms=3, color=pre_color[p], label=pre_label[p], **style[p])
        if p != "age_hold":
            axes[0].fill_between(g.mean().index, g.min(), g.max(), color=pre_color[p], alpha=0.12, lw=0)
    axes[0].axhline(5, color=PALETTE["red_strong"], ls="--", lw=0.8, label="研究预算 5%")
    axes[0].set(xlabel="噪声倍率", ylabel="近场点误报率 (%)")
    axes[0].set_title("S2：误报主要由输入噪声决定", fontsize=7.5)
    axes[0].legend(fontsize=5.5, loc="upper left")
    delay = s2[s2.noise_level == 0]
    for p in ("raw", "alpha_lp", "age_hold"):
        g = delay[delay.processor == p].groupby("delay_ms")["right_pct"]
        axes[1].plot(g.mean().index, g.mean(), marker="o", ms=3, color=pre_color[p], label=pre_label[p].split("（")[0],
                     **{k: v for k, v in style[p].items() if k != "alpha"})
    axes[1].set(xlabel="纯延迟 (ms)", ylabel="RIGHT 不足率均值 (%)")
    axes[1].set_title("S2：延迟主要推高迟报", fontsize=7.5)
    axes[1].legend(fontsize=5.5, loc="upper left")
    order = ["raw", "phi_ekf_q100", "phi_ekf_q025", "phi_ekf_q025_alphaLP050"]
    g = s4p.groupby("processor").agg(fp=("negative_fp_pct", "mean"), miss=("right_miss_rate", "mean"),
                                     anymiss=("any_window_miss", "sum")).reindex(order)
    x = np.arange(len(order))
    axes[2].bar(x - 0.2, g.fp, 0.4, color=PALETTE["blue_main"], label="近场点误报率均值 (%)")
    ax2 = axes[2].twinx()
    ax2.spines["right"].set_visible(True)
    ax2.bar(x + 0.2, g.miss, 0.4, color=PALETTE["red_strong"], label="窗口漏报率均值 (%)")
    for xi, n in enumerate(g.anymiss):
        ax2.text(xi + 0.2, g.miss.iloc[xi], f"{int(n)} 行", ha="center", va="bottom", fontsize=5.5, color=PALETTE["red_strong"])
    axes[2].set_xticks(x, ["raw", "φEKF\nq100", "φEKF\nq025", "φEKF q025\n+α低通"], fontsize=5.5)
    axes[2].set_ylabel("近场点误报率均值 (%)")
    axes[2].set_title("S4：状态估计降误报但带来漏报", fontsize=7.5)
    ax2.set_ylabel("窗口漏报率均值 (%)", color=PALETTE["red_strong"])
    ax2.tick_params(axis="y", colors=PALETTE["red_strong"])
    h1, l1 = axes[2].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    axes[2].legend(h1 + h2, l1 + l2, fontsize=5.5, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncols=1)
    ax2.set_ylim(0, g.miss.max() * 1.35)
    for k, ax in enumerate(axes):
        panel_label(ax, "abc"[k], x=-0.3, y=1.04)
    footnote(fig, HEADER + " a、b：S2（v3 口径），6 条轨迹 × 3 方法，噪声各 3 个种子，阴影为最小–最大；1 倍噪声 = α 0.15°、φ 0.25°、v 0.04 m/s 的标准差。"
                  "c：S4 状态估计筛选（修正口径），同 6 条轨迹 × 3 方法 × 8 条件；红字为出现窗口漏报的评分行数（不是独立事故数）。", y=-0.2)
    save(fig, OUT / "fig05_噪声延迟与状态估计.png")


def fig06(d3):
    d = d3[(d3.partition == "development_v2_n70000") & (d3.method != "hold")]
    metrics = [("d_post_right_pct", "RIGHT 不足率变化 (pp)"), ("d_post_right_miss_rate", "窗口漏报率变化 (pp)"),
               ("d_post_negative_fp_pct", "近场点误报率变化 (pp)"), ("d_post_common_2s_fpr_pct", "共同 2 s 逐帧误报率变化 (pp)")]
    cmap = plt.get_cmap(DIV_CMAP)
    fig, axes = plt.subplots(2, len(metrics), figsize=(7.2, 3.6))
    fig.subplots_adjust(wspace=0.55, hspace=0.35)
    for j, (col, name) in enumerate(metrics):
        piv_all = d.groupby(["EXIT_W_s", "margin_m", "confirmation_s"])[col].mean()
        lim = np.nanmax(np.abs(piv_all.to_numpy()))
        for i, W in enumerate((2.0, 3.0)):
            p = piv_all.loc[W].unstack("confirmation_s").fillna(0.0)  # 参照格（W2/0 m/0 s）本身恒为 0
            im = axes[i, j].imshow(p.to_numpy(), cmap=cmap, vmin=-lim, vmax=lim, origin="lower", aspect="auto")
            axes[i, j].set_xticks(range(p.shape[1]), [f"{c:g} s" for c in p.columns], fontsize=6)
            axes[i, j].set_yticks(range(p.shape[0]), [f"{m:g} m" for m in p.index], fontsize=6)
            for a in range(p.shape[0]):
                for b in range(p.shape[1]):
                    is_ref = W == 2.0 and p.index[a] == 0 and p.columns[b] == 0
                    val = p.iat[a, b]
                    axes[i, j].text(b, a, "参照" if is_ref else f"{val:+.2f}", ha="center", va="center", fontsize=6,
                                    color="white" if is_dark(cmap((val + lim) / (2 * lim))) else "black")
            for sp in axes[i, j].spines.values():
                sp.set_visible(False)
            if i == 0:
                axes[i, j].set_title(name, fontsize=6.8)
                panel_label(axes[i, j], "abcd"[j], x=-0.4, y=1.08)
            if j == 0:
                axes[i, j].set_ylabel(f"窗口 W={W:g} s\n空间膨胀", fontsize=6.5)
            if i == 1:
                axes[i, j].set_xlabel("确认时间", fontsize=6.5)
        cb = fig.colorbar(im, ax=axes[:, j], shrink=0.8)
        cb.ax.tick_params(labelsize=5.5)
    fig.suptitle("S3：后处理三因素相对“无后处理”的平均变化（蓝色 = 变好，红色 = 变差）", y=1.0, fontsize=8.5)
    footnote(fig, HEADER + " 数据 S3 修正口径，27 条开发轨迹 × 2 方法 × 8 观测条件求均值；W=2 s、0 m、0 s 为参照（恒为 0）；"
                           "四个指标都是越低越好，所以红色（增加）都表示变差。")
    save(fig, OUT / "fig06_后处理三因素交互.png")


def fig07(d5):
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
    fig.subplots_adjust(wspace=0.4)
    variants = {"W2_m0_c0": ("无后处理", "-"), "W2_m0.05_c0": ("膨胀 0.05 m", "--"), "W2_m0_c0.1": ("确认 0.1 s", ":")}
    for k, (ax, (col, name)) in enumerate(zip(axes, [("right_pct", "RIGHT 不足率均值 (%)"), ("right_miss_rate", "窗口漏报率均值 (%)"),
                                                     ("negative_fp_pct", "近场点误报率均值 (%)")])):
        for m in ("linear", "damped_linear"):
            for v, (vn, ls) in variants.items():
                s = d5[(d5.method == m) & (d5.variant == v)].groupby("gain_eff")[col].mean()
                ax.plot(s.index, s.values, marker="o", ms=2.5, lw=1.0, ls=ls, color=METHOD_COLOR[m], label=f"{METHOD_LABEL[m]} · {vn}")
        for v, (vn, ls) in variants.items():
            h = d5[(d5.method == "hold") & (d5.variant == v)][col].mean()
            ax.axhline(h, color=METHOD_COLOR["hold"], ls=ls, lw=0.8, label=f"保持 · {vn}")
        ax.set(xlabel="趋势增益 g", ylabel=name)
        panel_label(ax, "abc"[k], x=-0.28, y=1.03)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncols=3, fontsize=6)
    fig.suptitle("S4 联合精化：趋势增益细档与后处理的效果（水平线 = 保持方法）", fontsize=8.5, y=1.02)
    footnote(fig, HEADER + " 数据 S4 修正口径，12 条选择轨迹 × 8 观测条件求均值；线性的衰减时间参数为 0.5 s（对线性不生效）、衰减线性 τ=1 s。", y=-0.24)
    save(fig, OUT / "fig07_趋势增益曲线.png")


def fig12():
    d = pd.read_csv(DEEPSEEK_BOUNDS)
    lh = d["paired_pct"].str.split(r"\.\.", regex=True, expand=True).astype(float)
    d["lo"], d["hi"] = lh[0], lh[1]
    d = d.iloc[::-1].reset_index(drop=True)
    name = {"damped_linear_g1000_d1000": "衰减线性 τ=1 s", "linear_g0500_d0500": "线性 g=0.5"}
    fig, ax = plt.subplots(figsize=(4.8, 3.8))
    for i, r in d.iterrows():
        color = PALETTE["delta_up"] if r.hi < 0 else PALETTE["neutral_mid"]
        ax.plot([r.lo, r.hi], [i, i], color=color, lw=3, solid_capstyle="butt")
        ax.plot([r.lo, r.hi], [i, i], "|", color=PALETTE["neutral_black"], ms=6)
        if r.hi - r.lo < 1e-9:
            ax.plot([r.lo], [i], "o", color=color, ms=3.5)
            ax.annotate("恰为 0", (r.lo, i), xytext=(5, -2.5), textcoords="offset points", fontsize=5.5)
    ax.set_yticks(range(len(d)), [f"{r.condition} · {name.get(r.method_A, r.method_A)}" for _, r in d.iterrows()], fontsize=6)
    ax.axvline(0, color=PALETTE["neutral_black"], lw=0.8)
    ax.set_xlabel("RIGHT 不足率配对差 A − 保持 (pp)")
    ax.set_title("标签不确定性下配对差的上下界\n绿色：整段在 0 以下（方向不受标签影响）；灰色：跨 0", fontsize=7.5)
    footnote(fig, "数据：DeepSeek 正向区间评分，v2_r2_symmetric 一条轨迹、70000 点、1854 帧；"
                  "区间端点 = 未定接触点在其可能取值范围内取最有利/最不利时的配对差；独立核验尚未进行。")
    save(fig, OUT / "fig12_标签区间旁证.png")


def main():
    apply_style()
    s1, s2 = pd.read_csv(DATA / "D1.csv"), pd.read_csv(DATA / "D2.csv")
    d3, s4p, d5 = pd.read_csv(DATA / "D3.csv", low_memory=False), pd.read_csv(DATA / "D4.csv"), pd.read_csv(DATA / "D5.csv")
    fig01(s1); fig02(s1); fig03(s1); fig04(s1); fig05(s2, s4p); fig06(d3); fig07(d5); fig12()
    names = ["fig01_端点误差_各配置", "fig02_配对迟报差_相对保持", "fig03_迟报误报权衡", "fig04_驾驶因素_配对收益热图",
             "fig05_噪声延迟与状态估计", "fig06_后处理三因素交互", "fig07_趋势增益曲线", "fig12_标签区间旁证"]
    return [OUT / f"{n}.png" for n in names]


if __name__ == "__main__":
    main()
