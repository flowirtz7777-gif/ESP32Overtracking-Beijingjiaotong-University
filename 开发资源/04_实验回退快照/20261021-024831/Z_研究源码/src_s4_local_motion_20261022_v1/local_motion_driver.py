"""Full current scope, local edge candidates and exact unwitnessed diagnostics."""
import argparse
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
sys.path.insert(0, str(ROOT / "src_s4_upper_merge_20261022_v1"))
import upper_merge_driver as parent
import local_motion_core as core
import local_scope as scope_core
import numpy as np

base, r, AUTH = parent.base, parent.r, parent.AUTH
science, admin = parent.prior.science, parent.prior.admin
PARENT = parent.RUN
RUN = ROOT / "runs/resume_20261022_0000_local_motion_v1"
PROTOCOL = ROOT / "protocol_local_motion_20261022_0000_v1.json"
PLAN = ROOT / "resume_plan_20261022_0000_v25.json"
CLOSED_PLAN = ROOT / "resume_plan_20261022_0000_v26.json"
SESSION = AUTH / "runtime_sessions/local_motion_launch_v1"
TAGS = ("oldpath", "independent")
RESERVATION = 448 * 1024**2
DEPENDENCIES = (PARENT, science.RUN, admin.RUN)
HASHES = {
    "checkpoint.json": "033ad57e679af3f93643e5997b358c814f776cc686c9fce3ac31b7b58cc439f8",
    "acceptance.json": "df0af4b7d53d0ac3a14d04b34d667e3d0efac19f0e7f44f44d04e044fc380740",
    "close_receipt.json": "6e2aa908f386530cfd6d8b684cc4d2f6e243c8675a59a0f9d803cc82d5605228",
    "source_manifest.json": "2d442c8e9872dfaf0695f795d1db713d02011090e1ba386aeb057ac6ae74a6a1",
}


def configure():
    parent.configure()
    r.RUN, r.RUN_CAP = RUN, 512 * 1024**2


configure()


def execution():
    try:
        return parent.execution()
    finally:
        configure()


def gate():
    parent.verify()
    for name, sha in HASHES.items():
        r.require(r.file_hash(PARENT / name) == sha, "Complete closed upper merge dependency changed")
    accepted = r.read(PARENT / "acceptance.json")
    counts = accepted["accounting"]
    r.require(accepted["strict_merged_all_point_prefix_coverage_passed"] is True
        and accepted["truth_asset_promotion_allowed"] is False
        and counts["complete_census_point_file_records"] == 27025
        and counts["complete_census_group_unique_points"] == 22985,
        "Whole current accepted scope and complete prefixes required")
    r.require(r.file_hash(science.RUN / "acceptance.json") ==
        "75531236245699494006287d823aa7ec3eb6ff37b8eaef69600fda0e08871019"
        and r.file_hash(admin.RUN / "receipt.json") ==
        "3e39b3e27d089ae21ef6cff8bb79c06ac3d764da05b3eb90eb5335cad420e94e",
        "Scientific observability acceptance and its separate admin receipt required")


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / "source_manifest.json")}
    paths.update(PARENT / name for name in HASHES)
    paths.update(SOURCE.glob("*.py"))
    paths.update((PROTOCOL, PLAN, AUTH / "authorization.json",
        AUTH / "runtime_sessions/upper_merge_closed_v1/registration.json",
        AUTH / "runtime_sessions/upper_merge_closed_v1/all_closed_run_files_sha256.json",
        AUTH / "runtime_sessions/local_motion_development_ready_v1/development_state.json"))
    for folder in (AUTH / "runtime_sessions").glob("local_motion_development_tests_v*"):
        paths.update(p for p in folder.rglob("*") if p.is_file())
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / "source_manifest.json")
    r.require(signature() == expected, "Frozen local motion sources or dependencies differ")
    for rel, sha in expected.items():
        r.require(r.file_hash(RUN / "source" / rel) == sha, "Frozen source copy differs")
    if full:
        gate()
        for rel, inventory in r.read(RUN / "dependency_files_sha256.json").items():
            folder = ROOT / rel
            actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
            r.require(actual == set(inventory), "Complete stopped dependency file set differs")
            for name, sha in inventory.items():
                r.require(r.file_hash(folder / name) == sha, "Stopped dependency bytes changed")


def admit():
    try:
        gate()
        loaded, groups, old_assets, candidates, bindings = parent.admit()
        cp = r.read(PARENT / "checkpoint.json")
        diagnostic_cp = r.read(science.RUN / "checkpoint.json")
        assets, diagnostics = {}, {}
        for key, ids in groups.items():
            paths, combined, flags, scope, _, expected, summary = parent.build_group(
                key, old_assets[key], candidates, scalar=False)
            record = parent.group_record(key, ids, old_assets[key], bindings, summary)
            parent.merged.checked_output(PARENT / "groups" / key, expected, record, cp["completed"][key]["group"])
            full, meta = base.read_arrays(PARENT / "groups" / key)
            parent.merged.checked_output(PARENT / "census/groups" / key,
                parent.census.core.group_payload(full["xy"], paths, combined, flags, scope),
                record, cp["completed"][key]["census_group"])
            old, old_record = base.read_arrays(science.RUN / "groups" / key)
            r.require(r.file_hash(science.RUN / "groups" / key / "result.json") ==
                diagnostic_cp["completed"][key]["group"]["result_sha256"],
                "Complete accepted diagnostic result binding differs")
            scope_core.rows(old["union_index"], np.flatnonzero(scope).astype(np.int64))
            for tag in TAGS:
                labels = {name: value[scope] for name, value in paths[tag].items()}
                scope_core.retained_unknown(np.flatnonzero(scope).astype(np.int64),
                    full["xy"][scope], labels, old, tag)
            for dataset_id in ids:
                out, rec, unknown = parent.projection(dataset_id, loaded, full["xy"],
                    paths, combined, flags, scope, full, scalar=False)
                rec.update(group=key, original_input=loaded[dataset_id]["spec"])
                parent.merged.checked_output(PARENT / "datasets" / dataset_id,
                    out, rec, cp["completed"][key]["datasets"][dataset_id])
                parent.merged.checked_output(PARENT / "census/datasets" / dataset_id,
                    unknown, rec, cp["completed"][key]["census_datasets"][dataset_id])
            assets[key], diagnostics[key] = (full, meta, paths), (old, old_record)
        r.require(len(loaded) == 57 and len(groups) == len(cp["completed"]) == 39
            and sum(int((v[0]["all_reason_flags"] != 0).sum()) for v in assets.values()) == 22985,
            "All39 current groups and all57 input/projection bindings required")
        return loaded, groups, assets, diagnostics
    finally:
        configure()


def summary(original, candidate, trace, retained):
    mask = trace["unwitnessed_contact_unknown_retained"]
    n = len(mask)
    return {"scope_records": n, "selected_uncertain_witnessed_edges": int(trace["selected_edge_uncertain"].sum()),
        "new_edge_certified_candidates": int(trace["edge_newly_certified"].sum()),
        "remaining_selected_edge_uncertain": int((trace["selected_edge_uncertain"] & ~candidate["edge_certain"]).sum()),
        "unwitnessed_contact_unknown_exactly_retained": int(mask.sum()),
        "initial_unknown_exactly_retained": int(retained["retained_unknown_metric__initial_origin"].sum()),
        "noninitial_time_leaf_unknown_exactly_retained": int(retained["retained_unknown_metric__time_leaf_origin"].sum()),
        "known_noncontact_exact_reuse": int(trace["known_noncontact_exact_reuse"].sum()),
        "already_certain_exact_reuse": int(trace["already_certain_exact_reuse"].sum()),
        "point_geometry_queries": int(trace["new_midpoint_geometry_query"].sum()),
        "any_contact_endpoint_changes": int(np.sum(original["contact_lower_s"].view(np.uint64) != candidate["contact_lower_s"].view(np.uint64)))
            + int(np.sum(original["contact_upper_s"].view(np.uint64) != candidate["contact_upper_s"].view(np.uint64)))}


def build(key, tag, time, states, error, vehicle, all_labels, asset, diagnostic, *, saved=None):
    full = asset[0]
    mask = full["all_reason_flags"] != 0
    index = np.flatnonzero(mask).astype(np.int64)
    xy = full["xy"][index]
    labels = {k: v[index].copy() for k, v in all_labels.items()}
    params = dict(length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
    geometry = lambda points, poses: base.finite_face_geometry(points, poses, **params)
    checked = None
    if saved is None:
        candidate, trace, variation = core.candidate(xy, time, states, labels, error, vehicle, geometry)
    else:
        candidate = {k: v for k, v in parent.merged.budget.prefixed(saved, "candidate__").items()
                     if not k.endswith("__packbits")}
        trace = {k[len("trace__"):]: v for k, v in saved.items()
                 if k.startswith("trace__") and not k.endswith("__packbits")}
        variation = saved["motion_segment_variation_m"]
        checked = core.independent_check(xy, time, states, labels, candidate, error, vehicle,
            trace, variation, science.core.geos_geometry)
    retained = scope_core.retained_unknown(index, xy, labels, diagnostic[0], tag, scalar=saved is not None)
    out = {"union_index": index, "xy": xy, "full_scope_packbits": np.packbits(mask, bitorder="little"),
        "motion_segment_variation_m": variation}
    unknown = np.zeros(len(mask), bool)
    unknown[retained["retained_unknown_union_index"]] = True
    out["full_unknown_packbits"] = np.packbits(unknown, bitorder="little")
    for prefix, data in (("original__", labels), ("candidate__", candidate), ("trace__", trace)):
        out.update({prefix + k: v for k, v in data.items()})
        out.update({prefix + k + "__packbits": np.packbits(v, bitorder="little")
                    for k, v in data.items() if v.dtype == np.bool_})
    out.update(retained)
    for name, value in full.items():
        if name.startswith(("merge_", "upper_merge_")) and name.endswith("__packbits"):
            out["parent_provenance__" + name] = value.copy()
    values = summary(labels, candidate, trace, retained)
    if checked is not None:
        r.require(checked["newly_certified_edge_candidates"] == values["new_edge_certified_candidates"],
            "Every scalar candidate count must agree")
    return out, values, checked


def record(key, tag, summary, time, states, error, vehicle):
    return {"group": key, "path": tag, "summary": summary,
        "parent_group_result_sha256": r.file_hash(PARENT / "groups" / key / "result.json"),
        "diagnostic_group_result_sha256": r.file_hash(science.RUN / "groups" / key / "result.json"),
        "parent_hashes": HASHES, "time_sha256": base.common.array_hash(time),
        "states_sha256": base.common.array_hash(states), "spatial_error_m": error,
        "vehicle": {"L": vehicle.L, "width": vehicle.width, "l_h": vehicle.l_h},
        "both_scientific_endpoints_and_full_prefixes_exact_reuse": True,
        "unwitnessed_diagnostics_exact_reuse_not_contact_repair": True,
        "not_global_identifiability_or_formal_ODE_certificate": True,
        "truth_asset_promotion_allowed": False}


def projection(dataset_id, full, arrays, *, scalar=False):
    source, _ = base.read_arrays(PARENT / "datasets" / dataset_id)
    out = scope_core.project(full["xy"], source["union_index"], source["xy"], arrays, scalar=scalar)
    for name, value in out.items():
        if name.startswith("parent_provenance__"):
            r.require(scope_core.same(value, source[name[len("parent_provenance__"):]]),
                "Original-order parent provenance mask must be exactly retained")
    labels = parent.merged.budget.prefixed(out, "original__")
    candidate = parent.merged.budget.prefixed(out, "candidate__")
    labels = {k: v for k, v in labels.items() if not k.endswith("__packbits")}
    candidate = {k: v for k, v in candidate.items() if not k.endswith("__packbits")}
    trace = {k[len("trace__"):]: v for k, v in out.items() if k.startswith("trace__") and not k.endswith("__packbits")}
    values = summary(labels, candidate, trace, out)
    rec = {"dataset_id": dataset_id, "summary": values,
        "parent_dataset_result_sha256": r.file_hash(PARENT / "datasets" / dataset_id / "result.json"),
        "all_original_order_indices_coordinates_fields_masks_and_padding": True}
    return out, rec


def accounting(completed):
    rows = [value["summary"] for entry in completed.values() for value in entry["datasets"].values()]
    group_rows = [entry["path"]["summary"] for entry in completed.values()]
    fields = tuple(group_rows[0])
    return {"path_blocks": len(completed), "projected_path_files": len(rows),
        "scope_group_unique_points": sum(v["scope_records"] for v in group_rows) // 2,
        "scope_point_file_records": sum(v["scope_records"] for v in rows) // 2,
        "group_point_path_records_not_independent_samples": sum(v["scope_records"] for v in group_rows),
        "group_path_totals": {name: sum(v[name] for v in group_rows) for name in fields},
        "weighted_path_diagnostics": {tag: {name: sum(v["summary"][name]
            for key, entry in completed.items() if key.endswith("/" + tag)
            for v in entry["datasets"].values()) for name in fields} for tag in TAGS}}


def whole_counts(counts):
    r.require(counts["path_blocks"] == 78 and counts["projected_path_files"] == 114
        and counts["scope_group_unique_points"] == 22985 and counts["scope_point_file_records"] == 27025,
        "Both paths on the entire current scope and every original projection required")
    for tag, unknown, edge in (("oldpath", 13956, 13069), ("independent", 13710, 12669)):
        row = counts["weighted_path_diagnostics"][tag]
        r.require(row["unwitnessed_contact_unknown_exactly_retained"] == unknown
            and row["selected_uncertain_witnessed_edges"] == edge and row["any_contact_endpoint_changes"] == 0
            and row["initial_unknown_exactly_retained"] + row["noninitial_time_leaf_unknown_exactly_retained"] == unknown,
            "All unwitnessed initial/leaf records and witnessed uncertain edges must remain covered")


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN, CLOSED_PLAN)),
        "Already attempted or deadline")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), "-X", "utf8", "-B", "-m", "unittest", "discover",
            "-s", str(SOURCE), "-p", "test_*.py", "-v"], cwd=r"C:\Users\Admin",
            capture_output=True, encoding="utf-8", timeout=180)
        r.require(tests.returncode == 0, "Local motion synthetic tests failed: " + tests.stderr)
        protocol = {"version": "complete-current-scope-local-motion-edge-candidates-v1",
            "deadline": r.read(AUTH / "authorization.json")["deadline"], "parent": str(PARENT), "parent_hashes": HASHES,
            "scope": "all22985 group-unique current unknown points both paths, all27025 original point-file records",
            "all_57_inputs_and_39_groups": True, "full_original_bracket_all_intersected_intervals": True,
            "spatial_error_tol_time_corner_and_guard_unchanged": True,
            "motion_bound": "outward-rounded per-interval corner total variation, integrated from original midpoint to both endpoints",
            "independent_check": "all intervals high-precision Decimal70, separate scalar full sums, every new finite-face GEOS confidence",
            "all_unwitnessed_initial_leaf_errorband_diagnostics_exact_accepted_reuse": True,
            "unchanged_contact_existence_lower_upper_and_complete_prefix_proofs": True,
            "no_query_on_known_noncontact_or_before_proven_lower": True,
            "not_global_nonidentifiability_proof": True, "no_promoted_truth_or_scores": True,
            "no_subset_by_performance_or_midpoint_hypothetical_diagnostic": True,
            "separate_full_merge_and_updated_census_required_after_close": True,
            "workers": 1, "inflight": 1, "run_cap_bytes": r.RUN_CAP, "reservation_bytes": RESERVATION,
            "total_E_Z_cap_bytes": r.CAP, "Z_reserve_bytes": r.RESERVE,
            "submitted_block": "one path on a complete current group scope and every original-order projection; drain after cutoff",
            "development_first_fixture_failure_preserved": True, "corrected_truth_revalidated_prediction_jobs": 0}
        plan = {**r.read(ROOT / "resume_plan_20261022_0000_v24.json"),
            "version": "20261022-0000-v25-full-scope-local-motion-candidates",
            "stage_status": "prepared_not_admitted", "run_directory": str(RUN), "protocol": str(PROTOCOL),
            "entrypoint": str(Path(__file__)), "scientific_acceptance_exists": False,
            "next_action": "all57 inputs/full current both-path scope admission then local motion candidates and exact unknown diagnostic reuse",
            "ordered_remaining": ["independent full-scope candidate close", "new whole merge/all57projections/full census",
                "all remaining contact/time/edge identifiability and expanded coarse/fine populations/controls",
                "all affected scores/reports repaired or proved unaffected"]}
        inventory = {folder.relative_to(ROOT).as_posix():
            {p.relative_to(folder).as_posix(): r.file_hash(p) for p in sorted(folder.rglob("*")) if p.is_file()}
            for folder in DEPENDENCIES}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / "dependency_files_sha256.json", r.encoded(inventory)),
            (RUN / "prelaunch.json", r.encoded({"time": r.now(), "execution": idle, "mutex": mutex,
                "tests_stdout": tests.stdout, "tests_stderr": tests.stderr,
                "resources": r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / "source_manifest.json", r.encoded(signed))]
            + [(RUN / "source" / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print("LOCAL MOTION FULL-SCOPE PREPARED; real admission still pending", flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / "checkpoint.json").exists(), "Already attempted or deadline")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {"status": "preflight", "completed": {}}
        r.mutable(RUN / "runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            loaded, groups, assets, diagnostics = admit()
            r.freeze(RUN / "preflight.json", r.encoded({"time": r.now(), "groups": groups,
                "all57inputs_all39current_assets_fullscope_bothpaths_and_accepted_unknown_diagnostics_bound": True,
                "execution": idle, "mutex": mutex}))
            active = r.read(ROOT / "active_research_run.json")
            active.update(version="20261022-0000-v25-local-motion-full-scope-running",
                run_directory=str(RUN), protocol=str(PROTOCOL), plan=str(PLAN), entrypoint=str(Path(__file__)),
                status="local_motion_candidates_and_exact_unknown_diagnostics_running", pid=os.getpid(),
                running_analysis=True, running_predictions=False, input_worker_admitted=True,
                input_worker_admission_pending=False, scientific_acceptance=None, scientific_close_receipt=None,
                scientific_close_actual_wait_exit_code=None, stdout=str(SESSION / "stdout.log"), stderr=str(SESSION / "stderr.log"))
            r.mutable(ROOT / "active_research_run.json", active)
            print("LOCAL MOTION PREFLIGHT PASSED ALL57 /39 GROUPS /22985 FULL SCOPE BOTH PATHS /UNCHANGED UNKNOWN DIAGNOSTICS", flush=True)
            for key, ids in groups.items():
                for tag, time, states, error, vehicle, labels in parent.prior.path_iter(key, loaded, groups, assets[key]):
                    r.require(r.before_deadline(), "No new complete path block after cutoff")
                    verify(full=False)
                    arrays, values, _ = build(key, tag, time, states, error, vehicle, labels, assets[key], diagnostics[key])
                    name = key + "/" + tag
                    entry = {"path": base.save_arrays(RUN / "paths" / name, arrays,
                        record(key, tag, values, time, states, error, vehicle)), "datasets": {}}
                    for dataset_id in ids:
                        out, rec = projection(dataset_id, assets[key][0], arrays)
                        rec.update(group=key, path=tag)
                        entry["datasets"][dataset_id] = base.save_arrays(RUN / "datasets" / tag / dataset_id, out, rec)
                    cp["completed"][name] = entry
                    r.checkpoint(cp)
                    r.require(values["any_contact_endpoint_changes"] == 0, "Endpoint discrepancy saved; stop")
                    print("DONE LOCAL MOTION FULL SCOPE " + name, flush=True)
            counts = accounting(cp["completed"])
            whole_counts(counts)
            cp.update(status="complete_pending_independent_local_motion_close", accounting=counts)
            r.checkpoint(cp)
        except Exception:
            cp.update(status="stopped_failure_or_deadline", failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / "runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    print("LOCAL MOTION WORKER EXITING; candidates not accepted or merged", flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / "acceptance.json").exists(), "Already attempted or deadline")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / "checkpoint.json")
        r.require(cp["status"] == "complete_pending_independent_local_motion_close"
            and len(cp["completed"]) == 78, "Incomplete candidates cannot close")
        r.mutable(RUN / "analysis_runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            loaded, groups, assets, diagnostics = admit()
            checks = {}
            rebuilt = {}
            for key, ids in groups.items():
                for tag, time, states, error, vehicle, labels in parent.prior.path_iter(key, loaded, groups, assets[key]):
                    name = key + "/" + tag
                    saved, _ = base.read_arrays(RUN / "paths" / name)
                    expected, values, checked = build(key, tag, time, states, error, vehicle, labels,
                        assets[key], diagnostics[key], saved=saved)
                    entry = cp["completed"][name]
                    meta = record(key, tag, values, time, states, error, vehicle)
                    parent.merged.checked_output(RUN / "paths" / name, expected, meta, entry["path"])
                    r.require(set(entry["datasets"]) == set(ids), "Every original-order projection required")
                    for dataset_id in ids:
                        out, rec = projection(dataset_id, assets[key][0], expected, scalar=True)
                        rec.update(group=key, path=tag)
                        parent.merged.checked_output(RUN / "datasets" / tag / dataset_id, out, rec, entry["datasets"][dataset_id])
                    rebuilt[name] = entry
                    checks[name] = checked
                    print("CLOSE LOCAL MOTION SCALAR DECIMAL GEOS ALL RECORDS " + name, flush=True)
            counts = accounting(rebuilt)
            whole_counts(counts)
            r.require(counts == cp["accounting"], "Complete independent candidate accounting differs")
            value = {"time": r.now(), "status": "full_scope_local_motion_edge_candidates_and_retained_unknown_diagnostics_checked_not_merged",
                "accounting": counts, "checks": checks, "parent_census": r.read(PARENT / "acceptance.json")["accounting"],
                "both_scientific_endpoints_all_labels_except_certified_edge_and_original_provenance_exact": True,
                "complete_original_prefix_proofs_exact_reuse_no_excluded_points_recomputed": True,
                "all_unwitnessed_initial_leaf_spatial_diagnostics_exact_accepted_reuse": True,
                "all57_original_order_double_path_projections_full_fields_indices_masks_padding_checked": True,
                "all_unknowns_and_conflicts_retained": True, "truth_asset_promotion_allowed": False,
                "full_merge_all57projections_and_updated_census_required": True,
                "original_assets_predictions_scores_unchanged": True, "corrected_truth_revalidated_prediction_jobs": 0,
                "not_global_identifiability_or_formal_ODE_or_real_vehicle_certificate": True,
                "all_expanded_populations_controls_and_affected_scores_still_required": True,
                "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"), "source_signature": signature(),
                "execution": idle, "mutex": mutex}
            r.freeze(RUN / "acceptance.json", r.encoded(value))
        finally:
            r.mutable(RUN / "analysis_runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), "version": "20261022-0000-v26-local-motion-candidates-closed",
        "stage_status": "candidates_checked_not_merged", "scientific_acceptance_exists": True,
        "candidate_accounting": counts,
        "next_action": "new full merge/all57projections/full updated census, then all remaining unknowns/expanded populations/controls/scores"}
    report = ("# Full-Scope Local Motion Candidates\n\n"
        "Both original contact endpoints and all complete prefix proofs exact; no contact-existence repair. "
        "All unwitnessed original leaf/initial spatial diagnostics exactly retained from independently accepted parent. "
        "Full scope, every finite-face local envelope and all57 double-path projections checked; not merged or promoted.\n\n"
        + str(counts) + "\n").encode("utf-8")
    r.batch([(RUN / "close_receipt.json", r.encoded({"time": r.now(),
        "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"), "acceptance_sha256": r.file_hash(RUN / "acceptance.json"),
        "execution_after": after, "mutex_reacquired_released": released})),
        (CLOSED_PLAN, r.encoded(plan)), (ROOT / "reports/local_motion_candidates_20261022_0000_v1.md", report)])
    active = r.read(ROOT / "active_research_run.json")
    active.update(version=plan["version"], status="local_motion_candidates_closed_not_merged",
        pid=None, running_analysis=False, plan=str(CLOSED_PLAN), next_action=plan["next_action"],
        scientific_acceptance=str(RUN / "acceptance.json"), scientific_close_receipt=str(RUN / "close_receipt.json"),
        full_merge_all57projections_and_updated_census_required=True)
    r.mutable(ROOT / "active_research_run.json", active)
    print("LOCAL MOTION COMPLETE INDEPENDENT CANDIDATE CLOSE; parent census unchanged " + str(counts), flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / "runner_lock.json").exists(),
        "Already attempted or deadline")
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
    print("LOCAL MOTION LAUNCHED historical identity PID " + str(child.pid), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "run", "close"))
    globals()[parser.parse_args().action]()

