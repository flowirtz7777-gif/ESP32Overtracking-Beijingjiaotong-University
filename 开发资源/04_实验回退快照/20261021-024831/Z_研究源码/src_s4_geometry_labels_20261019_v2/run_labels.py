"""All-point contact-label step audit on newly admitted geometries only."""
from __future__ import annotations
import argparse
import gzip
import io as memory_io
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
DEPENDENCY = ROOT / "runs/resume_20261019_geometry_delay_recovery_v1"
RUN = ROOT / "runs/resume_20261019_geometry_labels_v2"
FAILED = ROOT / "runs/resume_20261019_geometry_labels_v1"
PROTOCOL = ROOT / "protocol_geometry_labels_20261019_v2.json"
PLAN = ROOT / "resume_plan_20261019_v4.json"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src_s4_repair_review_20261019_v1"))
import runtime as bounded_io
import run_repair as dep
import numpy as np
import shapely

def scan_size(root):
    total = 0
    stack = [Path(root)]
    while stack:
        directory = stack.pop()
        if not directory.exists():
            continue
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                else:
                    raise RuntimeError("Nonregular research asset: " + entry.path)
    return total

# This new process uses the frozen generic I/O with an explicitly versioned resource policy.
# No other process or historical source file is modified by these local bindings.
bounded_io.RUN = RUN
bounded_io.RUN_CAP = 512 * 1024**2
bounded_io.tree_bytes = scan_size
RESERVATION = 256 * 1024**2
require, read, encoded = bounded_io.require, bounded_io.read, bounded_io.encoded

def signature():
    paths = [*sorted(SOURCE.glob("*.py")), PROTOCOL,
             *sorted((ROOT/"src_s4_geometry_labels_20261019_v1").glob("*.py")),
             ROOT/"protocol_geometry_labels_20261019_v1.json",
             bounded_io.AUTH/"runtime_sessions/geometry_labels_capacity_failure_v1/failure_receipt.json",
             ROOT/"src_s4_repair_review_20261019_v1/runtime.py",
             ROOT/"src_s4_repair_review_20261019_v1/run_repair.py",
             *sorted((ROOT/"src_s4_repair_recovery_20261019_v1").glob("*.py")),
             ROOT/"resume_plan_20261019_recovery_v1.json",
             DEPENDENCY/"recovery_source_manifest.json",
             DEPENDENCY/"interruption_receipt.json",
             *sorted((ROOT/"src_v3").glob("*.py")),
             ROOT/"src_s4_v1/evaluation_scored.py",
             bounded_io.AUTH/"authorization.json"]
    return {p.relative_to(ROOT).as_posix(): bounded_io.file_hash(p) for p in paths}

def verify_sources():
    require(signature() == read(RUN/"source_manifest.json"), "New label-stage source changed")
    for rel, digest in signature().items():
        require(bounded_io.file_hash(RUN/"source"/rel) == digest, "New source snapshot changed")

def execution():
    h = bounded_io.helper()
    h.NAMES = (*h.NAMES, DEPENDENCY.name, FAILED.name)
    result = bounded_io.execution(h, include_new=(RUN/"runner_lock.json").exists())
    for path in DEPENDENCY.glob("*runner_lock.json"):
        require(read(path)["status"] == "stopped", "Dependency analysis is still running")
    return h, result

def specifications():
    failure = read(bounded_io.AUTH/"runtime_sessions/geometry_labels_capacity_failure_v1/failure_receipt.json")
    require(failure["no_labels_completed"], "Do not repeat previously completed labels")
    for rel, digest in failure["all_failed_run_files_sha256"].items():
        require(bounded_io.file_hash(FAILED/rel) == digest, "Failed G1 history changed")
    acceptance = read(DEPENDENCY/"acceptance.json")
    receipt = read(DEPENDENCY/"close_receipt.json")
    require(bounded_io.file_hash(DEPENDENCY/"acceptance.json") == receipt["acceptance_sha256"],
            "Dependency independent acceptance differs")
    require(acceptance["new_accepted_diagnostics"] == 9, "Dependency nine predictions not accepted")
    require(bounded_io.file_hash(DEPENDENCY/"checkpoint.json") == receipt["checkpoint_sha256"],
            "Dependency closed checkpoint differs")
    recovery = read(DEPENDENCY/"recovery_source_manifest.json")
    for rel, digest in recovery.items():
        require(bounded_io.file_hash(ROOT/rel) == digest
                and bounded_io.file_hash(DEPENDENCY/"recovery_source"/rel) == digest,
                "Recovery provenance differs")
    interrupted = read(DEPENDENCY/"interruption_receipt.json")
    original = Path(read(ROOT/"resume_plan_20261019_recovery_v1.json")["interrupted_run"])
    for rel, digest in interrupted["original_files_sha256"].items():
        require(bounded_io.file_hash(original/rel) == digest, "Preserved interruption history differs")
    result = []
    for key in acceptance["geometry_admitted"]:
        folder = DEPENDENCY/"geometry"/key
        record = read(folder/"result.json")
        require(record["status"] == "geometry_admitted", "Only predeclared phi-admitted cases allowed")
        require(bounded_io.file_hash(folder/"reference.npz") == record["reference_npz_sha256"],
                "Frozen new-geometry reference changed")
        result.append({"id": key, "reference_folder": str(folder),
                       "result_sha256": bounded_io.file_hash(folder/"result.json"),
                       "reference_sha256": record["reference_npz_sha256"], "spec": record["spec"]})
    require(bool(result), "No new geometry admitted; do not force a label batch")
    return result

def reference_arrays(spec):
    folder = Path(spec["reference_folder"])
    require(bounded_io.file_hash(folder/"reference.npz") == spec["reference_sha256"], "Reference changed")
    with np.load(folder/"reference.npz", allow_pickle=False) as saved:
        return {key: saved[key] for key in saved.files}

def compare_labels(a, b):
    finite_a, finite_b = np.isfinite(a["contact_time"]), np.isfinite(b["contact_time"])
    both = finite_a & finite_b
    delta = np.abs(a["contact_time"][both]-b["contact_time"][both])
    positive_changed = finite_a != finite_b
    right_changed = (a["edge"] == 2) != (b["edge"] == 2)
    front_changed = a["front_ignored"] != b["front_ignored"]
    masks = {"contact_existence_changed": positive_changed, "RIGHT_membership_changed": right_changed,
             "front_exclusion_changed": front_changed, "any_edge_changed": a["edge"] != b["edge"]}
    values = {key: int(mask.sum()) for key, mask in masks.items()}
    values["max_common_contact_time_change_s"] = float(delta.max()) if len(delta) else None
    values["label_step_gate_passed"] = (not positive_changed.any() and not right_changed.any()
            and not front_changed.any() and (not len(delta) or float(delta.max()) <= .005+1e-8))
    return values, masks

def union_membership_exact(xy, body, contact_time):
    return bool(np.array_equal(
        shapely.dwithin(shapely.points(xy), body, .05+dep.geometry.GEOMETRY_EPS),
        np.isfinite(contact_time)))


def capacity_admitted_pool(body, right, generator=None):
    generator = dep.geometry.generate_target_pool if generator is None else generator
    rejected = []
    for spacing in (.02, .01):
        try:
            xy, groups, sampling = generator(body, right, 140000, spacing)
        except ValueError as exc:
            if not str(exc).startswith("Insufficient unique near-field target pool:"):
                raise
            rejected.append({"spacing_m": spacing, "reason": str(exc)})
            continue
        sampling.update(capacity_rule_spacing_m=[.02, .01],
                        previous_capacity_rejections=rejected,
                        selection_uses_geometry_capacity_only=True)
        return xy, groups, sampling
    raise ValueError("Both frozen geometry-only capacity grids failed: " + json.dumps(rejected))

def prepare():
    require(bounded_io.before_deadline(), "08:00 cutoff passed")
    require(not RUN.exists() and not PROTOCOL.exists() and not PLAN.exists(), "Label admission already exists")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        specs = specifications()
        active = read(ROOT/"active_research_run.json")
        require(active["accepted_diagnostic_total"] == 66 and active["accepted_numeric_total"] == 2304,
                "Read actual accepted baseline before next stage")
        tests = subprocess.run([str(bounded_io.PYTHON), "-X", "utf8", "-B", "-m", "unittest", "discover",
                                "-s", str(SOURCE), "-p", "test_labels.py", "-v"],
                               cwd=r"C:\Users\Admin", capture_output=True, encoding="utf-8", timeout=180)
        require(tests.returncode == 0, "Label tests failed before freeze: " + tests.stderr)
        protocol = {"version": "new-geometry-contact-label-step-20261019-v2-capacity-admission",
                    "deadline_local": "2026-10-19T08:00:00+08:00", "specs": specs,
                    "dependency_acceptance_sha256": bounded_io.file_hash(DEPENDENCY/"acceptance.json"),
                    "target_pool_spacing_rule_m": [.02, .01],
                    "use_first_geometry_capacity_admitted_grid": True,
                    "no_prediction_or_label_performance_used_for_spacing": True,
                    "failed_v1_retained": str(FAILED), "new_maximum_unique_target_count": 140000,
                    "nested_counts": [70000, 140000], "minimum_unique_targets": 20000,
                    "contact_tolerance_m": .05, "reference_steps_s": [.005, .0025],
                    "all_target_contact_and_RIGHT_and_front_membership_step_check": True,
                    "contact_time_change_max_s": .005, "truth_phi_limit_deg": 45, "phi_clamping": False,
                    "rejected_geometry_cases_preserved_in_dependency": True,
                    "all_admitted_geometries_included_no_performance_selection": True,
                    "no_predictions_no_new_algorithm_ranking": True, "new_accepted_prediction_jobs": 0,
                    "density_prediction_effect_gate_not_yet_executed": True,
                    "source_signature_uses_actual_files_not_old_foundation_src_path": True,
                    "source_policy_override": "new process local RUN/RUN_CAP and fresh scandir tree enumeration only",
                    "workers": 1, "inflight": 1, "run_cap_bytes": bounded_io.RUN_CAP,
                    "whole_batch_reservation_bytes": RESERVATION,
                    "whole_E_Z_cap_bytes": bounded_io.CAP, "Z_physical_reserve_bytes": bounded_io.RESERVE}
        plan = {**read(ROOT/"resume_plan_20261019_v3.json"),
                "version": "20261019-v4-new-geometry-label-capacity-repair",
                "previous_plan": "resume_plan_20261019_v3.json",
                "run_directory": str(RUN), "protocol": str(PROTOCOL), "entrypoint": str(SOURCE/"run_labels.py"),
                "source_implemented": True, "geometry_label_cases": len(specs),
                "new_label_stage_predictions": 0, "full_foundation_passed": False,
                "next_action": "actual reference/input admission then full-label step audit; no algorithm search"}
        bounded_io.batch([(PROTOCOL, encoded(protocol)), (PLAN, encoded(plan)),
                          (RUN/"prelaunch.json", encoded({"time": bounded_io.now(), "mutex": mutex,
                              "idle": idle, "test_stdout": tests.stdout, "test_stderr": tests.stderr,
                              "resources": bounded_io.guard(RESERVATION, RESERVATION)}))])
        frozen = signature()
        bounded_io.batch([(RUN/"source_manifest.json", encoded(frozen))] +
                         [(RUN/"source"/rel, (ROOT/rel).read_bytes()) for rel in frozen])
        active.update(status="geometry_label_stage_registered_not_running", plan=str(PLAN), run_directory=str(RUN),
                      protocol=str(PROTOCOL), entrypoint=str(Path(__file__)), pid=None,
                      running_predictions=False, running_preflight=False, running_analysis=False,
                      next_action=plan["next_action"])
        bounded_io.mutable(ROOT/"active_research_run.json", active)
    print(json.dumps({"status": "label_stage_registered_not_running", "cases": len(specs), "new_predictions": 0}), flush=True)

def execute_case(spec, arrays):
    folder = RUN/"cases"/spec["id"]
    coarse_states, fine_states = arrays["state_005"], arrays["state_0025"]
    coarse_segments, _, _ = dep.geometry.complete_geometry(coarse_states)
    fine_segments, body, right = dep.geometry.complete_geometry(fine_states)
    xy, groups, sampling = capacity_admitted_pool(body, right)
    print("TARGET CAPACITY PASSED " + spec["id"] + " " + json.dumps(sampling), flush=True)
    require(len(np.unique(xy, axis=0)) == 140000 and np.isfinite(xy).all(), "Unique finite target pool failed")
    a = dep.geometry.label_contacts(xy, {"time": arrays["time_005"], "state": coarse_states}, coarse_segments)
    b = dep.geometry.label_contacts(xy, {"time": arrays["time_0025"], "state": fine_states}, fine_segments)
    values, masks = compare_labels(a, b)
    values.update(case_id=spec["id"], target_count=140000,
                  coarse_negative_layer_contacts=int(np.isfinite(a["contact_time"][groups == 2]).sum()),
                  fine_negative_layer_contacts=int(np.isfinite(b["contact_time"][groups == 2]).sum()),
                  positive_union_membership_exact=union_membership_exact(xy, body, b["contact_time"]))
    values["label_step_gate_passed"] &= (values["coarse_negative_layer_contacts"] == 0
                                        and values["fine_negative_layer_contacts"] == 0
                                        and values["positive_union_membership_exact"])
    nested = dep.geometry.subset_indices(groups, 70000)
    require(len(nested) == len(np.unique(nested)) == 70000, "Nested original-coordinate projection failed")
    payload_arrays = {"xy": xy, "group": groups, "nested_70000_indices": nested,
                      **{"coarse_"+k: v for k, v in a.items()}, **{"fine_"+k: v for k, v in b.items()},
                      **{"change_"+k: np.packbits(v, bitorder="little") for k, v in masks.items()}}
    metadata = {key: {"sha256": dep.common.array_hash(value), "dtype": value.dtype.str,
                      "shape": list(value.shape)} for key, value in payload_arrays.items()}
    blob = dep.npz_blob(payload_arrays)
    record = {"spec": spec, "checks": values, "sampling": sampling, "arrays": metadata,
              "targets_npz_sha256": bounded_io.sha(blob), "full_foundation_passed": False,
              "prediction_jobs": 0, "input_is_not_formal_unseen_test": True}
    bounded_io.batch([(folder/"targets.npz", blob), (folder/"result.json", encoded(record))])
    return {"result_sha256": bounded_io.file_hash(folder/"result.json"), "checks": values}

def run():
    require(bounded_io.before_deadline(), "No submission after cutoff")
    require(not (RUN/"checkpoint.json").exists(), "Label batch already started; do not duplicate")
    h, _ = execution()
    cp = {"status": "preflight", "completed": {}, "new_prediction_jobs": 0}
    with h.exclusive() as mutex:
        _, idle = execution()
        verify_sources()
        bounded_io.mutable(RUN/"runner_lock.json", {"status": "running", "pid": os.getpid(), "time": bounded_io.now()})
        try:
            specs = specifications()
            require(specs == read(PROTOCOL)["specs"], "Frozen geometry input matrix differs")
            loaded = {spec["id"]: reference_arrays(spec) for spec in specs}
            bounded_io.batch([(RUN/"preflight.json", encoded({"time": bounded_io.now(), "python": sys.executable,
                "actual_loaded_reference_cases": len(loaded), "protocol_sha256": bounded_io.file_hash(PROTOCOL),
                "source_signature": signature(), "mutex": mutex, "execution_before": idle,
                "resources": bounded_io.guard(RESERVATION, RESERVATION)}))])
            active = read(ROOT/"active_research_run.json")
            active.update(status="geometry_label_step_audit_running", pid=os.getpid(), running_analysis=True,
                          running_preflight=False, running_predictions=False)
            bounded_io.mutable(ROOT/"active_research_run.json", active)
            print("PREFLIGHT ALL NEW GEOMETRY REFERENCES PASSED", flush=True)
            for spec in specs:
                require(bounded_io.before_deadline(), "08:00 reached; no new case submission")
                verify_sources()
                bounded_io.guard(32*1024**2)
                print("START LABELS " + spec["id"], flush=True)
                cp["completed"][spec["id"]] = execute_case(spec, loaded[spec["id"]])
                bounded_io.checkpoint(cp)
                print("DONE LABELS " + spec["id"] + " " + json.dumps(cp["completed"][spec["id"]]["checks"]), flush=True)
            cp["status"] = "complete_pending_independent_acceptance"
            bounded_io.checkpoint(cp)
        except Exception as exc:
            cp["status"] = "stopped_failure_or_deadline"
            cp["failure"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
            bounded_io.checkpoint(cp)
            raise
        finally:
            bounded_io.mutable(RUN/"runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": bounded_io.now()})
    print("LABEL WORKER EXITING; await real exit before independent close", flush=True)

def close():
    require(bounded_io.before_deadline(), "No independent analysis submission after cutoff")
    require(not (RUN/"acceptance.json").exists(), "Label close already exists")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify_sources()
        cp = read(RUN/"checkpoint.json")
        specs = read(PROTOCOL)["specs"]
        require(cp["status"] == "complete_pending_independent_acceptance" and len(cp["completed"]) == len(specs),
                "Label batch not complete")
        bounded_io.mutable(RUN/"analysis_runner_lock.json",
                           {"status": "running", "pid": os.getpid(), "time": bounded_io.now()})
        try:
            rows = []
            for spec in specs:
                folder = RUN/"cases"/spec["id"]
                require(bounded_io.file_hash(folder/"result.json") == cp["completed"][spec["id"]]["result_sha256"],
                        "Label result/CP differs")
                record = read(folder/"result.json")
                sampling = record["sampling"]
                require(sampling["capacity_rule_spacing_m"] == [.02, .01]
                        and sampling["selection_uses_geometry_capacity_only"]
                        and sampling["spacing_m"] in (.02, .01)
                        and sampling["stratum_counts"] == [46667, 46667, 46666]
                        and all(c >= n for c, n in zip(sampling["capacity"], sampling["stratum_counts"])),
                        "Frozen geometry-only target capacity rule differs")
                require(bounded_io.file_hash(folder/"targets.npz") == record["targets_npz_sha256"], "Label NPZ differs")
                with np.load(folder/"targets.npz", allow_pickle=False) as z:
                    require(set(z.files) == set(record["arrays"]), "Complete label array set differs")
                    arrays = {key: z[key] for key in z.files}
                for key, value in arrays.items():
                    require({"sha256": dep.common.array_hash(value), "dtype": value.dtype.str,
                             "shape": list(value.shape)} == record["arrays"][key], "Full label-array decode differs")
                a = {key.removeprefix("coarse_"): value for key, value in arrays.items() if key.startswith("coarse_")}
                b = {key.removeprefix("fine_"): value for key, value in arrays.items() if key.startswith("fine_")}
                derived, masks = compare_labels(a, b)
                for key, value in derived.items():
                    require(value == record["checks"][key] or key == "label_step_gate_passed",
                            "Independent all-point step check differs")
                for key, mask in masks.items():
                    restored = np.unpackbits(arrays["change_"+key], bitorder="little")
                    require(len(restored) == 140000 and np.array_equal(restored.astype(bool), mask),
                            "Full all-point change indices differ")
                require(len(np.unique(arrays["xy"], axis=0)) == 140000, "Independent unique-target audit failed")
                expected_ids = dep.geometry.subset_indices(arrays["group"], 70000)
                require(np.array_equal(arrays["nested_70000_indices"], expected_ids), "Independent nesting differs")
                coarse_neg = int(np.isfinite(a["contact_time"][arrays["group"] == 2]).sum())
                fine_neg = int(np.isfinite(b["contact_time"][arrays["group"] == 2]).sum())
                references = reference_arrays(spec)
                _, body, _ = dep.geometry.complete_geometry(references["state_0025"])
                membership = union_membership_exact(arrays["xy"], body, b["contact_time"])
                require(coarse_neg == record["checks"]["coarse_negative_layer_contacts"]
                        and fine_neg == record["checks"]["fine_negative_layer_contacts"]
                        and membership == record["checks"]["positive_union_membership_exact"],
                        "Independent negative-layer or geometric-union check differs")
                passed = derived["label_step_gate_passed"] and coarse_neg == 0 and fine_neg == 0 and membership
                require(bool(passed) == record["checks"]["label_step_gate_passed"], "Independent label admission differs")
                rows.append(record["checks"])
            acceptance = {"status": "new_geometry_all_point_contact_label_step_audit_independently_closed",
                          "time": bounded_io.now(), "cases": len(rows), "rows": rows,
                          "label_step_gate_passed_all_cases": all(x["label_step_gate_passed"] for x in rows),
                          "new_prediction_jobs": 0, "new_accepted_prediction_jobs": 0,
                          "formal_total": 2238, "accepted_diagnostic_total": 66, "accepted_numeric_total": 2304,
                          "full_foundation_passed": False, "numeric_density_paired_effect_gate_completed": False,
                          "M2_or_S5_admitted": False, "source_signature": signature(),
                          "checkpoint_sha256": bounded_io.file_hash(RUN/"checkpoint.json"), "mutex": mutex, "execution_before": idle}
            lines = ["# 新几何全点接触标签步长核验", "",
                     "本次仅检查新几何下140000点接触标签的步长一致性与70000点嵌套资产，不是算法预测或完整基础门通过。", "",
                     "| 新几何 | 接触存在变化 | RIGHT归属变化 | FRONT排除变化 | 最大共同接触时差/s | 标签步长门 |",
                     "| --- | ---: | ---: | ---: | ---: | --- |"]
            for row in rows:
                lines.append(f"| {row['case_id']} | {row['contact_existence_changed']} | {row['RIGHT_membership_changed']} | "
                             f"{row['front_exclusion_changed']} | {row['max_common_contact_time_change_s']} | {row['label_step_gate_passed']} |")
            lines += ["", "任何失败均保留完整坐标、两种步长的全部接触/面标签和全长无损变化索引，不删除稀有点、不按结果改门限。",
                      "本阶段新增预测0；累计正式2238、诊断66、已验数值2304不变。完整密度/稀有覆盖及候选预算门仍未宣布通过，M2/S5不准入。",
                      "若标签归属对步长敏感，应先另版本修复接触分类/不确定性表达，不能拿不稳标签继续寻优。",
                      "有限栅格、仿真设计车型与静态开发点不是连续空间或实车安全证明。"]
            report = ("\n".join(lines)+"\n").encode("utf-8")
            bounded_io.batch([(RUN/"acceptance.json", encoded(acceptance)),
                              (RUN/"acceptance.json.gz", gzip.compress(encoded(acceptance), mtime=0)),
                              (RUN/"report.md", report),
                              (ROOT/"reports/\u65b0\u51e0\u4f55\u5168\u70b9\u63a5\u89e6\u6807\u7b7e\u6b65\u957f\u6838\u9a8c_20261019_v2.md", report)])
        finally:
            bounded_io.mutable(RUN/"analysis_runner_lock.json",
                               {"status": "stopped", "pid": os.getpid(), "time": bounded_io.now()})
    with h.exclusive() as released:
        _, idle_after = execution()
    bounded_io.freeze(RUN/"close_receipt.json", encoded({"time": bounded_io.now(),
        "acceptance_sha256": bounded_io.file_hash(RUN/"acceptance.json"), "mutex_reacquired_and_released": released,
        "execution_after": idle_after, "new_predictions": 0}))
    plan = read(PLAN)
    plan.update(version="20261019-v5-new-geometry-label-step-independently-closed",
                previous_plan=PLAN.name, label_step_gate_passed=acceptance["label_step_gate_passed_all_cases"],
                next_action="repair any label instability before numeric density comparison; never optimize with unstable labels")
    next_plan = ROOT/"resume_plan_20261019_v5.json"
    bounded_io.freeze(next_plan, encoded(plan))
    active = read(ROOT/"active_research_run.json")
    active.update(status="geometry_labels_independently_closed_not_running", plan=str(next_plan),
                  pid=None, running_analysis=False, running_predictions=False, running_preflight=False,
                  next_action=plan["next_action"])
    bounded_io.mutable(ROOT/"active_research_run.json", active)
    print(json.dumps({"status": acceptance["status"], "all_cases_passed": acceptance["label_step_gate_passed_all_cases"],
                      "cases": len(rows), "new_predictions": 0}), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run", "close"])
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "close": close}[args.action]()
