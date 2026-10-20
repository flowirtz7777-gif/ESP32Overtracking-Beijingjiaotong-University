"""Whole-scope local-motion edge merge, full projections and a fresh census."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"
sys.path.insert(0, str(ROOT / "src_s4_local_motion_20261022_v2"))
import local_motion_driver as local
import numpy as np

spec = importlib.util.spec_from_file_location("local_motion_merge_core_v1", SOURCE / "motion_merge_core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
base, r, AUTH = local.base, local.r, local.AUTH
parent, census, merged = local.parent, local.parent.census, local.parent.merged
PARENT = local.PARENT
RUN = ROOT / "runs/resume_20261022_0000_local_motion_merge_v1"
PROTOCOL = ROOT / "protocol_local_motion_merge_20261022_0000_v1.json"
PLAN = ROOT / "resume_plan_20261022_0000_v28.json"
CLOSED_PLAN = ROOT / "resume_plan_20261022_0000_v29.json"
SESSION = AUTH / "runtime_sessions/local_motion_merge_launch_v1"
CLOSURE = AUTH / "runtime_sessions/local_motion_v2_closed_v1"
DEPENDENCIES = (local.RUN, PARENT, local.science.RUN, local.admin.RUN, local.FAILED,
                CLOSURE, AUTH / "runtime_sessions/local_motion_v2_first_close_v1")
RESERVATION = 896 * 1024**2
HASHES = {
    "checkpoint.json": "1ea29e8694295d702d67c59183c6c116f8c4b5606b88de19f2967a41cfd65f35",
    "acceptance.json": "501320f640e803e912d308e958c719e3effb42c4177a6c789660c9e60d56d13b",
    "close_receipt.json": "a009ace210d161014bde477822babcb18a7119d8b2483a6d95e8e7748a127265",
    "source_manifest.json": "c9e76e6ed9086bf8200769066aa9e78e051a393513c2f1bb1e1ddc170a02c795"}


def configure():
    local.configure()
    r.RUN, r.RUN_CAP = RUN, 1024**3


configure()


def execution():
    try:
        return local.execution()
    finally:
        configure()


def gate():
    try:
        local.verify()
        for name, sha in HASHES.items():
            r.require(r.file_hash(local.RUN / name) == sha, "Closed local-motion v2 bytes changed")
        a = r.read(local.RUN / "acceptance.json")
        local.whole_counts(a["accounting"])
        r.require(a["accounting"]["group_point_path_records_not_independent_samples"] == 45970
            and a["accounting"]["group_path_totals"]["new_edge_certified_candidates"] == 147
            and a["both_scientific_endpoints_all_labels_except_certified_edge_and_original_provenance_exact"]
            and a["all_unwitnessed_initial_leaf_spatial_diagnostics_exact_accepted_reuse"]
            and a["truth_asset_promotion_allowed"] is False, "Full accepted candidate scope required")
        receipt = r.read(local.RUN / "close_receipt.json")
        r.require(receipt["acceptance_sha256"] == HASHES["acceptance.json"], "Local receipt mismatch")
        inventory = r.read(CLOSURE / "all_closed_run_files_sha256.json")
        actual = {p.relative_to(local.RUN).as_posix(): {"sha256": r.file_hash(p), "bytes": p.stat().st_size}
                  for p in sorted(local.RUN.rglob("*")) if p.is_file()}
        r.require(actual == inventory, "Complete independently closed local run required")
        r.require(r.read(AUTH / "runtime_sessions/local_motion_v2_first_close_v1/exit.json")[
            "actual_wait_exit_code"] == 0, "Actual ancestor wait exit evidence required")
    finally:
        configure()


def signature():
    paths = {ROOT / rel for rel in r.read(local.RUN / "source_manifest.json")}
    paths.update(local.RUN / name for name in HASHES)
    paths.update(SOURCE.glob("*.py"))
    paths.update((PROTOCOL, PLAN, AUTH / "authorization.json"))
    paths.update(p for p in CLOSURE.rglob("*") if p.is_file())
    for folder in (AUTH / "runtime_sessions").glob("local_motion_merge_development_tests_v*"):
        paths.update(p for p in folder.rglob("*") if p.is_file())
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / "source_manifest.json")
    r.require(signature() == expected, "Frozen local-motion merge dependencies changed")
    for rel, sha in expected.items():
        r.require(r.file_hash(RUN / "source" / rel) == sha, "Frozen source copy differs")
    if full:
        gate()
        for rel, inventory in r.read(RUN / "dependency_files_sha256.json").items():
            folder = ROOT / rel
            r.require({p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} == set(inventory),
                      "Complete stopped parent file set differs")
            for name, sha in inventory.items():
                r.require(r.file_hash(folder / name) == sha, "Stopped parent file bytes differ")


def strip(arrays, prefix):
    return {k[len(prefix):]: v for k, v in arrays.items()
            if k.startswith(prefix) and not k.endswith("__packbits")}


def admit():
    try:
        gate()
        loaded, groups, assets, diagnostics = local.admit()
        cp = r.read(local.RUN / "checkpoint.json")
        acceptance = r.read(local.RUN / "acceptance.json")
        candidates, bindings = {}, {}
        for key, ids in groups.items():
            asset = assets[key]
            full_scope = asset[0]["all_reason_flags"] != 0
            r.require(np.array_equal(core.unpack(asset[0]["all_scope_packbits"], len(full_scope)), full_scope),
                      "Full parent scope flags and mask differ")
            for tag, time, states, error, vehicle, labels in parent.prior.path_iter(key, loaded, groups, asset):
                name = key + "/" + tag
                arrays, _ = base.read_arrays(local.RUN / "paths" / name)
                expected, summary, _ = local.build(key, tag, time, states, error, vehicle, labels,
                    asset, diagnostics[key], saved=arrays, independent=False)
                entry = cp["completed"][name]
                merged.checked_output(local.RUN / "paths" / name, expected,
                    local.record(key, tag, summary, time, states, error, vehicle), entry["path"])
                index = np.flatnonzero(full_scope).astype(np.int64)
                r.require(core.same(index, arrays["union_index"]) and core.same(
                    arrays["xy"], asset[0]["xy"][index]), "All current scope coordinates and indices required")
                original, candidate = strip(arrays, "original__"), strip(arrays, "candidate__")
                certified = arrays["trace__edge_newly_certified"]
                for field, value in labels.items():
                    r.require(core.same(value[index], original[field]), "Every original seed field must be byte-exact")
                core.merge_path(labels, index, candidate, full_scope, certified)
                r.require(acceptance["checks"][name]["records"] == len(index)
                    and acceptance["checks"][name]["newly_certified_edge_candidates"] == int(certified.sum()),
                    "Every local candidate row must have independent parent acceptance")
                for dataset_id in ids:
                    out, rec = local.projection(dataset_id, asset[0], arrays, scalar=True)
                    rec.update(group=key, path=tag)
                    merged.checked_output(local.RUN / "datasets" / tag / dataset_id, out, rec,
                                          entry["datasets"][dataset_id])
                candidates[name] = index, candidate, certified
                bindings[name] = {"scope_records": len(index), "newly_certified": int(certified.sum()),
                    "path_result_sha256": entry["path"]["result_sha256"], "accepted_candidate_hashes": HASHES,
                    "original_lower_sha256": base.common.array_hash(original["contact_lower_s"]),
                    "original_upper_sha256": base.common.array_hash(original["contact_upper_s"]),
                    "all_unwitnessed_diagnostics_and_all114_projections_bound": True,
                    "complete_original_prefix_exact_reuse_no_geometry": True}
        r.require(set(candidates) == set(cp["completed"]) == set(acceptance["checks"])
            and len(candidates) == 78 and len(groups) == 39 and len(loaded) == 57
            and sum(len(v[0]) for v in candidates.values()) == 45970
            and sum(int(v[2].sum()) for v in candidates.values()) == 147,
            "Complete all-scope double-path candidates required, not changed rows alone")
        return loaded, groups, assets, candidates, bindings
    finally:
        configure()


def build_group(key, asset, candidates, *, scalar):
    original, _, old_paths = asset
    full_scope = original["all_reason_flags"] != 0
    selected, certified, paths = {}, {}, {}
    for tag in core.TAGS:
        index, candidate, proof = candidates[key + "/" + tag]
        selected[tag], certified[tag] = index, proof
        paths[tag] = core.merge_path(old_paths[tag], index, candidate, full_scope, proof, scalar=scalar)
    combined = merged.core.scalar_combine(paths["oldpath"], paths["independent"]) if scalar else base.combine(
        paths["oldpath"], paths["independent"])
    classify = census.core.independent_classify if scalar else census.core.classify
    flags, scope = classify(paths["oldpath"], paths["independent"], combined)
    arrays = core.group_payload(original, paths, combined, flags, scope, selected, certified)
    summary = census.core.summarize(paths["oldpath"], paths["independent"], combined, flags, scope)
    for tag in core.TAGS:
        for field in ("contact_lower_s", "contact_upper_s"):
            r.require(core.same(paths[tag][field], old_paths[tag][field]), "Every scientific endpoint byte must remain exact")
    for name, value in original.items():
        if name.startswith(("merge_", "upper_merge_")) and name.endswith("__packbits"):
            r.require(core.same(value, arrays[name]), "Original budget/upper provenance changed")
    return paths, combined, flags, scope, arrays, summary


def group_record(key, ids, asset, bindings, summary):
    return {"summary": summary, "original_dataset_ids": ids, "reference_meta": asset[1]["reference_meta"],
        "profile": asset[1]["profile"], "prefix_dependencies": asset[1]["prefix_dependencies"],
        "parent_group_result_sha256": r.file_hash(PARENT / "groups" / key / "result.json"),
        "local_motion_dependencies": {tag: bindings[key + "/" + tag] for tag in core.TAGS},
        "both_original_scientific_endpoints_all_bytes_exact": True,
        "strict_merged_all_point_prefix_coverage_passed": True,
        "all_proven_exclusions_exactly_reused_not_recomputed": True,
        "old_budget_and_upper_provenance_masks_exact_new_local_masks_separate": True,
        "truth_asset_promotion_allowed": False}


def census_group(xy, paths, combined, flags, scope, *, scalar):
    index = np.flatnonzero(scope)
    out = {"union_index": index, "xy": core.take(xy, index, scalar=scalar),
           "all_reason_flags": flags, "all_scope_packbits": np.packbits(scope, bitorder="little")}
    for tag, values in (*paths.items(), ("combined", combined)):
        out.update({tag + "__" + k: core.take(v, index, scalar=scalar) for k, v in values.items()})
    return out


def projection(dataset_id, loaded, xy, paths, combined, flags, scope, arrays, *, scalar):
    old, _ = base.read_arrays(PARENT / "datasets" / dataset_id)
    index, target = old["union_index"], loaded[dataset_id]["target"]
    out = core.project(index, xy, target["xy"], paths, combined, flags, scope, arrays, scalar=scalar)
    projected = {k: core.take(v, index, scalar=scalar) for k, v in combined.items()}
    diff = merged.core.scalar_discrepancies(target, projected) if scalar else base.old_discrepancies(target, projected)
    out.update({k + "__packbits": np.packbits(v, bitorder="little") for k, v in diff.items()})
    r.require(core.same(out["union_index"], old["union_index"]) and core.same(out["xy"], old["xy"]),
              "Original coordinate/index dtype, shape, order and bytes changed")
    for tag in core.TAGS:
        for field in ("contact_lower_s", "contact_upper_s"):
            r.require(core.same(out[tag + "__" + field], old[tag + "__" + field]), "Projected endpoint bytes differ")
    for name, value in old.items():
        if name.startswith(("merge_", "upper_merge_")) and name.endswith("__packbits"):
            r.require(core.same(value, out[name]), "Original-order provenance bytes changed")
    record = {"summary": census.summarize_projection(paths, combined, index, flags, scope),
        "old_label_incompatibilities_not_prediction_scores": {k: int(v.sum()) for k, v in diff.items()},
        "parent_result_sha256": r.file_hash(PARENT / "datasets" / dataset_id / "result.json"),
        "original_xy_sha256": base.common.array_hash(target["xy"]),
        "original_union_index_sha256": base.common.array_hash(index),
        "mask_length": len(index), "bitorder": "little", "both_original_endpoints_and_original_prefixes_exact": True}
    selected = core.take(scope, index, scalar=scalar)
    rows = np.flatnonzero(selected)
    union = core.take(index, rows, scalar=scalar)
    unknown = {"original_index": rows, "union_index": union,
        "xy": core.take(target["xy"], rows, scalar=scalar),
        "reason_flags": core.take(flags, union, scalar=scalar),
        "all_scope_packbits": np.packbits(selected, bitorder="little")}
    return out, record, unknown


def copy_parent_diagnostics(key, tag, dataset_id):
    source = local.RUN / "datasets" / tag / dataset_id
    dest = RUN / "retained_parent_candidate_diagnostics" / tag / dataset_id
    r.batch([(dest / filename, (source / filename).read_bytes()) for filename in ("arrays.npz", "result.json")])
    return r.read(local.RUN / "checkpoint.json")["completed"][key + "/" + tag]["datasets"][dataset_id]


def check_parent_diagnostics(tag, dataset_id, entry):
    source = local.RUN / "datasets" / tag / dataset_id
    dest = RUN / "retained_parent_candidate_diagnostics" / tag / dataset_id
    for name in ("arrays.npz", "result.json"):
        r.require((dest / name).read_bytes() == (source / name).read_bytes(),
                  "Every retained original-order diagnostic byte must remain exact")
    r.require(r.file_hash(dest / "result.json") == entry["result_sha256"], "Retained diagnostic CP binding differs")


def totals(completed):
    geometry = {key: value["group"]["summary"] for key, value in completed.items()}
    rows = [{"summary": v["summary"]} for value in completed.values() for v in value["datasets"].values()]
    return census.totals(rows, geometry)


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN, CLOSED_PLAN)), "Attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), "-X", "utf8", "-B", "-m", "unittest", "discover",
            "-s", str(SOURCE), "-p", "test_*.py", "-v"], cwd=r"C:\Users\Admin",
            capture_output=True, encoding="utf-8", timeout=180)
        r.require(tests.returncode == 0, "Synthetic contract tests failed: " + tests.stderr)
        protocol = {"version": "whole-combined-scope-local-motion-edge-only-merge-v1",
            "deadline": r.read(AUTH / "authorization.json")["deadline"],
            "parent_merged_assets": str(PARENT), "local_candidates": str(local.RUN), "candidate_hashes": HASHES,
            "selection": "all22985 current combined-scope group points on both paths; all45970 rows, not only147 certified",
            "only_mutable_fields": sorted(core.MUTABLE), "both_scientific_endpoints_and_all_other_fields_byte_exact": True,
            "all78path_blocks_and114parent_diagnostic_projections_exactly_bound_and_retained": True,
            "full_population": "all39 groups/all57 full original-order double-path projections/all3360000 point-file records",
            "new_masks": "local_motion_selected/certified/changed; old budget and upper provenance exact",
            "independent_close": "every scalar replacement/combination/conflict/classification/discrepancy/projection/packbits padding",
            "all_unwitnessed_contact_initial_leaf_diagnostics_exact_no_contact_repair": True,
            "full_census_recomputed_no_old_unknown_mask_or_valid_counts": True,
            "no_geometry_label_kernel_ODE_prediction_or_score_recomputed": True,
            "complete_accepted_prefix_proofs_exactly_reused_no_proven_exclusions_recomputed": True,
            "truth_asset_promotion_allowed": False, "corrected_truth_revalidated_prediction_jobs": 0,
            "not_global_identifiability_formal_ODE_or_real_vehicle_certificate": True,
            "workers": 1, "inflight": 1, "run_cap_bytes": r.RUN_CAP, "reservation_bytes": RESERVATION,
            "total_E_Z_cap_bytes": r.CAP, "Z_reserve_bytes": r.RESERVE,
            "submitted_block": "one complete merged group including all original-order projections and census; drain at cutoff"}
        plan = {"version": "20261022-0000-v28-local-motion-full-merge",
            "deadline": protocol["deadline"], "authorization": str(AUTH / "authorization.json"),
            "run_directory": str(RUN), "entrypoint": str(Path(__file__)), "protocol": str(PROTOCOL),
            "parent_merged_assets": str(PARENT), "all_local_motion_candidates": str(local.RUN),
            "parent_complete_census": r.read(PARENT / "acceptance.json")["accounting"],
            "stage_status": "prepared_not_admitted", "scientific_acceptance_exists": False,
            "truth_asset_promotion_allowed": False, "strict_merged_all_point_prefix_coverage_passed": None,
            "corrected_truth_revalidated_prediction_jobs": 0, "all_label_dependent_claims_withheld": True,
            "historical_ledger": {"formal": 2238, "accepted_diagnostics": 66, "numeric_records": 2304},
            "S4_overall_complete": False, "M2_allowed": False, "S5_allowed": False,
            "ordered_remaining": ["complete exact merge/all57projections/full census and independent close",
                "all remaining unwitnessed contact/time/edge identifiability",
                "complete coarse/fine expanded populations and negative controls/counterexamples",
                "every affected score/report repair or exact unaffected proof"],
            "next_action": "full input and closed-candidate admission, all-scope exact local-motion merge"}
        inventory = {p.relative_to(ROOT).as_posix(): {q.relative_to(p).as_posix(): r.file_hash(q)
            for q in sorted(p.rglob("*")) if q.is_file()} for p in DEPENDENCIES}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / "dependency_files_sha256.json", r.encoded(inventory)),
            (RUN / "prelaunch.json", r.encoded({"time": r.now(), "execution": idle, "mutex": mutex,
                "tests_stdout": tests.stdout, "tests_stderr": tests.stderr,
                "resources": r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / "source_manifest.json", r.encoded(signed))]
            + [(RUN / "source" / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print("LOCAL MOTION FULL MERGE PREPARED; actual full admission pending", flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / "checkpoint.json").exists(), "Attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {"status": "preflight", "completed": {}}
        r.mutable(RUN / "runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            loaded, groups, assets, candidates, bindings = admit()
            r.freeze(RUN / "preflight.json", r.encoded({"time": r.now(), "groups": groups, "bindings": bindings,
                "all57inputs_39groups_all45970_scope_candidates_and114_unknown_diagnostics_bound": True,
                "execution": idle, "mutex": mutex}))
            active = r.read(ROOT / "active_research_run.json")
            active.update(version="20261022-0000-v28-local-motion-merge-running", status="local_motion_full_merge_running",
                run_directory=str(RUN), protocol=str(PROTOCOL), plan=str(PLAN), entrypoint=str(Path(__file__)),
                pid=os.getpid(), running_analysis=True, running_predictions=False, input_worker_admitted=True,
                input_worker_admission_pending=False, scientific_acceptance=None, scientific_close_receipt=None,
                scientific_close_actual_wait_exit_code=None, full_merge_all57projections_and_updated_census_required=True,
                stdout=str(SESSION / "stdout.log"), stderr=str(SESSION / "stderr.log"))
            r.mutable(ROOT / "active_research_run.json", active)
            print("LOCAL MOTION MERGE PREFLIGHT PASSED ALL57 /39 GROUPS /ALL45970 BOTH-PATH SCOPE /114 DIAGNOSTICS /UNCHANGED ENDPOINTS", flush=True)
            for key, ids in groups.items():
                r.require(r.before_deadline(), "No new full merge group after cutoff")
                verify(full=False)
                paths, combined, flags, scope, arrays, summary = build_group(key, assets[key], candidates, scalar=False)
                meta = group_record(key, ids, assets[key], bindings, summary)
                entry = {"group": base.save_arrays(RUN / "groups" / key, arrays, meta),
                    "census_group": base.save_arrays(RUN / "census/groups" / key,
                        census_group(arrays["xy"], paths, combined, flags, scope, scalar=False), meta),
                    "datasets": {}, "census_datasets": {}, "retained_parent_diagnostics": {}}
                for dataset_id in ids:
                    out, rec, unknown = projection(dataset_id, loaded, arrays["xy"], paths, combined, flags, scope, arrays, scalar=False)
                    rec.update(group=key, original_input=loaded[dataset_id]["spec"])
                    entry["datasets"][dataset_id] = base.save_arrays(RUN / "datasets" / dataset_id, out, rec)
                    entry["census_datasets"][dataset_id] = base.save_arrays(RUN / "census/datasets" / dataset_id, unknown, rec)
                    entry["retained_parent_diagnostics"][dataset_id] = {tag: copy_parent_diagnostics(key, tag, dataset_id)
                                                                      for tag in core.TAGS}
                cp["completed"][key] = entry
                r.checkpoint(cp)
                print("DONE LOCAL MOTION FULL MERGE GROUP " + key, flush=True)
            counts = totals(cp["completed"])
            r.require(counts["geometry_groups"] == 39 and counts["dataset_files"] == 57
                and counts["point_file_records"] == 3360000, "Full population required")
            cp.update(status="complete_pending_independent_local_motion_merge_close", accounting=counts)
            r.checkpoint(cp)
        except Exception:
            cp.update(status="stopped_failure_or_deadline", failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / "runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    print("LOCAL MOTION FULL MERGE WORKER EXITING; independent close pending", flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / "acceptance.json").exists()
        and not (RUN / "analysis_runner_lock.json").exists(), "Close attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / "checkpoint.json")
        r.require(cp["status"] == "complete_pending_independent_local_motion_merge_close"
            and len(cp["completed"]) == 39, "Incomplete merge cannot close")
        r.mutable(RUN / "analysis_runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            loaded, groups, assets, candidates, bindings = admit()
            r.require(set(groups) == set(cp["completed"]), "Every original group required")
            geometry, rows = {}, []
            for key, ids in groups.items():
                paths, combined, flags, scope, arrays, summary = build_group(key, assets[key], candidates, scalar=True)
                meta, entry = group_record(key, ids, assets[key], bindings, summary), cp["completed"][key]
                merged.checked_output(RUN / "groups" / key, arrays, meta, entry["group"])
                merged.checked_output(RUN / "census/groups" / key,
                    census_group(arrays["xy"], paths, combined, flags, scope, scalar=True), meta, entry["census_group"])
                r.require(set(entry["datasets"]) == set(entry["census_datasets"])
                    == set(entry["retained_parent_diagnostics"]) == set(ids), "Every original-order dataset required")
                geometry[key] = summary
                for dataset_id in ids:
                    out, rec, unknown = projection(dataset_id, loaded, arrays["xy"], paths, combined, flags, scope, arrays, scalar=True)
                    rec.update(group=key, original_input=loaded[dataset_id]["spec"])
                    merged.checked_output(RUN / "datasets" / dataset_id, out, rec, entry["datasets"][dataset_id])
                    merged.checked_output(RUN / "census/datasets" / dataset_id, unknown, rec, entry["census_datasets"][dataset_id])
                    r.require(set(entry["retained_parent_diagnostics"][dataset_id]) == set(core.TAGS), "Both paths required")
                    for tag in core.TAGS:
                        check_parent_diagnostics(tag, dataset_id, entry["retained_parent_diagnostics"][dataset_id][tag])
                    rows.append({"dataset": dataset_id, "group": key, "summary": rec["summary"]})
                print("CLOSE LOCAL MOTION FULL SCALAR MERGE /PROJECTIONS /CENSUS " + key, flush=True)
            counts = census.totals(rows, geometry)
            r.require(counts == cp["accounting"], "Independent full census differs")
            acceptance = {"time": r.now(), "status": "local_motion_full_scope_merge_all57projections_census_independently_checked",
                "accounting": counts, "geometry": geometry, "rows": rows,
                "all45970_scope_records_exactly_merged_including_unchanged": True,
                "all147_independently_certified_edge_candidates_exactly_merged": True,
                "all114_original_order_parent_candidate_unknown_diagnostic_projections_byte_exact": True,
                "both_scientific_endpoints_all_bytes_unchanged": True,
                "strict_merged_all_point_prefix_coverage_passed": True,
                "full_original_prefix_proofs_exactly_reused_no_exclusions_recomputed": True,
                "old_budget_and_upper_provenance_masks_exact_new_local_masks_separate": True,
                "all57_full_fields_original_index_dtype_order_and_packbits_padding_checked": True,
                "scalar_full_population_replacement_combination_conflicts_reasons_discrepancies_and_projections": True,
                "all_unknowns_budgets_and_conflicts_retained": True,
                "original_assets_predictions_scores_unchanged": True, "no_new_geometry_label_kernel_ODE_prediction_or_score": True,
                "truth_asset_promotion_allowed": False, "corrected_truth_revalidated_prediction_jobs": 0,
                "full_merge_all57projections_and_updated_census_required": False,
                "all_remaining_unknowns_and_full_expanded_populations_still_required": True,
                "all_label_dependent_claims_withheld": True, "not_global_identifiability_formal_ODE_or_real_vehicle_certificate": True,
                "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"), "source_signature": signature(),
                "execution": idle, "mutex": mutex}
            r.freeze(RUN / "acceptance.json", r.encoded(acceptance))
        finally:
            r.mutable(RUN / "analysis_runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), "version": "20261022-0000-v29-local-motion-full-merge-census-closed",
        "stage_status": "full_scope_local_motion_merge_all57projections_and_census_closed_not_global_truth",
        "scientific_acceptance_exists": True, "accounting": counts, "strict_merged_all_point_prefix_coverage_passed": True,
        "next_action": "all remaining unwitnessed contact/time/edge identifiability, full coarse/fine populations and controls, every affected score/report"}
    report = ("# Local Motion Full-Scope Merge and Updated Census\n\n"
        "All45970 scope path records, all39 groups, all57 original-order full-field projections and all3360000 point-file records. "
        "Only independently certified edge confidence/set fields change. Both contact endpoints, original indices, trajectories, "
        "all unselected quantities and prior provenance byte-exact. All114 original-order parent diagnostic projections retained. "
        "Independent scalar full replacement, combination, conflicts, classification, discrepancies, all fields and padding checked. "
        "No new geometry or predictions. Reasons overlap; no new independent samples. Complete conditional merge only, "
        "not global truth/identifiability/score repair or a formal ODE/real-vehicle certificate.\n\n" + str(counts) + "\n").encode("utf-8")
    r.batch([(RUN / "close_receipt.json", r.encoded({"time": r.now(), "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"),
        "acceptance_sha256": r.file_hash(RUN / "acceptance.json"), "execution_after": after,
        "mutex_reacquired_released": released})), (CLOSED_PLAN, r.encoded(plan)),
        (ROOT / "reports/local_motion_full_merge_updated_census_20261022_0000_v1.md", report)])
    active = r.read(ROOT / "active_research_run.json")
    active.update(version=plan["version"], status=plan["stage_status"], pid=None, running_analysis=False,
        plan=str(CLOSED_PLAN), scientific_acceptance=str(RUN / "acceptance.json"),
        scientific_close_receipt=str(RUN / "close_receipt.json"), next_action=plan["next_action"],
        complete_current_census=counts, last_accepted_merged_run=str(RUN),
        full_merge_all57projections_and_updated_census_required=False,
        all_remaining_unknowns_and_full_expanded_populations_still_required=True)
    r.mutable(ROOT / "active_research_run.json", active)
    print("LOCAL MOTION FULL MERGE AND CENSUS CLOSED; claims still withheld " + str(counts), flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / "runner_lock.json").exists(), "Attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), "-X", "utf8", "-B", "-u", str(Path(__file__)), "run"]
        r.freeze(SESSION / "policy.json", r.encoded({"time": r.now(), "argv": argv, "cwd": r"C:\Users\Admin",
            "execution": idle, "mutex": mutex, "resources": r.guard(RESERVATION, RESERVATION)}))
    for name in ("stdout.log", "stderr.log"):
        r.freeze(SESSION / name, b"")
    with (SESSION / "stdout.log").open("ab") as out, (SESSION / "stderr.log").open("ab") as err:
        child = subprocess.Popen(argv, cwd=r"C:\Users\Admin", stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / "launched.json", r.encoded({"time": r.now(), "pid_historical_identity_only": child.pid,
        "poll": child.poll(), "not_admission_proof": True}))
    print("LOCAL MOTION FULL MERGE LAUNCHED historical identity PID " + str(child.pid), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "run", "close"))
    globals()[parser.parse_args().action]()

