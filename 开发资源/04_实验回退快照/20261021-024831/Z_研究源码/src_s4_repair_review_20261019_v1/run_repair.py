"""New geometry admission and corrected-score deterministic-delay diagnostics."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import gzip
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback
import runtime as r

sys.path.insert(0, str(r.ROOT / "src_v3"))
sys.path.insert(0, str(r.ROOT / "src_s4_v1"))
import numpy as np
import shapely
from scipy.integrate import solve_ivp
import common
import geometry
import observations
import prediction
import scenarios
import evaluation_scored as evaluator

CASE = "v3_r4_fast_entry"
INPUT = r.ROOT / "datasets/development_v2_n70000" / CASE
OLD = r.ROOT / "runs/overnight_20261014_v3/jobs"
TAG = "w2000_m0_c0"
SENSOR_KEYS = ("time", "state", "alpha", "v_B", "measurement_time", "source_index")

def npz_blob(arrays):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    blob = buffer.getvalue()
    with np.load(io.BytesIO(blob), allow_pickle=False) as restored:
        r.require(set(restored.files) == set(arrays), "NPZ keys differ")
        for key, array in arrays.items():
            r.require(common.array_hash(restored[key]) == common.array_hash(array), "Lossless NPZ roundtrip differs")
    return blob

def old_matrix():
    folders = sorted(OLD.glob("S2__" + CASE + "__*__delay200__*"))
    r.require(len(folders) == 9, "Exactly nine original deterministic-delay configurations required")
    result = []
    for folder in folders:
        job = r.read(folder / "configuration.json")
        r.require(job["condition"] == {"id": "delay200", "delay_s": .2, "noise_level": 0},
                  "No parameter/noise search allowed")
        r.require(job["variants"] == [{"exit_W": 2., "margin": 0., "confirmation": 0.}],
                  "Fixed W2 zero-margin zero-confirmation diagnosis only")
        result.append({"id": job["id"], "method": job["method"], "processor": job["preprocessing"],
                       "condition": job["condition"], "old_folder": str(folder),
                       "old_configuration_sha256": r.file_hash(folder / "configuration.json"),
                       "old_report_sha256": r.file_hash(folder / "report.json")})
    return result

def geometry_matrix():
    return [{"id": f"geo_a{round(peak*10):03d}_{template}", "alpha_peak_abs_deg": peak,
             "template": template, "v_B_mps": 3., "base_rate_deg_s": 4.,
             "entry_rate_abs_deg_s": 8. if template == "fast_entry" else 4.,
             "return_rate_abs_deg_s": 8. if template == "fast_return" else 4.,
             "turn_heading_change_deg": 90.}
            for peak in (5., 12.5, 15., 20.) for template in ("symmetric", "fast_entry", "fast_return")]

def load_inputs():
    manifest = r.read(INPUT / "manifest.json")
    for name, digest in manifest["files"].items():
        r.require(r.file_hash(INPUT / name) == digest, "Original input changed")
    with np.load(INPUT / "trajectory.npz", allow_pickle=False) as z:
        data = {key: z[key] for key in z.files}
    with np.load(INPUT / "targets.npz", allow_pickle=False) as z:
        targets = {key: z[key] for key in z.files}
    r.require(len(targets["xy"]) == len(np.unique(targets["xy"], axis=0)) == 70000, "Unique target admission failed")
    r.require(common.array_hash(targets["xy"]) == manifest["target_coordinates_sha256"], "Target coordinate SHA differs")
    r.require(common.array_hash(targets["contact_time"]) == manifest["contact_label_sha256"], "Contact label SHA differs")
    raw = observations.observe(data, {"id": "delay200", "delay_s": .2, "noise_level": 0})
    r.require(np.all(raw["source_index"] <= np.arange(len(raw["time"]))), "Future sensor sample")
    for job in old_matrix():
        original = r.read(Path(job["old_folder"]) / "report.json")
        observed = observations.preprocess(raw, job["processor"])
        r.require(common.array_hash(observed["state"]) == original["observed_state_sha256"],
                  "Processed state differs from frozen original S2")
        r.require(common.array_hash(observed["alpha"]) == original["observed_alpha_sha256"],
                  "Processed alpha differs from frozen original S2")
    return data, targets, raw, manifest

def independent_rhs(t, state, maneuver):
    x, y, heading, articulation = state
    speed = maneuver.speed
    steering = float(maneuver.alpha(t))
    tractor_rate = speed * math.tan(steering) / 4.
    trailer_rate = (speed * math.sin(articulation) + 1.8 * tractor_rate * math.cos(articulation)) / 13.5
    return np.array([speed * math.cos(heading), speed * math.sin(heading),
                     tractor_rate, tractor_rate - trailer_rate])

def rk4_reference(maneuver, step):
    times = np.arange(round(maneuver.end / step) + 1) * step
    states = np.empty((len(times), 4))
    states[0] = [0., 0., math.pi / 2, 0.]
    for k, t in enumerate(times[:-1]):
        state = states[k]
        # Existing independent reference RHS, not the online prediction integrator.
        a = float(maneuver.alpha(t))
        mid = float(maneuver.alpha(t + step / 2))
        last = float(maneuver.alpha(t + step))
        k1 = scenarios.reference_rhs(state, a, maneuver.speed, common.Vehicle())
        k2 = scenarios.reference_rhs(state + step*k1/2, mid, maneuver.speed, common.Vehicle())
        k3 = scenarios.reference_rhs(state + step*k2/2, mid, maneuver.speed, common.Vehicle())
        k4 = scenarios.reference_rhs(state + step*k3, last, maneuver.speed, common.Vehicle())
        states[k+1] = state + step*(k1 + 2*k2 + 2*k3 + k4)/6
    return times, states

def independent_right_edge(states):
    theta = states[:, 2]
    heading = theta - states[:, 3]
    hitch = states[:, :2] + 1.8*np.column_stack([np.cos(theta), np.sin(theta)])
    normal = np.column_stack([np.sin(heading), -np.cos(heading)])
    rear = hitch - 13.5*np.column_stack([np.cos(heading), np.sin(heading)])
    return np.stack([hitch + normal, rear + normal], axis=1)

def prepare():
    r.require(r.before_deadline(), "Authorization expired")
    r.require(not r.RUN.exists() and not r.AUTH.exists() and not r.PLAN.exists() and not r.PROTOCOL.exists(),
              "New version already exists; do not rerun prepare")
    h = r.helper()
    with h.exclusive() as mutex:
        idle = r.execution(h)
        active = r.read(r.ROOT / "active_research_run.json")
        r.require(active["accepted_diagnostic_total"] == 57 and active["accepted_numeric_total"] == 2295,
                  "Read newer ledger before authorization")
        receipt = r.ROOT / "runs/authorization_close_20261018_1200_v1/final_receipt.json"
        r.require(r.file_hash(receipt) == "4963c1a9d24b44fc9105dbe73f01d26046261702f87ce33050ca504a4511c24e",
                  "Noon closure changed")
        for rel, digest in active["source_signature"].items():
            r.require(r.file_hash(r.ROOT / rel) == digest, "Existing frozen source changed: " + rel)
        tests = subprocess.run([str(r.PYTHON), "-X", "utf8", "-B", "-m", "unittest", "discover",
                                "-s", str(r.SOURCE), "-p", "test_repair.py", "-v"],
                               cwd=r"C:\Users\Admin", capture_output=True, text=True, encoding="utf-8", timeout=180)
        r.require(tests.returncode == 0, "New tests failed before source freeze: " + tests.stderr)
        authorization = {"time": r.now(), "human_request": "\u4f60\u5148\u53cd\u601d\u4e00\u4e0b\u4e4b\u524d\u7684\u5b9e\u9a8c\u6709\u6ca1\u6709\u81f4\u547d\u7f3a\u9677\uff0c\u7136\u540e\u628a\u5269\u4e0b\u7684\u5b9e\u9a8c\u8865\u9f50",
                         "human_deadline_reply": "\u660e\u5929\u65e9\u4e0a8:00\uff0c\u5c3d\u91cf\u4eca\u665a\u6536\u5c3e",
                         "deadline_local": "2026-10-19T08:00:00+08:00", "no_automatic_extension": True,
                         "baseline": {"formal": 2238, "accepted_diagnostics": 57, "accepted_numeric": 2295},
                         "new_formal": 0, "new_accepted_diagnostics": 0,
                         "preserve_all_E_Z_history": True, "quota_bytes": r.CAP, "reserve_bytes": r.RESERVE}
        protocol = {"version": "geometry-delay-repair-review-20261019-v1",
                    "scope": "new geometry admissibility plus corrected-score deterministic-delay diagnosis; not algorithm optimization",
                    "deadline_local": authorization["deadline_local"], "geometry_specs": geometry_matrix(),
                    "old_10_degree_reference_controls": "reuse frozen profiles only; no reintegration or rerun",
                    "new_geometry_phi_limit_deg": 45, "phi_limit_origin": "existing simulation design boundary, not calibrated mechanical limit",
                    "truth_phi_clamping": False, "geometry_steps_s": [.005, .0025],
                    "independent_solver": {"method": "DOP853", "rtol": 1e-10, "atol": 1e-12, "max_step_s": .02},
                    "geometry_edge_error_limit_m": .005,
                    "geometry_is_not_new_contact_label_or_density_acceptance": True,
                    "delay_jobs": old_matrix(), "score_start_s": 2., "score_end": "last recorded time minus 3s",
                    "variant": {"exit_W": 2., "margin": 0., "confirmation": 0.},
                    "witness_rule": "all new RIGHT window-miss/no-before points plus all original S2 RIGHT window-miss points",
                    "all_late_and_miss_indices": "lossless full-length packbits with index hashes",
                    "no_parameter_search": True, "M2_allowed": False, "S5_allowed": False,
                    "global_or_vehicle_safety_claim": False,
                    "whole_batch_reservation_bytes": r.BATCH_RESERVATION, "run_cap_bytes": r.RUN_CAP,
                    "workers": 1, "inflight": 1, "BLAS_threads": 1}
        plan = {"version": "20261019-v1-reflection-and-two-bounded-foundation-diagnostics",
                "previous_plan": "resume_plan_20261018_v4.json", "authorization_status": "active",
                "deadline": authorization["deadline_local"], "formal_baseline": 2238,
                "accepted_diagnostic_baseline": 57, "accepted_numeric_baseline": 2295,
                "new_formal_predictions": 0, "new_diagnostics_accepted_this_authorization": 0,
                "accepted_diagnostic_total": 57, "accepted_numeric_total": 2295,
                "source_implemented": True, "input_worker_admission_pending": True,
                "new_geometry_cases_planned": 12, "new_diagnostic_predictions_maximum": 9,
                "full_foundation_passed": False, "S4_overall_complete": False,
                "M2_allowed": False, "S5_allowed": False,
                "remaining_after_this_batch": ["new-geometry contact-label/density validation and shared-input core comparisons",
                                              "qualified candidate and numerical stability gates",
                                              "M2 only after explicit gate clearance", "S5 with at least 18 frozen unseen trajectories"],
                "run_directory": str(r.RUN), "protocol": str(r.PROTOCOL),
                "next_action": "actual Windows worker input preflight before new science submission"}
        state = {**plan, "root": str(r.ROOT), "plan": str(r.PLAN),
                 "status": "repair_review_registered_worker_not_started", "pid": None,
                 "running_predictions": False, "running_analysis": False, "running_preflight": False,
                 "old_noon_authorization_closed": True}
        resources = r.guard(r.BATCH_RESERVATION, r.BATCH_RESERVATION)
        items = [(r.AUTH/"authorization.json", r.encoded(authorization)), (r.PROTOCOL, r.encoded(protocol)),
                 (r.PLAN, r.encoded(plan)), (r.AUTH/"active_before.json", r.encoded(active)),
                 (r.AUTH/"execution_admission.json", r.encoded({"time": r.now(), "mutex": mutex,
                        "idle": idle, "resources": resources, "test_stdout": tests.stdout, "test_stderr": tests.stderr,
                        "scientific_predictions_started": 0, "actual_input_worker_passed": False})),
                 (r.AUTH/"active_registered.json", r.encoded(state)),
                 (r.ROOT/"reports/\u65e2\u6709\u5b9e\u9a8c\u81f4\u547d\u7f3a\u9677\u5ba1\u67e5\u4e0e\u8865\u9a8c\u51c6\u5165_20261019_v1.md",
                  (r.SOURCE/"review.md").read_bytes())]
        r.batch(items)
        signature = r.source_signature()
        r.batch([(r.RUN/"source_manifest.json", r.encoded(signature))] +
                [(r.RUN/"source"/rel, (r.ROOT/rel).read_bytes()) for rel in signature])
        r.mutable(r.ROOT/"active_research_run.json", state)
    print(json.dumps({"status": "registered_not_running", "source_files": len(signature),
                      "geometry_cases": 12, "diagnostic_predictions_maximum": 9,
                      "actual_new_accepted_diagnostics": 0}), flush=True)

def geometry_job(spec):
    folder = r.RUN/"geometry"/spec["id"]
    try:
        maneuver = scenarios.Maneuver.from_spec(spec)
    except ValueError as exc:
        result = {"spec": spec, "status": "inadmissible_control_design", "reason": str(exc),
                  "geometry_case_not_prediction_job": True}
        r.freeze(folder/"result.json", r.encoded(result))
        return result
    tc, coarse = rk4_reference(maneuver, .005)
    tf, fine = rk4_reference(maneuver, .0025)
    solved = solve_ivp(lambda t, y: independent_rhs(t, y, maneuver), (0, maneuver.end), fine[0],
                       method="DOP853", rtol=1e-10, atol=1e-12, max_step=.02, t_eval=tc)
    r.require(solved.success, "Independent ODE solver failed")
    other = solved.y.T
    independent_error = float(np.linalg.norm(independent_right_edge(other) -
                              common.right_edge(coarse, common.Vehicle()), axis=-1).max())
    step_error = float(np.linalg.norm(common.right_edge(fine[::2], common.Vehicle()) -
                                     common.right_edge(coarse, common.Vehicle()), axis=-1).max())
    peak_phi = float(np.rad2deg(np.abs(fine[:, 3])).max())
    polygons = shapely.polygons(common.body_corners(fine, common.Vehicle()))
    valid = bool(np.all(shapely.is_valid(polygons)) and np.isfinite(fine).all())
    result = {"spec": spec, "status": "geometry_admitted" if peak_phi <= 45. else "inadmissible_phi_design_range",
              "phi_max_deg": peak_phi, "phi_limit_deg": 45., "phi_clamped": False,
              "independent_solver_max_right_edge_error_m": independent_error,
              "reference_step_max_right_edge_error_m": step_error,
              "finite_valid_body_rectangles": valid, "truth_heading_error_rad": float(abs(fine[-1, 2])),
              "new_targets_or_contact_labels_generated": False, "new_prediction_jobs": 0}
    r.require(independent_error <= .005 and step_error <= .005 and valid
              and abs(fine[-1, 2]) < 2e-5, "Reference/geometry implementation check failed")
    arrays = {"time_005": tc, "state_005": coarse, "time_0025": tf, "state_0025": fine,
              "independent_state_005": other}
    blob = npz_blob(arrays)
    result["arrays"] = {key: {"sha256": common.array_hash(value), "dtype": value.dtype.str,
                              "shape": list(value.shape)} for key, value in arrays.items()}
    result["reference_npz_sha256"] = r.sha(blob)
    r.batch([(folder/"reference.npz", blob), (folder/"result.json", r.encoded(result))])
    return result

def trace_witnesses(inputs, targets, sequence, ids):
    hits = np.zeros((len(inputs["time"]), len(ids)), dtype=bool)
    minimum = np.full(len(ids), np.inf)
    points = shapely.points(targets["xy"][ids])
    if len(ids):
        edges = common.right_edge(sequence, common.Vehicle())
        for k in range(len(hits)):
            shape = geometry.edge_union(edges[k])
            distances = shapely.distance(points, shape)
            hits[k] = distances <= .05 + geometry.GEOMETRY_EPS
            minimum = np.minimum(minimum, distances)
    time = inputs["time"]
    contact = targets["contact_time"][ids]
    support = (time[:, None] >= 2-1e-9) & (contact[None, :] >= time[:, None]-1e-9) & (contact[None, :] <= time[:, None]+2+1e-9)
    return {"indices": ids, "xy": targets["xy"][ids], "time": time, "contact_time": contact,
            "hit": hits, "supported": support, "minimum_distance_m": minimum,
            "measurement_age_s": time-inputs["measurement_time"],
            "true_phase_offline": inputs["true_phase"],
            "observed_phase": prediction.observed_phase(inputs)}

def delay_job(job, data, targets, raw):
    folder = r.RUN/"jobs"/job["id"]
    observed = observations.preprocess(raw, job["processor"])
    inputs = {**data, **observed}
    result = evaluator.evaluate(inputs, targets, prediction.Method(**job["method"]), [evaluator.Variant()],
                                retain_sequence=True)
    point = result["point_output"]
    contact = targets["contact_time"]
    right = ((targets["edge"] == 2) & ~targets["front_ignored"] & np.isfinite(contact)
             & (contact >= 2-1e-9) & (contact <= inputs["time"][-1]-3+1e-9))
    first, valid = point[TAG+"_first"], point[TAG+"_valid"]
    miss = right & ~np.isfinite(valid)
    late = right & np.isfinite(valid) & (contact-valid < 1-1e-9)
    no_before = right & (~np.isfinite(first) | (first > contact+1e-9))
    old_folder = Path(job["old_folder"])
    old_report = r.read(old_folder/"report.json")
    for name, digest in old_report["output_sha256"].items():
        r.require(r.file_hash(old_folder/name) == digest, "Frozen original S2 output changed")
    with np.load(old_folder/"target_results.npz", allow_pickle=False) as z:
        old_valid = z[TAG+"_valid"]
        old_miss = right & ~np.isfinite(old_valid)
    ids = np.flatnonzero(miss | no_before | old_miss)
    witness = trace_witnesses(inputs, targets, result["sequence"], ids)
    for pos, index in enumerate(ids):
        alarm = np.flatnonzero(witness["hit"][:, pos] & (inputs["time"] >= 2-1e-9))
        supported = np.flatnonzero(witness["hit"][:, pos] & witness["supported"][:, pos])
        r.require((len(alarm) == 0 and not np.isfinite(first[index]))
                  or (len(alarm) > 0 and first[index] == inputs["time"][alarm[0]]), "Witness first alarm differs")
        r.require((len(supported) == 0 and not np.isfinite(valid[index]))
                  or (len(supported) > 0 and valid[index] == inputs["time"][supported[0]]), "Witness valid alarm differs")
    masks = {"miss": miss, "late": late, "no_before": no_before, "old_miss": old_miss}
    index_arrays = {key: np.packbits(mask, bitorder="little") for key, mask in masks.items()}
    meta = {"point_count": 70000, "bitorder": "little",
            "masks": {key: {"count": int(mask.sum()), "indices_sha256": common.array_hash(np.flatnonzero(mask))}
                      for key, mask in masks.items()}}
    result["summaries"][0].pop("geometry", None)
    summary = {"job": job, "scoring": result["summaries"][0],
               "historical_scoring_is_not_mixed": True, "witness_count": len(ids),
               "EXIT_phase_cannot_change_W2_constant_horizon": True,
               "confirmation_is_zero_so_not_a_confirmation_drop": True,
               "raw_state_sha256": common.array_hash(raw["state"]),
               "processed_state_sha256": common.array_hash(observed["state"]),
               "processed_alpha_sha256": common.array_hash(observed["alpha"])}
    arrays_meta = {key: {"sha256": common.array_hash(value), "dtype": value.dtype.str,
                         "shape": list(value.shape)} for key, value in point.items()}
    items = [(folder/"configuration.json", r.encoded(job)),
             (folder/"summary.json", r.encoded(summary)),
             (folder/"target_results.npz", npz_blob(point)), (folder/"array_metadata.json", r.encoded(arrays_meta)),
             (folder/"frame_results.npz", npz_blob({"counts": result["frame_counts"], "time": inputs["time"]})),
             (folder/"witnesses.npz", npz_blob(witness)),
             (folder/"failure_indices.npz", npz_blob(index_arrays)), (folder/"index_metadata.json", r.encoded(meta)),
             (folder/"timing.json", r.encoded(result["timing"]))]
    r.batch(items)
    report = {"id": job["id"], "output_sha256": {p.name: r.sha(b) for p, b in items},
              "source_signature": r.read(r.RUN/"source_manifest.json"), "time": r.now()}
    r.freeze(folder/"report.json", r.encoded(report))
    return {"id": job["id"], "report_sha256": r.file_hash(folder/"report.json")}

def run():
    r.require(r.before_deadline(), "No new submission after 08:00")
    r.require(not (r.RUN/"checkpoint.json").exists(), "This batch already started; inspect its state, do not duplicate")
    h = r.helper()
    cp = {"status": "preflight", "geometry": {}, "completed": {}, "new_formal": 0, "new_accepted_diagnostics": 0}
    with h.exclusive() as mutex:
        r.execution(h)
        signature = r.verify_sources()
        r.mutable(r.RUN/"runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            data, targets, raw, manifest = load_inputs()
            loaded = {m.__name__: str(Path(m.__file__).resolve()) for m in
                      (common, geometry, observations, prediction, scenarios, evaluator)}
            r.require(loaded["prediction"] == str(r.ROOT/"src_v3/prediction.py")
                      and loaded["evaluation_scored"] == str(r.ROOT/"src_s4_v1/evaluation_scored.py"),
                      "Actual worker module provenance differs")
            preflight = {"time": r.now(), "python": sys.executable, "root": str(r.ROOT), "loaded_modules": loaded,
                         "source_signature": signature, "manifest": manifest,
                         "target_count": 70000, "all_nine_processed_original_S2_input_hashes_exact": True,
                         "mutex": mutex, "resources": r.guard(r.BATCH_RESERVATION, r.BATCH_RESERVATION),
                         "new_accepted_diagnostics": 0}
            r.batch([(r.RUN/"preflight.json", r.encoded(preflight)),
                     (r.RUN/"raw_observations.npz", npz_blob({key: raw[key] for key in SENSOR_KEYS}))])
            active = r.read(r.ROOT/"active_research_run.json")
            active.update(status="geometry_delay_running", pid=os.getpid(), running_preflight=False,
                          running_analysis=True, input_worker_admitted=True,
                          next_action="monitor append-only log; never hash active checkpoint")
            r.mutable(r.ROOT/"active_research_run.json", active)
            print("PREFLIGHT PASSED: exact worker/root/modules, all nine original processed inputs, quota and deadline", flush=True)
            cp["status"] = "geometry_running"
            for spec in geometry_matrix():
                if not r.before_deadline():
                    raise TimeoutError("08:00 submission deadline reached")
                r.verify_sources()
                r.guard(16*1024**2)
                print("START GEOMETRY " + spec["id"], flush=True)
                cp["geometry"][spec["id"]] = geometry_job(spec)
                r.checkpoint(cp)
                print("DONE GEOMETRY " + spec["id"] + " " + cp["geometry"][spec["id"]]["status"], flush=True)
            cp["status"] = "delay_predictions_running"
            active.update(status="deterministic_delay_predictions_running", running_analysis=False, running_predictions=True)
            r.mutable(r.ROOT/"active_research_run.json", active)
            for job in old_matrix():
                if not r.before_deadline():
                    raise TimeoutError("08:00 submission deadline reached")
                r.verify_sources()
                r.guard(16*1024**2)
                print("SUBMIT DELAY " + job["id"], flush=True)
                cp["completed"][job["id"]] = delay_job(job, data, targets, raw)
                r.checkpoint(cp)
                print("DONE DELAY " + job["id"], flush=True)
            cp["status"] = "complete_pending_independent_acceptance"
            r.checkpoint(cp)
        except Exception as exc:
            cp["status"] = "stopped_failure_or_deadline"
            cp["failure"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(r.RUN/"runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    print("WORKER EXITING; independent close requires real process exit and mutex reacquisition", flush=True)

def independently_check_job(job, record, targets, data):
    folder = r.RUN/"jobs"/job["id"]
    r.require(r.file_hash(folder/"report.json") == record["report_sha256"], "Report/CP mismatch")
    report = r.read(folder/"report.json")
    r.require(report["source_signature"] == r.read(r.RUN/"source_manifest.json"), "Job source differs")
    for name, digest in report["output_sha256"].items():
        r.require(r.file_hash(folder/name) == digest, "Output SHA mismatch: " + name)
    metadata = r.read(folder/"array_metadata.json")
    with np.load(folder/"target_results.npz", allow_pickle=False) as z:
        r.require(set(z.files) == set(metadata), "Complete array set mismatch")
        point = {key: z[key] for key in z.files}
    for key, value in point.items():
        r.require({"sha256": common.array_hash(value), "dtype": value.dtype.str, "shape": list(value.shape)}
                  == metadata[key], "Full point array decode differs")
    contact = targets["contact_time"]
    right = ((targets["edge"] == 2) & ~targets["front_ignored"] & np.isfinite(contact)
             & (contact >= 2-1e-9) & (contact <= data["time"][-1]-3+1e-9))
    first, valid = point[TAG+"_first"], point[TAG+"_valid"]
    masks = {"miss": right & ~np.isfinite(valid),
             "late": right & np.isfinite(valid) & (contact-valid < 1-1e-9),
             "no_before": right & (~np.isfinite(first) | (first > contact+1e-9))}
    with np.load(Path(job["old_folder"])/"target_results.npz", allow_pickle=False) as old:
        masks["old_miss"] = right & ~np.isfinite(old[TAG+"_valid"])
    meta = r.read(folder/"index_metadata.json")
    with np.load(folder/"failure_indices.npz", allow_pickle=False) as z:
        for key, mask in masks.items():
            restored = np.unpackbits(z[key], bitorder="little")
            r.require(len(restored) == 70000 and np.array_equal(restored.astype(bool), mask), "Full failure mask differs")
            r.require(meta["masks"][key] == {"count": int(mask.sum()), "indices_sha256": common.array_hash(np.flatnonzero(mask))},
                      "Lossless failure index SHA differs")
    summary = r.read(folder/"summary.json")["scoring"]
    for name in ("miss", "late", "no_before"):
        r.require(summary["right_"+name] == int(masks[name].sum()), "Independent RIGHT summary differs")
    negative = ~np.isfinite(contact)
    fp = negative & np.isfinite(first) & (first >= 2-1e-9) & (first <= data["time"][-1]-3+1e-9)
    r.require(summary["negative_count"] == int(negative.sum()) and summary["negative_fp"] == int(fp.sum()),
              "Independent negative summary differs")
    columns = ["TP", "FP", "negative_opportunities", "support"]
    totals = {key: int(point[TAG+"_"+key].sum()) for key in columns}
    expected = [totals["TP"], totals["FP"], totals["negative_opportunities"]-totals["FP"], totals["support"]-totals["TP"]]
    r.require(all(x >= 0 for x in expected), "Negative confusion total")
    for key, value in zip(("frame_TP", "frame_FP", "frame_TN", "frame_FN"), expected):
        r.require(summary[key] == value, "Independent confusion summary differs")
    def ratio(a, b):
        return float(100*a/b) if b else None
    derived = {"right_contacts": int(right.sum()),
               "right_pct": ratio(int((masks["miss"] | masks["late"]).sum()), int(right.sum())),
               "negative_fp_pct": ratio(int(fp.sum()), int(negative.sum())),
               "frame_fpr_pct": ratio(expected[1], expected[1]+expected[2]),
               "frame_recall_pct": ratio(expected[0], expected[0]+expected[3])}
    for key, value in derived.items():
        r.require(summary[key] == value, "Independent ratio differs: " + key)
    for key, quantile in (("right_lead_p10_s", .1), ("right_lead_median_s", .5)):
        values = contact[right & np.isfinite(valid)]-valid[right & np.isfinite(valid)]
        wanted = float(np.quantile(values, quantile)) if len(values) else None
        r.require(summary[key] == wanted, "Independent lead summary differs")
    r.require(np.array_equal(point[TAG+"_ref_FP"], point[TAG+"_FP"])
              and np.array_equal(point[TAG+"_ref_negative_opportunities"], point[TAG+"_negative_opportunities"]),
              "Fixed W2 own/common reference arrays differ")
    r.require(summary["common_2s_reference_fpr_pct"] == summary["frame_fpr_pct"],
              "Fixed W2 own/common reference summary differs")
    for name in ("first", "valid"):
        timestamps = point[TAG+"_"+name]
        finite = timestamps[np.isfinite(timestamps)]
        r.require(np.isin(finite, data["time"]).all() and np.all(finite >= 2-1e-9),
                  "Scored first/valid timestamp outside exact scoring grid")
    with np.load(folder/"frame_results.npz", allow_pickle=False) as z:
        r.require(np.array_equal(z["counts"].sum(axis=(0, 1)), expected), "Independent frame/point totals differ")
    with np.load(folder/"witnesses.npz", allow_pickle=False) as z:
        expected_ids = np.flatnonzero(masks["miss"] | masks["no_before"] | masks["old_miss"])
        r.require(np.array_equal(z["indices"], expected_ids), "Witness selection differs")
        for j, index in enumerate(expected_ids):
            hit = np.flatnonzero(z["hit"][:, j] & z["supported"][:, j])
            r.require((len(hit) == 0 and not np.isfinite(valid[index]))
                      or (len(hit) > 0 and z["time"][hit[0]] == valid[index]), "Independent witness valid timestamp differs")
    return {"id": job["id"], "right_miss": summary["right_miss"], "right_late": summary["right_late"],
            "right_no_before": summary["right_no_before"], "near_point_fp_pct": summary["negative_fp_pct"],
            "frame_fpr_pct": summary["frame_fpr_pct"], "arrays_independently_decoded": len(point)}

def close():
    r.require(r.before_deadline(), "No independent scientific close after 08:00")
    r.require(not (r.RUN/"acceptance.json").exists(), "Independent close already exists; do not rerun")
    h = r.helper()
    with h.exclusive() as mutex:
        idle = r.execution(h, include_new=True)
        r.verify_sources()
        cp = r.read(r.RUN/"checkpoint.json")
        r.require(cp["status"] == "complete_pending_independent_acceptance"
                  and len(cp["geometry"]) == 12 and len(cp["completed"]) == 9, "Batch incomplete")
        r.mutable(r.RUN/"analysis_runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            data, targets, raw, manifest = load_inputs()
            rows = [independently_check_job(job, cp["completed"][job["id"]], targets, data) for job in old_matrix()]
            admitted, rejected = [], []
            for key, record in cp["geometry"].items():
                folder = r.RUN/"geometry"/key
                r.require(r.read(folder/"result.json") == record, "Geometry report/CP differs")
                if "arrays" in record:
                    r.require(r.file_hash(folder/"reference.npz") == record["reference_npz_sha256"], "Reference NPZ differs")
                    with np.load(folder/"reference.npz", allow_pickle=False) as z:
                        r.require(set(z.files) == set(record["arrays"]), "Complete geometry array set differs")
                        for name, desc in record["arrays"].items():
                            r.require(common.array_hash(z[name]) == desc["sha256"], "Full geometry array decode differs")
                        phi = float(np.rad2deg(np.abs(z["state_0025"][:, 3])).max())
                        r.require(phi == record["phi_max_deg"], "Independent phi admission differs")
                        r.require((phi <= 45.) == (record["status"] == "geometry_admitted"), "Phi gate differs")
                        independent_error = float(np.linalg.norm(independent_right_edge(z["independent_state_005"])
                            - common.right_edge(z["state_005"], common.Vehicle()), axis=-1).max())
                        step_error = float(np.linalg.norm(common.right_edge(z["state_0025"][::2], common.Vehicle())
                            - common.right_edge(z["state_005"], common.Vehicle()), axis=-1).max())
                        r.require(independent_error == record["independent_solver_max_right_edge_error_m"]
                                  and step_error == record["reference_step_max_right_edge_error_m"]
                                  and independent_error <= .005 and step_error <= .005,
                                  "Independent geometry convergence summary differs")
                (admitted if record["status"] == "geometry_admitted" else rejected).append(key)
            acceptance = {"status": "geometry_admission_and_nine_corrected_delay_diagnostics_independently_accepted",
                          "time": r.now(), "new_formal_predictions": 0, "new_accepted_diagnostics": 9,
                          "formal_total": 2238, "accepted_diagnostic_total": 66, "accepted_numeric_total": 2304,
                          "geometry_cases_checked": 12, "geometry_admitted": admitted, "geometry_rejected": rejected,
                          "geometry_is_not_contact_label_or_full_density_gate": True,
                          "independent_complete_point_arrays_decoded": sum(x["arrays_independently_decoded"] for x in rows),
                          "delay_results": rows, "checkpoint_sha256": r.file_hash(r.RUN/"checkpoint.json"),
                          "new_source_signature": r.read(r.RUN/"source_manifest.json"),
                          "full_foundation_passed": False, "S4_overall_complete": False, "M2_complete": False, "S5_complete": False,
                          "no_parameter_search_or_safety_candidate_selection": True, "execution_before": idle, "mutex": mutex}
            lines = ["# 新几何准入与纯200ms延迟失效诊断", "",
                     "本批次为基础诊断，不是补齐S4/M2/S5，也不改变旧排名或门限。", "",
                     "新增正式0、已验诊断9；累计正式2238、诊断66、已验数值2304。12项几何检查另记，不计预测。", "",
                     f"新几何准入{len(admitted)}项、不准入{len(rejected)}项。45度仍是仿真设计边界，没有当作机械极限或放宽。",
                     "参考积分由两种步长与独立DOP853核对；新几何尚未生成接触标签及目标密度资产，不是完整S0通过。", "",
                     "| 固定诊断 | 窗口漏报 | 迟报 | 接触前无报警 | 点误报% | 帧误报% |",
                     "| --- | ---: | ---: | ---: | ---: | ---: |"]
            for row in rows:
                lines.append(f"| {row['id']} | {row['right_miss']} | {row['right_late']} | {row['right_no_before']} | "
                             f"{row['near_point_fp_pct']:.8f} | {row['frame_fpr_pct']:.8f} |")
            lines += ["", "全部使用同一原7万坐标、标签和原始纯延迟观测；处理后输入SHA精确复现旧S2，但评分统一从2秒开始，不能与旧评分百分比混排。",
                      "所有漏报、迟报及接触前无报警索引完整无损保存；所有预登记漏报见证点均保留逐帧命中、窗口支持及数据年龄。",
                      "本批配置W始终为2秒，且持续确认为0，因此EXIT相位切换和确认丢弃不能解释本批漏报；其余姿态/控制预测误差仍需受控诊断，不能把相关误差当因果证明。",
                      "", "剩余：新几何接触标签/密度与共同输入比较；基础及预算门；合格候选后的M2与至少18条未见轨迹S5。未经上述准入不启动M2/S5。",
                      "有限栅格、静态目标、低速运动学仿真不是连续空间或实车安全证明。"]
            report = ("\n".join(lines)+"\n").encode("utf-8")
            r.batch([(r.RUN/"acceptance.json", r.encoded(acceptance)),
                     (r.RUN/"acceptance.json.gz", gzip.compress(r.encoded(acceptance), mtime=0)),
                     (r.RUN/"report.md", report),
                     (r.ROOT/"reports/\u51e0\u4f55\u6269\u5c55\u51c6\u5165\u4e0e200ms\u5ef6\u8fdf\u8bca\u65ad_20261019_v1.md", report)])
        finally:
            r.mutable(r.RUN/"analysis_runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    with h.exclusive() as released:
        idle_after = r.execution(h, include_new=True)
    receipt = {"time": r.now(), "acceptance_sha256": r.file_hash(r.RUN/"acceptance.json"),
               "checkpoint_sha256": acceptance["checkpoint_sha256"], "mutex_reacquired_and_released": released,
               "execution_after": idle_after, "accepted_new_diagnostics": 9}
    r.freeze(r.RUN/"close_receipt.json", r.encoded(receipt))
    plan = r.read(r.PLAN)
    plan.update(version="20261019-v2-two-bounded-diagnostics-accepted", previous_plan=r.PLAN.name,
                new_diagnostics_accepted_this_authorization=9, accepted_diagnostic_total=66, accepted_numeric_total=2304,
                next_action="no admissible candidate; remaining stages require separate frozen gate-respecting design")
    next_plan = r.ROOT/"resume_plan_20261019_v2.json"
    r.freeze(next_plan, r.encoded(plan))
    active = r.read(r.ROOT/"active_research_run.json")
    active.update(status="geometry_delay_independently_closed_not_running", plan=str(next_plan), pid=None,
                  running_predictions=False, running_analysis=False, running_preflight=False,
                  new_diagnostics_accepted_this_authorization=9, accepted_diagnostic_total=66, accepted_numeric_total=2304,
                  next_action=plan["next_action"])
    r.mutable(r.ROOT/"active_research_run.json", active)
    print(json.dumps({"status": acceptance["status"], "geometry_admitted": len(admitted),
                      "geometry_rejected": len(rejected), "accepted_diagnostic_total": 66}), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run", "close"])
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "close": close}[args.action]()
