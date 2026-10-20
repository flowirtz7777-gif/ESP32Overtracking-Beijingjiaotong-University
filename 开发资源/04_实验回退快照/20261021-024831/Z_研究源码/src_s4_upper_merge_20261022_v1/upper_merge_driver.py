"""All earlier-upper candidates, complete original-order projections and census."""
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
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'
sys.path.insert(0, str(ROOT / 'src_s4_witness_upper_20261022_v1'))
import upper_driver as prior
import numpy as np

# The parent has a different frozen merge_core module with a budget-only contract.
spec = importlib.util.spec_from_file_location('upper_merge_core_20261022_v1', SOURCE / 'merge_core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
base, r, AUTH = prior.base, prior.r, prior.AUTH
merged, census = prior.merge, prior.merge.census
PARENT = merged.RUN
RUN = ROOT / 'runs/resume_20261022_0000_upper_merge_v1'
PROTOCOL = ROOT / 'protocol_upper_merge_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v23.json'
CLOSED_PLAN = ROOT / 'resume_plan_20261022_0000_v24.json'
SESSION = AUTH / 'runtime_sessions/upper_merge_launch_v1'
RESERVATION = 896 * 1024**2
DEPENDENCIES = (prior.RUN, PARENT, prior.science.RUN, prior.admin.RUN)
HASHES = {
    'checkpoint.json': 'a40d90d338c91c3cb42d05a7ebb9e91ecef201b8d67ce4f3ee3fcec3ce9f7ce7',
    'acceptance.json': 'da9eb3edcc962c7eb7a1696267e34e31961572007592de74d42b5147ce215576',
    'close_receipt.json': 'e4dc48ba672fe2aba81cbc729a20de545a3da47aed9623d8334aaa4011796f74',
    'source_manifest.json': 'ca3d878ca390f698b9156a844bb2efae4c4f3b4ded7dea038edda5f12b8e1c4d'}


def configure():
    prior.configure()
    r.RUN, r.RUN_CAP = RUN, 1024**3


configure()


def execution():
    try:
        return prior.execution()
    finally:
        configure()


def gate():
    prior.verify()
    for name, digest in HASHES.items():
        r.require(r.file_hash(prior.RUN / name) == digest, 'Closed whole-upper dependency changed')
    a = r.read(prior.RUN / 'acceptance.json')
    r.require(a['status'] == 'all_witness_upper_candidates_independently_checked_not_merged_or_promoted'
        and a['accounting']['path_blocks'] == 78 and a['accounting']['selected_point_path_records'] == 60078
        and a['all_original_lower_bytes_exact_unchanged_and_complete_existing_prefix_coverage_reused']
        and a['truth_asset_promotion_allowed'] is False, 'All candidates and unchanged-lower prefix proof required')
    r.require(r.read(PARENT / 'acceptance.json')['strict_merged_all_point_prefix_coverage_passed'] is True,
              'Complete parent all-point prefix coverage required')


def signature():
    paths = {ROOT / rel for rel in r.read(prior.RUN / 'source_manifest.json')}
    paths.update(prior.RUN / name for name in HASHES)
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json',
        AUTH / 'runtime_sessions/witness_upper_closed_v1/registration.json',
        AUTH / 'runtime_sessions/witness_upper_closed_v1/all_closed_run_files_sha256.json'))
    for folder in (AUTH / 'runtime_sessions').glob('upper_merge_development_tests_v*'):
        paths.update(p for p in folder.rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen whole-upper merge dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Frozen source copy differs')
    if full:
        gate()
        for root, files in r.read(RUN / 'dependency_files_sha256.json').items():
            folder = ROOT / root
            r.require({q.relative_to(folder).as_posix() for q in folder.rglob('*') if q.is_file()} == set(files),
                      'Complete closed parent inventory differs')
            for rel, digest in files.items():
                r.require(r.file_hash(folder / rel) == digest, 'Complete parent bytes differ')


def admit():
    try:
        gate()
        loaded, groups, assets = prior.admit()
        cp = r.read(prior.RUN / 'checkpoint.json')
        accepted = r.read(prior.RUN / 'acceptance.json')
        candidates, bindings = {}, {}
        for key in groups:
            for tag, time, states, error, vehicle, labels in prior.path_iter(key, loaded, groups, assets[key]):
                name = key + '/' + tag
                arrays, saved = base.read_arrays(prior.RUN / 'paths' / name)
                index = np.flatnonzero(core.selected_mask(labels))
                original = {k: v[index] for k, v in labels.items()}
                seed = merged.budget.prefixed(arrays, 'original__')
                candidate = merged.budget.prefixed(arrays, 'candidate__')
                trace = merged.budget.prefixed(arrays, 'trace__')
                r.require(base.array_meta(seed) == base.array_meta(original), 'Every current original seed field required')
                r.require(np.array_equal(index, arrays['union_index'])
                    and np.array_equal(arrays['xy'], assets[key][0]['xy'][index]), 'All selected coordinates and indices required')
                summary = prior.core.summary(original, candidate, trace)
                expected = {'union_index': index, 'xy': assets[key][0]['xy'][index],
                    'full_selection_packbits': np.packbits(core.selected_mask(labels), bitorder='little'),
                    'changed_upper_packbits': np.packbits(candidate['contact_upper_s'] < original['contact_upper_s'], bitorder='little'),
                    'candidate_certain_packbits': np.packbits(candidate['edge_certain'], bitorder='little')}
                for prefix, values in (('original__', original), ('candidate__', candidate), ('trace__', trace)):
                    expected.update({prefix + k: v for k, v in values.items()})
                merged.checked_output(prior.RUN / 'paths' / name, expected,
                    prior.record(key, tag, summary, assets[key], time, states, error, vehicle), cp['completed'][name])
                r.require(accepted['checks'][name]['all_selected_records'] == len(index),
                          'Every selected row must be independently accepted by the parent')
                # Validate replacement semantics here without rerunning accepted probe geometry.
                core.merge_path(labels, index, candidate)
                candidates[name] = index, candidate
                bindings[name] = {'selected_records': len(index), 'candidate_result_sha256': cp['completed'][name]['result_sha256'],
                    'candidate_acceptance_sha256': HASHES['acceptance.json'], 'candidate_receipt_sha256': HASHES['close_receipt.json'],
                    'original_scientific_lower_sha256': base.common.array_hash(original['contact_lower_s']),
                    'all_original_lower_bytes_exact': original['contact_lower_s'].tobytes() == candidate['contact_lower_s'].tobytes(),
                    'complete_parent_prefix_proof_reused_no_new_geometry': True}
        r.require(set(candidates) == set(cp['completed']) == set(accepted['checks'])
            and len(loaded) == 57 and len(groups) == 39 and len(candidates) == 78
            and sum(len(v[0]) for v in candidates.values()) == 60078, 'Complete upper candidate population required')
        return loaded, groups, assets, candidates, bindings
    finally:
        configure()


def build_group(key, asset, candidates, *, scalar):
    original, _, old_paths = asset
    selected, paths = {}, {}
    for tag in core.TAGS:
        index, candidate = candidates[key + '/' + tag]
        selected[tag] = index
        paths[tag] = core.merge_path(old_paths[tag], index, candidate, scalar=scalar)
    combined = merged.core.scalar_combine(paths['oldpath'], paths['independent']) if scalar else base.combine(
        paths['oldpath'], paths['independent'])
    classify = census.core.independent_classify if scalar else census.core.classify
    flags, scope = classify(paths['oldpath'], paths['independent'], combined)
    arrays = core.group_payload(original, paths, combined, flags, scope, selected)
    summary = census.core.summarize(paths['oldpath'], paths['independent'], combined, flags, scope)
    for tag in core.TAGS:
        r.require(paths[tag]['contact_lower_s'].tobytes() == old_paths[tag]['contact_lower_s'].tobytes(),
                  'Full all-point science lower must remain byte-exact')
        for kind in ('selected', 'changed'):
            name = 'merge_' + kind + '_' + tag + '__packbits'
            r.require(arrays[name].tobytes() == original[name].tobytes(), 'Original budget-merge provenance must remain exact')
    return paths, combined, flags, scope, selected, arrays, summary


def group_record(key, ids, asset, bindings, summary):
    return {'summary': summary, 'original_dataset_ids': ids,
        'reference_meta': asset[1]['reference_meta'], 'profile': asset[1]['profile'],
        'parent_group_result_sha256': r.file_hash(PARENT / 'groups' / key / 'result.json'),
        'prefix_dependencies': asset[1]['prefix_dependencies'],
        'upper_candidate_dependencies': {tag: bindings[key + '/' + tag] for tag in core.TAGS},
        'all_original_scientific_lower_bytes_exact': True,
        'strict_merged_all_point_prefix_coverage_passed': True, 'all_proven_exclusions_exactly_reused_not_recomputed': True,
        'old_budget_merge_masks_exact_new_upper_masks_separate': True, 'truth_asset_promotion_allowed': False}


def projection(dataset_id, loaded, xy, paths, combined, flags, scope, arrays, *, scalar):
    old, _ = base.read_arrays(PARENT / 'datasets' / dataset_id)
    index = old['union_index']
    target = loaded[dataset_id]['target']
    out = merged.core.project(index, xy, target['xy'], paths, combined, flags, scope, arrays)
    core.add_projection_masks(out, index, arrays, len(xy))
    projected = {k: v[index] for k, v in combined.items()}
    discrepancies = merged.core.scalar_discrepancies(target, projected) if scalar else base.old_discrepancies(target, projected)
    out.update({k + '__packbits': np.packbits(v, bitorder='little') for k, v in discrepancies.items()})
    for tag in core.TAGS:
        for kind in ('selected', 'changed'):
            name = 'merge_' + kind + '_' + tag + '__packbits'
            r.require(out[name].tobytes() == old[name].tobytes(), 'Original-order budget provenance changed')
        r.require(out[tag + '__contact_lower_s'].tobytes() == old[tag + '__contact_lower_s'].tobytes(),
                  'Every original-order lower must remain byte-exact')
    record = {'summary': census.summarize_projection(paths, combined, index, flags, scope),
        'old_label_incompatibilities_not_prediction_scores': {k: int(v.sum()) for k, v in discrepancies.items()},
        'parent_result_sha256': r.file_hash(PARENT / 'datasets' / dataset_id / 'result.json'),
        'original_xy_sha256': base.common.array_hash(target['xy']), 'mask_length': len(index), 'bitorder': 'little',
        'all_lower_bytes_unchanged_and_complete_original_prefixes_reused': True}
    unknown = census.core.projection_payload(index, xy, target['xy'], flags, scope)
    return out, record, unknown


def totals(completed):
    geometry = {key: entry['group']['summary'] for key, entry in completed.items()}
    rows = [{'summary': v['summary']} for entry in completed.values() for v in entry['datasets'].values()]
    return census.totals(rows, geometry)


def prepare():
    r.require(r.before_deadline() and not any(q.exists() for q in (RUN, PROTOCOL, PLAN, CLOSED_PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True, encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Whole upper merge synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'complete-earlier-upper-merge-original-order-projections-and-census-v1',
            'deadline': r.read(AUTH / 'authorization.json')['deadline'], 'parent_merged_assets': str(PARENT),
            'upper_candidates': str(prior.RUN), 'upper_candidate_hashes': HASHES,
            'selection': 'every finite upper and edge_certain false in current parent path, not budget-mask selection',
            'all_candidate_path_blocks': 78, 'selected_group_point_path_records': 60078,
            'unchanged_upper_candidates_still_merged': 884, 'initial_zero_width_candidates_included': 878,
            'all_scientific_lowers_and_unselected_fields_byte_exact': True,
            'old_budget_merge_masks_retained_new_upper_masks_separate': True,
            'full_population': 'all39 groups, all57 original-order full-field projections, all3360000 point-file records',
            'full_census_recomputed_not_old_unknown_mask': True,
            'independent_close': 'scalar replacement/paired combination/time and edge/model conflicts/reasons/discrepancies, every array/index/padding',
            'no_geometry_label_kernel_ODE_prediction_or_score_recomputed': True,
            'complete_accepted_geometry_and_all_prefix_proofs_exactly_bound_and_reused': True,
            'all_unknowns_budgets_and_model_conflicts_retained': True, 'truth_asset_promotion_allowed': False,
            'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True,
            'workers': 1, 'inflight': 1, 'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION,
            'total_E_Z_cap_bytes': r.CAP, 'Z_reserve_bytes': r.RESERVE,
            'submitted_block': 'one full merged group and all its original-order projections and census, drain at cutoff'}
        plan = {'version': '20261022-0000-v23-complete-upper-merge-and-census',
            'deadline': r.read(AUTH / 'authorization.json')['deadline'], 'authorization': str(AUTH / 'authorization.json'),
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'stage_status': 'prepared_not_admitted', 'scientific_acceptance_exists': False,
            'truth_asset_promotion_allowed': False, 'strict_merged_all_point_prefix_coverage_passed': None,
            'parent_merged_assets': str(PARENT), 'all_upper_candidates': str(prior.RUN),
            'parent_complete_census': r.read(PARENT / 'acceptance.json')['accounting'],
            'ordered_remaining': ['complete exact merge/all57projections/updated census and independent close',
                'all unwitnessed contact/time/edge unknowns with complete identifiability evidence',
                'complete coarse-fine expanded populations and negative controls/counterexamples',
                'every affected score/report repair or exact unaffected proof'],
            'historical_ledger': {'formal': 2238, 'accepted_diagnostics': 66, 'numeric_records': 2304},
            'corrected_truth_revalidated_prediction_jobs': 0, 'all_label_dependent_claims_withheld': True,
            'S4_overall_complete': False, 'M2_allowed': False, 'S5_allowed': False,
            'next_action': 'full input/closed-candidate proof admission and exact whole-upper merge'}
        inventories = {q.relative_to(ROOT).as_posix(): {p.relative_to(q).as_posix(): r.file_hash(p)
            for p in sorted(q.rglob('*')) if p.is_file()} for q in DEPENDENCIES}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'dependency_files_sha256.json', r.encoded(inventories)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))]
            + [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('COMPLETE UPPER MERGE PREPARED; actual full admission pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'truth_asset_promotion_allowed': False}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, candidates, bindings = admit()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'groups': groups, 'upper_bindings': bindings,
                'all57inputs_39current_groups_78closed_upper_candidates_and_complete_prefixes_bound': True,
                'execution': idle, 'mutex': mutex}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(version='20261022-0000-v23-complete-upper-merge-running',
                status='whole_upper_merge_all_projections_census_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                running_predictions=False, input_worker_admitted=True, input_worker_admission_pending=False,
                scientific_acceptance=None, scientific_close_receipt=None, scientific_close_actual_wait_exit_code=None,
                full_merge_all57projections_and_updated_census_required=True,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'))
            r.mutable(ROOT / 'active_research_run.json', active)
            print('UPPER MERGE PREFLIGHT PASSED ALL57 INPUTS /39 GROUPS /78 PATHS /ALL60078 CANDIDATES /UNCHANGED LOWER FULL PREFIXES', flush=True)
            for key, ids in groups.items():
                r.require(r.before_deadline(), 'No new full upper-merge group after cutoff')
                verify(full=False)
                paths, combined, flags, scope, _, arrays, summary = build_group(key, assets[key], candidates, scalar=False)
                meta = group_record(key, ids, assets[key], bindings, summary)
                entry = {'group': base.save_arrays(RUN / 'groups' / key, arrays, meta),
                    'census_group': base.save_arrays(RUN / 'census/groups' / key,
                        census.core.group_payload(arrays['xy'], paths, combined, flags, scope), meta),
                    'datasets': {}, 'census_datasets': {}}
                for dataset_id in ids:
                    out, record, unknown = projection(dataset_id, loaded, arrays['xy'], paths, combined,
                        flags, scope, arrays, scalar=False)
                    record.update(group=key, original_input=loaded[dataset_id]['spec'])
                    entry['datasets'][dataset_id] = base.save_arrays(RUN / 'datasets' / dataset_id, out, record)
                    entry['census_datasets'][dataset_id] = base.save_arrays(RUN / 'census/datasets' / dataset_id, unknown, record)
                cp['completed'][key] = entry
                r.checkpoint(cp)
                print('DONE COMPLETE UPPER MERGE GROUP ' + key + ' unknown=' + str(summary['census_points']), flush=True)
            counts = totals(cp['completed'])
            r.require(counts['geometry_groups'] == 39 and counts['dataset_files'] == 57
                and counts['point_file_records'] == 3360000, 'Full population required, not selected candidates only')
            cp.update(status='complete_pending_independent_upper_merge_close', accounting=counts)
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('COMPLETE UPPER MERGE WORKER EXITING; full independent close pending', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_upper_merge_close' and len(cp['completed']) == 39,
                  'Incomplete upper merge cannot close')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, candidates, bindings = admit()
            r.require(set(groups) == set(cp['completed']), 'Every current merged group required')
            geometry, rows = {}, []
            for key, ids in groups.items():
                paths, combined, flags, scope, _, arrays, summary = build_group(key, assets[key], candidates, scalar=True)
                meta = group_record(key, ids, assets[key], bindings, summary)
                entry = cp['completed'][key]
                merged.checked_output(RUN / 'groups' / key, arrays, meta, entry['group'])
                merged.checked_output(RUN / 'census/groups' / key,
                    census.core.group_payload(arrays['xy'], paths, combined, flags, scope), meta, entry['census_group'])
                r.require(set(entry['datasets']) == set(entry['census_datasets']) == set(ids), 'All original-order files required')
                geometry[key] = summary
                for dataset_id in ids:
                    out, record, unknown = projection(dataset_id, loaded, arrays['xy'], paths, combined,
                        flags, scope, arrays, scalar=True)
                    record.update(group=key, original_input=loaded[dataset_id]['spec'])
                    merged.checked_output(RUN / 'datasets' / dataset_id, out, record, entry['datasets'][dataset_id])
                    merged.checked_output(RUN / 'census/datasets' / dataset_id, unknown, record, entry['census_datasets'][dataset_id])
                    rows.append({'dataset': dataset_id, 'group': key, 'summary': record['summary']})
                print('CLOSE FULL SCALAR UPPER MERGE /PROJECTIONS /CENSUS GROUP ' + key, flush=True)
            counts = census.totals(rows, geometry)
            r.require(counts == cp['accounting'], 'Independent full updated census differs')
            value = {'time': r.now(), 'status': 'whole_upper_merge_all_original_order_projections_and_census_independently_checked',
                'accounting': counts, 'geometry': geometry, 'rows': rows,
                'all_60078_upper_candidates_exactly_merged_including_884_unchanged': True,
                'strict_merged_all_point_prefix_coverage_passed': True,
                'all_original_scientific_lower_bytes_unchanged_and_full_prefixes_exactly_reused': True,
                'every_unselected_field_and_original_budget_mask_exact_new_upper_masks_separate': True,
                'all57original_order_full_fields_indices_and_packbits_padding_checked': True,
                'scalar_full_population_combination_conflicts_classification_and_discrepancies': True,
                'all_unknowns_and_conflicts_retained': True, 'no_geometry_or_prediction_recomputed': True,
                'original_assets_predictions_scores_unchanged': True, 'truth_asset_promotion_allowed': False,
                'full_merge_all57projections_and_updated_census_required': False,
                'all_remaining_unknowns_and_full_expanded_populations_still_required': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'all_label_dependent_claims_withheld': True,
                'not_formal_ODE_or_real_vehicle_certificate': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex}
            r.freeze(RUN / 'acceptance.json', r.encoded(value))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261022-0000-v24-whole-upper-merge-census-closed',
        'stage_status': 'complete_upper_merge_all_original_order_projections_census_closed_not_global_truth',
        'scientific_acceptance_exists': True, 'scientific_acceptance_scope': 'conditional upper merge and complete updated census',
        'strict_merged_all_point_prefix_coverage_passed': True, 'accounting': counts,
        'next_action': 'all remaining unwitnessed contact/time/edge unknowns and identifiability evidence; complete expanded populations/controls/counterexamples and every affected score/report repair'}
    report = ('# Whole Earlier-Upper Merge and Complete Updated Census\n\n'
        'All60078 candidates including884 unchanged; all39 groups/all57 original-order projections/all3360000 point-file records. '
        'All science lowers, trajectories and unselected fields exact; original budget-merge masks retained, new upper masks separate. '
        'Every scalar replacement/combined time-edge/model conflict/classification/old-label discrepancy, full arrays and padding checked. '
        'All independent geometry and complete original prefixes reused by exact signatures, no geometry recomputed. '
        'New conditional asset version only, not global truth or score repair; unknowns/conflicts retained. Reasons overlap.\n\n'
        + str(counts) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'execution_after': after, 'mutex_reacquired_and_released': released})),
        (CLOSED_PLAN, r.encoded(plan)), (ROOT / 'reports/upper_merge_and_updated_census_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(version=plan['version'], status='complete_upper_merge_all57projections_census_closed_not_global_truth',
        pid=None, running_analysis=False, plan=str(CLOSED_PLAN), next_action=plan['next_action'],
        scientific_acceptance=str(RUN / 'acceptance.json'), scientific_close_receipt=str(RUN / 'close_receipt.json'),
        full_merge_all57projections_and_updated_census_required=False,
        all_remaining_unknowns_and_full_expanded_populations_still_required=True)
    r.mutable(ROOT / 'active_research_run.json', active)
    print('COMPLETE UPPER MERGE AND FULL CENSUS CLOSED; claims still withheld ' + str(counts), flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(__file__)), 'run']
        r.freeze(SESSION / 'policy.json', r.encoded({'time': r.now(), 'argv': argv, 'cwd': r'C:\Users\Admin',
            'execution': idle, 'mutex': mutex, 'resources': r.guard(RESERVATION, RESERVATION)}))
    for name in ('stdout.log', 'stderr.log'):
        r.freeze(SESSION / name, b'')
    with (SESSION / 'stdout.log').open('ab') as stdout, (SESSION / 'stderr.log').open('ab') as stderr:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_admission_proof': True}))
    print('COMPLETE UPPER MERGE LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()

