"""Exhausted-label refinement candidates; no promotion before new prefix proofs."""
from __future__ import annotations
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
sys.path.insert(0, str(ROOT / 'src_s4_label_unknown_census_20261022_v1'))
import census as prior
import budget_core as core
import numpy as np

base, r, p = prior.base, prior.r, prior.p
PARENT, POPULATION, AUTH = prior.RUN, prior.POPULATION, prior.AUTH
RUN = ROOT / 'runs/resume_20261022_0000_label_budget_refinement_v1'
PROTOCOL = ROOT / 'protocol_label_budget_refinement_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v11.json'
SESSION = AUTH / 'runtime_sessions/label_budget_refinement_launch_v1'
RESERVATION = 480 * 1024**2
PARENT_HASHES = {
    'checkpoint.json': '22865a60b87dff56edb9516e861e65d08fc6817595f163204a97a2eaea7628c8',
    'acceptance.json': '6dde6e54acaa0769d0ba18e6373851974ed5557d4e7d1f159edea6321fd4ca35',
    'close_receipt.json': '84dc0d0f9c8e2e8479f49e5053b7db3ba07f8dffedce583445cdbad2806a0fb1'}


def configure():
    prior.configure()
    r.RUN, r.RUN_CAP = RUN, 512 * 1024**2


configure()


def execution():
    try:
        return prior.execution()
    finally:
        configure()


def gate():
    r.require(core.TIME_RESOLUTION == base.TIME_RESOLUTION and core.TOLERANCE == base.TOLERANCE
              and core.SEED_BUDGET == base.EVALUATIONS, 'Original conditional-label policy must remain exact')
    prior.verify()
    for name, digest in PARENT_HASHES.items():
        r.require(r.file_hash(PARENT / name) == digest, 'Closed complete census changed')
    accepted = r.read(PARENT / 'acceptance.json')
    r.require(accepted['all_labels_times_and_predictions_unchanged'] is True
              and accepted['accounting']['complete_census_point_file_records'] == 53967, 'Complete closed census required')


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')}
    paths.update(PARENT / name for name in (*PARENT_HASHES, 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json'))
    return {path.relative_to(ROOT).as_posix(): r.file_hash(path) for path in sorted(paths)}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen budget-candidate dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Budget source snapshot differs')
    for rel, digest in r.read(RUN / 'parent_files_sha256.json').items():
        r.require(r.file_hash(PARENT / rel) == digest, 'Closed census asset changed')


def admit():
    gate()
    loaded, groups, assets = prior.admit()
    cp = r.read(PARENT / 'checkpoint.json')
    selection, weighted = {}, {'oldpath': 0, 'independent': 0}
    for key, ids in groups.items():
        xy, paths, combined = prior.label_views(assets[key])
        flags, scope = prior.core.classify(paths['oldpath'], paths['independent'], combined)
        saved, meta = base.read_arrays(PARENT / 'groups' / key)
        r.require(base.array_meta(saved) == base.array_meta(prior.core.group_payload(xy, paths, combined, flags, scope))
                  and r.file_hash(PARENT / 'groups' / key / 'result.json') == cp['completed'][key]['group']['result_sha256'],
                  'Full original census group binding differs')
        for tag, bit in (('oldpath', 32), ('independent', 64)):
            indices = core.selected_indices(paths[tag], flags, bit)
            if len(indices):
                selection[key + '__' + tag] = {'group': key, 'path': tag, 'union_indices': indices.tolist()}
        for dataset_id in ids:
            original, _ = base.read_arrays(POPULATION / 'datasets' / dataset_id)
            index = original['union_index']
            projected, _ = base.read_arrays(PARENT / 'datasets' / dataset_id)
            expected = prior.core.projection_payload(index, xy, loaded[dataset_id]['target']['xy'], flags, scope)
            r.require(base.array_meta(projected) == base.array_meta(expected)
                      and r.file_hash(PARENT / 'datasets' / dataset_id / 'result.json') == cp['completed'][key]['datasets'][dataset_id]['result_sha256'],
                      'All census original-order projections required')
            for tag in weighted:
                weighted[tag] += int(paths[tag]['budget_exhausted'][index].sum())
    r.require(weighted == {'oldpath': 2295, 'independent': 1669} and selection, 'Whole original exhausted population differs')
    return loaded, groups, assets, selection, weighted


def path_input(key, tag, loaded, groups, asset):
    for row in p.follow.paths_for(key, loaded, groups, asset):
        if row[0] == tag:
            return row[1:]
    raise RuntimeError('Unknown original path')


def prefixed(arrays, prefix):
    return {key[len(prefix):]: value for key, value in arrays.items() if key.startswith(prefix)}


def prepare():
    r.require(r.before_deadline() and not any(path.exists() for path in (RUN, PROTOCOL, PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Budget synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'all-exhausted-path-label-budget-candidates-v1', 'deadline': p.parent.DEADLINE_LOCAL,
            'parent': str(PARENT), 'parent_hashes': PARENT_HASHES,
            'selection': 'every and only raw per-path budget_exhausted bound to full census flags',
            'original_budget_point_file_records': {'oldpath': 2295, 'independent': 1669},
            'original_seed_budget': core.SEED_BUDGET, 'fixed_candidate_budget': core.REFINE_BUDGET,
            'time_resolution_s': core.TIME_RESOLUTION, 'tolerance_m': core.TOLERANCE,
            'conditional_label_time_resolution_unchanged_s': 1e-7,
            'existing_prefix_time_resolution_unchanged_s': 1e-8,
            'no_new_prefix_computation_in_this_stage': True,
            'submitted_block': 'one path original seed plus fixed refinement; cutoff checked before seed; drain submitted block',
            'original_corner_rule_m': .001, 'original_spatial_errors_and_full_paths_unchanged': True,
            'same_original_label_population_code_object': True, 'exact_original_seed_required_before_refinement': True,
            'new_candidate_prefix_proof_required': True, 'truth_asset_promotion_allowed': False,
            'no_original_labels_predictions_or_scores_overwritten': True,
            'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION, 'total_E_Z_cap_bytes': r.CAP,
            'Z_reserve_bytes': r.RESERVE, 'workers': 1, 'inflight': 1,
            'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v10.json'),
            'version': '20261022-0000-v11-label-budget-candidates', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'next_action': 'same frozen kernel, original exact seed then fixed higher-budget candidates; no promotion before new prefix proofs'}
        hashes = {path.relative_to(PARENT).as_posix(): r.file_hash(path) for path in sorted(PARENT.rglob('*')) if path.is_file()}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'parent_files_sha256.json', r.encoded(hashes)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
                [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('LABEL BUDGET CANDIDATES PREPARED; actual admission still pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'corrected_truth_revalidated_prediction_jobs': 0,
              'truth_asset_promotion_allowed': False, 'new_candidate_prefix_proof_required': True}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            print('BUDGET CANDIDATE PREFLIGHT: full inputs, conditional/prefix/census arrays', flush=True)
            loaded, groups, assets, selection, weighted = admit()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'input_files': len(loaded),
                'geometry_groups': len(groups), 'selection': selection, 'weighted_original_budget_counts': weighted,
                'execution': idle, 'mutex': mutex}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='label_budget_candidates_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'),
                input_worker_admitted=True, input_worker_admission_pending=False)
            r.mutable(ROOT / 'active_research_run.json', active)
            print('BUDGET PREFLIGHT PASSED ALL 57 INPUTS / 39 GROUPS / FULL CENSUS / ALL EXHAUSTED PATH POINTS', flush=True)
            cp['planned_paths'] = list(selection)
            for name, spec in selection.items():
                r.require(r.before_deadline(), 'New budget-candidate path submission cutoff')
                key, tag = spec['group'], spec['path']
                indices = np.asarray(spec['union_indices'], np.int64)
                xy = assets[key][0]['xy'][indices]
                time, state, error, vehicle, original_path = path_input(key, tag, loaded, groups, assets[key])
                original = {field: values[indices] for field, values in original_path.items()}
                print('START ORIGINAL SEED ' + name + ' points=' + str(len(indices)), flush=True)
                seed = core.compute(base.label_population, xy, time, state, error, vehicle, core.SEED_BUDGET)
                seed_arrays = {'union_index': indices, 'xy': xy}
                seed_arrays.update({'original__' + field: values for field, values in original.items()})
                seed_arrays.update({'seed__' + field: values for field, values in seed.items()})
                folder = RUN / 'paths' / name
                exact = base.array_meta(seed) == base.array_meta(original)
                seed_entry = base.save_arrays(folder / 'seed', seed_arrays,
                    {'summary': {'points': len(indices), 'all_original_arrays_exact': exact}, 'selection': spec})
                cp['current_seed'] = {'name': name, 'entry': seed_entry}
                r.checkpoint(cp)
                r.require(exact, 'Original seed mismatch saved; no higher-budget propagation')
                print('START FIXED HIGHER BUDGET ' + name, flush=True)
                refined = core.compute(base.label_population, xy, time, state, error, vehicle, core.REFINE_BUDGET)
                summary = core.summarize(original, refined)
                arrays = {'union_index': indices, 'xy': xy,
                    'original_full_budget_mask_packbits': np.packbits(original_path['budget_exhausted'], bitorder='little'),
                    'any_changed_packbits': np.packbits(core.changed_points(original, refined), bitorder='little')}
                arrays.update({'refined__' + field: values for field, values in refined.items()})
                entry = base.save_arrays(folder, arrays, {'summary': summary, 'selection': spec,
                    'seed_result_sha256': seed_entry['result_sha256'], 'spatial_error_m': float(error),
                    'parent_group_result_sha256': r.file_hash(POPULATION / 'groups' / key / 'result.json'),
                    'new_candidate_prefix_proof_required': True, 'truth_asset_promotion_allowed': False})
                cp['completed'][name] = entry
                cp.pop('current_seed')
                r.checkpoint(cp)
                print('DONE FIXED BUDGET CANDIDATE ' + name + ' remaining_budget=' + str(summary['remaining_budget_points']), flush=True)
            cp['status'] = 'complete_pending_independent_candidate_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('BUDGET CANDIDATE WORKER EXITING; independent close and new prefix proofs still pending', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted close or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_candidate_close'
                  and set(cp['completed']) == set(cp['planned_paths']), 'Incomplete candidate batch')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, selection, weighted = admit()
            r.require(set(cp['completed']) == set(selection), 'Every and only exhausted path required')
            checks = []
            for name, spec in selection.items():
                key, tag = spec['group'], spec['path']
                indices = np.asarray(spec['union_indices'], np.int64)
                xy = assets[key][0]['xy'][indices]
                time, state, error, vehicle, original_path = path_input(key, tag, loaded, groups, assets[key])
                original = {field: value[indices] for field, value in original_path.items()}
                folder = RUN / 'paths' / name
                arrays, saved = base.read_arrays(folder)
                seed, seed_meta = base.read_arrays(folder / 'seed')
                expected_seed = {'union_index': indices, 'xy': xy}
                expected_seed.update({'original__' + field: value for field, value in original.items()})
                expected_seed.update({'seed__' + field: value for field, value in original.items()})
                r.require(base.array_meta(seed) == base.array_meta(expected_seed)
                          and seed_meta['summary']['all_original_arrays_exact'] is True
                          and seed_meta['selection'] == spec, 'Full exact original seed differs')
                refined = prefixed(arrays, 'refined__')
                summary = core.summarize(original, refined)
                expected = {'union_index': indices, 'xy': xy,
                    'original_full_budget_mask_packbits': np.packbits(original_path['budget_exhausted'], bitorder='little'),
                    'any_changed_packbits': np.packbits(core.changed_points(original, refined), bitorder='little')}
                expected.update({'refined__' + field: value for field, value in refined.items()})
                r.require(base.array_meta(arrays) == base.array_meta(expected)
                          and saved['selection'] == spec and saved['summary'] == cp['completed'][name]['summary'] == summary
                          and r.file_hash(folder / 'result.json') == cp['completed'][name]['result_sha256']
                          and saved['seed_result_sha256'] == r.file_hash(folder / 'seed/result.json')
                          and saved['spatial_error_m'] == float(error)
                          and saved['parent_group_result_sha256'] == r.file_hash(POPULATION / 'groups' / key / 'result.json')
                          and saved['new_candidate_prefix_proof_required'] is True
                          and saved['truth_asset_promotion_allowed'] is False, 'Candidate/source/boundary binding differs')
                geometry = base.validate_path(xy, time, state, refined, error, vehicle)
                checks.append({'name': name, 'selection': spec, 'summary': summary, 'independent_GE0S': geometry})
            accepted = {'time': r.now(), 'status': 'budget_refinement_candidates_checked_not_promoted',
                'checks': checks, 'weighted_original_budget_counts': weighted,
                'new_candidate_prefix_proof_required': True, 'truth_asset_promotion_allowed': False,
                'all_original_assets_and_predictions_unchanged': True, 'all_label_dependent_claims_withheld': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex}
            r.freeze(RUN / 'acceptance.json', r.encoded(accepted))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    next_plan = {**r.read(PLAN), 'version': '20261022-0000-v12-budget-candidates-closed-not-promoted',
        'stage_status': 'conditional_budget_candidates_closed_new_prefix_and_merge_proofs_required',
        'next_action': 'new first-contact prefix proof all refined path points, exact full merges and projections; then every remaining unknown and expanded population'}
    report = ('# Fixed Budget Refinement Candidates\n\nEvery and only original exhausted path point; '
        'same frozen label kernel, exact original 2048-budget seed, fixed 131072 candidate budget, '
        'original time resolution, space error, tolerance and corner rule unchanged. '
        'Independent GEOS witnesses/finite faces/noncontact checks completed, but new first-contact prefix '
        'proofs, all merges and original-order projections are still required. Candidates are not promoted '
        'truth, not repaired scores, not new independent prediction samples. All prior assets retained.\n\n'
        + '\n'.join(str(row) for row in checks) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v12.json', r.encoded(next_plan)),
        (ROOT / 'reports/label_budget_refinement_candidates_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='label_budget_candidates_closed_not_promoted', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v12.json'), next_action=next_plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('BUDGET CANDIDATES CLOSED; no promotion before new prefix and full merge proofs', flush=True)


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
    print('LABEL BUDGET CANDIDATES LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
