"""Multi-condition alarm replay + forward scoring driver (DeepSeek, midterm batch).

Scope: v2_r2_symmetric, the 8 observation conditions present under
runs/afternoon_S4_v1/observations/, 3 methods (hold, damped_linear_g1000_d1000,
linear_g0500_d0500). For every (method, condition) it:

  1. replays the ORIGINAL causal online alarm stream from the frozen
     observation sensors (no truth labels read), storing complete
     frames x 12variants x 70000 raw/confirmed bit matrices;
  2. runs the FORWARD scoring path over each stored sequence against the
     post-anchor contact domains, producing paired RIGHT-insufficiency
     fraction bounds.

INDEPENDENT CLOSE IS INTENTIONALLY DEFERRED (human instruction 2026-10-22).
Nothing here writes acceptance/close receipts; results are explicitly marked
forward-only and are NOT rankable or trainable.

AUTHOR MARKER: DeepSeek (AI assistant). Midterm-support execution artefact.
Not a frozen Z: asset; no acceptance claim.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

sys.dont_write_bytecode = True
for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_k] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"Z:\大创内轮差项目_实验结果\科研实验_2026-10-14"
sys.path.insert(0, os.path.join(ROOT, "src_v3"))
sys.path.insert(0, os.path.join(ROOT, "src_s4_full_alarm_replay_20261022_v1"))
sys.path.insert(0, os.path.join(ROOT, "src_s4_remaining_summary_bound_20261022_v1"))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import prediction, geometry, common  # noqa: E402  (original online code)
import full_alarm_replay_core as replay_core  # noqa: E402
import remaining_summary_core_v2 as score_core  # noqa: E402
import full_metric_domain_core as ratio_core  # noqa: E402

# metric_options layout: A[0:10], B[10:20], paired A-B[20:30]
# RATE_NAMES[2] == 'right_insufficient'  (miss OR late)
IDX_A_RIGHT_INSUFFICIENT = 2
IDX_B_RIGHT_INSUFFICIENT = 10 + 2
IDX_PAIRED_RIGHT_INSUFFICIENT = 20 + 2

AFTERNOON = os.path.join(ROOT, "runs", "afternoon_S4_v1")
CASE = "v2_r2_symmetric"
PARTITION = "development_v2_n70000"
OUT = os.path.join(HERE, "midterm_batch_v1")

# Methods present in afternoon_S4_v1 for this case.
METHODS = {
    "damped_linear_g1000_d1000": dict(mode="damped_linear", gain=1.0, decay_s=1.0,
                                      acceleration_duration_s=0.25, history_s=0.2,
                                      alpha_limit_deg=30.0, rate_limit_deg_s=32.0,
                                      acceleration_limit_deg_s2=160.0, dt=0.02),
    "linear_g0500_d0500": dict(mode="linear", gain=0.5, decay_s=0.5,
                               acceleration_duration_s=0.25, history_s=0.2,
                               alpha_limit_deg=30.0, rate_limit_deg_s=32.0,
                               acceleration_limit_deg_s2=160.0, dt=0.02),
    "hold": dict(mode="hold", gain=1.0, decay_s=0.5,
                 acceleration_duration_s=0.25, history_s=0.2,
                 alpha_limit_deg=30.0, rate_limit_deg_s=32.0,
                 acceleration_limit_deg_s2=160.0, dt=0.02),
}

VARIANTS = [dict(exit_W=w, margin=m, confirmation=c)
            for w in (2.0, 3.0) for m in (0.0, 0.02, 0.05) for c in (0.0, 0.1)]


def condition_dirs():
    base = os.path.join(AFTERNOON, "observations", PARTITION, CASE)
    return sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))


def find_original_job(method_key, condition):
    """Locate the frozen original job for (method, condition) to bind hashes."""
    jobs = os.path.join(AFTERNOON, "jobs")
    for name in sorted(os.listdir(jobs)):
        if CASE not in name:
            continue
        parts = name.split("__")
        if len(parts) < 5:
            continue
        if parts[2] == method_key and parts[3] == condition and parts[4] == "raw":
            return os.path.join(jobs, name)
    return None


def load_observations(condition):
    folder = os.path.join(AFTERNOON, "observations", PARTITION, CASE, condition)
    with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    with np.load(os.path.join(folder, "sensors.npz"), allow_pickle=False) as z:
        sensors = {k: z[k] for k in z.files}
    return sensors, manifest


def load_targets():
    folder = os.path.join(ROOT, "datasets", PARTITION, CASE)
    with np.load(os.path.join(folder, "targets.npz"), allow_pickle=False) as z:
        return z["xy"], z["group"]


def load_domains():
    p = os.path.join(ROOT, "runs", "resume_20261024_0000_analytic_prefix_merge_v1",
                     "datasets", PARTITION, CASE, "domains.npz")
    with np.load(p, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def npz_bytes(values):
    buf = io.BytesIO()
    np.savez_compressed(buf, **values)
    return buf.getvalue()


def replay_method(method_key, condition, xy, outdir):
    """Replay one method's causal alarm stream; return unpacked variant-0 hits."""
    sensors, obs_manifest = load_observations(condition)
    online = {k: sensors[k] for k in ("time", "state", "alpha", "v_B")}
    time_axis = np.asarray(online["time"])
    method = prediction.Method(**METHODS[method_key])

    t0 = time.perf_counter()
    blocks = []
    for item in replay_core.generate(online, xy, method, VARIANTS,
                                     prediction, geometry, common,
                                     lambda: None, independent=False):
        if item.get("final"):
            continue
        values = {k: item[k] for k in ("time", "horizons", "raw", "confirmed", "phases")}
        name = f"blocks/f{int(item['start']):06d}.npz"
        path = os.path.join(outdir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        blob = npz_bytes(values)
        with open(path, "wb") as fh:
            fh.write(blob)
        blocks.append({"path": name, "start": int(item["start"]), "end": int(item["end"]),
                       "bytes": len(blob)})
    replay_seconds = time.perf_counter() - t0

    hits = np.empty((len(time_axis), len(xy)), bool)
    for row in blocks:
        with np.load(os.path.join(outdir, row["path"]), allow_pickle=False) as z:
            pack = z["confirmed"][:, 0, :]
            unpacked = np.unpackbits(pack, axis=1, bitorder="little")
            hits[row["start"]:row["end"]] = unpacked[:, : len(xy)]
    return time_axis, hits, blocks, replay_seconds


def score_pair(time_axis, phase, hits_a, hits_b, dom, start_s, end_s):
    """Forward-only paired scoring for RIGHT insufficiency (miss OR late)."""
    events = score_core.global_events(time_axis, phase, start_s, end_s, False)
    ca, cb, cp = [], [], []
    for i in range(len(dom["xy"])):
        opts = [(float(dom["lower_s"][i, j]), float(dom["upper_s"][i, j]),
                 int(dom["edge_mask"][i, j]), bool(dom["can_contact"][i, j]),
                 bool(dom["can_noncontact"][i, j])) for j in range(2)]
        prof = score_core.profile(time_axis, phase, hits_a[:, i], hits_b[:, i],
                                  opts, start_s, end_s, events, False)
        mo = prof["metric_options"]
        ca.append((1, tuple(mo[IDX_A_RIGHT_INSUFFICIENT])))
        cb.append((1, tuple(mo[IDX_B_RIGHT_INSUFFICIENT])))
        cp.append((1, tuple(mo[IDX_PAIRED_RIGHT_INSUFFICIENT])))
    return {
        "A": ratio_core.exact_record(ratio_core.bounds(ca)),
        "B": ratio_core.exact_record(ratio_core.bounds(cb)),
        "paired_A_minus_B": ratio_core.exact_record(ratio_core.bounds(cp)),
    }


def load_phase(dom, time_axis):
    phase = np.asarray(dom.get("offline_phase", np.zeros(len(time_axis), np.int8)))
    if len(phase) != len(time_axis):
        with np.load(os.path.join(ROOT, "datasets", PARTITION, CASE, "trajectory.npz"),
                     allow_pickle=False) as z:
            phase = z["true_phase"]
    return phase


def main():
    os.makedirs(OUT, exist_ok=True)
    xy, group = load_targets()
    dom = load_domains()
    conds = condition_dirs()
    record = {
        "author": "DeepSeek",
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case": CASE,
        "conditions": conds,
        "methods": sorted(METHODS),
        "variants": len(VARIANTS),
        "metric": "right_insufficient (miss OR late) / eligible_RIGHT",
        "forward_only": True,
        "independent_close_deferred_by_human_instruction": True,
        "corrected_labels_accepted": 0,
        "corrected_scores_accepted": 0,
        "rankable": False,
        "trainable": False,
        "pairs": [],
    }
    for cond in conds:
        t_cond = time.perf_counter()
        streams = {}
        for method_key in sorted(METHODS):
            outdir = os.path.join(OUT, cond, method_key)
            os.makedirs(outdir, exist_ok=True)
            try:
                t_axis, hits, blocks, rs = replay_method(method_key, cond, xy, outdir)
                streams[method_key] = (t_axis, hits)
                print(f"  replay {method_key} / {cond}: {rs:.0f}s blocks={len(blocks)}", flush=True)
            except Exception as exc:
                print(f"  FAIL replay {method_key} / {cond}: {exc!r}", flush=True)

        if "hold" not in streams:
            record["pairs"].append({"condition": cond, "error": "hold stream missing"})
            continue
        t_axis, hits_hold = streams["hold"]
        phase = load_phase(dom, t_axis)
        start_s, end_s = 2.0, float(t_axis[-1] - 3.0)

        for method_key in sorted(METHODS):
            if method_key == "hold" or method_key not in streams:
                continue
            t_a, hits_a = streams[method_key]
            try:
                t1 = time.perf_counter()
                bounds = score_pair(t_axis, phase, hits_a, hits_hold, dom, start_s, end_s)
                ss = time.perf_counter() - t1
                record["pairs"].append({
                    "condition": cond,
                    "method_A": method_key,
                    "method_B": "hold",
                    "targets": int(len(xy)),
                    "frames": int(len(t_axis)),
                    "score_start_s": start_s,
                    "score_end_s": end_s,
                    "score_seconds": round(ss, 2),
                    "right_insufficient_bound": bounds,
                })
                print(f"  score {method_key} vs hold / {cond}: {ss:.0f}s", flush=True)
            except Exception as exc:
                record["pairs"].append({"condition": cond, "method_A": method_key,
                                        "error": repr(exc)})
                print(f"  FAIL score {method_key} / {cond}: {exc!r}", flush=True)
        print(f"condition {cond} total {time.perf_counter()-t_cond:.0f}s", flush=True)

    out = os.path.join(OUT, "midterm_batch_record_v1.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False)
    ok = sum(1 for r in record["pairs"] if "error" not in r)
    print(json.dumps({"pairs_completed": ok, "pairs_failed": len(record["pairs"]) - ok,
                      "out": out}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
