"""Whole-scope bounded-suffix edge merge, full projections and a fresh census."""
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
sys.path.insert(0, str(ROOT / "src_s4_suffix_witness_search_20261022_v3"))
import suffix_driver as local
import numpy as np

spec = importlib.util.spec_from_file_location("suffix_full_merge_core_v1", SOURCE / "suffix_merge_core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
base, r, AUTH = local.base, local.r, local.AUTH
parent, census, merged = local.parent, local.parent.census, local.parent.merged
PARENT = local.PARENT
RUN = ROOT / "runs/resume_20261022_0000_suffix_full_merge_v1"
PROTOCOL = ROOT / "protocol_suffix_full_merge_20261022_0000_v1.json"
PLAN = ROOT / "resume_plan_20261022_0000_v36.json"
CLOSED_PLAN = ROOT / "resume_plan_20261022_0000_v37.json"
SESSION = AUTH / "runtime_sessions/suffix_full_merge_launch_v1"
CLOSURE = AUTH / "runtime_sessions/suffix_witness_search_closed_v3"
DEPENDENCIES = tuple(dict.fromkeys((local.RUN, PARENT, *local.DEPENDENCIES,
    CLOSURE, AUTH / "runtime_sessions/suffix_witness_search_first_close_v3")))
RESERVATION = 3584 * 1024**2
HASHES = {'checkpoint.json': '09b90a0a6f428a72cd369f5aa87176b906fa62bb3a13bac7cbfdf60403962c54', 'acceptance.json': '621886966468a89ffd65e8abcb7cafc511612bdacd2606f6bb7e8f7a059a92d0', 'close_receipt.json': '1a7fba4bf9d7f2917c7efb51d67e339bb4f01fb142aa1b70c04dd90e2ace1f3d', 'source_manifest.json': '282a6a187d6a1c75b314972ac9f66e7c701994ae760f0ef41515556f33d1d6c2'}



def configure():
    local.configure()
    r.RUN, r.RUN_CAP = RUN, 4 * 1024**3


configure()


def execution():
    try:
        return local.execution()
    finally:
        configure()


def gate():
    try:
        local.verify()
        r.require(set(HASHES)=={'checkpoint.json','acceptance.json','close_receipt.json','source_manifest.json'},
            'Actual accepted suffix hashes must be frozen before any real work')
        for name,digest in HASHES.items():
            r.require(r.file_hash(local.RUN/name)==digest,'Closed suffix dependency changed')
        a=r.read(local.RUN/'acceptance.json')
        local.whole_counts(a['accounting'])
        r.require(a['all_original_scientific_lowers_and_complete_prefix_proofs_byte_exact']
            and a['all57_original_order_double_path_full_fields_indices_probe_traces_and_padding_checked']
            and a['strict_new_witnesses_only_no_failed_probe_exclusions_or_scientific_lower_promotions']
            and a['all_no_witness_rows_exactly_unknown_not_negative']
            and all(v['complete_suffix_control_budget_and_frontier_checked'] for v in a['checks'].values())
            and a['truth_asset_promotion_allowed'] is False,'Complete independent bounded suffix candidate close required')
        receipt=r.read(local.RUN/'close_receipt.json')
        r.require(receipt['acceptance_sha256']==HASHES['acceptance.json']
            and receipt['checkpoint_sha256']==HASHES['checkpoint.json'],'Candidate close receipt differs')
        inventory=r.read(CLOSURE/'all_closed_run_files_sha256.json')
        actual={p.relative_to(local.RUN).as_posix():r.file_hash(p) for p in sorted(local.RUN.rglob('*')) if p.is_file()}
        registration=r.read(CLOSURE/'registration.json')
        r.require(actual==inventory and len(actual)==registration['all_closed_file_count'],
            'Every closed suffix candidate file required')
        r.require(r.read(AUTH/'runtime_sessions/suffix_witness_search_first_close_v3/exit.json')['actual_wait_exit_code']==0
            and registration['scientific_close_succeeded'],'Actual first-close wait and stopped signature registration required')
        r.require(r.read(PARENT/'acceptance.json')['strict_merged_all_point_prefix_coverage_passed'],
            'Complete current accepted lower-prefix coverage required')
    finally:
        configure()


def signature():
    paths = {ROOT / rel for rel in r.read(local.RUN / "source_manifest.json")}
    paths.update(local.RUN / name for name in HASHES)
    paths.update(SOURCE.glob("*.py"))
    paths.update((PROTOCOL, PLAN, AUTH / "authorization.json"))
    paths.update(p for p in CLOSURE.rglob("*") if p.is_file())
    for folder in (AUTH / "runtime_sessions").glob("suffix_full_merge_development_tests_v*"):
        paths.update(p for p in folder.rglob("*") if p.is_file())
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / "source_manifest.json")
    r.require(signature() == expected, "Frozen bounded-suffix merge dependencies changed")
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
        loaded,groups,assets,diagnostics=local.admit()
        cp=r.read(local.RUN/'checkpoint.json')
        acceptance=r.read(local.RUN/'acceptance.json')
        candidates,bindings={},{}
        for key,ids in groups.items():
            asset=assets[key]
            scope=asset[0]['all_reason_flags']!=0
            r.require(np.array_equal(core.unpack(asset[0]['all_scope_packbits'],len(scope)),scope),'Parent scope mask differs')
            for tag,time,states,error,vehicle,labels in local.path_iter(key,loaded,groups,asset):
                name=key+'/'+tag
                arrays,meta=base.read_arrays(local.RUN/'paths'/name)
                entry=cp['completed'][name]
                expected_index=np.flatnonzero(scope).astype(np.int64)
                r.require(r.file_hash(local.RUN/'paths'/name/'result.json')==entry['path']['result_sha256']
                    and meta['summary']==entry['path']['summary'],'Accepted path metadata binding differs')
                r.require(core.same(arrays['union_index'],expected_index)
                    and core.same(arrays['xy'],asset[0]['xy'][expected_index]),'All22857 full-scope coordinates required')
                original,candidate=strip(arrays,'original__'),strip(arrays,'candidate__')
                found=arrays['trace__found_strict_witness']
                r.require(set(original)==set(labels),'Every original field required')
                for field,value in labels.items():
                    r.require(core.same(original[field],value[expected_index]),'Original field bytes changed')
                core.merge_path(labels,expected_index,candidate,scope,found)
                check=acceptance['checks'][name]
                r.require(check['new_strict_contact_witnesses']==int(found.sum())
                    and check['selected_unwitnessed_records']==int(arrays['trace__selected_unwitnessed'].sum()),
                    'Full per-path independent probe acceptance must bind')
                for dataset_id in ids:
                    out,rec=local.projection(dataset_id,asset[0],arrays,scalar=True)
                    rec.update(group=key,path=tag)
                    merged.checked_output(local.RUN/'datasets'/tag/dataset_id,out,rec,entry['datasets'][dataset_id])
                candidates[name]=expected_index,candidate,found
                bindings[name]={'scope_records':len(expected_index),'new_strict_witnesses':int(found.sum()),
                    'path_result_sha256':entry['path']['result_sha256'],'accepted_candidate_hashes':HASHES,
                    'original_lower_sha256':base.common.array_hash(original['contact_lower_s']),
                    'complete_original_prefix_exact_reuse_no_geometry':True,
                    'all_successful_failed_2D_probes_original_diagnostics_and114_projections_bound':True}
        r.require(set(candidates)==set(cp['completed'])==set(acceptance['checks'])
            and len(candidates)==78 and len(groups)==39 and len(loaded)==57
            and sum(len(v[0]) for v in candidates.values())==45714
            and sum(int(v[2].sum()) for v in candidates.values())==acceptance['accounting']['group_path_totals']['strict_new_witnesses'],
            'All scope rows, paths and accepted witnesses required')
        return loaded,groups,assets,candidates,bindings
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
        for field in ("contact_lower_s",):
            r.require(core.same(paths[tag][field], old_paths[tag][field]), "Every scientific endpoint byte must remain exact")
    for name, value in original.items():
        if name.startswith(("merge_", "upper_merge_", "local_motion_", "probe_merge_")) and name.endswith("__packbits"):
            r.require(core.same(value, arrays[name]), "Original budget/upper provenance changed")
    return paths, combined, flags, scope, arrays, summary


def group_record(key, ids, asset, bindings, summary):
    return {"summary": summary, "original_dataset_ids": ids, "reference_meta": asset[1]["reference_meta"],
        "profile": asset[1]["profile"], "prefix_dependencies": asset[1]["prefix_dependencies"],
        "parent_group_result_sha256": r.file_hash(PARENT / "groups" / key / "result.json"),
        "bounded_suffix_dependencies": {tag: bindings[key + "/" + tag] for tag in core.TAGS},
        "all_original_scientific_lowers_and_prefixes_byte_exact": True,
        "strict_merged_all_point_prefix_coverage_passed": True,
        "all_proven_exclusions_exactly_reused_not_recomputed": True,
        "all_old_provenance_masks_exact_new_suffix_merge_masks_separate": True,
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
        for field in ("contact_lower_s",):
            r.require(core.same(out[tag + "__" + field], old[tag + "__" + field]), "Projected endpoint bytes differ")
    for name, value in old.items():
        if name.startswith(("merge_", "upper_merge_", "local_motion_", "probe_merge_")) and name.endswith("__packbits"):
            r.require(core.same(value, out[name]), "Original-order provenance bytes changed")
    record = {"summary": census.summarize_projection(paths, combined, index, flags, scope),
        "old_label_incompatibilities_not_prediction_scores": {k: int(v.sum()) for k, v in diff.items()},
        "parent_result_sha256": r.file_hash(PARENT / "datasets" / dataset_id / "result.json"),
        "original_xy_sha256": base.common.array_hash(target["xy"]),
        "original_union_index_sha256": base.common.array_hash(index),
        "mask_length": len(index), "bitorder": "little", "all_original_lowers_and_original_prefixes_exact": True}
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
        protocol = {"version":"whole-full-scope-accepted-bounded-suffix-merge-v1",
            "deadline":r.read(AUTH/"authorization.json")["deadline"],
            "parent_merged_assets":str(PARENT),"accepted_probes":str(local.RUN),"candidate_hashes":HASHES,
            "selection":"all22857 current scope points, both45714 path rows, not only changed or successful rows",
            "only_mutable_fields_for_independently_accepted_new_witnesses":sorted(core.MUTABLE),
            "all_scientific_lowers_original_prefix_proofs_and_other_provenance_byte_exact":True,
            "every_no_witness_existing_witness_and_noncontact_row_byte_exact":True,
            "full_population":"all39groups/57original-order projections/3360000point-file records",
            "all114_original_order_full_2D_probe_traces_and_unknown_diagnostics_retained_byte_exact":True,
            "independent_close":"scalar full replacement/combine/conflicts/classify/discrepancies/projection/all fields/padding",
            "full_census_recomputed_no_readding_old_valid_or_unknown_counts":True,
            "no_new_geometry_ODE_prediction_or_score_computation":True,
            "truth_asset_promotion_allowed":False,"corrected_truth_revalidated_prediction_jobs":0,
            "not_global_earliest_identifiability_formal_ODE_or_real_vehicle_certificate":True,
            "workers":1,"inflight":1,"run_cap_bytes":r.RUN_CAP,"reservation_bytes":RESERVATION,
            "total_E_Z_cap_bytes":r.CAP,"Z_reserve_bytes":r.RESERVE,
            "submitted_block":"one complete group and all original-order projections/census; drain at cutoff"}
        plan={"version":"20261022-0000-v36-bounded-suffix-full-merge",
            "deadline":protocol["deadline"],"authorization":str(AUTH/"authorization.json"),
            "run_directory":str(RUN),"entrypoint":str(Path(__file__)),"protocol":str(PROTOCOL),
            "parent_merged_assets":str(PARENT),"accepted_probes":str(local.RUN),
            "parent_complete_census":r.read(PARENT/"acceptance.json")["accounting"],
            "stage_status":"prepared_not_admitted","scientific_acceptance_exists":False,
            "truth_asset_promotion_allowed":False,"corrected_truth_revalidated_prediction_jobs":0,
            "all_label_dependent_claims_withheld":True,"S4_overall_complete":False,"M2_allowed":False,"S5_allowed":False,
            "ordered_remaining":["full merge all57projections fresh census independent close",
                "all remaining contact/time/edge identifiability and full coarse/fine populations/controls",
                "every affected score/report repair or exact unaffected proof"],
            "next_action":"full input/closed probe admission, all-scope strict-witness merge"}
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
    print("BOUNDED SUFFIX FULL MERGE FULL MERGE PREPARED; actual full admission pending", flush=True)


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
                "all57inputs_39groups_all45714_scope_candidates_and114_probe_diagnostics_bound": True,
                "execution": idle, "mutex": mutex}))
            active = r.read(ROOT / "active_research_run.json")
            active.update(version="20261022-0000-v36-bounded-suffix-merge-running", status="suffix_full_merge_full_merge_running",
                run_directory=str(RUN), protocol=str(PROTOCOL), plan=str(PLAN), entrypoint=str(Path(__file__)),
                pid=os.getpid(), running_analysis=True, running_predictions=False, input_worker_admitted=True,
                input_worker_admission_pending=False, scientific_acceptance=None, scientific_close_receipt=None,
                scientific_close_actual_wait_exit_code=None, full_merge_all57projections_and_updated_census_required=True,
                stdout=str(SESSION / "stdout.log"), stderr=str(SESSION / "stderr.log"))
            r.mutable(ROOT / "active_research_run.json", active)
            print("BOUNDED SUFFIX FULL MERGE MERGE PREFLIGHT PASSED ALL57 /39 GROUPS /ALL45714 BOTH-PATH SCOPE /114 DIAGNOSTICS /UNCHANGED SCIENTIFIC LOWERS", flush=True)
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
                print("DONE BOUNDED SUFFIX FULL MERGE FULL MERGE GROUP " + key, flush=True)
            counts = totals(cp["completed"])
            r.require(counts["geometry_groups"] == 39 and counts["dataset_files"] == 57
                and counts["point_file_records"] == 3360000, "Full population required")
            cp.update(status="complete_pending_independent_suffix_full_merge_merge_close", accounting=counts)
            r.checkpoint(cp)
        except Exception:
            cp.update(status="stopped_failure_or_deadline", failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / "runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    print("BOUNDED SUFFIX FULL MERGE FULL MERGE WORKER EXITING; independent close pending", flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / "acceptance.json").exists()
        and not (RUN / "analysis_runner_lock.json").exists(), "Close attempted or cutoff")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / "checkpoint.json")
        r.require(cp["status"] == "complete_pending_independent_suffix_full_merge_merge_close"
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
                print("CLOSE BOUNDED SUFFIX FULL MERGE FULL SCALAR MERGE /PROJECTIONS /CENSUS " + key, flush=True)
            counts = census.totals(rows, geometry)
            r.require(counts == cp["accounting"], "Independent full census differs")
            acceptance = {"time": r.now(), "status": "suffix_full_merge_full_scope_merge_all57projections_census_independently_checked",
                "accounting": counts, "geometry": geometry, "rows": rows,
                "all45714_scope_records_exactly_merged_including_unchanged": True,
                "all_independently_accepted_suffix_strict_witness_candidates_exactly_merged": True,
                "all114_original_order_parent_candidate_unknown_diagnostic_projections_byte_exact": True,
                "all_original_scientific_lower_bytes_unchanged": True,
                "strict_merged_all_point_prefix_coverage_passed": True,
                "full_original_prefix_proofs_exactly_reused_no_exclusions_recomputed": True,
                "all_old_provenance_masks_exact_new_suffix_merge_masks_separate": True,
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
    plan = {**r.read(PLAN), "version": "20261022-0000-v37-bounded-suffix-full-merge-census-closed",
        "stage_status": "full_scope_suffix_full_merge_merge_all57projections_and_census_closed_not_global_truth",
        "scientific_acceptance_exists": True, "accounting": counts, "strict_merged_all_point_prefix_coverage_passed": True,
        "next_action": "all remaining contact/time/edge identifiability, full coarse/fine populations and controls, every affected score/report"}
    report=("# Bounded Suffix Candidate Full Merge and Updated Census\n\n"
        "All45714 scope path records, all39 groups, all57 original-order double-path projections and all3360000 point-file records. "
        "Only independently accepted strict new-witness fields may change. Scientific lowers and original prefix proofs, "
        "unwitnessed unknowns, existing witnesses, noncontacts and prior provenance are byte-exact. "
        "All114 full 2D probe trace/diagnostic projections retained byte-exact. "
        "Independent scalar replacement, combination/conflicts/classification/discrepancies/projection/padding checked. "
        "Reasons overlap; this is neither global truth promotion nor complete identifiability, score repair, formal ODE or real-vehicle certification.\n\n"
        +str(counts)+"\n").encode("utf-8")
    r.batch([(RUN / "close_receipt.json", r.encoded({"time": r.now(), "checkpoint_sha256": r.file_hash(RUN / "checkpoint.json"),
        "acceptance_sha256": r.file_hash(RUN / "acceptance.json"), "execution_after": after,
        "mutex_reacquired_released": released})), (CLOSED_PLAN, r.encoded(plan)),
        (ROOT / "reports/suffix_full_merge_updated_census_20261022_0000_v1.md", report)])
    active = r.read(ROOT / "active_research_run.json")
    active.update(version=plan["version"], status=plan["stage_status"], pid=None, running_analysis=False,
        plan=str(CLOSED_PLAN), scientific_acceptance=str(RUN / "acceptance.json"),
        scientific_close_receipt=str(RUN / "close_receipt.json"), next_action=plan["next_action"],
        complete_current_census=counts, last_accepted_merged_run=str(RUN),
        full_merge_all57projections_and_updated_census_required=False,
        all_remaining_unknowns_and_full_expanded_populations_still_required=True)
    r.mutable(ROOT / "active_research_run.json", active)
    print("BOUNDED SUFFIX FULL MERGE FULL MERGE AND CENSUS CLOSED; claims still withheld " + str(counts), flush=True)


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
    print("BOUNDED SUFFIX FULL MERGE FULL MERGE LAUNCHED historical identity PID " + str(child.pid), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "run", "close"))
    globals()[parser.parse_args().action]()

