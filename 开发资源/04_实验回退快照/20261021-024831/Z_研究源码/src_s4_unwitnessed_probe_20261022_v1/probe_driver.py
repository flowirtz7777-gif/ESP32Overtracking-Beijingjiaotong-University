"""All-current-scope supplemental unwitnessed probes; candidates are not promoted."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
sys.path.insert(0, str(ROOT / "src_s4_local_motion_merge_20261022_v1"))
import motion_merge_driver as parent
import probe_core as core
import numpy as np

base, r, AUTH = parent.base, parent.r, parent.AUTH
scope_core, science = parent.local.scope_core, parent.local.science
PARENT = parent.RUN
RUN = ROOT / "runs/resume_20261022_0000_unwitnessed_probe_v1"
PROTOCOL = ROOT / "protocol_unwitnessed_probe_20261022_0000_v1.json"
PLAN = ROOT / "resume_plan_20261022_0000_v30.json"
CLOSED_PLAN = ROOT / "resume_plan_20261022_0000_v31.json"
SESSION = AUTH / "runtime_sessions/unwitnessed_probe_launch_v1"
CLOSURE = AUTH / "runtime_sessions/local_motion_merge_closed_v1"
DEPENDENCIES = (PARENT, parent.local.RUN, parent.PARENT, science.RUN, parent.local.admin.RUN,
    parent.local.FAILED, CLOSURE, AUTH / "runtime_sessions/local_motion_merge_first_close_v1")
TAGS = ("oldpath", "independent")
RESERVATION = 896 * 1024**2
HASHES = {
    "checkpoint.json": "d94fdabd9d60d35cf69da262a11e52b648589c82b7b1abf189517ab50631735e",
    "acceptance.json": "991868ef3618d9a9fcbd9b72d955a7c961c1598bfb38f962d12767eb8ed791f4",
    "close_receipt.json": "cac17571e57fbb5b72534efed5a9b08d0c80527e2f9128f78ba52a672db8719e",
    "source_manifest.json": "3acf17cc60dc39fd867c45950cf50b0c52a625d954e28dbb222ce19c3f747c37"}


def configure():
    parent.configure()
    r.RUN, r.RUN_CAP = RUN, 1024**3


configure()


def execution():
    try:
        return parent.execution()
    finally:
        configure()


def gate():
    try:
        parent.verify()
        for name, digest in HASHES.items():
            r.require(r.file_hash(PARENT / name) == digest, "Closed v29 dependency changed")
        a = r.read(PARENT / "acceptance.json")
        r.require(a["strict_merged_all_point_prefix_coverage_passed"]
            and a["all45970_scope_records_exactly_merged_including_unchanged"]
            and a["both_scientific_endpoints_all_bytes_unchanged"]
            and a["accounting"]["complete_census_point_file_records"] == 26878
            and a["accounting"]["complete_census_group_unique_points"] == 22857
            and a["truth_asset_promotion_allowed"] is False, "Complete current accepted assets required")
        inventory = r.read(CLOSURE / "all_closed_run_files_sha256.json")
        actual = {p.relative_to(PARENT).as_posix(): r.file_hash(p) for p in PARENT.rglob("*") if p.is_file()}
        r.require(inventory == actual and len(actual) == 947, "Every closed parent file required")
        r.require(r.read(AUTH / "runtime_sessions/local_motion_merge_first_close_v1/exit.json")[
            "actual_wait_exit_code"] == 0, "Actual parent close exit required")
        r.require(r.file_hash(SOURCE / "probe_core.py") ==
            "4e541ddc29b65e1930bc270b852d3006826181c46570e9b46127188f4e851399",
            "Use exactly the synthetic-checked pure core")
    finally:
        configure()


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / "source_manifest.json")}
    paths.update(PARENT / name for name in HASHES)
    paths.update(SOURCE.glob("*.py"))
    paths.update((PROTOCOL, PLAN, AUTH / "authorization.json",
        AUTH / "runtime_sessions/unwitnessed_probe_development_ready_v1/development_state.json"))
    paths.update(p for p in CLOSURE.rglob("*") if p.is_file())
    for folder in (AUTH / "runtime_sessions").glob("unwitnessed_probe_development_tests_v*"):
        paths.update(p for p in folder.rglob("*") if p.is_file())
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / "source_manifest.json")
    r.require(signature() == expected, "Frozen supplemental-probe dependencies changed")
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / "source" / rel) == digest, "Frozen source copy changed")
    if full:
        gate()
        for rel, inventory in r.read(RUN / "dependency_files_sha256.json").items():
            folder = ROOT / rel
            r.require({p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} == set(inventory),
                      "Full stopped-parent inventory differs")
            for name, digest in inventory.items():
                r.require(r.file_hash(folder / name) == digest, "Stopped-parent bytes differ")


def path_iter(key, loaded, groups, asset):
    return parent.parent.prior.path_iter(key, loaded, groups, asset)


def admit():
    try:
        gate()
        loaded, groups, old_assets, candidates, bindings = parent.admit()
        cp = r.read(PARENT / "checkpoint.json")
        diagnostic_cp = r.read(science.RUN / "checkpoint.json")
        assets, diagnostics = {}, {}
        for key, ids in groups.items():
            paths, combined, flags, scope, expected, summary = parent.build_group(key, old_assets[key], candidates, scalar=False)
            rec = parent.group_record(key, ids, old_assets[key], bindings, summary)
            parent.merged.checked_output(PARENT / "groups" / key, expected, rec, cp["completed"][key]["group"])
            parent.merged.checked_output(PARENT / "census/groups" / key,
                parent.census_group(expected["xy"], paths, combined, flags, scope, scalar=False),
                rec, cp["completed"][key]["census_group"])
            full, meta = base.read_arrays(PARENT / "groups" / key)
            r.require(np.array_equal(parent.core.unpack(full["all_scope_packbits"], len(scope)), scope),
                      "All current scope flags and masks must bind")
            diagnostic, diagnostic_meta = base.read_arrays(science.RUN / "groups" / key)
            r.require(r.file_hash(science.RUN / "groups" / key / "result.json") ==
                diagnostic_cp["completed"][key]["group"]["result_sha256"], "Accepted unknown diagnostic binding differs")
            index = np.flatnonzero(scope).astype(np.int64)
            for tag in TAGS:
                labels = {k: v[index] for k, v in paths[tag].items()}
                scope_core.retained_unknown(index, full["xy"][index], labels, diagnostic, tag, scalar=True)
                core.selection(labels)
            for dataset_id in ids:
                out, projection_rec, unknown = parent.projection(dataset_id, loaded, full["xy"], paths,
                    combined, flags, scope, full, scalar=False)
                projection_rec.update(group=key, original_input=loaded[dataset_id]["spec"])
                entry = cp["completed"][key]
                parent.merged.checked_output(PARENT / "datasets" / dataset_id, out, projection_rec, entry["datasets"][dataset_id])
                parent.merged.checked_output(PARENT / "census/datasets" / dataset_id, unknown,
                    projection_rec, entry["census_datasets"][dataset_id])
                for tag in TAGS:
                    parent.check_parent_diagnostics(tag, dataset_id, entry["retained_parent_diagnostics"][dataset_id][tag])
            assets[key], diagnostics[key] = (full, meta, paths), (diagnostic, diagnostic_meta)
        r.require(len(groups) == 39 and len(loaded) == 57 and sum(
            int((a[0]["all_reason_flags"] != 0).sum()) for a in assets.values()) == 22857,
            "All current groups, files and scope required")
        return loaded, groups, assets, diagnostics
    finally:
        configure()


def summary(original, candidate, trace, retained):
    chosen, found = trace["selected_unwitnessed"], trace["found_strict_witness"]
    return {"scope_records": len(chosen), "selected_unwitnessed": int(chosen.sum()),
        "strict_new_witnesses": int(found.sum()), "remaining_unwitnessed": int((chosen & ~found).sum()),
        "source_initial_unknown": int(retained["retained_unknown_metric__initial_origin"].sum()),
        "source_time_leaf_unknown": int(retained["retained_unknown_metric__time_leaf_origin"].sum()),
        "source_witnessed_edge_unknown_exact_reuse": int((np.isfinite(original["contact_upper_s"]) & ~original["edge_certain"]).sum()),
        "known_noncontact_exact_reuse": int((original["contact_status"] == 0).sum()),
        "existing_witnesses_exact_reuse": int(np.isfinite(original["contact_upper_s"]).sum()),
        "new_witness_edge_certain": int((found & candidate["edge_certain"]).sum()),
        "forward_evaluations": int(trace["forward_evaluations"].sum()),
        "refine_evaluations": int(trace["refine_evaluations"].sum()),
        "forward_budget_exhausted": int(trace["forward_budget_exhausted"].sum()),
        "refine_budget_exhausted": int(trace["refine_budget_exhausted"].sum()),
        "scientific_lower_changes": int(np.sum(original["contact_lower_s"].view(np.uint64) != candidate["contact_lower_s"].view(np.uint64))),
        "science_upper_changed_only_for_strict_witnesses": int(found.sum())}


def build(key, tag, time, states, error, vehicle, all_labels, asset, diagnostic, *, saved=None):
    full = asset[0]
    mask = full["all_reason_flags"] != 0
    index = np.flatnonzero(mask).astype(np.int64)
    xy = full["xy"][index]
    labels = {k: v[index].copy() for k, v in all_labels.items()}
    params = dict(length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
    last = {}
    def geometry(points, pose):
        last.clear()
        last.update(query_xy=points.copy(), query_pose=pose.copy())
        body, faces = base.finite_face_geometry(points, pose, **params)
        last.update(body=body.copy(), faces=faces.copy())
        return body, faces
    def geos(point, pose, v):
        last.clear()
        last.update(query_xy=np.asarray(point).copy(), query_pose=np.asarray(pose).copy())
        body, faces = science.core.geos_geometry(point, pose, v)
        last.update(body=np.asarray(body), faces=np.asarray(faces))
        return body, faces
    checked = None
    try:
        if saved is None:
            proposed, trace, variation = core.candidate(xy, time, states, labels, error, vehicle, geometry)
        else:
            proposed, trace = parent.strip(saved, "candidate__"), parent.strip(saved, "trace__")
            variation = saved["motion_segment_variation_m"]
            checked = core.independent_check(xy, time, states, labels, proposed, error, vehicle, trace, variation, geos)
        retained = scope_core.retained_unknown(index, xy, labels, diagnostic[0], tag, scalar=saved is not None)
        out = {"union_index": index, "xy": xy, "full_scope_packbits": np.packbits(mask, bitorder="little"),
               "motion_segment_variation_m": variation}
        unknown = np.zeros(len(mask), bool)
        unknown[retained["retained_unknown_union_index"]] = True
        out["full_unknown_packbits"] = np.packbits(unknown, bitorder="little")
        for prefix, arrays in (("original__", labels), ("candidate__", proposed), ("trace__", trace)):
            out.update({prefix + k: v for k, v in arrays.items()})
            out.update({prefix + k + "__packbits": np.packbits(v, bitorder="little")
                        for k, v in arrays.items() if v.dtype == np.bool_})
        out.update(retained)
        for name, value in full.items():
            if name.startswith(("merge_", "upper_merge_", "local_motion_")) and name.endswith("__packbits"):
                out["parent_provenance__" + name] = value.copy()
        values = summary(labels, proposed, trace, retained)
        r.require(values["scientific_lower_changes"] == 0, "No new scientific lower is permitted")
        return out, values, checked
    except Exception:
        failure_arrays = {"original_xy": xy, "original_union_index": index, "time": time, "states": states,
            **{"original__" + k: v for k, v in labels.items()}, **{"last_geometry__" + k: v for k, v in last.items()}}
        if saved is not None:
            failure_arrays.update({"saved__" + k: v for k, v in saved.items()})
        base.save_arrays(RUN / "failure_context" / key / tag, failure_arrays,
            {"summary": {"failure": traceback.format_exc()}, "phase": "worker" if saved is None else "independent_close",
             "original_error_m": error, "vehicle": params, "not_accepted": True})
        raise


def record(key, tag, values, time, states, error, vehicle):
    return {"group": key, "path": tag, "summary": values, "parent_hashes": HASHES,
        "parent_group_result_sha256": r.file_hash(PARENT / "groups" / key / "result.json"),
        "diagnostic_group_result_sha256": r.file_hash(science.RUN / "groups" / key / "result.json"),
        "time_sha256": base.common.array_hash(time), "states_sha256": base.common.array_hash(states),
        "spatial_error_m": error, "vehicle": {"L": vehicle.L, "width": vehicle.width, "l_h": vehicle.l_h},
        "all_original_lowers_and_full_prefixes_exact_reuse": True,
        "original_unknown_diagnostics_retained_as_source_not_new_census": True,
        "fixed_probes_not_exhaustive_or_global_earliest_or_noncontact_proof": True,
        "truth_asset_promotion_allowed": False}


def projection(dataset_id, full, arrays, *, scalar=False):
    expected_scope = full["all_reason_flags"] != 0
    expected_index = np.flatnonzero(expected_scope).astype(np.int64)
    r.require(scope_core.same(arrays["union_index"], expected_index)
        and np.array_equal(parent.core.unpack(arrays["full_scope_packbits"], len(expected_scope)), expected_scope),
        "Projection requires all original scope indices and exact padding, not changed rows alone")
    r.require(all(value.ndim >= 1 and len(value) == len(expected_index) for name, value in arrays.items()
        if name.startswith(("original__", "candidate__", "trace__")) and not name.endswith("__packbits")),
        "All full-scope fields and two-dimensional probe traces required")
    source, _ = base.read_arrays(PARENT / "datasets" / dataset_id)
    out = scope_core.project(full["xy"], source["union_index"], source["xy"], arrays, scalar=scalar)
    r.require(scope_core.same(out["source_union_index"], source["union_index"]), "Original index dtype/order/bytes differ")
    for name, value in out.items():
        if name.startswith("parent_provenance__"):
            r.require(scope_core.same(value, source[name[len("parent_provenance__"):]]), "Every original-order provenance mask must bind")
    old, proposed, trace = (parent.strip(out, prefix) for prefix in ("original__", "candidate__", "trace__"))
    values = summary(old, proposed, trace, out)
    return out, {"dataset_id": dataset_id, "summary": values,
        "parent_dataset_result_sha256": r.file_hash(PARENT / "datasets" / dataset_id / "result.json"),
        "all_original_order_fields_indices_2D_probe_traces_and_padding_checked": True}


def accounting(completed):
    groups = [entry["path"]["summary"] for entry in completed.values()]
    rows = [v["summary"] for entry in completed.values() for v in entry["datasets"].values()]
    names = tuple(groups[0])
    return {"path_blocks": len(completed), "projected_path_files": len(rows),
        "scope_group_unique_points": sum(v["scope_records"] for v in groups) // 2,
        "scope_point_file_records": sum(v["scope_records"] for v in rows) // 2,
        "group_point_path_records_not_independent_samples": sum(v["scope_records"] for v in groups),
        "group_path_totals": {k: sum(v[k] for v in groups) for k in names},
        "weighted_path_diagnostics": {tag: {k: sum(v["summary"][k] for key, entry in completed.items()
            if key.endswith("/" + tag) for v in entry["datasets"].values()) for k in names} for tag in TAGS}}


def whole_counts(value):
    r.require(value["path_blocks"] == 78 and value["projected_path_files"] == 114
        and value["scope_group_unique_points"] == 22857 and value["scope_point_file_records"] == 26878
        and value["group_point_path_records_not_independent_samples"] == 45714
        and value["group_path_totals"]["selected_unwitnessed"] == 22836
        and value["group_path_totals"]["scientific_lower_changes"] == 0, "Complete both-path current scope required")
    for tag, selected, initial, leaf, edge in (("oldpath", 13956, 8973, 4983, 12922),
                                              ("independent", 13710, 8940, 4770, 12645)):
        row = value["weighted_path_diagnostics"][tag]
        r.require(row["selected_unwitnessed"] == selected and row["source_initial_unknown"] == initial
            and row["source_time_leaf_unknown"] == leaf and row["source_witnessed_edge_unknown_exact_reuse"] == edge,
            "All initial/leaf unknowns and witnessed-edge unknowns must be included")


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN, CLOSED_PLAN)), "Attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), "-X", "utf8", "-B", "-m", "unittest", "discover",
            "-s", str(SOURCE), "-p", "test_*.py", "-v"], cwd=r"C:\Users\Admin",
            capture_output=True, encoding="utf-8", timeout=180)
        r.require(tests.returncode == 0, "Synthetic probe/driver tests failed: " + tests.stderr)
        protocol = {"version": "full-current-scope-supplemental-unwitnessed-witness-candidates-v1",
            "deadline": r.read(AUTH / "authorization.json")["deadline"], "parent_merged_assets": str(PARENT),
            "parent_hashes": HASHES, "scope": "all22857 current group-scope points, both paths45714 records, all57/114 projections",
            "probe_selection": "all finite original lower and NaN upper; all original initial and noninitial unknowns",
            "original_kernel_already_tries_later_interval_start_mid_end": True,
            "supplemental_not_missing_original_later_search_repair": True,
            "forward_schedule": "original lower, then min(horizon,lower+1e-7*2**j), up to64",
            "refine_schedule": "up to64 internal witness probes, internal width1e-7, not scientific lower",
            "strict_body_witness": "distance+original empirical spatial error+1e-12<=.050000001",
            "confidence": "original full bracket segment variation + original spatial error/1e-12 and1mm rule",
            "all_original_lower_bytes_provenance_and_unselected_fields_exact": True,
            "new_budgets_separate_original_budget_masks_exact": True,
            "independent_close": "all scalar probes GEOS/strict final witnesses/full brackets Decimal70/finite faces/all arrays and original-order projections",
            "no_global_exhaustive_or_earliest_or_noncontact_proof": True, "no_proven_excluded_points_recomputed": True,
            "truth_asset_promotion_allowed": False, "corrected_truth_revalidated_prediction_jobs": 0,
            "all_remaining_unknowns_expanded_populations_controls_scores_still_required": True,
            "workers": 1, "inflight": 1, "run_cap_bytes": r.RUN_CAP, "reservation_bytes": RESERVATION,
            "total_E_Z_cap_bytes": r.CAP, "Z_reserve_bytes": r.RESERVE,
            "submitted_block": "one complete scope path and all its original-order projections, drain at cutoff"}
        plan = {"version": "20261022-0000-v30-unwitnessed-probe-candidates", "deadline": protocol["deadline"],
            "authorization": str(AUTH / "authorization.json"), "run_directory": str(RUN),
            "protocol": str(PROTOCOL), "entrypoint": str(Path(__file__)), "parent_merged_assets": str(PARENT),
            "parent_complete_census": r.read(PARENT / "acceptance.json")["accounting"],
            "stage_status": "prepared_not_admitted", "scientific_acceptance_exists": False,
            "truth_asset_promotion_allowed": False, "corrected_truth_revalidated_prediction_jobs": 0,
            "all_label_dependent_claims_withheld": True, "S4_overall_complete": False, "M2_allowed": False, "S5_allowed": False,
            "ordered_remaining": ["independent full-scope candidate close", "new whole merge/all57projections/full census",
                "all remaining contact/time/edge identifiability, full expanded populations/controls",
                "every affected score/report repair or exact unaffected proof"],
            "next_action": "complete real admission and supplemental strict witness candidates, not truth promotion"}
        inventories = {p.relative_to(ROOT).as_posix(): {q.relative_to(p).as_posix(): r.file_hash(q)
            for q in sorted(p.rglob("*")) if q.is_file()} for p in DEPENDENCIES}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / "dependency_files_sha256.json", r.encoded(inventories)),
            (RUN / "prelaunch.json", r.encoded({"time": r.now(), "execution": idle, "mutex": mutex,
                "tests_stdout": tests.stdout, "tests_stderr": tests.stderr,
                "resources": r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / "source_manifest.json", r.encoded(signed))]
            + [(RUN / "source" / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print("UNWITNESSED PROBE FULL SCOPE PREPARED; real admission pending", flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / "checkpoint.json").exists(), "Attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {"status": "preflight", "completed": {}}
        r.mutable(RUN / "runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            loaded, groups, assets, diagnostics = admit()
            r.freeze(RUN / "preflight.json", r.encoded({"time": r.now(), "groups": groups,
                "all57inputs_39current_assets_full22857_scope_bothpaths_and_original_unknown_diagnostics_bound": True,
                "execution": idle, "mutex": mutex}))
            active = r.read(ROOT / "active_research_run.json")
            active.update(version="20261022-0000-v30-unwitnessed-probe-running", status="full_scope_unwitnessed_probe_candidates_running",
                run_directory=str(RUN), protocol=str(PROTOCOL), plan=str(PLAN), entrypoint=str(Path(__file__)),
                pid=os.getpid(), running_analysis=True, running_predictions=False,
                input_worker_admitted=True, input_worker_admission_pending=False,
                scientific_acceptance=None, scientific_close_receipt=None, scientific_close_actual_wait_exit_code=None,
                full_merge_all57projections_and_updated_census_required=True,
                stdout=str(SESSION / "stdout.log"), stderr=str(SESSION / "stderr.log"))
            r.mutable(ROOT / "active_research_run.json", active)
            print("UNWITNESSED PROBE PREFLIGHT PASSED ALL57 /39 GROUPS /22857 FULL SCOPE BOTH PATHS /ALL ORIGINAL UNKNOWN DIAGNOSTICS", flush=True)
            for key, ids in groups.items():
                for tag, time, states, error, vehicle, labels in path_iter(key, loaded, groups, assets[key]):
                    r.require(r.before_deadline(), "No new complete probe path after cutoff")
                    verify(full=False)
                    arrays, values, _ = build(key, tag, time, states, error, vehicle, labels, assets[key], diagnostics[key])
                    entry = {"path": base.save_arrays(RUN / "paths" / key / tag, arrays,
                        record(key, tag, values, time, states, error, vehicle)), "datasets": {}}
                    for dataset_id in ids:
                        out, rec = projection(dataset_id, assets[key][0], arrays)
                        rec.update(group=key, path=tag)
                        entry["datasets"][dataset_id] = base.save_arrays(RUN / "datasets" / tag / dataset_id, out, rec)
                    cp["completed"][key + "/" + tag] = entry
                    r.checkpoint(cp)
                    print("DONE UNWITNESSED PROBE FULL SCOPE " + key + "/" + tag, flush=True)
            counts = accounting(cp["completed"])
            whole_counts(counts)
            cp.update(status="complete_pending_independent_unwitnessed_probe_close", accounting=counts)
            r.checkpoint(cp)
        except Exception:
            cp.update(status="stopped_failure_or_deadline", failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / "runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    print("UNWITNESSED PROBE WORKER EXITING; candidate acceptance and merge pending", flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / "acceptance.json").exists()
        and not (RUN / "analysis_runner_lock.json").exists(), "Close attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / "checkpoint.json")
        r.require(cp["status"] == "complete_pending_independent_unwitnessed_probe_close" and len(cp["completed"]) == 78,
                  "Incomplete candidates cannot close")
        r.mutable(RUN / "analysis_runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            loaded, groups, assets, diagnostics = admit()
            checks, rebuilt = {}, {}
            for key, ids in groups.items():
                for tag, time, states, error, vehicle, labels in path_iter(key, loaded, groups, assets[key]):
                    name = key + "/" + tag
                    saved, _ = base.read_arrays(RUN / "paths" / name)
                    arrays, values, checked = build(key, tag, time, states, error, vehicle, labels,
                        assets[key], diagnostics[key], saved=saved)
                    entry = cp["completed"][name]
                    parent.merged.checked_output(RUN / "paths" / name, arrays,
                        record(key, tag, values, time, states, error, vehicle), entry["path"])
                    r.require(set(entry["datasets"]) == set(ids), "Every original-order projection required")
                    for dataset_id in ids:
                        out, rec = projection(dataset_id, assets[key][0], arrays, scalar=True)
                        rec.update(group=key, path=tag)
                        parent.merged.checked_output(RUN / "datasets" / tag / dataset_id, out, rec, entry["datasets"][dataset_id])
                    checks[name], rebuilt[name] = checked, entry
                    print("CLOSE UNWITNESSED SCALAR GEOS DECIMAL FULL SCOPE " + name, flush=True)
            counts = accounting(rebuilt)
            whole_counts(counts)
            r.require(counts == cp["accounting"], "Independent all-candidate accounting differs")
            a = {"time": r.now(), "status": "full_scope_supplemental_unwitnessed_witness_candidates_checked_not_merged",
                "accounting": counts, "checks": checks, "parent_census": r.read(PARENT / "acceptance.json")["accounting"],
                "all_original_scientific_lowers_and_complete_prefix_proofs_byte_exact": True,
                "all_original_initial_leaf_diagnostics_and_provenance_retained_as_source": True,
                "all57_original_order_double_path_full_fields_indices_probe_traces_and_padding_checked": True,
                "strict_new_witnesses_only_no_failed_probe_exclusions_or_scientific_lower_promotions": True,
                "all_no_witness_rows_exactly_unknown_not_negative": True,
                "truth_asset_promotion_allowed": False, "full_merge_all57projections_and_updated_census_required": True,
                "original_assets_predictions_scores_unchanged": True, "corrected_truth_revalidated_prediction_jobs": 0,
                "not_exhaustive_global_earliest_identifiability_formal_ODE_or_real_vehicle_certificate": True,
                "all_expanded_populations_controls_and_affected_scores_still_required": True,
                "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"), "source_signature": signature(),
                "execution": idle, "mutex": mutex}
            r.freeze(RUN / "acceptance.json", r.encoded(a))
        finally:
            r.mutable(RUN / "analysis_runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), "version": "20261022-0000-v31-unwitnessed-probe-candidates-closed",
        "stage_status": "supplemental_witness_candidates_checked_not_merged", "scientific_acceptance_exists": True,
        "candidate_accounting": counts, "next_action": "new full39 merge/all57 projections/fresh census, then every remaining unknown/population/control/score"}
    report = ("# Supplemental Unwitnessed Contact Witness Candidates\n\n"
        "Complete current scope on both paths, all57 double-path projections and original diagnostic evidence. "
        "Only strict new contact witnesses may change candidate status/upper/edge fields; all scientific lower bytes unchanged. "
        "Every scalar probe GEOS/full bracket Decimal70/finite face/field/projection/padding checked. "
        "Failed probes and internal search cursors are not exclusion/lower proofs; finite sampling may miss contacts. "
        "No-witness rows remain exact unknowns. Candidate acceptance only, no merge/promotion/score repair, "
        "not global earliest/identifiability/formal ODE/real-vehicle proof.\n\n" + str(counts) + "\n").encode("utf-8")
    r.batch([(RUN / "close_receipt.json", r.encoded({"time": r.now(), "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"),
        "acceptance_sha256": r.file_hash(RUN / "acceptance.json"), "execution_after": after,
        "mutex_reacquired_released": released})), (CLOSED_PLAN, r.encoded(plan)),
        (ROOT / "reports/unwitnessed_probe_candidates_20261022_0000_v1.md", report)])
    active = r.read(ROOT / "active_research_run.json")
    active.update(version=plan["version"], status=plan["stage_status"], pid=None, running_analysis=False,
        plan=str(CLOSED_PLAN), scientific_acceptance=str(RUN / "acceptance.json"),
        scientific_close_receipt=str(RUN / "close_receipt.json"), next_action=plan["next_action"],
        full_merge_all57projections_and_updated_census_required=True)
    r.mutable(ROOT / "active_research_run.json", active)
    print("UNWITNESSED PROBE COMPLETE INDEPENDENT CANDIDATE CLOSE; census unchanged " + str(counts), flush=True)


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
    print("UNWITNESSED PROBE LAUNCHED historical identity PID " + str(child.pid), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "run", "close"))
    globals()[parser.parse_args().action]()

