"""数据总览图：39 条轨迹与 273 万个目标点（nature-figure skill，Python 后端）。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

图表契约
  核心结论：中期仿真覆盖 39 条 90° 右转轨迹（27 条开发 + 12 条选择；车速 2–4 m/s、基准转角速率 2–8 °/s、
            三种动作模板），每条布置 70,000 个静态目标点，共 2,730,000 个；目标点集中在挂车扫掠区及其右侧边界附近，
            约 43% 会被挂车右侧先碰到（RIGHT，其中 89 万个进入迟报评估），三分之一是近场不接触点（误报评估）。
            数据量充足，但只有一种转弯几何。
  证据链：a 实验设计网格（39 条轨迹怎么来的；选择集落在开发集网格之间）
          b 转角输入 α(t)（动作模板与转向速率的含义）
          c 39 条轨迹各自的 70,000 个目标点与后轴轨迹（hero：数据量与空间结构，挂车后轴比牵引车更靠内）
          d 三类布点的接触边标签构成（多少点进入哪种评分）
  类型：image plate + quant（点集小多图为主，设计与构成为定量辅图）。
  口径：冻结数据集 development_v2_n70000（27 条）与 selection_v2（12 条）的 trajectory.npz / targets.npz，只读；
        轨迹、点位与设计和评分无关；d 的接触边是纠错前标签。独立的设计单元是轨迹，目标点不是独立车辆试验。

输出：fig15_数据总览_轨迹与目标点.{svg,pdf,png}；源数据 source_data/fig15_*.csv。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
DATASETS = REPO / "工具" / "转弯全过程盲区分析软件" / "科研实验_2026-10-14" / "datasets"
sys.path.insert(0, str(ROOT))

from common.config import HEADER  # noqa: E402
from common.plotting import PALETTE, apply_style, footnote, panel_label, plt, save  # noqa: E402

OUT = Path(__file__).resolve().parent
SRC = OUT / "source_data"
STEM = "fig15_数据总览_轨迹与目标点"
PARTS = {"development_v2_n70000": "开发集", "selection_v2": "选择集"}
TEMPLATES = ["symmetric", "fast_entry", "fast_return"]
TPL_LABEL = {"symmetric": "对称", "fast_entry": "较快入弯", "fast_return": "较快回正"}
TPL_MARKER = {"symmetric": "o", "fast_entry": "^", "fast_return": "v"}
TPL_OFFSET = {"symmetric": 0.0, "fast_entry": -0.32, "fast_return": 0.32}
TPL_LS = {"symmetric": "-", "fast_entry": (0, (4.0, 1.5)), "fast_return": (0, (1.2, 1.2))}
L_H, L_TRAILER = 1.8, 13.5                       # 牵引销到牵引车后轴、挂车轴距 (m)，与仿真参数一致

# 布点分层（targets.npz 的 group）：蓝 = 右边界邻域（迟报评估的主体），橙 = 近场不接触（误报评估），灰 = 扫掠内部
GROUPS = {0: ("右边界邻域", PALETTE["blue_main"]), 1: ("扫掠内部", PALETTE["neutral_light"]),
          2: ("近场不接触", PALETTE["orange"])}
# 接触边标签（v3 geometry.EDGE_NAMES）归为四类：0 不接触，1 前缘，2 右侧，3 后缘，4 左侧，5–8 四个角
EDGE_CLASS = {0: "不接触", 1: "FRONT", 2: "RIGHT", 3: "其他边", 4: "其他边", 5: "FRONT", 6: "其他边", 7: "FRONT", 8: "其他边"}
CLASS_COLOR = {"RIGHT": PALETTE["blue_main"], "FRONT": PALETTE["neutral_mid"], "其他边": PALETTE["neutral_light"],
               "不接触": PALETTE["orange"]}


# ---------------- 数据 ----------------
def load_cases():
    cases = []
    for part, part_name in PARTS.items():
        for d in sorted(p for p in (DATASETS / part).iterdir() if p.is_dir()):
            prof = json.loads((d / "profile.json").read_text(encoding="utf-8"))
            design = prof["design"]
            with np.load(d / "trajectory.npz") as z:
                traj = {k: z[k] for k in ("time", "state", "alpha")}
            with np.load(d / "targets.npz") as z:
                tg = {k: z[k] for k in ("xy", "group", "edge", "contact_time", "front_ignored")}
            template = next(t for t in TEMPLATES if d.name.endswith(t))
            entry, ret = float(design["entry_rate_abs_deg_s"]), float(design["return_rate_abs_deg_s"])
            cases.append({"case_id": d.name, "partition": part, "partition_name": part_name, "template": template,
                          "v_B_mps": float(design["v_B_mps"]), "base_rate_deg_s": min(entry, ret),
                          "entry_rate_deg_s": entry, "return_rate_deg_s": ret,
                          "alpha_peak_deg": float(design["alpha_peak_abs_deg"]), "pre_s": float(prof["control"]["pre"]),
                          "phi_max_deg": float(prof["summary"]["phi_max_deg"]), "traj": traj, "tg": tg})
    return cases


def trailer_rear(states):
    th, ph = states[:, 2], states[:, 3]
    hitch = states[:, :2] + L_H * np.column_stack((np.cos(th), np.sin(th)))
    return hitch - L_TRAILER * np.column_stack((np.cos(th - ph), np.sin(th - ph)))


def tables(cases):
    """每条轨迹一行的设计与计数表；以及 布点分层 × 接触边类别 的计数（逐轨迹）。"""
    rows, comp = [], []
    for c in cases:
        tg, t = c["tg"], c["traj"]["time"]
        cls = np.vectorize(EDGE_CLASS.get)(tg["edge"])
        ct = tg["contact_time"]
        scored = (cls == "RIGHT") & ~tg["front_ignored"] & np.isfinite(ct) & (ct >= 2) & (ct <= t[-1] - 3)
        row = {k: c[k] for k in ("case_id", "partition", "template", "v_B_mps", "base_rate_deg_s", "entry_rate_deg_s",
                                 "return_rate_deg_s", "alpha_peak_deg", "phi_max_deg")}
        row.update({"duration_s": float(t[-1]), "targets": len(tg["xy"]), "right_scored": int(scored.sum())})
        for g, (name, _) in GROUPS.items():
            row[f"group_{name}"] = int((tg["group"] == g).sum())
        for k in CLASS_COLOR:
            row[f"label_{k}"] = int((cls == k).sum())
        rows.append(row)
        for g, (name, _) in GROUPS.items():
            m = tg["group"] == g
            for k in CLASS_COLOR:
                comp.append({"case_id": c["case_id"], "group": name, "label": k, "count": int((m & (cls == k)).sum())})
    return pd.DataFrame(rows), pd.DataFrame(comp)


# ---------------- 子图 ----------------
def panel_design(ax, ax_leg, cases):
    for c in cases:
        dev = c["partition"] == "development_v2_n70000"
        ax.scatter(c["base_rate_deg_s"] + TPL_OFFSET[c["template"]], c["v_B_mps"], s=18, marker=TPL_MARKER[c["template"]],
                   facecolor=PALETTE["neutral_black"] if dev else "white", edgecolor=PALETTE["neutral_black"], lw=0.7, zorder=3)
    ax.set_xticks([2, 3, 4, 6, 8])
    ax.set_yticks([2, 2.5, 3, 3.5, 4])
    ax.set_xlim(1.3, 8.7)
    ax.set_ylim(1.75, 4.25)
    ax.set_xlabel("基准转角速率 r (°/s)")
    ax.set_ylabel("车速 $v_B$ (m/s)")
    ax.set_title("实验设计（39 条轨迹）", fontsize=7.5)
    panel_label(ax, "a", x=-0.3, y=1.02)
    k = PALETTE["neutral_black"]
    handles = [plt.Line2D([], [], ls="", marker="s", ms=4.2, mfc=k, mec=k, label="开发集 27 条"),
               plt.Line2D([], [], ls="", marker="s", ms=4.2, mfc="white", mec=k, label="选择集 12 条")]
    handles += [plt.Line2D([], [], ls="", marker=TPL_MARKER[t], ms=4.2, mfc=PALETTE["neutral_mid"], mec="none",
                           label=TPL_LABEL[t]) for t in TEMPLATES]
    ax_leg.set_axis_off()
    ax_leg.legend(handles=handles, loc="center left", bbox_to_anchor=(-0.05, 0.55), fontsize=6, handletextpad=0.3,
                  borderaxespad=0.0, labelspacing=0.55)
    ax_leg.text(-0.02, 0.06, "实心 / 空心 = 轨迹集\n形状 = 动作模板", transform=ax_leg.transAxes, fontsize=5.6,
                color=PALETTE["neutral_mid"], va="bottom")


def panel_alpha(ax, cases):
    for c in cases:
        t, a = c["traj"]["time"] - c["pre_s"], np.rad2deg(np.abs(c["traj"]["alpha"]))
        ax.plot(t, a, color=PALETTE["neutral_light"], lw=0.5, zorder=1)
    handles = [plt.Line2D([], [], color=PALETTE["neutral_light"], lw=0.8, label="全部 39 条轨迹")]
    highlight = {c["template"]: c for c in cases if c["case_id"].startswith("v3_r4_")}
    for c in (highlight[t] for t in TEMPLATES):
        t, a = c["traj"]["time"] - c["pre_s"], np.rad2deg(np.abs(c["traj"]["alpha"]))
        h, = ax.plot(t, a, color=PALETTE["neutral_black"], lw=1.0, ls=TPL_LS[c["template"]], zorder=3,
                     label=f"{TPL_LABEL[c['template']]}：入弯 {c['entry_rate_deg_s']:g}、回正 {c['return_rate_deg_s']:g} °/s")
        handles.append(h)
    ax.set_xlim(-1.5, 24.5)
    ax.set_ylim(-0.4, 17.5)
    ax.set_yticks([0, 5, 10])
    ax.set_xlabel("开始转向后的时间 (s)")
    ax.set_ylabel("|α| (°)", labelpad=2)
    ax.set_title("右转前轮转角输入（黑线：v = 3 m/s、r = 4 °/s 的三种模板）", fontsize=7.5)
    ax.legend(handles=handles, loc="upper right", fontsize=5.8, ncols=2, columnspacing=1.0, handlelength=2.2,
              borderaxespad=0.1)
    panel_label(ax, "b", x=-0.1, y=1.02)


def mini(ax, c, xlim, ylim):
    xy, grp = c["tg"]["xy"], c["tg"]["group"]
    for g in (1, 2, 0):                                   # 先画扫掠内部，再画近场与右边界，保证边界清晰
        m = grp == g
        ax.scatter(xy[m, 0], xy[m, 1], s=0.04, c=GROUPS[g][1], lw=0, rasterized=True)
    st = c["traj"]["state"]
    ax.plot(st[:, 0], st[:, 1], color=PALETTE["neutral_black"], lw=0.45)
    tr = trailer_rear(st)
    ax.plot(tr[:, 0], tr[:, 1], color=PALETTE["neutral_dark"], lw=0.45, ls=(0, (2.0, 1.2)))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.set_axis_off()


def panel_composition(ax, comp):
    tot = comp.groupby(["group", "label"])["count"].sum().unstack()[list(CLASS_COLOR)]
    order = [GROUPS[g][0] for g in (0, 1, 2)]
    tot = tot.loc[order]
    y = np.arange(len(order))[::-1]
    left = np.zeros(len(order))
    totals = tot.sum(axis=1).to_numpy(float)
    for k, color in CLASS_COLOR.items():
        v = tot[k].to_numpy(float)
        ax.barh(y, v, left=left, color=color, height=0.62, lw=0)
        for yi, li, vi, total in zip(y, left, v, totals):
            if vi / total >= 0.2:
                ax.text(li + vi / 2, yi, f"{k} {vi / total:.0%}", ha="center", va="center", fontsize=5.6,
                        color="white" if k in ("RIGHT", "FRONT") else PALETTE["neutral_black"])
        left += v
    ax.set_yticks(y, order, fontsize=6)
    ax.set_xlim(0, totals.max() * 1.02)
    ax.set_xticks([0, 3e5, 6e5, 9e5], ["0", "30 万", "60 万", "90 万"])
    ax.set_xlabel("39 条轨迹合计的目标点数", fontsize=6)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    patches = [plt.Rectangle((0, 0), 1, 1, color=c, lw=0) for c in CLASS_COLOR.values()]
    ax.legend(patches, list(CLASS_COLOR), loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncols=4, fontsize=5.6,
              handlelength=0.9, handleheight=0.9, handletextpad=0.3, columnspacing=0.8, borderaxespad=0.15)
    ax.set_title("接触边标签构成", fontsize=7.5, loc="left", pad=13)
    panel_label(ax, "d", x=-0.45, y=1.17)


# ---------------- 总图 ----------------
def wrap_units(text, units):
    """按显示宽度折行（中日韩字符算 2，其余算 1），尽量不把英文单词或数字拆开。"""
    lines, cur, w = [], "", 0
    for ch in text:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > units:
            tail = ""
            m = len(cur)
            while m > 0 and ord(cur[m - 1]) < 0x2E80 and cur[m - 1] not in " ，。；：、（）":
                m -= 1
            if 0 < len(cur) - m < 28 and m > 0:          # 末尾是一段英文或数字：整段挪到下一行
                cur, tail = cur[:m], cur[m:]
            lines.append(cur.rstrip())
            cur = tail.lstrip()
            w = sum(2 if ord(c) > 0x2E80 else 1 for c in cur)
            if ch == " " and not cur:
                continue
        cur += ch
        w += cw
    lines.append(cur)
    return "\n".join(lines)


def figure(cases, rows, comp):
    apply_style(7)
    fig = plt.figure(figsize=(7.2, 7.4))
    outer = fig.add_gridspec(2, 1, height_ratios=[1.0, 2.55], hspace=0.3, left=0.085, right=0.985, top=0.965, bottom=0.155)
    top = outer[0].subgridspec(1, 3, width_ratios=[1.0, 0.5, 1.95], wspace=0.12)
    ax_a, ax_leg, ax_b = fig.add_subplot(top[0]), fig.add_subplot(top[1]), fig.add_subplot(top[2])
    panel_design(ax_a, ax_leg, cases)
    panel_alpha(ax_b, cases)

    plate = outer[1].subgridspec(6, 9, height_ratios=[1, 1, 1, 0.42, 1, 1], hspace=0.04, wspace=0.04)
    allxy = np.vstack([c["tg"]["xy"] for c in cases])
    xlim = (allxy[:, 0].min() - 1, allxy[:, 0].max() + 1)
    ylim = (allxy[:, 1].min() - 1, allxy[:, 1].max() + 1)
    by_id = {c["case_id"]: c for c in cases}
    blocks = [(0, (2, 3, 4), (2, 4, 8), "v{v:g}_r{r}_{t}", "开发集 27 条"),
              (4, (2.5, 3.5), (3, 6), "sel_v{v:g}_r{r}_{t}", "选择集 12 条")]
    axes = {}
    for row0, speeds, rates, pattern, title in blocks:
        for i, v in enumerate(speeds):
            for j, (r, t) in enumerate((r, t) for r in rates for t in TEMPLATES):
                ax = fig.add_subplot(plate[row0 + i, j])
                mini(ax, by_id[pattern.format(v=v, r=r, t=t)], xlim, ylim)
                axes[(row0 + i, j)] = ax
            axes[(row0 + i, 0)].text(-0.06, 0.5, f"{v:g} m/s", transform=axes[(row0 + i, 0)].transAxes, ha="right",
                                     va="center", fontsize=6.2)
        for gi, r in enumerate(rates):
            for ti, t in enumerate(TEMPLATES):
                axes[(row0, 3 * gi + ti)].text(0.5, 1.0, TPL_LABEL[t], transform=axes[(row0, 3 * gi + ti)].transAxes,
                                               ha="center", va="bottom", fontsize=5.6, color=PALETTE["neutral_dark"])
            axes[(row0, 3 * gi + 1)].text(0.5, 1.17, f"r = {r} °/s", transform=axes[(row0, 3 * gi + 1)].transAxes,
                                          ha="center", va="bottom", fontsize=6.4)
        axes[(row0, 0)].text(-0.62, 1.17, title, transform=axes[(row0, 0)].transAxes, ha="left", va="bottom",
                             fontsize=6.4, fontweight="bold")
    panel_label(axes[(0, 0)], "c", x=-0.62, y=1.36)
    axes[(0, 0)].text(-0.36, 1.36, "39 条轨迹，每条 70,000 个目标点（各格同一比例尺）", transform=axes[(0, 0)].transAxes,
                      ha="left", va="bottom", fontsize=7.5)
    ax0 = axes[(2, 0)]                                    # 20 m 比例尺，放在右下角的空白处
    x1, y0 = xlim[1] - 4, ylim[0] + 3
    ax0.plot([x1 - 20, x1], [y0, y0], color=PALETTE["neutral_black"], lw=1.0, solid_capstyle="butt", clip_on=False)
    ax0.text(x1 - 10, y0 + 2.5, "20 m", ha="center", va="bottom", fontsize=5.6)

    corner = plate[4:6, 6:9].subgridspec(2, 1, height_ratios=[0.8, 1.0], hspace=0.75)
    ax_l2 = fig.add_subplot(corner[0])
    ax_l2.set_axis_off()
    handles = [plt.Line2D([], [], ls="", marker="o", ms=3.4, mfc=GROUPS[g][1], mec="none", label=f"{GROUPS[g][0]}（每条约 2.33 万）")
               for g in (0, 1, 2)]
    handles += [plt.Line2D([], [], color=PALETTE["neutral_black"], lw=0.8, label="牵引车后轴轨迹"),
                plt.Line2D([], [], color=PALETTE["neutral_dark"], lw=0.8, ls=(0, (2.0, 1.2)), label="挂车后轴轨迹（更靠内 = 内轮差）")]
    ax_l2.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 1.12), fontsize=5.7, handlelength=1.6,
                 labelspacing=0.32, borderaxespad=0.0)
    ax_d = fig.add_subplot(corner[1].subgridspec(1, 2, width_ratios=[0.5, 1.0], wspace=0.0)[1])
    panel_composition(ax_d, comp)

    n_t, n_r, n_s = int(rows.targets.sum()), int(rows.label_RIGHT.sum()), int(rows.right_scored.sum())
    note = (HEADER + f"数据：冻结数据集 development_v2_n70000（27 条）与 selection_v2（12 条），共 {n_t:,} 个静态目标点。"
            "运动学仿真参数 l = 4.0 m、l_h = 1.8 m、L = 13.5 m、W = 2.0 m；全部为 90° 右转、转角峰值 10°，开始转向前直行 6 s，"
            "只有这一种转弯几何。c 中每格一条轨迹，世界坐标（起点在原点、初始朝 +y），各格同一比例尺。"
            f"d 的接触边为纠错前标签：RIGHT {n_r:,} 个，其中接触时刻在评分时段 [2 s, 结束前 3 s] 内的 {n_s:,} 个进入迟报评估；"
            "FRONT 为挂车前缘或前角先碰到的点，不计分。独立的设计单元是轨迹，目标点不是独立车辆试验。")
    fig.text(0.01, 0.088, wrap_units(note, 150), fontsize=6.3, color="#555555", ha="left", va="top", linespacing=1.35)
    return fig


def main():
    cases = load_cases()
    assert len(cases) == 39, len(cases)
    rows, comp = tables(cases)
    SRC.mkdir(exist_ok=True)
    rows.to_csv(SRC / "fig15_trajectories.csv", index=False, encoding="utf-8-sig")
    comp.groupby(["group", "label"])["count"].sum().reset_index().to_csv(SRC / "fig15_label_by_group.csv", index=False,
                                                                       encoding="utf-8-sig")
    fig = figure(cases, rows, comp)
    for old in OUT.glob(f"{STEM}.*"):
        old.unlink()
    save(fig, OUT / f"{STEM}.png")
    print(f"{len(rows)} 条轨迹，{int(rows.targets.sum()):,} 个目标点；RIGHT {int(rows.label_RIGHT.sum()):,}，"
          f"计入迟报评估 {int(rows.right_scored.sum()):,}，不接触 {int(rows['label_不接触'].sum()):,}")
    return OUT / f"{STEM}.png"


if __name__ == "__main__":
    main()
