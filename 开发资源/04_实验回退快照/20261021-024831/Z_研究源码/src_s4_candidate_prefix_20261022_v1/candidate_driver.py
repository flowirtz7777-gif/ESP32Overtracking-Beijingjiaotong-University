"""Candidate-only full prefixes; no label merge or score promotion here."""
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
import numpy as np
sys.path.insert(0, str(ROOT / 'src_s4_label_budget_refinement_20261022_v1'))
import budget as parent
import candidate_core as core

base, r, AUTH = parent.base, parent.r, parent.AUTH
PARENT = parent.RUN
RUN = ROOT / 'runs/resume_20261022_0000_candidate_prefix_v1'
PROTOCOL = ROOT / 'protocol_candidate_prefix_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v13.json'
SESSION = AUTH / 'runtime_sessions/candidate_prefix_launch_v1'
RESERVATION = 480 * 1024**2
PARENT_HASHES = {
    'checkpoint.json': '06196609ac9249b74d03b065ba8d31f0694b9a1c3409156342c4115c8b386297',
    'acceptance.json': 'ac45b663f2a2ee84a676bebb53cbbedb221d48ad55d53a8a03e91b256347e14c',
    'close_receipt.json': '8ae55d83230b319429835b7026ff80e4e68b7d8ac0f0f7b5341ef41a717752b1'}


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
    for name, digest in PARENT_HASHES.items():
        r.require(r.file_hash(PARENT / name) == digest, 'Closed candidate parent changed')
    a = r.read(PARENT / 'acceptance.json')
    r.require(a['truth_asset_promotion_allowed'] is False and a['new_candidate_prefix_proof_required'] is True
              and len(a['checks']) == 78 and a['all_original_assets_and_predictions_unchanged'] is True,
              'Whole closed candidate population required')


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')}
    paths.update(PARENT / name for name in (*PARENT_HASHES, 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json'))
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Candidate prefix frozen source dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Frozen source copy changed')
    for rel, digest in r.read(RUN / 'parent_files_sha256.json').items():
        r.require(r.file_hash(PARENT / rel) == digest, 'Stopped candidate asset changed')


def admit():
    gate()
    loaded, groups, assets, selection, weighted = parent.admit()
    cp = r.read(PARENT / 'checkpoint.json')
    accepted = {row['name']: row for row in r.read(PARENT / 'acceptance.json')['checks']}
    r.require(set(selection) == set(cp['completed']) == set(accepted), 'Full parent selection differs')
    candidates = {}
    for name, spec in selection.items():
        key, tag = spec['group'], spec['path']
        indices = np.asarray(spec['union_indices'], np.int64)
        xy = assets[key][0]['xy'][indices]
        time, state, error, vehicle, raw = parent.path_input(key, tag, loaded, groups, assets[key])
        original = {k: v[indices] for k, v in raw.items()}
        folder = PARENT / 'paths' / name
        arrays, saved = base.read_arrays(folder)
        seed, seed_meta = base.read_arrays(folder / 'seed')
        expected_seed = {'union_index': indices, 'xy': xy}
        expected_seed.update({'original__' + k: v for k, v in original.items()})
        expected_seed.update({'seed__' + k: v for k, v in original.items()})
        r.require(base.array_meta(seed) == base.array_meta(expected_seed)
                  and seed_meta['selection'] == spec and seed_meta['summary']['all_original_arrays_exact'] is True,
                  'Every original seed quantity must remain exact')
        refined = parent.prefixed(arrays, 'refined__')
        summary = parent.core.summarize(original, refined)
        expected = {'union_index': indices, 'xy': xy,
            'original_full_budget_mask_packbits': np.packbits(raw['budget_exhausted'], bitorder='little'),
            'any_changed_packbits': np.packbits(parent.core.changed_points(original, refined), bitorder='little')}
        expected.update({'refined__' + k: v for k, v in refined.items()})
        r.require(base.array_meta(arrays) == base.array_meta(expected) and saved['selection'] == spec
                  and saved['summary'] == cp['completed'][name]['summary'] == accepted[name]['summary'] == summary
                  and accepted[name]['selection'] == spec
                  and r.file_hash(folder / 'result.json') == cp['completed'][name]['result_sha256']
                  and saved['seed_result_sha256'] == r.file_hash(folder / 'seed/result.json')
                  and saved['spatial_error_m'] == float(error)
                  and saved['parent_group_result_sha256'] == r.file_hash(parent.POPULATION / 'groups' / key / 'result.json'),
                  'Full candidate/seed/parent binding differs')
        candidates[name] = (xy, indices, time, state, error, vehicle, refined)
    r.require(len(candidates) == 78 and sum(len(row[0]) for row in candidates.values()) == 3507,
              'All 3507 candidate path points required, not outcome selection')
    return loaded, groups, selection, candidates


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PLAN, PROTOCOL)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        test = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(test.returncode == 0, 'Synthetic candidate prefix tests failed: ' + test.stderr)
        protocol = {'version': 'all-budget-candidate-sparse-hull-full-prefix-v1', 'deadline': r.read(AUTH / 'authorization.json'),
            'parent': str(PARENT), 'parent_hashes': PARENT_HASHES, 'path_blocks': 78, 'group_path_points': 3507,
            'selection': 'every and only closed budget candidate union_index, both paths, including unchanged bounds',
            'finite_lower_endpoint_unchanged': True, 'NaN_lower_means_full_original_path': True,
            'broadphase': 'full original interval endpoint-corner AABB plus full-span chord bound, spatial error, 1e-12 guard; strict positive only',
            'narrowphase': 'unchanged frozen hull.audit_point and independent_geometry for each selected original interval, chronological',
            'fixed_GE0S_budget_per_selected_original_interval': core.INTERVAL_BUDGET,
            'budget_accounting_scope_not_per_point': True, 'time_resolution_s': core.RESOLUTION,
            'tolerance_m': core.TOLERANCE, 'corner_rule_m': .001, 'spatial_errors_not_reduced': True,
            'unknowns_and_all_tree_nodes_saved': True, 'early_witness_saved_then_stop': True,
            'submitted_block': 'one complete candidate path; cutoff before each new path; drain submitted path',
            'truth_asset_promotion_allowed': False, 'full_merge_projection_and_updated_census_required': True,
            'workers': 1, 'inflight': 1, 'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION,
            'total_E_Z_cap_bytes': r.CAP, 'Z_reserve_bytes': r.RESERVE,
            'not_formal_ODE_or_real_vehicle_certificate': True, 'corrected_truth_revalidated_prediction_jobs': 0}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v12.json'),
            'version': '20261022-0000-v13-budget-candidate-prefix', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'strict_all_point_prefix_gate_passed': None, 'original_baseline_prefix_gate_passed': True,
            'next_action': 'all candidate full-prefix proofs; then independently close; exact full merge and projections still pending'}
        hashes = {p.relative_to(PARENT).as_posix(): r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'parent_files_sha256.json', r.encoded(hashes)), (RUN / 'prelaunch.json', r.encoded({
                'time': r.now(), 'execution': idle, 'mutex': mutex, 'tests_stdout': test.stdout,
                'tests_stderr': test.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))]
                + [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('CANDIDATE PREFIX PREPARED; actual full input admission still required', flush=True)


def run_path(name, spec, candidate):
    xy, indices, time, state, error, vehicle, refined = candidate
    broad = core.boxes(time, state, vehicle)
    output = {'union_index': indices, 'xy': xy, 'candidate_lower_s': refined['contact_lower_s'],
              'original_time': time, **{'broad__' + k: v for k, v in broad.items()}}
    rows = []
    for i, point in enumerate(xy):
        proof, summary = core.audit(point, time, state, refined['contact_lower_s'][i], error, vehicle, broad)
        output.update({str(i) + '__' + field: value for field, value in proof.items()})
        rows.append(summary)
        if summary['status'] == 'early_contact_witness':
            break
    counts = {status: sum(row['status'] == status for row in rows)
              for status in ('excluded', 'unknown_time_leaf', 'unknown_budget', 'early_contact_witness')}
    summary = {'planned_points': len(xy), 'processed_points': len(rows), 'counts': counts,
        'GEOS_evaluations': sum(row['GEOS_evaluations'] for row in rows),
        'strict_prefix_gate_passed': len(rows) == len(xy) and counts['excluded'] == len(xy)}
    return base.save_arrays(RUN / 'paths' / name, output, {'selection': spec, 'rows': rows, 'summary': summary,
        'candidate_result_sha256': r.file_hash(PARENT / 'paths' / name / 'result.json'),
        'spatial_error_m': float(error), 'truth_asset_promotion_allowed': False})


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'source_signature': signature(),
              'truth_asset_promotion_allowed': False, 'corrected_truth_revalidated_prediction_jobs': 0}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, selection, candidates = admit()
            cp['planned_paths'] = list(selection)
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'selection': selection,
                'input_files': len(loaded), 'groups': len(groups), 'group_path_points': 3507,
                'all_parent_candidates_and_seeds_fully_decoded': True, 'execution': idle, 'mutex': mutex,
                'resources': r.guard(RESERVATION, RESERVATION)}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='candidate_prefix_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                running_predictions=False, input_worker_admitted=True, input_worker_admission_pending=False,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'))
            r.mutable(ROOT / 'active_research_run.json', active)
            print('CANDIDATE PREFIX PREFLIGHT PASSED ALL 57 INPUTS / 39 GROUPS / 78 PATHS / ALL 3507 CANDIDATES', flush=True)
            for name, spec in selection.items():
                r.require(r.before_deadline(), 'No new candidate prefix path block after cutoff')
                verify()
                print('START CANDIDATE PREFIX ' + name, flush=True)
                cp['completed'][name] = run_path(name, spec, candidates[name])
                r.checkpoint(cp)
                s = cp['completed'][name]['summary']
                print('DONE CANDIDATE PREFIX ' + name + ' ' + str(s), flush=True)
                r.require(s['counts']['early_contact_witness'] == 0, 'Early-contact counterexample saved; stop')
            cp['status'] = 'complete_pending_independent_prefix_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('CANDIDATE PREFIX WORKER EXITING; independent close and full merge still pending', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_prefix_close'
                  and set(cp['completed']) == set(cp['planned_paths']), 'Incomplete candidate prefix batch')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, selection, candidates = admit()
            r.require(set(cp['completed']) == set(selection), 'Whole candidate scope required')
            checks = []
            for name, spec in selection.items():
                xy, indices, time, state, error, vehicle, refined = candidates[name]
                arrays, saved = base.read_arrays(RUN / 'paths' / name)
                r.require(saved['selection'] == spec and saved['summary'] == cp['completed'][name]['summary']
                          and r.file_hash(RUN / 'paths' / name / 'result.json') == cp['completed'][name]['result_sha256']
                          and saved['candidate_result_sha256'] == r.file_hash(PARENT / 'paths' / name / 'result.json')
                          and saved['spatial_error_m'] == float(error) and len(saved['rows']) == len(xy), 'Full source/result binding differs')
                broad = core.boxes(time, state, vehicle)
                conservative_broad = core.independent_boxes(state, vehicle, broad)
                expected = {'union_index': indices, 'xy': xy, 'candidate_lower_s': refined['contact_lower_s'],
                    'original_time': time, **{'broad__' + k: v for k, v in broad.items()}}
                for i, point in enumerate(xy):
                    proof = parent.prefixed(arrays, str(i) + '__')
                    expected.update({str(i) + '__' + k: v for k, v in proof.items()})
                    core.validate(point, time, state, refined['contact_lower_s'][i], error, vehicle, conservative_broad, proof, saved['rows'][i])
                r.require(base.array_meta(expected) == base.array_meta(arrays), 'All original endpoints, indices and broadphase arrays differ')
                counts = {status: sum(row['status'] == status for row in saved['rows'])
                          for status in ('excluded', 'unknown_time_leaf', 'unknown_budget', 'early_contact_witness')}
                summary = {'planned_points': len(xy), 'processed_points': len(xy), 'counts': counts,
                    'GEOS_evaluations': sum(row['GEOS_evaluations'] for row in saved['rows']),
                    'strict_prefix_gate_passed': counts['excluded'] == len(xy)}
                r.require(summary == saved['summary'] and counts['early_contact_witness'] == 0, 'Prefix classification differs or counterexample exists')
                geometry = base.validate_path(xy, time, state, refined, error, vehicle)
                checks.append({'name': name, 'summary': summary, 'independent_GE0S': geometry})
            strict = all(row['summary']['strict_prefix_gate_passed'] for row in checks)
            a = {'time': r.now(), 'status': 'all_budget_candidate_prefixes_independently_checked_not_merged',
                'strict_all_candidate_prefix_gate_passed': strict, 'checks': checks,
                'truth_asset_promotion_allowed': False, 'full_merge_projection_and_updated_census_required': True,
                'original_assets_predictions_scores_unchanged': True, 'corrected_truth_revalidated_prediction_jobs': 0,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex, 'not_formal_ODE_or_real_vehicle_certificate': True}
            r.freeze(RUN / 'acceptance.json', r.encoded(a))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261022-0000-v14-candidate-prefix-closed',
        'stage_status': 'candidate_prefix_closed_not_merged', 'strict_all_point_prefix_gate_passed': strict,
        'next_action': 'if candidate prefix gate passes, new version exact full merges/projections/census; otherwise all unknowns retained'}
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(), 'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'),
        'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'), 'execution_after': after,
        'mutex_reacquired_and_released': released})), (ROOT / 'resume_plan_20261022_0000_v14.json', r.encoded(plan)),
        (ROOT / 'reports/candidate_prefix_20261022_0000_v1.md', ('# Candidate Full Prefixes\n\nStrict candidate prefix gate: '
        + str(strict) + '. Original finite/NaN lower endpoints, full paths, all spatial errors and tolerance unchanged. '
        'All omitted interval AABB bounds and all selected hull trees checked. No label merge, truth promotion or score repair.\n').encode('utf-8'))])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='candidate_prefix_closed_not_merged', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v14.json'), next_action=plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('CANDIDATE PREFIX CLOSED; strict gate=' + str(strict) + '; full merge still pending', flush=True)


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
    print('CANDIDATE PREFIX LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
