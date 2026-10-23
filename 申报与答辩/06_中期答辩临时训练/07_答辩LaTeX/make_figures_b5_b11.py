"""Build the trajectory-similarity and confusion-matrix figures for the midterm
defense deck (07_答辩LaTeX/img). Reads only P0_数据整理/data and M3 results.

[DeepSeek 生成]
"""
import csv
import json
import os
import collections

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "img")


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def build_similarity():
    import pandas as pd

    d = pd.read_csv(os.path.join(ROOT, "P0_数据整理/data/D3.csv"))
    sub = d[d.method != "hold"]
    piv = sub.pivot_table(index="case_id",
                          columns=["config_id", "condition", "variant"],
                          values="right_pct")
    sim = piv.T.corr(method="spearman")
    cases = list(sim.index)
    S = sim.to_numpy()

    n = len(cases)
    D = np.clip(1.0 - S, 0, None)
    np.fill_diagonal(D, 0.0)
    order = leaves_list(linkage(squareform(D, checks=False), method="average"))
    S = S[np.ix_(order, order)]
    cases = [cases[i] for i in order]

    off = S[~np.eye(n, dtype=bool)]
    sel = [c for c in cases if c.startswith("sel_")]
    print(f"pairwise median {np.median(off):.3f} min {off.min():.3f}")
    return S, cases, float(np.median(off)), float(off.min()), len(sel)


def _short(case):
    """v2_r2_symmetric -> 2|2|S ; sel_v2.5_r3_fast_entry -> *2.5|3|E"""
    sel = case.startswith("sel_")
    body = case[4:] if sel else case
    parts = body.split("_")
    v = parts[0][1:]
    r = parts[1][1:]
    tpl = {"symmetric": "S", "fast_entry": "E", "fast_return": "R"}.get("_".join(parts[2:]), "?")
    return ("*" if sel else " ") + f"{v}|{r}|{tpl}"


def fig_similarity(S, cases, median, vmin_obs, n_sel):
    n = len(cases)
    fig, ax = plt.subplots(figsize=(4.55, 4.05), dpi=260)
    vmin = 0.74
    im = ax.imshow(S, cmap="magma", vmin=vmin, vmax=1.0, interpolation="nearest")

    ax.set_xticks([])
    ax.set_yticks(range(n))
    ax.set_yticklabels([_short(c) for c in cases], fontsize=4.5,
                       fontfamily="Consolas")
    for t, c in zip(ax.get_yticklabels(), cases):
        if c.startswith("sel_"):
            t.set_color("#4da3ff")
            t.set_fontweight("bold")
    ax.tick_params(axis="y", length=1.0, pad=1.4)
    ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.18, alpha=0.30)
    ax.tick_params(which="minor", length=0)
    for sp in ax.spines.values():
        sp.set_linewidth(0.6)

    cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
    cb.set_label("Spearman 相似度", fontsize=6.6)
    cb.ax.tick_params(labelsize=5.8)

    ax.set_title("39 条轨迹两两相似度（RIGHT 不足率，层次聚类排序）\n"
                 f"中位数 {median:.2f}，最低 {vmin_obs:.2f}",
                 fontsize=7.6, pad=4)
    fig.subplots_adjust(left=0.125, right=0.900, top=0.885, bottom=0.006)
    path = os.path.join(OUT, "b5_similarity.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path, os.path.getsize(path))


def fig_confusion():
    """Three classification tasks at the safety-first threshold, large enough to
    read on a projected slide. The default-vs-safety comparison goes in the
    slide's table, not in the figure."""
    src = os.path.join(ROOT, "M3_二级处理联合/results/confusion_matrices.json")
    d = json.load(open(src, encoding="utf-8"))
    order = [
        ("any_window_miss", "出现窗口漏报"),
        ("any_no_before", "接触前完全无报警"),
        ("fp_budget_pass", "误报预算达标"),
    ]
    pol = "安全优先（目标召回≥90%）"

    fig, axes = plt.subplots(1, 3, figsize=(7.10, 2.28), dpi=240)
    for ax, (key, label) in zip(axes, order):
        blk = d[key][pol]
        m = np.array(blk["matrix"], dtype=float)
        ax.imshow(m, cmap="Blues", vmin=0, vmax=m.max() * 1.15)
        for (yy, xx), v in np.ndenumerate(m):
            ax.text(xx, yy, f"{int(v)}", ha="center", va="center", fontsize=15.5,
                    color="white" if v > m.max() * 0.55 else "#1b2a41",
                    fontweight="bold")
        ax.set_xticks([0, 1]); ax.set_xticklabels(["否", "是"], fontsize=11)
        ax.set_yticks([0, 1]); ax.set_yticklabels(["否", "是"], fontsize=11)
        ax.tick_params(length=0, pad=2.5)
        ax.set_title(f"{label}\n召回 {blk['recall']:.2f}   精确 {blk['precision']:.2f}",
                     fontsize=10.6, pad=5)
        for sp in ax.spines.values():
            sp.set_linewidth(0.8)

    fig.subplots_adjust(left=0.028, right=0.992, top=0.775, bottom=0.155, wspace=0.24)
    path = os.path.join(OUT, "b11_confusion.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path, os.path.getsize(path))
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path, os.path.getsize(path))


if __name__ == "__main__":
    S, cases, med, vmin, n_sel = build_similarity()
    print(f"{len(cases)} trajectories, {n_sel} selection")
    fig_similarity(S, cases, med, vmin, n_sel)
    fig_confusion()
