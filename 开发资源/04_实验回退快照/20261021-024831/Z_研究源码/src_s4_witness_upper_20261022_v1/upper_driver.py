"""Fixed-policy earlier witness candidates for the whole current uncertain-edge scope."""
import argparse
import math
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
sys.path.insert(0, str(ROOT / 'src_s4_label_observability_finalize_20261022_v1'))
import finalize as admin
import upper_core as core
import numpy as np

science, r = admin.science, admin.r
merge, base, AUTH = science.parent, science.base, science.AUTH
RUN = ROOT / 'runs/resume_20261022_0000_witness_upper_v1'
PROTOCOL = ROOT / 'protocol_witness_upper_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v21.json'
CLOSED_PLAN = ROOT / 'resume_plan_20261022_0000_v22.json'
SESSION = AUTH / 'runtime_sessions/witness_upper_launch_v1'
RESERVATION = 448 * 1024**2
DEPENDENCIES = (science.RUN, admin.RUN, merge.RUN)
HASHES = {
    (science.RUN, 'checkpoint.json'): 'e558638d9cd5d7e628dafd7cf00098ccbe4cb7e8f6b93a3766016230eff862f2',
    (science.RUN, 'acceptance.json'): '75531236245699494006287d823aa7ec3eb6ff37b8eaef69600fda0e08871019',
    (admin.RUN, 'receipt.json'): '3e39b3e27d089ae21ef6cff8bb79c06ac3d764da05b3eb90eb5335cad420e94e'}


def configure():
    admin.configure()
    r.RUN, r.RUN_CAP = RUN, 512 * 1024**2


configure()


def execution():
    try:
        return admin.execution()
    finally:
        configure()


def gate():
    science.verify()
    for (folder, name), digest in HASHES.items():
        r.require(r.file_hash(folder / name) == digest, 'Science acceptance or separate administrative receipt differs')
    r.require(not (science.RUN / 'close_receipt.json').exists(), 'Original failed scientific close must not be rewritten')
    receipt = r.read(admin.RUN / 'receipt.json')
    r.require(receipt['original_close_receipt_remains_absent'] is True, 'Separate administrative recovery required')
    accepted = r.read(science.RUN / 'acceptance.json')
    r.require(accepted['labels_and_prefix_proofs_unchanged'] and accepted['truth_asset_promotion_allowed'] is False,
              'Diagnostic parent must not have relabeled data')


def signature():
    paths = {ROOT / rel for rel in r.read(admin.RUN / 'source_manifest.json')}
    paths.update(folder / name for folder, name in HASHES)
    paths.update(folder / 'source_manifest.json' for folder in DEPENDENCIES)
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json',
        AUTH / 'runtime_sessions/label_observability_admin_finalized_v1/registration.json'))
    for folder in (AUTH / 'runtime_sessions').glob('witness_upper_development_tests_v*'):
        paths.update(p for p in folder.rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen upper candidate source/dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Frozen source copy differs')
    if full:
        gate()
        for root, files in r.read(RUN / 'parent_files_sha256.json').items():
            folder = ROOT / root
            r.require({p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()} == set(files),
                      'Complete dependency file inventory differs')
            for rel, digest in files.items():
                r.require(r.file_hash(folder / rel) == digest, 'Dependency bytes differ')


def admit():
    try:
        gate()
        loaded, groups, assets, accounting = science.admit()
        for key, asset in assets.items():
            flags = asset[0]['all_reason_flags']
            for tag, bit in (('oldpath', 1024), ('independent', 2048)):
                mask = core.selection(asset[2][tag])
                r.require(np.array_equal(mask, (flags & bit) != 0), 'Whole current witnessed-edge scope differs')
        r.require(accounting['complete_census_point_file_records'] == 51606, 'Whole current census required')
        return loaded, groups, assets
    finally:
        configure()


def path_iter(key, loaded, groups, asset):
    return merge.census.p.follow.paths_for(key, loaded, groups, asset)


def build(tag, time, states, error, vehicle, labels, full_xy):
    mask = core.selection(labels)
    index = np.flatnonzero(mask)
    original = {k: v[index].copy() for k, v in labels.items()}
    xy = full_xy[index]
    params = dict(length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
    geometry = lambda x, pose: base.finite_face_geometry(x, pose, **params)
    speed = base.motion_bound(states, time, **params)
    proposed, trace = core.candidate(xy, time, states, original, error, geometry, speed,
        base.original_corner_rule, science.core.confidence)
    changed = proposed['contact_upper_s'] < original['contact_upper_s']
    out = {'union_index': index, 'xy': xy, 'full_selection_packbits': np.packbits(mask, bitorder='little'),
        'changed_upper_packbits': np.packbits(changed, bitorder='little'),
        'candidate_certain_packbits': np.packbits(proposed['edge_certain'], bitorder='little')}
    for prefix, data in (('original__', original), ('candidate__', proposed), ('trace__', trace)):
        out.update({prefix + k: v for k, v in data.items()})
    return out, core.summary(original, proposed, trace)


def record(key, tag, summary, asset, time, states, error, vehicle):
    return {'summary': summary, 'group': key, 'path': tag,
        'original_dataset_ids': asset[1]['original_dataset_ids'],
        'parent_merged_result_sha256': r.file_hash(merge.RUN / 'groups' / key / 'result.json'),
        'time_sha256': base.common.array_hash(time), 'states_sha256': base.common.array_hash(states),
        'xy_sha256': base.common.array_hash(asset[0]['xy']), 'original_path_arrays': base.array_meta(asset[2][tag]),
        'space_error_m': error, 'vehicle': vars(vehicle), 'original_lower_bytes_unchanged': True,
        'complete_existing_prefix_proofs_exactly_reused_no_pre_lower_queries': True,
        'internal_probe_low_not_a_scientific_lower': True, 'not_a_monotonic_or_global_earliest_witness_search': True,
        'original_interval_evaluations_retained_as_provenance_new_probe_counts_separate': True,
        'truth_asset_promotion_allowed': False}


def total(completed):
    summaries = [v['summary'] for v in completed.values()]
    keys = ('selected_point_path_records', 'earlier_witnesses', 'all_fields_exact_reused_no_earlier_witness',
            'initial_zero_width_exact_reuse', 'candidate_edge_certain', 'candidate_edge_still_uncertain',
            'probe_evaluations', 'probe_budget_exhausted')
    return {'path_blocks': len(summaries), **{k: sum(v[k] for v in summaries) for k in keys},
            'not_independent_samples': True}


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN, CLOSED_PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Upper candidate synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'whole-witnessed-uncertain-edge-earlier-upper-candidates-v1',
            'deadline': r.read(AUTH / 'authorization.json')['deadline'],
            'selection': 'every and only current raw path finite upper and uncertain edge, both paths all39groups, including zero-width initial and spatial-only-rule failures',
            'weighted_parent_selected_oldpath': 37650, 'weighted_parent_selected_independent': 32449,
            'probe_policy': 'fixed64 binary probe chain until internal width <=1e-7; only strict valid earlier witnesses update upper; failure is not exclusion or monotonicity',
            'scientific_lower': 'all original bytes unchanged; internal probe low never promoted',
            'probe_budget_per_point': core.STEPS, 'internal_resolution_s': core.RESOLUTION,
            'tol_m': core.TOL, 'new_witness_additional_guard_m': core.GUARD, 'corner_m': .001,
            'all_original_space_errors_and_path_endpoints_unchanged': True,
            'no_earlier_witness_every_original_label_byte_exact_reuse': True,
            'complete_probe_trace_and_full_candidate_fields_saved_and_independently_checked': True,
            'complete_current_prefix_coverage_reuse_by_exact_lowers_trajectories_coordinates_errors': True,
            'not_global_earliest_witness_or_formal_ODE_certificate': True,
            'truth_asset_promotion_allowed': False, 'separate_full_merge_all57projections_updated_census_required': True,
            'unwitnessed_unknowns_full_expanded_populations_controls_and_scores_remain_required': True,
            'corrected_truth_revalidated_prediction_jobs': 0, 'workers': 1, 'inflight': 1,
            'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION, 'total_E_Z_cap_bytes': r.CAP,
            'Z_reserve_bytes': r.RESERVE, 'submitted_block': 'one complete path, finish submitted block after cutoff',
            'scientific_diagnostic_parent_and_separate_admin_receipt_both_bound': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v20.json'),
            'version': '20261022-0000-v21-complete-witness-upper-candidates', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'scientific_acceptance_exists': False, 'next_action': 'all current witnessed uncertain-edge rows, earlier upper witnesses only; independent close then separate complete merge'}
        inventories = {p.relative_to(ROOT).as_posix(): {q.relative_to(p).as_posix(): r.file_hash(q)
            for q in sorted(p.rglob('*')) if q.is_file()} for p in DEPENDENCIES}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'parent_files_sha256.json', r.encoded(inventories)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))]
            + [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('WHOLE WITNESS UPPER CANDIDATES PREPARED; actual admission pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'truth_asset_promotion_allowed': False}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets = admit()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'groups': groups,
                'all_57_inputs_current_merged_fields_full_census_parent_diagnostic_and_admin_receipt_bound': True,
                'execution': idle, 'mutex': mutex}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='whole_witness_upper_candidates_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                running_predictions=False, input_worker_admitted=True, input_worker_admission_pending=False,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'))
            r.mutable(ROOT / 'active_research_run.json', active)
            print('WITNESS UPPER PREFLIGHT PASSED ALL57 INPUTS /39 MERGED GROUPS /ALL CURRENT WITNESSED UNCERTAIN EDGES', flush=True)
            for key in groups:
                for tag, time, states, error, vehicle, labels in path_iter(key, loaded, groups, assets[key]):
                    r.require(r.before_deadline(), 'No new witness-upper path block after cutoff')
                    verify(full=False)
                    arrays, summary = build(tag, time, states, error, vehicle, labels, assets[key][0]['xy'])
                    entry = base.save_arrays(RUN / 'paths' / key / tag, arrays,
                        record(key, tag, summary, assets[key], time, states, error, vehicle))
                    cp['completed'][key + '/' + tag] = entry
                    r.checkpoint(cp)
                    r.require(summary['probe_budget_exhausted'] == 0, 'Complete probe budget failure saved; no promotion')
                    print('DONE UPPER CANDIDATE PATH ' + key + '/' + tag + ' ' + str(summary), flush=True)
            cp.update(status='complete_pending_independent_upper_close', accounting=total(cp['completed']))
            r.require(cp['accounting']['path_blocks'] == 78, 'All current path blocks required')
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('WHOLE UPPER CANDIDATE WORKER EXITING; independent close pending', flush=True)


def scalar_max_speed(time, states, vehicle):
    return max((math.hypot(float(b[0]-a[0]), float(b[1]-a[1])) + abs(vehicle.l_h)*abs(float(b[2]-a[2]))
        + math.hypot(vehicle.L, vehicle.width/2)*abs(float((b[2]-a[2])-(b[3]-a[3])))) / float(tb-ta)
        for a, b, ta, tb in zip(states[:-1], states[1:], time[:-1], time[1:]))


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_upper_close' and len(cp['completed']) == 78,
                  'Incomplete candidates cannot close')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets = admit()
            checks, weighted = {}, {tag: {} for tag in merge.core.TAGS}
            for key, ids in groups.items():
                for tag, time, states, error, vehicle, labels in path_iter(key, loaded, groups, assets[key]):
                    name = key + '/' + tag
                    arrays, meta = base.read_arrays(RUN / 'paths' / name)
                    index = np.flatnonzero(core.selection(labels))
                    original = {k: v[index].copy() for k, v in labels.items()}
                    saved = merge.budget.prefixed(arrays, 'original__')
                    proposed = merge.budget.prefixed(arrays, 'candidate__')
                    trace = merge.budget.prefixed(arrays, 'trace__')
                    r.require(base.array_meta(saved) == base.array_meta(original), 'All original fields/NaNs/dtypes exact')
                    r.require(np.array_equal(arrays['union_index'], index) and
                        base.array_meta({'xy': arrays['xy']}) == base.array_meta({'xy': assets[key][0]['xy'][index]}),
                        'Complete selected index order and coordinates required')
                    values = core.summary(original, proposed, trace)
                    expected = {'union_index': index, 'xy': assets[key][0]['xy'][index],
                        'full_selection_packbits': np.packbits(core.selection(labels), bitorder='little'),
                        'changed_upper_packbits': np.packbits(proposed['contact_upper_s'] < original['contact_upper_s'], bitorder='little'),
                        'candidate_certain_packbits': np.packbits(proposed['edge_certain'], bitorder='little')}
                    for prefix, data in (('original__', original), ('candidate__', proposed), ('trace__', trace)):
                        expected.update({prefix + k: v for k, v in data.items()})
                    merge.checked_output(RUN / 'paths' / name, expected,
                        record(key, tag, values, assets[key], time, states, error, vehicle), cp['completed'][name])
                    checks[name] = core.independently_check(arrays['xy'], time, states, original, proposed, error,
                        vehicle, trace, science.core.geos_geometry, scalar_max_speed(time, states, vehicle))
                    checks[name]['candidate_full_GE0S_finite_faces_and_confidence'] = base.validate_path(
                        arrays['xy'], time, states, proposed, error, vehicle)
                    r.require(values['probe_budget_exhausted'] == 0, 'Probe-budget unknown must not be promoted')
                    for dataset_id in ids:
                        projection, _ = base.read_arrays(merge.RUN / 'datasets' / dataset_id)
                        union_index = projection['union_index']
                        r.require(np.array_equal(assets[key][0]['xy'][union_index], loaded[dataset_id]['target']['xy']),
                                  'Every original-order coordinate projection must remain bound')
                        multiplicity = np.bincount(union_index, minlength=len(labels['contact_status']))[index]
                        row = weighted[tag]
                        row['selected_point_file_path_records'] = row.get('selected_point_file_path_records', 0) + int(multiplicity.sum())
                        row['earlier_witness_point_file_path_records'] = row.get('earlier_witness_point_file_path_records', 0) + int(
                            multiplicity[proposed['contact_upper_s'] < original['contact_upper_s']].sum())
                        row['candidate_edge_certain_point_file_path_records'] = row.get('candidate_edge_certain_point_file_path_records', 0) + int(
                            multiplicity[proposed['edge_certain']].sum())
                    print('CLOSE ALL PROBES/FACES/UNCHANGED LOWER/PREFIX BINDING ' + name, flush=True)
            counts = total(cp['completed'])
            r.require(counts == cp['accounting'] and set(checks) == set(cp['completed']), 'Complete accounting differs')
            r.require(weighted['oldpath']['selected_point_file_path_records'] == 37650
                and weighted['independent']['selected_point_file_path_records'] == 32449, 'All original uncertain edge points required')
            accepted = {'time': r.now(), 'status': 'all_witness_upper_candidates_independently_checked_not_merged_or_promoted',
                'accounting': counts, 'weighted_path_records_not_unique_or_independent_samples': weighted, 'checks': checks,
                'all_original_lower_bytes_exact_unchanged_and_complete_existing_prefix_coverage_reused': True,
                'no_pre_lower_exclusion_recomputed': True, 'internal_probe_low_never_scientific_lower': True,
                'not_monotonicity_or_globally_earliest_witness_search': True, 'truth_asset_promotion_allowed': False,
                'full_merge_all57projections_and_updated_census_required': True, 'original_assets_predictions_scores_unchanged': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'all_label_dependent_claims_withheld': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex, 'not_formal_ODE_or_real_vehicle_certificate': True}
            r.freeze(RUN / 'acceptance.json', r.encoded(accepted))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261022-0000-v22-whole-witness-upper-candidates-closed',
        'stage_status': 'all_upper_candidates_independently_closed_not_merged', 'scientific_acceptance_exists': True,
        'candidate_accounting': counts, 'next_action': 'new frozen exact merge / all57original-order projections / whole updated census; all unwitnessed unknowns and full expanded populations still required'}
    report = ('# Whole Witness Upper Candidates\n\n'
        'Every current witnessed uncertain-edge path point, including initial zero-width and spatial-rule-failing cases. '
        'All original scientific lower bytes unchanged; all existing full prefix proofs bound and exactly reused. '
        'Every probe independently replayed with scalar trigonometry and GEOS; failed witness probes are not exclusions. '
        'Candidates only: not merged, not promoted, no score or prediction repair, no global earliest-witness claim.\n\n'
        + str(counts) + '\n\n' + str(weighted) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'execution_after': after, 'mutex_reacquired_and_released': released})),
        (CLOSED_PLAN, r.encoded(plan)), (ROOT / 'reports/witness_upper_candidates_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='whole_witness_upper_candidates_closed_not_merged', pid=None, running_analysis=False,
        plan=str(CLOSED_PLAN), next_action=plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('ALL WITNESS UPPER CANDIDATES CLOSED NOT MERGED ' + str(counts), flush=True)


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
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=stderr, env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_admission_proof': True}))
    print('WITNESS UPPER CANDIDATES LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
