"""两张直观案例图（nature-figure skill，Python 后端）。

中期答辩临时训练：基于接触标签纠错前评分，非冻结科研资产。

fig13 方法究竟改善了哪里？
  核心结论：入弯阶段保持方法假设转角不再变化，预测区落后于真实扫掠边界；
            衰减线性外推补上了这块“漏掉的区域”，代价是外侧多画了一些。
  证据链：a 全局轨迹与点集 → b 关键帧：真实 2 s 扫掠边界与三种方法预测区叠加
          → c 同一帧的未来转角假设（机制）→ d 全程漏覆盖面积（改善集中在哪个阶段）。
  类型：asymmetric mixed-modality（空间 hero 面板 + 定量辅图）。

fig14 提前了多少、为什么仍会失败？
  核心结论：同一目标上，趋势外推让首次有效报警平均提前；失败案例是接触发生在
            转向开始后很短时间内，任何只用历史数据的方法都来不及看到趋势。
  证据链：a/b 改善案例的位置与报警—接触时间轴 → c/d 失败案例同样两图
          → e 该轨迹全部 RIGHT 目标的提前量分布（案例在总体中的位置）。
  类型：quantitative grid。

口径：S1 clean、v4_r8_fast_entry（4 m/s、基准 8°/s、较快入弯）一条轨迹；窗口 2 s、无膨胀、无确认。
报警由冻结的 v3 预测器与几何代码逐帧重算，并与原作业 target_results 中的首次有效报警逐点核对一致。
接触时间为纠错前标签。目标点不是独立车辆试验。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RESEARCH = REPO / "工具" / "转弯全过程盲区分析软件" / "科研实验_2026-10-14"
sys.path.insert(0, str(ROOT))

import shapely  # noqa: E402
import shapely.affinity  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon, Rectangle  # noqa: E402

from common.config import HEADER  # noqa: E402
from common.plotting import PALETTE, apply_style, footnote, panel_label, plt, save  # noqa: E402

import importlib.util  # noqa: E402


def _load(name):
    """按路径加载冻结的 v3 模块（只读使用，不修改源码）。"""
    spec = importlib.util.spec_from_file_location(name, RESEARCH / "src_v3" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# v3 源码内部写的是 `from common import ...`，与本项目的 common 包同名：加载期间临时换成 v3 的 common
_project_common = sys.modules.pop("common")
v3c = _load("common")
v3pred = _load("prediction")
v3geo = _load("geometry")
sys.modules["common"] = _project_common

Vehicle, right_edge, body_corners = v3c.Vehicle, v3c.right_edge, v3c.body_corners
Method, rollout = v3pred.Method, v3pred.rollout
edge_union, edge_segments, GEOMETRY_EPS = v3geo.edge_union, v3geo.edge_segments, v3geo.GEOMETRY_EPS

OUT = Path(__file__).resolve().parent
CASE = "v4_r8_fast_entry"
PART = "development_v2_n70000"
TOL = 0.05
H = 2.0
VEH = Vehicle()
METHODS = {  # 与 S1 作业的生效参数一致
    "hold": ("保持", "S1_nominal", dict(mode="hold")),
    "linear_g050": ("线性 g=0.5", "S1_search", dict(mode="linear", gain=0.5)),
    "damped_d1000": ("衰减线性 τ=1 s", "S1_search", dict(mode="damped_linear", gain=1.0, decay_s=1.0)),
}
MCOLOR = {"hold": PALETTE["red_strong"], "linear_g050": PALETTE["teal"], "damped_d1000": PALETTE["blue_main"]}
PHASE_NAME = {1: "入弯", 2: "保持", 3: "回正"}
FOOT = (HEADER + " 数据：S1 clean，轨迹 v4_r8_fast_entry（4 m/s、基准转角速率 8°/s、较快入弯，转角峰值 10°）；"
        "窗口 2 s、无膨胀、无确认。报警由冻结 v3 预测器与几何代码逐帧重算，并与原作业结果逐点核对一致；接触时间为纠错前标签。")


# ---------------- 数据 ----------------
def load():
    d = RESEARCH / "datasets" / PART / CASE
    with np.load(d / "trajectory.npz") as z:
        traj = {k: z[k] for k in z.files}
    traj["v_B"] = traj["v_B"].astype(float)
    with np.load(d / "targets.npz") as z:
        tg = {k: z[k] for k in z.files}
    s1 = pd.read_csv(RESEARCH / "reports" / "S1_all_scores.csv")
    stored = {}
    for key in METHODS:
        job = s1[(s1.case_id == CASE) & (s1.config_id == key)].job_id.iloc[0]
        with np.load(RESEARCH / "runs" / "overnight_20261014_v3" / "jobs" / job / "target_results.npz") as z:
            stored[key] = {"first": z["w2000_m0_c0_first"], "valid": z["w2000_m0_c0_valid"]}
    return traj, tg, stored


def predict(traj):
    online = {k: traj[k] for k in ("time", "state", "alpha", "v_B")}
    edges = {}
    for key, (_, _, kw) in METHODS.items():
        seq = rollout(online, Method(**kw), H, VEH)
        edges[key] = right_edge(seq, VEH)  # (n, 101, 2, 2)
    return edges


def true_swept(traj, t):
    ft, fs = traj["fine_time"], traj["fine_state"]
    lo = np.searchsorted(ft, t - 1e-9)
    hi = np.searchsorted(ft, t + H + 1e-9, side="right")
    return edge_union(right_edge(fs[lo:hi], VEH))


def area_series(traj, edges, step=5):
    t = traj["time"]
    cut = t[-1] - 3
    rows = []
    for k in range(0, len(t), step):
        if t[k] < 2 or t[k] > cut:
            continue
        actual = true_swept(traj, t[k])
        rec = {"k": k, "time_s": float(t[k]), "phase": int(traj["true_phase"][k]), "truth_area_m2": float(actual.area)}
        for key in METHODS:
            pred = edge_union(edges[key][k])
            rec[f"missed_{key}"] = float(shapely.difference(actual, pred).area)
            rec[f"excess_{key}"] = float(shapely.difference(pred, actual).area)
        rows.append(rec)
    return pd.DataFrame(rows)


def point_hits(edges_m, xy):
    """每一帧目标点是否落在 2 s 预测扫掠区（含 0.05 m 几何容差）。与 evaluation.py 的判定等价。"""
    p = shapely.points(xy)
    hit = np.zeros(len(edges_m), bool)
    for k in range(len(edges_m)):
        hit[k] = np.min(shapely.distance(p, edge_segments(edges_m[k]))) <= TOL + GEOMETRY_EPS
    return hit


def first_valid(time, hit, contact):
    ok = hit & (contact >= time - 1e-9) & (contact <= time + H + 1e-9)
    return float(time[np.argmax(ok)]) if ok.any() else np.nan


# ---------------- 绘图工具 ----------------
def polys(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]


def draw(ax, geom, **kw):
    for g in polys(geom):
        ax.add_patch(MplPolygon(np.asarray(g.exterior.coords), closed=True, **kw))


def draw_vehicle(ax, state, color, ls="-", lw=0.8, alpha=1.0, label=None):
    tr = body_corners(state[None], VEH)[0]
    ax.add_patch(MplPolygon(tr, closed=True, fill=False, ec=color, ls=ls, lw=lw, alpha=alpha, label=label))
    x, y, th = state[0], state[1], state[2]
    u, n = np.array([np.cos(th), np.sin(th)]), np.array([-np.sin(th), np.cos(th)])
    rear, front, w = np.array([x, y]) - 1.0 * u, np.array([x, y]) + (VEH.l + 1.2) * u, VEH.width / 2
    cab = np.array([rear + w * n, front + w * n, front - w * n, rear - w * n])
    ax.add_patch(MplPolygon(cab, closed=True, fill=False, ec=color, ls=ls, lw=lw, alpha=alpha))


def trailer_rear(states):
    th, ph = states[:, 2], states[:, 3]
    hitch = states[:, :2] + VEH.l_h * np.column_stack((np.cos(th), np.sin(th)))
    return hitch - VEH.L * np.column_stack((np.cos(th - ph), np.sin(th - ph)))


class Frame:
    """以某一时刻牵引车后轴为原点、行驶方向为 x 轴（左为 +y）的车身坐标系。"""

    def __init__(self, state):
        self.x0, self.y0, self.th = state[0], state[1], state[2]
        c, s = np.cos(self.th), np.sin(self.th)
        self.m = [c, s, -s, c, -(c * self.x0 + s * self.y0), -(-s * self.x0 + c * self.y0)]

    def g(self, geom):
        return shapely.affinity.affine_transform(geom, self.m)

    def p(self, xy):
        xy = np.atleast_2d(xy)
        a, b, d, e, xo, yo = self.m
        return np.column_stack((a * xy[:, 0] + b * xy[:, 1] + xo, d * xy[:, 0] + e * xy[:, 1] + yo))

    def s(self, state):
        out = np.array(state, float).copy()
        out[:2] = self.p(state[:2])[0]
        out[2] = state[2] - self.th
        return out


def shade_phases(ax, time, phase, alpha=0.08):
    for code, color in ((1, PALETTE["blue_secondary"]), (2, PALETTE["neutral_light"]), (3, PALETTE["teal"])):
        m = phase == code
        if m.any():
            ax.axvspan(time[m].min(), time[m].max(), color=color, alpha=alpha, lw=0)


# ---------------- fig13 ----------------
def fig13(traj, tg, edges, areas):
    gain = areas["missed_hold"] - areas["missed_damped_d1000"]
    k = int(areas.loc[gain.idxmax(), "k"])
    t0 = float(traj["time"][k])
    actual = true_swept(traj, t0)
    pred = {key: edge_union(edges[key][k]) for key in METHODS}
    missed_hold = shapely.difference(actual, pred["hold"])
    recovered = shapely.intersection(missed_hold, pred["damped_d1000"])

    fig = plt.figure(figsize=(7.2, 6.0))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 1.15], width_ratios=[1.0, 1.0, 1.25], wspace=0.42, hspace=0.55)
    ax_b = fig.add_subplot(gs[0, :])
    ax_a, ax_c, ax_d = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1]), fig.add_subplot(gs[1, 2])
    fr = Frame(traj["state"][k])

    # a 全局：轨迹 + 70000 目标点（按分层着色）+ 车辆姿态
    xy, grp = tg["xy"], tg["group"]
    for g, c, lab in ((1, PALETTE["neutral_light"], "扫掠内部"), (2, PALETTE["green_2"], "近场非接触"),
                      (0, PALETTE["red_2"], "右边界邻域")):
        m = grp == g
        ax_a.scatter(xy[m, 0], xy[m, 1], s=0.15, c=c, lw=0, rasterized=True, label=f"{lab}（{m.sum():,}）")
    st = traj["state"]
    ax_a.plot(st[:, 0], st[:, 1], color=PALETTE["neutral_black"], lw=0.8, label="牵引车后轴轨迹")
    tr = trailer_rear(st)
    ax_a.plot(tr[:, 0], tr[:, 1], color=PALETTE["neutral_mid"], lw=0.8, ls="--", label="挂车后轴轨迹")
    for kk in np.linspace(0, len(st) - 1, 6).astype(int):
        draw_vehicle(ax_a, st[kk], PALETTE["neutral_dark"], lw=0.5, alpha=0.6)
    draw_vehicle(ax_a, st[k], PALETTE["blue_main"], lw=1.1)
    ax_a.annotate("a 所示时刻", xy=(st[k, 0], st[k, 1]), xytext=(st[k, 0] + 14, st[k, 1] - 6), fontsize=6,
                  color=PALETTE["blue_main"], arrowprops=dict(arrowstyle="->", color=PALETTE["blue_main"], lw=0.7))
    ax_a.set_aspect("equal")
    ax_a.set_xlabel("x (m)")
    ax_a.set_ylabel("y (m)")
    ax_a.legend(loc="lower right", fontsize=5.4, markerscale=10, handlelength=1.4, borderaxespad=0.2)
    panel_label(ax_a, "b", y=1.1)
    ax_a.set_title(f"全转弯：{len(xy):,} 个目标点", fontsize=7.5, y=1.1)

    # b 关键帧叠加（车身坐标系：x 沿当前行驶方向，y 向左）
    L = fr.g
    draw(ax_b, L(actual), fc=PALETTE["neutral_light"], ec="none", alpha=0.9, label="真实未来 2 s 右缘扫掠区")
    draw(ax_b, L(missed_hold), fc=PALETTE["red_1"], ec="none", label="保持漏掉的区域")
    draw(ax_b, L(recovered), fc=PALETTE["blue_secondary"], ec="none", alpha=0.45, label="其中被衰减线性补上")
    for key, (name, _, _) in METHODS.items():
        draw(ax_b, L(pred[key]), fill=False, ec=MCOLOR[key], lw=1.0, ls="-" if key != "linear_g050" else "--",
             label=f"{name} 预测区")
    draw_vehicle(ax_b, fr.s(st[k]), PALETTE["neutral_black"], lw=0.9, label="当前车辆")
    fut = np.array([np.interp(t0 + H, traj["fine_time"], traj["fine_state"][:, i]) for i in range(4)])
    draw_vehicle(ax_b, fr.s(fut), PALETTE["neutral_mid"], ls=":", lw=0.9, label="2 s 后真实车辆")
    ct = tg["contact_time"]
    right = (tg["edge"] == 2) & np.isfinite(ct) & (ct >= t0) & (ct <= t0 + H)
    inside = lambda geom, pts: shapely.dwithin(geom, shapely.points(pts), TOL + GEOMETRY_EPS)  # noqa: E731
    pts = xy[right]
    in_h, in_d = inside(pred["hold"], pts), inside(pred["damped_d1000"], pts)
    gained = ~in_h & in_d
    gp = fr.p(pts[gained])
    ax_b.scatter(gp[:, 0], gp[:, 1], s=1.0, c=PALETTE["blue_main"], lw=0, rasterized=True,
                 label=f"2 s 内将被挂车右侧扫到、仅衰减线性提前覆盖的目标（{gained.sum():,} 个）")
    verts = np.vstack([p.get_xy() for p in ax_b.patches])  # 所有区域与车辆轮廓，保证都在画面内
    ax_b.set_xlim(verts[:, 0].min() - 0.5, verts[:, 0].max() + 0.5)
    ax_b.set_ylim(verts[:, 1].min() - 0.4, verts[:, 1].max() + 0.4)
    ax_b.set_aspect("equal")
    ax_b.set_xlabel("沿当前行驶方向 (m)")
    ax_b.set_ylabel("横向，左为正 (m)")
    ax_b.legend(loc="upper left", bbox_to_anchor=(0, -0.32), ncols=3, fontsize=5.8, handlelength=1.6)
    panel_label(ax_b, "a", x=-0.05)
    ph = PHASE_NAME.get(int(traj["true_phase"][k]), "直行")
    m_h, m_d = missed_hold.area, shapely.difference(actual, pred["damped_d1000"]).area
    ax_b.set_title(f"关键帧 t = {t0:.2f} s（{ph}，开始转向后 {t0 - float(traj['time'][np.argmax(np.abs(traj['alpha']) > np.deg2rad(0.5))]):.2f} s）："
                   f"真实扫掠区中未被覆盖的面积  保持 {m_h:.2f} m² → 衰减线性 {m_d:.2f} m²", fontsize=7.5)

    # c 机制：该帧对未来转角的假设
    tt, al = traj["time"], np.rad2deg(traj["alpha"])
    w = (tt >= t0 - 1.5) & (tt <= t0 + H)
    ax_c.plot(tt[w & (tt <= t0)], -al[w & (tt <= t0)], color=PALETTE["neutral_black"], lw=1.1, label="已观测")
    ax_c.plot(tt[w & (tt >= t0)], -al[w & (tt >= t0)], color=PALETTE["neutral_mid"], lw=1.1, ls=":", label="真实未来")
    dot, ddot = v3pred.historical_rates(traj["alpha"], history=0.2)
    u = np.linspace(0, H, 101)
    for key, (name, _, kw) in METHODS.items():
        fa = np.array([v3pred.future_alpha(traj["alpha"][k:k + 1], dot[k:k + 1], ddot[k:k + 1], x, Method(**kw))[0] for x in u])
        ax_c.plot(t0 + u, -np.rad2deg(fa), color=MCOLOR[key], lw=1.0, ls="-" if key != "linear_g050" else "--", label=name)
    ax_c.axvline(t0, color=PALETTE["neutral_mid"], lw=0.6)
    ax_c.set_xlabel("时间 (s)")
    ax_c.set_ylabel("右转前轮转角 |α| (°)")
    ax_c.legend(fontsize=5.8, loc="upper left")
    ax_c.set_title("同一帧对未来 2 s 转角的假设", fontsize=7.5, y=1.1)
    panel_label(ax_c, "c", y=1.1)

    # d 全程漏覆盖面积
    shade_phases(ax_d, traj["time"], traj["true_phase"])
    for key, (name, _, _) in METHODS.items():
        ax_d.plot(areas.time_s, areas[f"missed_{key}"], color=MCOLOR[key], lw=1.0,
                  ls="-" if key != "linear_g050" else "--", label=name)
    ax_d.axvline(t0, color=PALETTE["neutral_mid"], lw=0.6)
    ymax = ax_d.get_ylim()[1]
    for code, name in PHASE_NAME.items():
        m = traj["true_phase"] == code
        if m.any():
            ax_d.text(traj["time"][m].mean(), ymax * 0.97, name, ha="center", va="top", fontsize=6, color=PALETTE["neutral_dark"])
    ax_d.set_xlabel("时间 (s)")
    ax_d.set_ylabel("未被预测覆盖的面积 (m²)")
    ax_d.legend(fontsize=5.8, loc="center right")
    means = "，".join(f"{METHODS[key][0]} {areas[f'missed_{key}'].mean():.2f}" for key in METHODS)
    ax_d.set_title("全程漏覆盖面积（越低越好）", fontsize=7.5, y=1.1)
    ax_d.text(0.5, 1.0, f"均值（m²）：{means}；{len(areas)} 帧", transform=ax_d.transAxes,
              ha="center", va="bottom", fontsize=5.6, color="#333333")
    panel_label(ax_d, "d", y=1.1)
    footnote(fig, FOOT + " a 中关键帧取“保持漏覆盖 − 衰减线性漏覆盖”最大的一帧，画在当前时刻的车身坐标系中；挂车轮廓按仿真参数（L=13.5 m、W=2.0 m），"
                  "牵引车为示意。d 中入弯初期三种方法同时出现漏覆盖峰：转向开始前任何只用历史数据的方法都无法预知；回正阶段衰减线性反而略差。", y=0.0)
    save(fig, OUT / "fig13_案例_预测区叠加.png")
    return {"frame_k": k, "time_s": t0, "phase": ph, "missed_hold_m2": m_h, "missed_damped_m2": m_d,
            "recovered_m2": recovered.area, "targets_gained": int(gained.sum())}


# ---------------- fig14 ----------------
def lead_table(traj, tg, stored):
    t = traj["time"]
    cut = t[-1] - 3
    ct = tg["contact_time"]
    elig = (tg["edge"] == 2) & ~tg["front_ignored"] & np.isfinite(ct) & (ct >= 2) & (ct <= cut)
    ids = np.flatnonzero(elig)
    df = pd.DataFrame({"idx": ids, "contact_s": ct[ids]})
    for key in ("hold", "damped_d1000"):
        df[f"lead_{key}"] = ct[ids] - stored[key]["valid"][ids]
    return df


def pick_cases(df):
    lh, ld = df.lead_hold, df.lead_damped_d1000
    imp = df[(lh < 1) & (ld >= 1)]
    imp = imp.iloc[(imp.lead_damped_d1000 - imp.lead_hold - (imp.lead_damped_d1000 - imp.lead_hold).median()).abs().argsort()]
    fail = df[ld < 1]
    fail = fail.iloc[(fail.lead_damped_d1000 - fail.lead_damped_d1000.median()).abs().argsort()]
    return int(imp.idx.iloc[0]), int(fail.idx.iloc[0]), len(imp), len(fail)


def fig14(traj, tg, edges, stored):
    df = lead_table(traj, tg, stored)
    i_imp, i_fail, n_imp, n_fail = pick_cases(df)
    t = traj["time"]
    al = np.rad2deg(np.abs(traj["alpha"]))
    onset = float(t[np.argmax(al > 0.5)])
    rows, checks = [], []
    for idx, tag in ((i_imp, "改善案例"), (i_fail, "失败案例")):
        rec = {"case": tag, "idx": idx, "xy": tg["xy"][idx].tolist(), "contact_s": float(tg["contact_time"][idx])}
        for key in ("hold", "damped_d1000"):
            hit = point_hits(edges[key], tg["xy"][idx])
            fv = first_valid(t, hit, rec["contact_s"])
            sv = float(stored[key]["valid"][idx])
            checks.append({"case": tag, "method": key, "recomputed_valid_s": fv, "stored_valid_s": sv,
                           "match": bool(np.isclose(fv, sv, atol=1e-9) or (np.isnan(fv) and np.isnan(sv)))})
            rec[f"hit_{key}"] = hit
            rec[f"valid_{key}"] = fv
        rows.append(rec)
    if not all(c["match"] for c in checks):
        raise AssertionError(f"重算报警与原作业不一致：{checks}")

    fig = plt.figure(figsize=(7.2, 6.6))
    gs = fig.add_gridspec(3, 2, height_ratios=[0.75, 1.0, 0.9], hspace=0.95, wspace=0.22, top=0.93)
    st = traj["state"]
    for col, rec in enumerate(rows):
        ax_m = fig.add_subplot(gs[0, col])
        ax_t = fig.add_subplot(gs[1, col])
        c = rec["contact_s"]
        kc = int(np.argmin(np.abs(t - c)))
        # 位置图（接触前 1 s 时刻的车身坐标系）：两种方法在接触前 1 s 的预测区 + 接触时车辆 + 目标点
        k1 = int(np.argmin(np.abs(t - (c - 1.0))))
        fr = Frame(st[k1])
        draw(ax_m, fr.g(edge_union(edges["hold"][k1])), fill=False, ec=MCOLOR["hold"], lw=1.0, label="保持预测区（接触前 1 s）")
        draw(ax_m, fr.g(edge_union(edges["damped_d1000"][k1])), fill=False, ec=MCOLOR["damped_d1000"], lw=1.0,
             label="衰减线性预测区（接触前 1 s）")
        draw_vehicle(ax_m, fr.s(st[k1]), PALETTE["neutral_mid"], ls=":", lw=0.8, label="接触前 1 s 车辆")
        draw_vehicle(ax_m, fr.s(st[kc]), PALETTE["neutral_black"], lw=0.9, label="接触时车辆")
        px, py = fr.p(np.array(rec["xy"]))[0]
        ax_m.plot(px, py, marker="*", ms=9, color=PALETTE["gold"], mec=PALETTE["neutral_black"], mew=0.6, ls="", label="目标点")
        ax_m.set_xlim(-VEH.L - 3, 11); ax_m.set_ylim(-3.6, 2.0); ax_m.set_aspect("equal")
        ax_m.set_xlabel("沿接触前 1 s 的行驶方向 (m)")
        if col == 0:
            ax_m.set_ylabel("横向 (m)")
        if c - 1 < onset:
            msg = ("接触前 1 s 车辆还在直行、转向尚未开始：\n两种方法的预测区都只是车身右侧一条直线，目标不在其中。\n"
                   f"接触距开始转向仅 {c - onset:.2f} s，只用历史数据的方法都不可能提前满 1 s。")
        else:
            msg = ("接触前 1 s 已开始转向：\n衰减线性看到转角在增大，预测区向右展开盖住目标；保持仍是直线。\n"
                   f"接触距开始转向 {c - onset:.2f} s，留给趋势外推的观察时间够用。")
        ax_m.text(0.0, -0.85, msg, transform=ax_m.transAxes, fontsize=5.8, va="top", color=PALETTE["neutral_black"],
                  linespacing=1.35)
        ax_m.set_title(f"{rec['case']} #{rec['idx']}：接触 {c:.2f} s，距开始转向 {c - onset:.2f} s", fontsize=7.2)
        panel_label(ax_m, "ac"[col], x=-0.1, y=1.06)
        if col == 1:
            handles, labels = ax_m.get_legend_handles_labels()

        # 时间轴
        lo, hi = c - 2.2, c + 0.35
        ax_t.axvspan(c - 1, c, color=PALETTE["red_1"], alpha=0.6, lw=0)
        ax_t.text(c - 0.5, 3.05, "需要的 1 s 反应时间", ha="center", va="bottom", fontsize=5.8, color=PALETTE["red_strong"])
        ax_t.axvline(c, color=PALETTE["neutral_black"], lw=1.0)
        ax_t.text(c + 0.02, 3.05, "接触", ha="left", va="bottom", fontsize=6)
        for yv, key, name in ((2, "damped_d1000", "衰减线性"), (1, "hold", "保持")):
            hit = rec[f"hit_{key}"]
            m = (t >= lo) & (t <= hi)
            tt, hh = t[m], hit[m]
            starts = tt[np.flatnonzero(hh & ~np.r_[False, hh[:-1]])]
            ends = tt[np.flatnonzero(hh & ~np.r_[hh[1:], False])]
            for s0, s1 in zip(starts, ends):
                ax_t.add_patch(Rectangle((s0, yv - 0.18), s1 - s0 + 0.02, 0.36, color=MCOLOR[key], alpha=0.35, lw=0))
            v = rec[f"valid_{key}"]
            if np.isfinite(v):
                lead = c - v
                ax_t.plot(v, yv, marker="v", ms=6, color=MCOLOR[key], ls="")
                ax_t.annotate("", xy=(c, yv + 0.3), xytext=(v, yv + 0.3),
                              arrowprops=dict(arrowstyle="<->", color=MCOLOR[key], lw=0.8))
                ax_t.text(v - 0.04, yv + 0.33, f"提前 {lead:.2f} s" + ("（不足 1 s）" if lead < 1 else ""),
                          ha="right", va="bottom", fontsize=6, color=MCOLOR[key])
            else:
                ax_t.text(lo + 0.1, yv + 0.3, "接触前未报警", fontsize=6, color=MCOLOR[key])
        if onset >= lo:
            ax_t.axvline(onset, color=PALETTE["neutral_mid"], lw=0.7, ls="--")
            ax_t.text(onset - 0.03, 0.45, f"开始转向 {onset:.2f} s", ha="right", va="bottom", fontsize=5.8,
                      color=PALETTE["neutral_dark"])
        ax_t.set_xlim(lo, hi); ax_t.set_ylim(0.3, 3.4)
        ax_t.set_yticks([1, 2], ["保持", "衰减线性"])
        ax_t.spines["left"].set_visible(False)
        ax_t.tick_params(axis="y", length=0)
        ax_t.set_xlabel("时间 (s)（色块：目标落在 2 s 预测区内；▼：首次有效报警）")
        panel_label(ax_t, "bd"[col], x=-0.1)

    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.995), ncols=5, fontsize=5.8)

    # e 总体提前量分布
    ax_e = fig.add_subplot(gs[2, :])
    late_d = df[df.lead_damped_d1000 < 1]
    frac_early = float(((late_d.contact_s - onset) < 1).mean()) if len(late_d) else np.nan
    bins = np.linspace(0, 2, 41)
    for key, name in (("hold", "保持"), ("damped_d1000", "衰减线性 τ=1 s")):
        lead = df[f"lead_{key}"]
        ax_e.hist(lead.dropna(), bins=bins, histtype="step", lw=1.2, color=MCOLOR[key],
                  label=f"{name}：中位 {lead.median():.2f} s，不足 1 s 的 {int((lead < 1).sum())} 个")
    ax_e.axvline(1, color=PALETTE["red_strong"], lw=0.8, ls="--")
    ax_e.text(1.0, ax_e.get_ylim()[1] * 0.95, " 1 s 反应阈值", fontsize=6, color=PALETTE["red_strong"], va="top")
    for rec, mk in zip(rows, ("o", "X")):
        for key in ("hold", "damped_d1000"):
            v = rec[f"valid_{key}"]
            if np.isfinite(v):
                ax_e.plot(rec["contact_s"] - v, ax_e.get_ylim()[1] * 0.06, marker=mk, ms=5, color=MCOLOR[key], mec="k", mew=0.4, ls="")
    ax_e.set_yscale("log")
    ax_e.set_xlabel("首次有效报警的提前量 (s)（窗口 2 s，最大约 2 s；圆点 = 改善案例，叉 = 失败案例）")
    ax_e.set_ylabel("RIGHT 目标数（对数）")
    ax_e.legend(fontsize=6, loc="upper left")
    ax_e.set_title(f"该轨迹全部 {len(df):,} 个 RIGHT 接触目标：从迟报变为及时 {n_imp} 个；衰减线性仍迟报 {n_fail} 个，"
                   f"其中 {frac_early:.0%} 的接触发生在开始转向后 1 s 内", fontsize=7.2, y=1.08)
    panel_label(ax_e, "e", x=-0.06, y=1.06)
    footnote(fig, FOOT + " 改善案例取“保持迟报、衰减线性及时”的目标中提前量增幅最接近中位数者；失败案例取衰减线性仍迟报的目标中提前量最接近中位数者。", y=0.0)
    save(fig, OUT / "fig14_案例_报警接触时间轴.png")
    rows_out = [{k: v for k, v in r.items() if not k.startswith("hit_")} for r in rows]
    return {"cases": rows_out, "checks": checks, "steering_onset_s": onset, "n_improved": n_imp, "n_still_late": n_fail,
            "still_late_contact_within_1s_of_onset_share": frac_early,
            "right_targets": int(len(df)), "median_lead_hold_s": float(df.lead_hold.median()),
            "median_lead_damped_s": float(df.lead_damped_d1000.median())}, df


def main():
    apply_style(7)
    traj, tg, stored = load()
    edges = predict(traj)
    areas = area_series(traj, edges)
    r13 = fig13(traj, tg, edges, areas)
    r14, leads = fig14(traj, tg, edges, stored)
    src = OUT / "source_data"
    src.mkdir(exist_ok=True)
    areas.to_csv(src / "fig13_missed_area_series.csv", index=False, encoding="utf-8-sig")
    leads.to_csv(src / "fig14_right_target_leads.csv", index=False, encoding="utf-8-sig")
    (src / "fig13_fig14_case_summary.json").write_text(
        json.dumps({"header": HEADER, "case": CASE, "fig13": r13, "fig14": r14}, ensure_ascii=False, indent=2, default=float),
        encoding="utf-8")
    print(json.dumps({"fig13": r13, "fig14": {k: v for k, v in r14.items() if k != "cases"},
                      "cases": [{k: r[k] for k in ("case", "idx", "contact_s", "valid_hold", "valid_damped_d1000")} for r in r14["cases"]]},
                     ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
