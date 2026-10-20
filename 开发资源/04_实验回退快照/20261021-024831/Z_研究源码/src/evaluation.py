from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np
import shapely
from shapely import STRtree

from common import Vehicle, right_edge
from geometry import edge_union, subset_indices, GEOMETRY_EPS
from prediction import Method, observed_phase, rollout

EPS = 1e-9


@dataclass(frozen=True)
class Variant:
    exit_W: float = 2.0
    margin: float = 0.0
    confirmation: float = 0.0

    @property
    def tag(self):
        return f"w{round(self.exit_W*1000)}_m{round(self.margin*1000)}_c{round(self.confirmation*1000)}"


def ratio(a, b):
    return float(100*a/b) if b else None


def support_counts(time, contact, exit_mask, horizon):
    time = np.asarray(time)
    upper = np.searchsorted(time, contact+EPS, side="right")
    lower = np.searchsorted(time, contact-2-EPS, side="left")
    support = upper-lower
    if horizon > 2:
        et = time[exit_mask]
        support += np.searchsorted(et, contact-2-EPS, side="left")-np.searchsorted(et, contact-horizon-EPS, side="left")
    return upper, support


def summarize(data, targets, state, count=None):
    n = len(targets["xy"])
    ids = np.arange(n) if count is None else subset_indices(targets["group"], count)
    mask = np.zeros(n, dtype=bool)
    mask[ids] = True
    time = data["time"]
    cut = time[-1]-3
    contact = targets["contact_time"]
    eligible = (~targets["front_ignored"]) & np.isfinite(contact) & (contact >= 2-EPS) & (contact <= cut+EPS)
    right = mask & eligible & (targets["edge"] == 2)
    all_positive = mask & eligible
    negative = mask & ~np.isfinite(contact)
    valid = state["valid"]
    first = state["first"]
    miss = ~np.isfinite(valid)
    late = np.isfinite(valid) & (contact-valid < 1-EPS)
    no_before = ~np.isfinite(first) | (first > contact+EPS)
    fp = np.isfinite(first) & (first <= cut+EPS)
    right_n, negative_n = int(right.sum()), int(negative.sum())
    counts = state["point_counts"]
    TP = int(counts["TP"][mask].sum())
    FP = int(counts["FP"][mask].sum())
    FN = int(counts["support"][mask].sum())-TP
    TN = int(counts["negative_opportunities"][mask].sum())-FP
    ref_FP = int(counts["ref_FP"][mask].sum())
    ref_TN = int(counts["ref_negative_opportunities"][mask].sum())-ref_FP
    def qlead(selected, q):
        leads = contact[selected & ~miss]-valid[selected & ~miss]
        return float(np.quantile(leads, q)) if len(leads) else None
    layer_rows = []
    for layer in range(3):
        selected = right & (targets["group"] == layer)
        if np.any(selected):
            layer_rows.append({"group": layer, "right_contacts": int(selected.sum()),
                "right_insufficient_pct": ratio(int(((miss|late)&selected).sum()), int(selected.sum()))})
    score_duration = max(.02, cut-time[0])
    false_seconds = float(counts["FP"][negative].sum()*.02)
    contacts_phase = np.full(n, -1, dtype=np.int8)
    finite = np.isfinite(contact)
    positions = np.searchsorted(time, contact[finite], side="left")
    positions = np.clip(positions, 0, len(time)-1)
    contacts_phase[finite] = data["true_phase"][positions]
    exit_right = right & (contacts_phase == 3)
    return {"target_count": len(ids), "right_contacts": right_n,
        "right_miss": int((right & miss).sum()), "right_late": int((right & late).sum()),
        "right_no_before": int((right & no_before).sum()),
        "right_pct": ratio(int((right & (miss|late)).sum()), right_n),
        "stratum_right_rows": layer_rows,
        "stratified_right_pct": float(np.mean([x["right_insufficient_pct"] for x in layer_rows])) if layer_rows else None,
        "right_lead_p10_s": qlead(right, .1), "right_lead_median_s": qlead(right, .5),
        "exit_right_contacts": int(exit_right.sum()), "exit_right_miss": int((exit_right & miss).sum()),
        "exit_right_pct": ratio(int((exit_right & (miss|late)).sum()), int(exit_right.sum())),
        "all_contacts": int(all_positive.sum()), "all_miss": int((all_positive & miss).sum()),
        "all_late": int((all_positive & late).sum()), "negative_count": negative_n,
        "negative_fp": int((negative & fp).sum()), "negative_fp_pct": ratio(int((negative & fp).sum()), negative_n),
        "frame_TP": TP, "frame_FP": FP, "frame_TN": TN, "frame_FN": FN,
        "frame_fpr_pct": ratio(FP, FP+TN), "frame_recall_pct": ratio(TP, TP+FN),
        "common_2s_reference_fpr_pct": ratio(ref_FP, ref_FP+ref_TN),
        "mean_negative_false_alarm_seconds_per_minute": false_seconds/(negative_n*score_duration/60) if negative_n else None,
        "alarm_duration_scope": "mean_per_static_negative_test_target_not_real_vehicle_traffic",
        "front_ignored": int((mask & targets["front_ignored"]).sum()),
        "startup_truncated": int((mask & ~targets["front_ignored"] & (contact < 2)).sum()),
        "end_truncated": int((mask & ~targets["front_ignored"] & np.isfinite(contact) & (contact > cut)).sum()),
        "score_end_s": float(cut)}


def evaluate(data, targets, method, variants=None, vehicle=Vehicle(), retain_sequence=False):
    start = time.perf_counter()
    variants = variants or [Variant()]
    maximum = max(2., max(v.exit_W for v in variants))
    online = {key: data[key] for key in ["time", "state", "alpha", "v_B"]}
    sequence = rollout(online, method, maximum, vehicle)
    prediction_seconds = time.perf_counter()-start
    edges = right_edge(sequence, vehicle)
    n = len(targets["xy"])
    time_axis, contact = data["time"], targets["contact_time"]
    cut = time_axis[-1]-3
    common = time_axis <= cut+EPS
    common_time = time_axis[common]
    phases = observed_phase(data, method.history_s)
    eligible = (~targets["front_ignored"]) & np.isfinite(contact) & (contact >= 2-EPS) & (contact <= cut+EPS)
    negative = ~np.isfinite(contact)
    positive_time = np.sort(contact[eligible])
    negative_count = int(negative.sum())
    points = shapely.points(targets["xy"])
    tree = STRtree(points)
    states = []
    for variant in variants:
        before, opportunities = support_counts(common_time, contact[eligible], phases[common] == 3, variant.exit_W)
        _, reference_opportunities = support_counts(common_time, contact[eligible], phases[common] == 3, 2)
        count = {key: np.zeros(n, dtype=np.int32) for key in ["TP", "FP", "ref_FP", "support", "negative_opportunities", "ref_negative_opportunities"]}
        count["support"][eligible] = opportunities
        count["negative_opportunities"][eligible] = before-opportunities
        count["ref_negative_opportunities"][eligible] = before-reference_opportunities
        count["negative_opportunities"][negative] = len(common_time)
        count["ref_negative_opportunities"][negative] = len(common_time)
        states.append({"variant": variant, "first": np.full(n, np.nan), "raw": np.full(n, np.nan),
                       "valid": np.full(n, np.nan), "starts": np.full(n, np.nan),
                       "last": np.full(n, -2, dtype=np.int32), "point_counts": count})
    frame_counts = np.zeros((len(time_axis), len(states), 4), dtype=np.int32)
    work_ms = []
    for k, t in enumerate(time_axis):
        clock = time.perf_counter()
        windows = {2.}
        if phases[k] == 3:
            windows |= {v.exit_W for v in variants}
        geometries = {h: edge_union(edges[k, :round(h/method.dt)+1]) for h in windows}
        geometry_cache = {}
        for h, shape in geometries.items():
            max_margin = max((v.margin for v in variants if (v.exit_W if phases[k] == 3 else 2) == h), default=0)
            ids = tree.query(shape, predicate="dwithin", distance=.05+max_margin+GEOMETRY_EPS)
            geometry_cache[h] = (ids, shapely.distance(points[ids], shape))
        for z, s in enumerate(states):
            v = s["variant"]
            h = v.exit_W if phases[k] == 3 else 2.
            candidates, distances = geometry_cache[h]
            hits = candidates[distances <= .05+v.margin+GEOMETRY_EPS]
            new = ~np.isfinite(s["raw"][hits])
            s["raw"][hits[new]] = t
            restarted = s["last"][hits] != k-1
            s["starts"][hits[restarted]] = t
            s["last"][hits] = k
            confirmed = hits[t-s["starts"][hits] >= v.confirmation-EPS]
            new = ~np.isfinite(s["first"][confirmed])
            s["first"][confirmed[new]] = t
            supported = (contact[confirmed] >= t-EPS) & (contact[confirmed] <= t+h+EPS)
            ids_valid = confirmed[supported & ~np.isfinite(s["valid"][confirmed])]
            s["valid"][ids_valid] = t
            if common[k]:
                score = confirmed[(eligible[confirmed] | negative[confirmed]) & ((contact[confirmed] >= t-EPS) | negative[confirmed])]
                support_mask = (contact[score] >= t-EPS) & (contact[score] <= t+h+EPS)
                tp = score[support_mask]
                fp = score[~support_mask]
                ref_fp = score[~((contact[score] >= t-EPS) & (contact[score] <= t+2+EPS))]
                s["point_counts"]["TP"][tp] += 1
                s["point_counts"]["FP"][fp] += 1
                s["point_counts"]["ref_FP"][ref_fp] += 1
                low = np.searchsorted(positive_time, t-EPS, side="left")
                up = np.searchsorted(positive_time, t+h+EPS, side="right")
                support_n = int(up-low)
                noncontact_n = negative_count+len(positive_time)-int(up)
                frame_counts[k, z] = [len(tp), len(fp), noncontact_n-len(fp), support_n-len(tp)]
        work_ms.append((time.perf_counter()-clock)*1000)
    summaries = []
    point_output = {}
    for s in states:
        v = s["variant"]
        summary = summarize(data, targets, s)
        summary.update({"method": method.mode, "gain": method.gain, "decay_s": method.decay_s,
                        "acceleration_duration_s": method.acceleration_duration_s,
                        "EXIT_W_s": v.exit_W, "margin_m": v.margin, "confirmation_s": v.confirmation})
        summaries.append(summary)
        for key in ["first", "raw", "valid"]:
            point_output[v.tag+"_"+key] = s[key]
        for key, value in s["point_counts"].items():
            point_output[v.tag+"_"+key] = value
    geometric = {}
    valid_frames = np.flatnonzero(common)
    for h in [.3, 1., 2.]:
        future = time_axis[valid_frames]+h
        truth_state = np.column_stack([np.interp(future, data["fine_time"], data["fine_state"][:, i]) for i in range(4)])
        actual_edges = right_edge(truth_state, vehicle)
        prediction_edges = edges[valid_frames, round(h/method.dt)]
        error = np.linalg.norm(prediction_edges-actual_edges, axis=-1).max(axis=1)
        geometric[str(h)] = {"mean_endpoint_error_m": float(np.mean(error)),
                             "p95_endpoint_error_m": float(np.quantile(error, .95)),
                             "max_endpoint_error_m": float(error.max())}
    area_rows = []
    for k in valid_frames[::50]:
        lo = np.searchsorted(data["fine_time"], time_axis[k]-EPS)
        hi = np.searchsorted(data["fine_time"], time_axis[k]+2+EPS, side="right")
        actual = edge_union(right_edge(data["fine_state"][lo:hi], vehicle))
        predicted = edge_union(edges[k, :round(2/method.dt)+1])
        area_rows.append({"time_s": float(time_axis[k]), "truth_area_m2": float(shapely.area(actual)),
                          "missed_area_m2": float(shapely.area(shapely.difference(actual, predicted))),
                          "excess_area_m2": float(shapely.area(shapely.difference(predicted, actual)))})
    geometric["unexpanded_2s_swept_area"] = {"sample_frames": len(area_rows),
        "mean_missed_area_m2": float(np.mean([a["missed_area_m2"] for a in area_rows])),
        "mean_excess_area_m2": float(np.mean([a["excess_area_m2"] for a in area_rows])),
        "rows": area_rows}
    for summary in summaries:
        summary["geometry"] = geometric
    for z, s in enumerate(states):
        counts = s["point_counts"]
        assert np.all(counts["support"] >= counts["TP"]), "Negative false-negative count"
        assert np.all(counts["negative_opportunities"] >= counts["FP"]), "Negative true-negative count"
        expected = [counts["TP"].sum(), counts["FP"].sum(),
                    counts["negative_opportunities"].sum()-counts["FP"].sum(), counts["support"].sum()-counts["TP"].sum()]
        assert np.array_equal(frame_counts[:, z].sum(axis=0), expected), "Point/frame confusion disagreement"
    result = {"summaries": summaries, "states": states, "point_output": point_output,
              "frame_counts": frame_counts, "observed_phase": phases,
              "timing": {"batched_prediction_s": prediction_seconds,
                "geometry_query_decision_frame_p50_ms": float(np.quantile(work_ms, .5)),
                "geometry_query_decision_frame_p95_ms": float(np.quantile(work_ms, .95)),
                "geometry_query_decision_frame_max_ms": float(max(work_ms)),
                "wall_s": time.perf_counter()-start, "desktop_not_MCU": True}}
    if retain_sequence:
        result["sequence"] = sequence
    return result
