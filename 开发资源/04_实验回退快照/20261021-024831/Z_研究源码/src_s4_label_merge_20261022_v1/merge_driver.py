"""Versioned exact label merge, all projections and complete updated census."""
import argparse
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
sys.path.insert(0, str(ROOT / 'src_s4_candidate_prefix_20261022_v2'))
import resume_driver as prior
import merge_core as core
import numpy as np

base, r = prior.base, prior.r
budget = prior.previous.parent
census = budget.prior
POPULATION, AUTH = budget.POPULATION, prior.AUTH
RUN = ROOT / 'runs/resume_20261022_0000_label_merge_v1'
PROTOCOL = ROOT / 'protocol_label_merge_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v17.json'
SESSION = AUTH / 'runtime_sessions/label_merge_launch_v1'
RESERVATION = 896 * 1024**2
PREFIX_HASHES = {
    'checkpoint.json': '91ff3480811d9ebd58cf91a71543ee3cfa66508f78f8136b7a10b303a74debaf',
    'acceptance.json': 'b5b4c75ee32e9da1f67f07b0743fe97bd6a64f575bbddd889b3925360b133401',
    'close_receipt.json': 'e98524dd418a86a94ec599e728bf0c74b28fe287eba5edaffc8845b8d9634a22'}
DEPENDENCIES = tuple(dict.fromkeys((prior.RUN, budget.RUN, census.RUN, census.PARENT,
                                   census.p.RUN, POPULATION)))


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
    prior.gate()
    for name, digest in PREFIX_HASHES.items():
        r.require(r.file_hash(prior.RUN / name) == digest, 'Closed candidate prefix dependency changed')
    a = r.read(prior.RUN / 'acceptance.json')
    r.require(a['strict_all_candidate_prefix_gate_passed'] is True and len(a['checks']) == 78
              and a['group_path_points'] == 3507 and a['exact_reused_paths'] == 32
              and a['new_audited_paths'] == 46 and a['truth_asset_promotion_allowed'] is False,
              'Complete independently closed candidate prefixes required')


def signature():
    paths = {ROOT / rel for rel in r.read(prior.RUN / 'source_manifest.json')}
    paths.update(prior.RUN / name for name in (*PREFIX_HASHES, 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json',
                  AUTH / 'runtime_sessions/candidate_prefix_lossless_v2_closed_v1/registration.json'))
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen merge source dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Frozen merge source copy differs')
    if full:
        inventories = r.read(RUN / 'dependency_files_sha256.json')
        for relroot, files in inventories.items():
            folder = ROOT / relroot
            r.require({p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()} == set(files),
                      'Closed dependency full file set changed')
            for rel, digest in files.items():
                r.require(r.file_hash(folder / rel) == digest, 'Closed dependency file changed: ' + rel)


def admit():
    try:
        gate()
        loaded, groups, selection, candidates, _, _ = prior.admit()
        cp = r.read(prior.RUN / 'checkpoint.json')
        r.require(set(selection) == set(cp['completed']) and len(selection) == 78, 'Every candidate path required')
        assets, bindings = {}, {}
        population_cp = r.read(POPULATION / 'checkpoint.json')
        for key in groups:
            arrays, record = base.read_arrays(POPULATION / 'groups' / key)
            r.require(r.file_hash(POPULATION / 'groups' / key / 'result.json') ==
                      population_cp['completed'][key]['group']['result_sha256'], 'Original asset CP differs')
            paths = {tag: budget.prefixed(arrays, tag + '__') for tag in core.TAGS}
            assets[key] = (arrays, record, paths)
        for name, spec in selection.items():
            proof, saved = prior.storage.read_arrays(prior.RUN / 'paths' / name)
            summary = prior.check_binding(name, spec, candidates[name], proof, saved, independently=False)
            r.require(summary['strict_prefix_gate_passed'] is True and
                      r.file_hash(prior.RUN / 'paths' / name / 'result.json') == cp['completed'][name]['result_sha256'],
                      'Candidate full-prefix endpoint/selection/proof binding differs')
            bindings[name] = {'candidate_result_sha256': r.file_hash(budget.RUN / 'paths' / name / 'result.json'),
                'prefix_result_sha256': cp['completed'][name]['result_sha256'],
                'union_indices': spec['union_indices'], 'points': summary['processed_points'],
                'prefix_checkpoint_sha256': PREFIX_HASHES['checkpoint.json'],
                'prefix_acceptance_sha256': PREFIX_HASHES['acceptance.json']}
        r.require(len(loaded) == 57 and len(groups) == 39 and sum(v['points'] for v in bindings.values()) == 3507,
                  'Complete population and every candidate required')
        return loaded, groups, assets, selection, candidates, bindings
    finally:
        configure()


def build_group(key, asset, selection, candidates, *, scalar):
    original, _, paths = asset
    selected, merged = {}, {}
    for tag in core.TAGS:
        name = key + '__' + tag
        spec = selection[name]
        candidate = candidates[name]
        selected[tag] = np.asarray(spec['union_indices'], np.int64)
        r.require(np.array_equal(candidate[1], selected[tag]) and
                  np.array_equal(candidate[0], original['xy'][selected[tag]]), 'Full replacement coordinate/index binding differs')
        merged[tag] = core.merge_path(paths[tag], selected[tag], candidate[-1], scalar=scalar)
    combined = core.scalar_combine(merged['oldpath'], merged['independent']) if scalar else base.combine(
        merged['oldpath'], merged['independent'])
    classify = census.core.independent_classify if scalar else census.core.classify
    flags, scope = classify(merged['oldpath'], merged['independent'], combined)
    output = core.group_payload(original, merged, combined, flags, scope, selected)
    summary = census.core.summarize(merged['oldpath'], merged['independent'], combined, flags, scope)
    return merged, combined, flags, scope, selected, output, summary


def projection(dataset_id, loaded, xy, paths, combined, flags, scope, group_arrays, *, scalar):
    parent, _ = base.read_arrays(POPULATION / 'datasets' / dataset_id)
    index, target = parent['union_index'], loaded[dataset_id]['target']
    output = core.project(index, xy, target['xy'], paths, combined, flags, scope, group_arrays)
    projected = {k: v[index] for k, v in combined.items()}
    discrepancies = core.scalar_discrepancies(target, projected) if scalar else base.old_discrepancies(target, projected)
    output.update({k + '__packbits': np.packbits(v, bitorder='little') for k, v in discrepancies.items()})
    summary = census.summarize_projection(paths, combined, index, flags, scope)
    record = {'summary': summary, 'old_label_incompatibilities_not_prediction_scores':
              {k: int(v.sum()) for k, v in discrepancies.items()},
              'parent_result_sha256': r.file_hash(POPULATION / 'datasets' / dataset_id / 'result.json'),
              'original_xy_sha256': base.common.array_hash(target['xy']), 'mask_length': len(index), 'bitorder': 'little'}
    unknown = census.core.projection_payload(index, xy, target['xy'], flags, scope)
    return output, record, unknown


def group_record(key, ids, asset, bindings, summary):
    return {'summary': summary, 'original_dataset_ids': ids,
        'reference_meta': asset[1]['reference_meta'], 'profile': asset[1]['profile'],
        'parent_group_result_sha256': r.file_hash(POPULATION / 'groups' / key / 'result.json'),
        'prefix_dependencies': {tag: bindings[key + '__' + tag] for tag in core.TAGS},
        'unselected_original_full_prefix_proof_reused': True,
        'baseline_prefix_acceptance_sha256': census.PARENT_HASHES['acceptance.json'],
        'strict_merged_all_point_prefix_coverage_passed': True,
        'all_other_original_arrays_exact': True, 'truth_asset_promotion_allowed': False}


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Merge synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'exact-conditional-candidate-merge-full-projections-census-v1',
            'deadline': r.read(AUTH / 'authorization.json')['deadline'], 'candidate_prefix_parent': str(prior.RUN),
            'prefix_parent_hashes': PREFIX_HASHES, 'budget_candidates': str(budget.RUN),
            'original_population': str(POPULATION), 'input_files': 57, 'groups': 39,
            'point_file_records': 3360000, 'replaced_group_point_path_records': 3507,
            'selection': 'every and only original per-path exhausted index; all 78 fixed candidate paths',
            'unchanged_points_all_fields_bytes_exact': True, 'all_other_original_group_arrays_exact': True,
            'all_57_original_order_all_path_and_combined_fields_projected': True,
            'all_full_masks_and_padding_checked': True, 'updated_census_complete_population_not_old_mask': True,
            'independent_close': 'scalar pointwise replacement/combination/conflicts/reasons/discrepancies; full decoded arrays',
            'geometry_proof_reuse': 'exact bound independent original and candidate receipts; no recomputation of proven exclusions',
            'no_label_kernel_trajectory_prediction_or_scoring_calls': True,
            'all_unknowns_budgets_and_conflicts_preserved': True, 'truth_asset_promotion_allowed': False,
            'conditional_merge_is_not_global_truth_or_score_repair': True, 'corrected_truth_revalidated_prediction_jobs': 0,
            'submitted_block': 'one full geometry group and all its original-order projections and census; drain at deadline',
            'workers': 1, 'inflight': 1, 'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION,
            'total_E_Z_cap_bytes': r.CAP, 'Z_reserve_bytes': r.RESERVE,
            'not_formal_ODE_or_real_vehicle_certificate': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v16.json'),
            'version': '20261022-0000-v17-conditional-merge-and-updated-census', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'scientific_acceptance_exists': False, 'truth_asset_promotion_allowed': False,
            'strict_merged_all_point_prefix_coverage_passed': None,
            'ordered_remaining': ['complete exact 39-group merge/all 57 projections/full updated census and independent close',
                'all nonbudget label unknowns/full coarse-fine expanded populations/negative controls/counterexamples',
                'every affected score and report or exact unaffected proof'],
            'next_action': 'worker full input and closed proof admission, exact merge and updated complete census'}
        inventory = {folder.relative_to(ROOT).as_posix():
            {p.relative_to(folder).as_posix(): r.file_hash(p) for p in sorted(folder.rglob('*')) if p.is_file()}
            for folder in DEPENDENCIES}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'dependency_files_sha256.json', r.encoded(inventory)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))]
                + [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('EXACT LABEL MERGE PREPARED; full actual input/proof admission pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'truth_asset_promotion_allowed': False,
              'corrected_truth_revalidated_prediction_jobs': 0}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, selection, candidates, bindings = admit()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'groups': groups, 'selection': selection,
                'candidate_prefix_bindings': bindings, 'inputs': len(loaded), 'execution': idle, 'mutex': mutex,
                'all_original_and_candidate_proof_dependencies_bound': True, 'resources': r.resources()}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='conditional_label_merge_and_census_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                running_predictions=False, input_worker_admitted=True, input_worker_admission_pending=False,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'))
            r.mutable(ROOT / 'active_research_run.json', active)
            print('MERGE PREFLIGHT PASSED ALL 57 INPUTS / 39 GROUPS / 78 CLOSED CANDIDATES AND FULL PREFIXES', flush=True)
            for key, ids in groups.items():
                r.require(r.before_deadline(), 'No new complete merge group after cutoff')
                verify(full=False)
                paths, combined, flags, scope, selected, arrays, summary = build_group(
                    key, assets[key], selection, candidates, scalar=False)
                record = group_record(key, ids, assets[key], bindings, summary)
                group = base.save_arrays(RUN / 'groups' / key, arrays, record)
                unknown = base.save_arrays(RUN / 'census/groups' / key,
                    census.core.group_payload(arrays['xy'], paths, combined, flags, scope), record)
                entry = {'group': group, 'census_group': unknown, 'datasets': {}, 'census_datasets': {}}
                for dataset_id in ids:
                    output, meta, projected_unknown = projection(dataset_id, loaded, arrays['xy'], paths,
                        combined, flags, scope, arrays, scalar=False)
                    meta.update(group=key, original_input=loaded[dataset_id]['spec'])
                    entry['datasets'][dataset_id] = base.save_arrays(RUN / 'datasets' / dataset_id, output, meta)
                    entry['census_datasets'][dataset_id] = base.save_arrays(
                        RUN / 'census/datasets' / dataset_id, projected_unknown, meta)
                cp['completed'][key] = entry
                r.checkpoint(cp)
                print('DONE EXACT MERGE GROUP ' + key + ' unknown=' + str(summary['census_points']), flush=True)
            geometry = {key: entry['group']['summary'] for key, entry in cp['completed'].items()}
            rows = [{'summary': v['summary']} for entry in cp['completed'].values() for v in entry['datasets'].values()]
            accounting = census.totals(rows, geometry)
            r.require(accounting['dataset_files'] == 57 and accounting['geometry_groups'] == 39
                      and accounting['point_file_records'] == 3360000, 'Incomplete full merged population')
            cp.update(status='complete_pending_independent_merge_close', accounting=accounting)
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('EXACT LABEL MERGE WORKER EXITING; complete independent close pending', flush=True)


def checked_output(folder, expected, record, entry):
    arrays, saved = base.read_arrays(folder)
    r.require(base.array_meta(arrays) == base.array_meta(expected), 'Every merged/projected quantity or mask padding differs')
    r.require({k: v for k, v in saved.items() if k not in ('arrays', 'npz_sha256')} == record
              and saved['summary'] == entry['summary']
              and r.file_hash(folder / 'result.json') == entry['result_sha256'], 'Full metadata, CP and source binding differs')


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_merge_close' and len(cp['completed']) == 39,
                  'Incomplete merge cannot close')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, selection, candidates, bindings = admit()
            r.require(set(groups) == set(cp['completed']), 'Every group required')
            geometry, rows = {}, []
            for key, ids in groups.items():
                paths, combined, flags, scope, selected, arrays, summary = build_group(
                    key, assets[key], selection, candidates, scalar=True)
                entry = cp['completed'][key]
                record = group_record(key, ids, assets[key], bindings, summary)
                checked_output(RUN / 'groups' / key, arrays, record, entry['group'])
                checked_output(RUN / 'census/groups' / key,
                    census.core.group_payload(arrays['xy'], paths, combined, flags, scope), record, entry['census_group'])
                r.require(set(entry['datasets']) == set(entry['census_datasets']) == set(ids), 'Every original file required')
                geometry[key] = summary
                for dataset_id in ids:
                    output, meta, projected_unknown = projection(dataset_id, loaded, arrays['xy'], paths,
                        combined, flags, scope, arrays, scalar=True)
                    meta.update(group=key, original_input=loaded[dataset_id]['spec'])
                    checked_output(RUN / 'datasets' / dataset_id, output, meta, entry['datasets'][dataset_id])
                    checked_output(RUN / 'census/datasets' / dataset_id, projected_unknown, meta, entry['census_datasets'][dataset_id])
                    rows.append({'dataset': dataset_id, 'group': key, 'summary': meta['summary']})
                print('CLOSE CHECKED ALL MERGED FIELDS AND CENSUS GROUP ' + key, flush=True)
            accounting = census.totals(rows, geometry)
            r.require(accounting == cp['accounting'], 'Independent full census differs')
            value = {'time': r.now(), 'status': 'exact_conditional_merge_all_projections_and_updated_census_independently_checked',
                'accounting': accounting, 'geometry': geometry, 'rows': rows,
                'strict_merged_all_point_prefix_coverage_passed': True,
                'replaced_group_point_path_records': 3507, 'all_78_candidates_exactly_merged': True,
                'every_unselected_path_field_and_other_group_array_exact': True,
                'all_57_original_order_full_fields_and_packbits_padding_checked': True,
                'independent_scalar_merge_combination_conflicts_reasons_and_discrepancies': True,
                'original_assets_predictions_scores_unchanged': True, 'truth_asset_promotion_allowed': False,
                'all_remaining_unknowns_and_full_expanded_populations_still_required': True,
                'all_label_dependent_claims_withheld': True, 'corrected_truth_revalidated_prediction_jobs': 0,
                'not_formal_ODE_or_real_vehicle_certificate': True, 'source_signature': signature(),
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'execution': idle, 'mutex': mutex}
            r.freeze(RUN / 'acceptance.json', r.encoded(value))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261022-0000-v18-conditional-merge-and-updated-census-closed',
        'stage_status': 'conditional_merge_all_projections_updated_census_closed_not_global_truth_repair',
        'scientific_acceptance_exists': True, 'scientific_acceptance_scope': 'conditional merge and complete census only',
        'strict_merged_all_point_prefix_coverage_passed': True, 'accounting': accounting,
        'next_action': 'all remaining nonbudget label unknowns/full coarse-fine expanded populations/negative controls/counterexamples; every affected score or exact unaffected proof'}
    report = ('# Exact Conditional Merge and Updated Complete Census\n\n'
        '39 groups, all 57 original-order full-field projections and all 3360000 point-file records checked. '
        'Every and only 3507 fixed candidate path records merged; all other quantities exact. '
        'Independent scalar replacement, combination, conflicts, reasons and old-label discrepancies checked against '
        'all decoded worker outputs including every mask padding bit. All geometry/prefix proofs exactly bound to '
        'their independent receipts, without rerunning proven exclusions. Unknowns retained; reasons overlap. '
        'No original asset, prediction or score overwritten. Not global truth repair or ODE/vehicle certification.\n\n'
        + str(accounting) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v18.json', r.encoded(plan)),
        (ROOT / 'reports/label_merge_and_updated_census_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='conditional_label_merge_updated_census_closed', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v18.json'), next_action=plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('EXACT CONDITIONAL MERGE CLOSED; unknowns retained; no global truth/score promotion ' + str(accounting), flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(__file__)), 'run']
        r.freeze(SESSION / 'policy.json', r.encoded({'time': r.now(), 'argv': argv, 'execution': idle,
            'mutex': mutex, 'resources': r.guard(RESERVATION, RESERVATION), 'cwd': r'C:\Users\Admin'}))
    for name in ('stdout.log', 'stderr.log'):
        r.freeze(SESSION / name, b'')
    with (SESSION / 'stdout.log').open('ab') as stdout, (SESSION / 'stderr.log').open('ab') as stderr:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_admission_proof': True}))
    print('EXACT LABEL MERGE LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
