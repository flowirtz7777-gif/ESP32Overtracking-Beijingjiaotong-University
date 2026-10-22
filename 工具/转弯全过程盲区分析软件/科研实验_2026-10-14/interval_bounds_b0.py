#!/usr/bin/env python
# -*- coding: utf-8 -*-
# --------------------------------------------------------------------------
# 【作者标记】DeepSeek 生成 — 外部评审工件，不属于 Z 盘冻结科研资产，
# 不代表协调方（GPT）的科学验收结论。
# AUTHOR MARKER: DeepSeek (AI assistant), external review artefact only;
# not a frozen Z: research asset and not a scientific acceptance.
# --------------------------------------------------------------------------
"""DEPRECATED — UNSOUND. DO NOT USE. Kept only as an audit trail.

This first version was withdrawn on 2026-10-21 after external review found three
defects that invalidate every number it produced:

  1. It held the stored `valid` array fixed while enumerating alternative contact
     times. `valid` is written only when the contact time lands inside the
     prediction support window (evaluation.py:168-170), so it is a FUNCTION of
     the label. Reusing it under a different contact time does not cover the
     allowed label space. The same applies to TP/FP/support/negative counts.
  2. The ratio bound reused N_lo/D_hi and N_hi/D_lo unconditionally; for a
     negative numerator those extremes swap, so the reported interval could be
     inverted and cease to be conservative.
  3. The `verdict` field read a positive delta as "A strictly better", but delta
     is defined as late_A - late_B, so positive means A is WORSE.

Consequently the claimed aggregate bound [+0.134, +2.533] pp and the claim that
"trend extrapolation is interval-proved" are RETRACTED.

Use interval_bounds_b0_v2.py instead. It scores from `first` (label-independent,
evaluation.py:165-167) and reports both an unconstrained and an explicitly
assumed edge-family variant.

--- original (unsound) implementation follows, unmodified ---
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

# BLAS single thread must be set before numpy import in a real run; here numpy
# is already imported, so document the requirement instead of pretending.
E_ROOT = r"E:\大创内轮差项目\工具\转弯全过程盲区分析软件\科研实验_2026-10-14"
Z_ROOT = r"Z:\大创内轮差项目_实验结果\科研实验_2026-10-14"
CENSUS = os.path.join(
    Z_ROOT, "runs", "resume_20261022_0000_edge_cover_merge_v1", "census"
)
JOBS = os.path.join(E_ROOT, "runs", "overnight_20261014_v3", "jobs")
PARTITION = "development_v2_n70000"
THR_S = 1.0  # reaction threshold; frozen by the original protocol
STARTUP_S = 2.0
END_EXCLUDE_S = 3.0


# --------------------------------------------------------------------------
# census loading
# --------------------------------------------------------------------------
def load_census(partition, case):
    """Return per-census-point arrays aligned to `original_index`."""
    ds = os.path.join(CENSUS, "datasets", partition, case)
    result = json.load(open(os.path.join(ds, "result.json"), encoding="utf-8"))
    da = np.load(os.path.join(ds, "arrays.npz"))
    ga = np.load(os.path.join(CENSUS, "groups", result["group"], "arrays.npz"))

    by_union = {int(u): i for i, u in enumerate(ga["union_index"])}
    idx = np.array([by_union[int(u)] for u in da["union_index"]], dtype=np.int64)
    return {
        "original_index": da["original_index"],
        "status": ga["combined__contact_status"][idx],
        "lower_s": ga["combined__contact_lower_s"][idx],
        "upper_s": ga["combined__contact_upper_s"][idx],
        "edge_codes": ga["combined__possible_edge_codes"][idx],
        "group": result["group"],
    }


def load_valid(case, config):
    """First-valid-alarm time per target for one config (single-variant job)."""
    import glob

    pat = os.path.join(JOBS, "S1_*__" + case + "__" + config + "__clean__raw")
    hits = glob.glob(pat)
    if len(hits) != 1:
        raise RuntimeError(f"expected exactly one job for {case}/{config}, got {len(hits)}")
    arr = np.load(os.path.join(hits[0], "target_results.npz"))
    keys = [k for k in arr.files if k.endswith("_valid")]
    if len(keys) != 1:
        raise RuntimeError(f"expected one *_valid array, got {keys}")
    return arr[keys[0]]


# --------------------------------------------------------------------------
# per-point contribution reachable set
# --------------------------------------------------------------------------
def late_reachable(valid_t, lower, upper, allow_noncontact):
    """Reachable {0,1} set of the `late` indicator for one candidate contact time.

    late(t) = 1 iff t < valid_t + THR_S   (or valid_t is non-finite -> always 1)
    The contact time is only known to lie in [lower, upper]; status==2 points may
    additionally be non-contact, which contributes 0.
    """
    if not np.isfinite(valid_t):
        values = {1}
    else:
        edge = valid_t + THR_S
        values = set()
        if lower < edge:
            values.add(1)
        if upper >= edge:
            values.add(0)
        if not values:  # degenerate bracket; keep conservative
            values = {1}
    if allow_noncontact:
        values.add(0)
    return min(values), max(values)


# --------------------------------------------------------------------------
# aggregate bound for a paired difference
# --------------------------------------------------------------------------
def paired_bound(partition, case, config_a, config_b):
    census = load_census(partition, case)
    targets = np.load(os.path.join(E_ROOT, "datasets", partition, case, "targets.npz"))
    traj = np.load(os.path.join(E_ROOT, "datasets", partition, case, "trajectory.npz"))
    cut = float(traj["time"][-1] - END_EXCLUDE_S)

    contact = targets["contact_time"]
    edge = targets["edge"]
    front = targets["front_ignored"]

    va = load_valid(case, config_a)
    vb = load_valid(case, config_b)

    oi = census["original_index"]
    uncertain = np.zeros(len(contact), dtype=bool)
    uncertain[oi] = True

    eligible = (
        (~front)
        & np.isfinite(contact)
        & (contact >= STARTUP_S - 1e-9)
        & (contact <= cut + 1e-9)
    )
    right = eligible & (edge == 2)
    resolved = right & ~uncertain

    def late(v, mask):
        return int((((~np.isfinite(v)) | (contact - v < THR_S - 1e-9)) & mask).sum())

    d0 = int(resolved.sum())
    base = late(va, resolved) - late(vb, resolved)

    d_lo = d_hi = 0
    n_unc = 0
    pivot = 0
    for k, j in enumerate(oi):
        allow_nc = bool(census["status"][k] == 2)
        upper = float(census["upper_s"][k]) if census["status"][k] == 1 else cut
        lower = float(census["lower_s"][k])
        a_lo, a_hi = late_reachable(float(va[j]), lower, upper, allow_nc)
        b_lo, b_hi = late_reachable(float(vb[j]), lower, upper, allow_nc)
        d_lo += a_lo - b_hi
        d_hi += a_hi - b_lo
        if (a_hi - b_lo) - (a_lo - b_hi) > 0:
            pivot += 1
        n_unc += 1

    d_max = d0 + n_unc  # every uncertain point may join the denominator
    lo_pp = 100.0 * (base + d_lo) / d_max
    hi_pp = 100.0 * (base + d_hi) / d0
    return {
        "case": case,
        "config_a": config_a,
        "config_b": config_b,
        "resolved_denominator": d0,
        "resolved_delta": base,
        "uncertain_points": n_unc,
        "pivot_points": pivot,
        "delta_pp_lower": lo_pp,
        "delta_pp_upper": hi_pp,
        "verdict": (
            "A_strictly_better"
            if lo_pp > 0
            else ("B_strictly_better" if hi_pp < 0 else "undetermined")
        ),
    }


def main():
    pairs = [("hold", "damped_d1000"), ("hold", "linear_g050"),
             ("linear_g050", "damped_d1000"), ("damped_d1000", "second_a1000")]

    cases = sorted(
        d for d in os.listdir(os.path.join(CENSUS, "datasets", PARTITION))
        if os.path.isdir(os.path.join(CENSUS, "datasets", PARTITION, d))
    )

    out = []
    for a, b in pairs:
        for case in cases:
            try:
                out.append(paired_bound(PARTITION, case, a, b))
            except Exception as exc:  # keep going; report, never fabricate
                out.append({"case": case, "config_a": a, "config_b": b,
                            "error": repr(exc)})

    tally = {}
    for row in out:
        if "verdict" in row:
            tally.setdefault((row["config_a"], row["config_b"]), {}).setdefault(
                row["verdict"], 0)
            tally[(row["config_a"], row["config_b"])][row["verdict"]] += 1

    print(json.dumps({"rows": out, "tally": {f"{a} vs {b}": v for (a, b), v in tally.items()}},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
