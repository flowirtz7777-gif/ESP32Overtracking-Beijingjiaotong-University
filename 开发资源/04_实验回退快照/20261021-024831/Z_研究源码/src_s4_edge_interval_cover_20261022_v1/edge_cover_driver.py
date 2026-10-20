"""All-current-scope complete bracket edge cover; candidates are not promoted."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(r"Z:\大创内轮差项目_实验结果\科研实验_2026-10-14")
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
sys.path.insert(0, str(ROOT / "src_s4_suffix_full_merge_20261022_v1"))
import suffix_full_merge_driver as parent
import edge_cover_core as core
import numpy as np

base, r, AUTH = parent.base, parent.r, parent.AUTH
scope_core, science = parent.local.scope_core, parent.local.science
PARENT = parent.RUN
RUN = ROOT / "runs/resume_20261022_0000_edge_interval_cover_v1"
PROTOCOL = ROOT / "protocol_edge_interval_cover_20261022_0000_v1.json"
PLAN = ROOT / "resume_plan_20261022_0000_v14.json"
CLOSED_PLAN = ROOT / "resume_plan_20261022_0000_v15.json"
SESSION = AUTH / "runtime_sessions/edge_interval_cover_launch_v1"
CLOSURE = AUTH / "runtime_sessions/suffix_full_merge_closed_v1"
DEPENDENCIES = tuple(dict.fromkeys((PARENT,parent.local.RUN,*parent.DEPENDENCIES,
    CLOSURE,AUTH/"runtime_sessions/suffix_full_merge_first_close_v1")))
TAGS = ("oldpath", "independent")
RESERVATION = 3584 * 1024**2
HASHES = {'checkpoint.json': '47a120b10059e406fdd9e29a7d6fb9ef6a46b4c38d61129ce93f78262e0c253d', 'acceptance.json': 'f1f494e65e974e1bad8faf5cbeab44a497f0d8a05e241e67b3e4965891202067', 'close_receipt.json': '7888837f4b558f1a51c302840d6c151a1ac755aaa1e10edfbd7ec5542f70926d', 'source_manifest.json': 'd80b03d11eca7738a5484c307f4a24d8bfc718c2872706a3f2ec25f70fc29887'}


def configure():
    parent.configure()
    r.RUN, r.RUN_CAP = RUN, 4 * 1024**3


configure()


def execution():
    try:
        return parent.execution()
    finally:
        configure()


def gate():
    try:
        parent.verify()
        for name,digest in HASHES.items():
            r.require(r.file_hash(PARENT/name)==digest,'Closed v37 dependency changed')
        a=r.read(PARENT/'acceptance.json')
        r.require(a['strict_merged_all_point_prefix_coverage_passed']
            and a['all45714_scope_records_exactly_merged_including_unchanged']
            and a['all_original_scientific_lower_bytes_unchanged']
            and a['accounting']['complete_census_point_file_records']==26878
            and a['accounting']['complete_census_group_unique_points']==22857
            and a['accounting']['combined_status_unknown_point_file_records']==13949
            and a['truth_asset_promotion_allowed'] is False,'Complete accepted v37 population required')
        inventory=r.read(CLOSURE/'all_closed_run_files_sha256.json')
        actual={p.relative_to(PARENT).as_posix():r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.require(actual==inventory and len(actual)==1059,'All1059 stopped closed-parent files required')
        r.require(r.read(AUTH/'runtime_sessions/suffix_full_merge_first_close_v1/exit.json')['actual_wait_exit_code']==0,
            'Actual first-close wait required')
        r.require((SOURCE/'local_motion_core.py').read_bytes()==(ROOT/'src_s4_local_motion_20261022_v2/local_motion_core.py').read_bytes(),
            'Original outward-rounded and independent Decimal70 motion code byte-exact')
    finally:
        configure()


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / "source_manifest.json")}
    paths.update(PARENT / name for name in HASHES)
    paths.update(SOURCE.glob("*.py"))
    paths.update((PROTOCOL, PLAN, AUTH / "authorization.json",
        CLOSURE / "registration.json"))
    paths.update(p for p in CLOSURE.rglob("*") if p.is_file())
    for folder in (AUTH / "runtime_sessions").glob("edge_interval_cover_development_tests_v*"):
        paths.update(p for p in folder.rglob("*") if p.is_file())
    for folder in ("src_s4_edge_interval_cover_20261022_v1","src_s4_edge_interval_cover_20261022_v2"):
        paths.update((ROOT/folder).glob("*.py"))
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


def path_iter(key,loaded,groups,asset):
    return parent.local.path_iter(key,loaded,groups,asset)


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


def summary(original,candidate,trace,retained):
    chosen,found=trace['selected_edge_uncertain'],trace['edge_newly_certified']
    lower=original['contact_lower_s']; upper=original['contact_upper_s']
    return dict(scope_records=len(chosen),selected_uncertain_witnessed_edges=int(chosen.sum()),
        new_edge_certified_candidates=int(found.sum()),remaining_selected_edge_uncertain=int((chosen&~found).sum()),
        unwitnessed_contact_unknown_exactly_retained=int((np.isfinite(lower)&~np.isfinite(upper)).sum()),
        initial_unknown_exactly_retained=int(retained['retained_unknown_metric__initial_origin'].sum()),
        noninitial_time_leaf_unknown_exactly_retained=int(retained['retained_unknown_metric__time_leaf_origin'].sum()),
        known_noncontact_exact_reuse=int((original['contact_status']==0).sum()),
        already_certain_exact_reuse=int((np.isfinite(upper)&original['edge_certain']).sum()),
        interval_geometry_queries=int(trace['query_count'].sum()),cover_budget_exhausted=int(trace['cover_budget_exhausted'].sum()),
        cover_resolution_unresolved=int(trace['cover_resolution_unresolved'].sum()),
        cover_different_stable_code=int(trace['cover_different_stable_code'].sum()),
        scientific_lower_changes=int(np.sum(lower.view(np.uint64)!=candidate['contact_lower_s'].view(np.uint64))),
        scientific_upper_changes=int(np.sum(upper.view(np.uint64)!=candidate['contact_upper_s'].view(np.uint64))))


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
            if name.startswith(("merge_", "upper_merge_", "local_motion_", "probe_merge_", "suffix_merge_")) and name.endswith("__packbits"):
                out["parent_provenance__" + name] = value.copy()
        values = summary(labels, proposed, trace, retained)
        r.require(values["scientific_lower_changes"] == values["scientific_upper_changes"] == 0, "No new scientific lower is permitted")
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
        "complete_original_bracket_cover_only_not_physical_identifiability_or_noncontact_proof": True,
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
    totals=value['group_path_totals']
    r.require(value['path_blocks']==78 and value['projected_path_files']==114
        and value['scope_group_unique_points']==22857 and value['scope_point_file_records']==26878
        and value['group_point_path_records_not_independent_samples']==45714
        and totals['selected_uncertain_witnessed_edges']==22464
        and totals['unwitnessed_contact_unknown_exactly_retained']==22830
        and totals['scientific_lower_changes']==totals['scientific_upper_changes']==0,'Complete current both-path scope required')
    for tag,unknown,edge in (('oldpath',13949,12929),('independent',13707,12645)):
        row=value['weighted_path_diagnostics'][tag]
        r.require(row['unwitnessed_contact_unknown_exactly_retained']==unknown
            and row['initial_unknown_exactly_retained']+row['noninitial_time_leaf_unknown_exactly_retained']==unknown
            and row['selected_uncertain_witnessed_edges']==edge,'All current unknowns and edge uncertainty required')


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
        protocol = dict(version='full-current-scope-complete-bracket-edge-cover-v1',
            deadline=r.read(AUTH/'authorization.json')['deadline'],parent_merged_assets=str(PARENT),parent_hashes=HASHES,
            scope='all22857 current group-scope points, both45714 path records, all57/114 original-order projections',
            selection='all finite witnessed upper, edge uncertain; retain all unwitnessed/initial/leaf diagnostics',
            tree='original full lower/upper; deterministic chronological midpoint subdivision, at most64 node queries per point',
            leaf_proof='same original nominal code on every covering leaf, full local motion plus original empirical error and1e-12, original1mm corner rule',
            resolution_s=1e-7,maximum_queries=64,scientific_lower_and_upper_and_all_contact_evidence_byte_exact=True,
            budget_resolution_different_code_open_frontier='keep original uncertainty and every field; never a negative or impossibility proof',
            mutable_fields=['edge_certain','possible_edge_codes'],new_budgets_separate_original_budget_masks_exact=True,
            independent_close='all scalar GEOS probes; independent exact tree/frontier/budget/padding replay, full original-segment Decimal70 and all114 projections',
            no_global_physical_identifiability_or_noncontact_or_real_vehicle_certificate=True,
            no_proven_excluded_points_recomputed=True,truth_asset_promotion_allowed=False,corrected_truth_revalidated_prediction_jobs=0,
            all_remaining_unknowns_expanded_populations_controls_scores_still_required=True,
            workers=1,inflight=1,run_cap_bytes=r.RUN_CAP,reservation_bytes=RESERVATION,total_E_Z_cap_bytes=r.CAP,Z_reserve_bytes=r.RESERVE,
            submitted_block='one complete scope path and every original-order projection, drain at cutoff')
        plan = {"version": "20261022-0000-v38-edge-interval-cover-candidates", "deadline": protocol["deadline"],
            "authorization": str(AUTH / "authorization.json"), "run_directory": str(RUN),
            "protocol": str(PROTOCOL), "entrypoint": str(Path(__file__)), "parent_merged_assets": str(PARENT),
            "parent_complete_census": r.read(PARENT / "acceptance.json")["accounting"],
            "stage_status": "prepared_not_admitted", "scientific_acceptance_exists": False,
            "truth_asset_promotion_allowed": False, "corrected_truth_revalidated_prediction_jobs": 0,
            "all_label_dependent_claims_withheld": True, "S4_overall_complete": False, "M2_allowed": False, "S5_allowed": False,
            "ordered_remaining": ["independent full-scope candidate close", "new whole merge/all57projections/full census",
                "all remaining contact/time/edge identifiability, full expanded populations/controls",
                "every affected score/report repair or exact unaffected proof"],
            "next_action": "complete real admission and complete bracket uniform-code edge candidates, not truth promotion"}
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
    print("EDGE INTERVAL COVER FULL SCOPE PREPARED; real admission pending", flush=True)


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
            active.update(version="20261022-0000-v38-edge-interval-cover-search-running", status="full_scope_edge_interval_cover_candidates_running",
                run_directory=str(RUN), protocol=str(PROTOCOL), plan=str(PLAN), entrypoint=str(Path(__file__)),
                pid=os.getpid(), running_analysis=True, running_predictions=False,
                input_worker_admitted=True, input_worker_admission_pending=False,
                scientific_acceptance=None, scientific_close_receipt=None, scientific_close_actual_wait_exit_code=None,
                full_merge_all57projections_and_updated_census_required=True,
                stdout=str(SESSION / "stdout.log"), stderr=str(SESSION / "stderr.log"))
            r.mutable(ROOT / "active_research_run.json", active)
            print("EDGE INTERVAL COVER PREFLIGHT PASSED ALL57 /39 GROUPS /22857 FULL SCOPE BOTH PATHS /ALL ORIGINAL UNKNOWN DIAGNOSTICS", flush=True)
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
                    print("DONE EDGE INTERVAL COVER FULL SCOPE " + key + "/" + tag, flush=True)
            counts = accounting(cp["completed"])
            whole_counts(counts)
            cp.update(status="complete_pending_independent_edge_interval_cover_close", accounting=counts)
            r.checkpoint(cp)
        except Exception:
            cp.update(status="stopped_failure_or_deadline", failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / "runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    print("EDGE INTERVAL COVER WORKER EXITING; candidate acceptance and merge pending", flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / "acceptance.json").exists()
        and not (RUN / "analysis_runner_lock.json").exists(), "Close attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / "checkpoint.json")
        r.require(cp["status"] == "complete_pending_independent_edge_interval_cover_close" and len(cp["completed"]) == 78,
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
                    print("CLOSE EDGE COVER SCALAR GEOS DECIMAL FULL SCOPE " + name, flush=True)
            counts = accounting(rebuilt)
            whole_counts(counts)
            r.require(counts == cp["accounting"], "Independent all-candidate accounting differs")
            a = {"time": r.now(), "status": "full_scope_complete_bracket_edge_cover_candidates_checked_not_merged",
                "accounting": counts, "checks": checks, "parent_census": r.read(PARENT / "acceptance.json")["accounting"],
                "all_original_scientific_lowers_and_complete_prefix_proofs_byte_exact": True,
                "all_original_initial_leaf_diagnostics_and_provenance_retained_as_source": True,
                "all57_original_order_double_path_full_fields_indices_probe_traces_and_padding_checked": True,
                "only_complete_uniform_edge_cover_candidates_no_contact_endpoint_changes": True,
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
    plan = {**r.read(PLAN), "version": "20261022-0000-v39-edge-interval-cover-candidates-closed",
        "stage_status": "complete_bracket_edge_cover_candidates_checked_not_merged", "scientific_acceptance_exists": True,
        "candidate_accounting": counts, "next_action": "new full39 merge/all57 projections/fresh census, then every remaining unknown/population/control/score"}
    report = ("# Complete Bracket Uniform Edge Cover Candidates\n\n"
        "Complete current scope on both paths, all57 double-path projections and original diagnostic evidence. "
        "Only complete uniform-code bracket covers may strengthen edge_certain/possible_edge_codes; all contact status, lower and upper bytes unchanged. "
        "Every successful and failed scalar probe GEOS, exact budget/control/frontier replay, full bracket Decimal70, finite face, field/projection/padding checked. "
        "Failed probes and internal search cursors are not exclusion/lower proofs; finite sampling may miss contacts. "
        "No-witness rows remain exact unknowns. Candidate acceptance only, no merge/promotion/score repair, "
        "not global earliest/identifiability/formal ODE/real-vehicle proof.\n\n" + str(counts) + "\n").encode("utf-8")
    r.batch([(RUN / "close_receipt.json", r.encoded({"time": r.now(), "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"),
        "acceptance_sha256": r.file_hash(RUN / "acceptance.json"), "execution_after": after,
        "mutex_reacquired_released": released})), (CLOSED_PLAN, r.encoded(plan)),
        (ROOT / "reports/edge_interval_cover_candidates_20261022_0000_v1.md", report)])
    active = r.read(ROOT / "active_research_run.json")
    active.update(version=plan["version"], status=plan["stage_status"], pid=None, running_analysis=False,
        plan=str(CLOSED_PLAN), scientific_acceptance=str(RUN / "acceptance.json"),
        scientific_close_receipt=str(RUN / "close_receipt.json"), next_action=plan["next_action"],
        full_merge_all57projections_and_updated_census_required=True)
    r.mutable(ROOT / "active_research_run.json", active)
    print("EDGE INTERVAL COVER COMPLETE INDEPENDENT CANDIDATE CLOSE; census unchanged " + str(counts), flush=True)


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
    print("EDGE INTERVAL COVER LAUNCHED historical identity PID " + str(child.pid), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "run", "close"))
    globals()[parser.parse_args().action]()

