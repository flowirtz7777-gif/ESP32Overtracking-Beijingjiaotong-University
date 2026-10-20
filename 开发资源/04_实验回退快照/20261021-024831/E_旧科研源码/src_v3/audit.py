from __future__ import annotations

from dataclasses import replace

import numpy as np
import shapely

from common import ROOT, Vehicle, body_corners, read_json, right_edge, write_json, file_hash
from geometry import GEOMETRY_EPS, edge_segments, label_contacts, swept_segments
from prediction import Method, rollout, future_alpha, historical_rates
from pathlib import Path
from scenarios import Maneuver, integrate_reference


def numerical_and_contact_audit(partition="development_v2"):
    rows = []
    for case in ["v2_r2_symmetric", "v3_r4_fast_return", "v4_r8_fast_entry"]:
        p = ROOT/"datasets"/partition/case
        data, targets = dict(np.load(p/"trajectory.npz")), dict(np.load(p/"targets.npz"))
        online = {k: data[k] for k in ["time", "state", "alpha", "v_B"]}
        dot, ddot = historical_rates(data["alpha"])
        for method in [Method(m) for m in ["hold", "linear", "damped_linear", "bounded_second_order"]]+[
                Method("linear", gain=2), Method("bounded_second_order", acceleration_duration_s=1)]:
            controls = np.column_stack([future_alpha(data["alpha"], dot, ddot, u, method) for u in np.arange(401)*.005])
            speed = float(np.rad2deg(np.max(np.abs(np.diff(controls, axis=1))/.005)))
            if speed > method.rate_limit_deg_s+1e-7:
                raise AssertionError("Future control exceeds common rate envelope")
            rows.append({"case": case, "mode": method.mode, "gain": method.gain,
                         "acceleration_duration_s": method.acceleration_duration_s,"future_max_rate_deg_s": speed})
        for mode in ["hold", "linear", "damped_linear", "bounded_second_order"]:
            coarse = rollout(online, Method(mode), 2)
            fine = rollout(online, Method(mode, dt=.005), 2)
            delta = np.linalg.norm(right_edge(coarse, Vehicle())-right_edge(fine[:, ::4], Vehicle()), axis=-1)
            error = float(delta.max())
            if error > .005:
                raise AssertionError(f"Prediction integration not stable: {case} {mode} {error}")
            rows.append({"case": case, "mode": mode, "prediction_max_edge_diff_020_vs_005_m": error})
        valid = (targets["edge"]==2) & (targets["contact_index"] > 0)
        indices = targets["contact_index"][valid]
        segments = edge_segments(right_edge(data["fine_state"], Vehicle()))
        evidence = shapely.dwithin(shapely.points(targets["xy"][valid]), segments[indices-1], .05+GEOMETRY_EPS+1e-8)
        if not np.all(evidence):
            raise AssertionError(f"RIGHT labels lack right-face oracle evidence: {case} {(~evidence).sum()}")
        rng = np.random.default_rng(2026101405)
        sampled = np.concatenate([rng.choice(np.flatnonzero(targets["group"]==g), 120, replace=False) for g in range(3)])
        maneuver = Maneuver.from_spec(read_json(p/"profile.json")["design"])
        reference = integrate_reference(maneuver, .0025)
        fine_body = swept_segments(body_corners(reference["state"], Vehicle()))
        relabel = label_contacts(targets["xy"][sampled], reference, fine_body)
        old = targets["contact_time"][sampled]
        new = relabel["contact_time"]
        if not np.array_equal(np.isfinite(old), np.isfinite(new)):
            raise AssertionError("Contact existence depends on reference step")
        both = np.isfinite(old)
        difference = float(np.max(np.abs(old[both]-new[both]))) if np.any(both) else 0
        if difference > .005+1e-8:
            raise AssertionError("Contact time did not converge")
        edge_changed = targets["edge"][sampled] != relabel["edge"]
        if np.any(edge_changed & ((targets["edge"][sampled]==2)|(relabel["edge"]==2))):
            raise AssertionError("Primary RIGHT labels depend on reference step")
        rows.append({"case": case, "contact_probe_points": len(sampled), "max_contact_time_diff_s": difference,
                     "nonprimary_edge_label_changes": int(edge_changed.sum()), "right_oracle_points_checked": int(valid.sum())})
    report = {"status": "passed", "rows": rows, "online_prediction_dt_s": .02,
              "validation_prediction_source_sha256": file_hash(Path(__file__).parent/"prediction.py"),
              "reference_dt_s": .005, "oracle_is_offline_label_check_not_candidate_algorithm": True}
    write_json(ROOT/"reports"/"S0_numerical_contact_audit.json", report)
    return report
