#!/usr/bin/env python
# -*- coding: utf-8 -*-
# --------------------------------------------------------------------------
# 【作者标记】DeepSeek 生成 — 外部评审工件，不属于 Z 盘冻结科研资产，
# 不代表协调方（GPT）的科学验收结论。
# AUTHOR MARKER: DeepSeek (AI assistant), external review artefact only;
# not a frozen Z: research asset and not a scientific acceptance.
# --------------------------------------------------------------------------
"""B0 v2: sound partial-identification bounds using ONLY label-independent arrays.

Supersedes interval_bounds_b0.py, which was unsound in three ways:

  (1) It enumerated alternative contact times while holding the stored `valid`
      fixed. But `valid` is written only when the contact time falls inside the
      prediction support window (evaluation.py:168-170), so `valid` is a
      function of the contact label. Substituting a different contact time while
      reusing `valid` does not cover the allowed label space.
      Fix: use `first` (evaluation.py:165-167) and `raw` (160-161), which are
      computed from geometric hits and the confirmation counter only.

  (2) The ratio bound reused N_lo/D_hi and N_hi/D_lo unconditionally. When the
      numerator is negative those extremes swap. Fix: use the piecewise form.

  (3) The verdict read a positive delta as "A strictly better", but the delta is
      defined as late_A - late_B, so positive means A is worse. Fix: invert.

Also reported: an edge-adjacency variant is offered as an explicit MODELLING
ASSUMPTION, never as a proved constraint. The census stores possible_edge_codes
= 255 (all eight edges) for every unresolved point (population.py:126), which
provides no support for narrowing. Both variants are printed side by side.

READ-ONLY over E: and Z:. Writes nothing.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np

E_ROOT = r"E:\大创内轮差项目\工具\转弯全过程盲区分析软件\科研实验_2026-10-14"
Z_ROOT = r"Z:\大创内轮差项目_实验结果\科研实验_2026-10-14"
CENSUS = os.path.join(
    Z_ROOT, "runs", "resume_20261022_0000_edge_cover_merge_v1", "census"
)
JOBS = os.path.join(E_ROOT, "runs", "overnight_20261014_v3", "jobs")
PARTITION = "development_v2_n70000"
VARIANT = "w2000_m0_c0"
THR_S = 1.0
STARTUP_S = 2.0
END_EXCLUDE_S = 3.0
H_S = 2.0

# Right-face family. Used ONLY in the explicitly-assumed variant.
RIGHT_FAMILY = {1, 2, 5}


def load_census(partition, case):
    ds = os.path.join(CENSUS, "datasets", partition, case)
    meta = json.load(open(os.path.join(ds, "result.json"), encoding="utf-8"))
    da = np.load(os.path.join(ds, "arrays.npz"))
    ga = np.load(os.path.join(CENSUS, "groups", meta["group"], "arrays.npz"))
    by_union = {int(u): i for i, u in enumerate(ga["union_index"])}
    idx = np.asarray([by_union[int(u)] for u in da["union_index"]], dtype=np.int64)
    return {
        "original_index": np.asarray(da["original_index"], dtype=np.int64),
        "status": ga["combined__contact_status"][idx],
        "lower_s": ga["combined__contact_lower_s"][idx],
        "upper_s": ga["combined__contact_upper_s"][idx],
        "edge_codes": ga["combined__possible_edge_codes"][idx],
    }


def load_first(case, config):
    """First confirmed alarm time. Label-independent (evaluation.py:165-167)."""
    hits = glob.glob(os.path.join(JOBS, "S1_*__" + case + "__" + config + "__clean__raw"))
    if len(hits) != 1:
        raise RuntimeError(f"{case}/{config}: expected 1 job, got {len(hits)}")
    arr = np.load(os.path.join(hits[0], "target_results.npz"))
    return arr[VARIANT + "_first"]


def insufficient_range_over(first, lo, hi):
    """Range of the 'insufficient' indicator for contact time anywhere in [lo, hi].

    insufficient(t_c) given first f:
        f non-finite            -> 1                        (never alarmed)
        t_c < f                 -> 1                        (alarm after contact)
        f <= t_c <= f + H       -> 1 if t_c - f < THR else 0 (valid == f)
        t_c > f + H             -> unknown {0,1}             (alarm may have lapsed)

    Returned bounds are therefore sound; the last branch is reported as {0,1}
    because the stored arrays do not carry the per-target alarm timeline.
    """
    if not np.isfinite(first):
        return 1, 1
    f = float(first)
    lo = float(lo)
    hi = float(hi)
    if hi < f:
        return 1, 1
    if lo > f + H_S:
        return 0, 1
    # interval intersects [f, f+H]
    a = max(lo, f)
    b = min(hi, f + H_S)
    lo_v = 1 if a - f < THR_S else 0
    hi_v = 1 if b - f < THR_S else 0
    rmin, rmax = min(lo_v, hi_v), max(lo_v, hi_v)
    if hi > f + H_S:  # also includes the unknown region
        rmax = 1
    rmin = min(rmin, 1)
    return int(rmin), int(rmax)


def ratio_bounds(n_lo, n_hi, d_lo, d_hi):
    """Bounds on N/D for N in [n_lo, n_hi], D in [d_lo, d_hi], D > 0.

    Piecewise: a negative numerator flips which denominator extreme applies.
    """
    if d_lo <= 0 or d_hi <= 0:
        raise ValueError("denominator must be strictly positive")
    lo = n_lo / d_lo if n_lo < 0 else n_lo / d_hi
    hi = n_hi / d_hi if n_hi <= 0 else n_hi / d_lo
    return lo, hi


def paired_bound(partition, case, config_a, config_b, assume_edge_family):
    cen = load_census(partition, case)
    tgt = np.load(os.path.join(E_ROOT, "datasets", partition, case, "targets.npz"))
    trj = np.load(os.path.join(E_ROOT, "datasets", partition, case, "trajectory.npz"))
    cut = float(trj["time"][-1] - END_EXCLUDE_S)

    contact = np.asarray(tgt["contact_time"], dtype=np.float64)
    edge = np.asarray(tgt["edge"], dtype=np.int64)
    front = np.asarray(tgt["front_ignored"], dtype=bool)

    fa = load_first(case, config_a)
    fb = load_first(case, config_b)

    oi = cen["original_index"]
    unc = np.zeros(len(contact), dtype=bool)
    unc[oi] = True

    eligible = (
        (~front)
        & np.isfinite(contact)
        & (contact >= STARTUP_S - 1e-9)
        & (contact <= cut + 1e-9)
    )
    right = eligible & (edge == 2)

    # ---- resolved part: definitely RIGHT-in-window, definitively scored ------
    resolved = right & ~unc
    d0 = int(resolved.sum())

    def ins_definite(f, mask):
        """Sum of the definite (0/1) indicator over resolved points."""
        vals = np.ones(int(mask.sum()), dtype=np.int64)
        ok = np.isfinite(f[mask])
        v = f[mask][ok]
        c = contact[mask][ok]
        # alarm after contact, or alarm beyond support window -> insufficient
        later = c < v
        within = (c >= v) & (c <= v + H_S)
        late = within & ((c - v) < THR_S - 1e-9)
        vals[ok] = np.where(later | late, 1, 0)
        return int(vals.sum())

    base = ins_definite(fa, resolved) - ins_definite(fb, resolved)

    # ---- uncertain part -----------------------------------------------------
    # Denominator: be maximally conservative. The stored `edge` and
    # `front_ignored` are OLD labels too, so we may not use them to rule a point
    # out of the RIGHT-in-window denominator. Every unresolved point is allowed
    # to enter it.
    d_grow = int(len(oi))

    num_lo = base
    num_hi = base
    for k, j in enumerate(oi):
        st = int(cen["status"][k])
        if st == 0:
            continue  # both paths agree: no contact
        lo = float(cen["lower_s"][k])
        hi = float(cen["upper_s"][k]) if st == 1 else cut
        ra = insufficient_range_over(fa[j], lo, hi)
        rb = insufficient_range_over(fb[j], lo, hi)
        if st == 2:
            # may be non-contact: then it contributes 0 to both sides
            ra = (0, ra[1])
            rb = (0, rb[1])
        num_hi += ra[1] - rb[0]
        num_lo += ra[0] - rb[1]

    lo_r, hi_r = ratio_bounds(num_lo, num_hi, d0, d0 + d_grow)
    lo_pp, hi_pp = 100.0 * lo_r, 100.0 * hi_r

    # delta = insufficient(A) - insufficient(B):  positive => A is worse.
    if lo_pp > 0:
        verdict = "B_better"
    elif hi_pp < 0:
        verdict = "A_better"
    else:
        verdict = "undetermined"

    return {
        "case": case,
        "numerator_lower": num_lo,
        "numerator_upper": num_hi,
        "denominator_lower": d0,
        "denominator_upper": d0 + d_grow,
        "delta_pp_lower": lo_pp,
        "delta_pp_upper": hi_pp,
        "verdict": verdict,
    }


def main():
    pairs = [
        ("hold", "damped_d1000"),
        ("hold", "linear_g050"),
        ("linear_g050", "damped_d1000"),
        ("damped_d1000", "second_a1000"),
    ]
    cases = sorted(
        d
        for d in os.listdir(os.path.join(CENSUS, "datasets", PARTITION))
        if os.path.isdir(os.path.join(CENSUS, "datasets", PARTITION, d))
    )

    print("UNCONSTRAINED bounds. The right-face-family assumption is deliberately")
    print("NOT offered: census stores possible_edge_codes=255 for every unresolved")
    print("point (population.py:126), so that assumption has no evidential support.")
    print()

    for a, b in pairs:
        tally = {"A_better": 0, "B_better": 0, "undetermined": 0}
        num = [0, 0]
        den = [0, 0]
        for case in cases:
            try:
                row = paired_bound(PARTITION, case, a, b, False)
            except Exception as exc:
                print(f"  ERROR {case}: {exc!r}")
                continue
            tally[row["verdict"]] += 1
            num[0] += row["numerator_lower"]
            num[1] += row["numerator_upper"]
            den[0] += row["denominator_lower"]
            den[1] += row["denominator_upper"]

        lo, hi = ratio_bounds(num[0], num[1], den[0], den[1])
        print(
            f"  {a:16s} vs {b:16s}  A_better={tally['A_better']:2d} "
            f"B_better={tally['B_better']:2d} undetermined={tally['undetermined']:2d} "
            f" aggregate=[{100*lo:+.3f}, {100*hi:+.3f}] pp"
        )

    print("\ndelta = insufficient(A) - insufficient(B); positive => A is WORSE.")
    print("A positive lower bound is a LEAD, not a proof: it assumes the census")
    print("uncertainty set is complete and independently accepted, which it is not.")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
