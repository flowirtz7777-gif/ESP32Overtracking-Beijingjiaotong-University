"""Lossless continuation of full candidate prefixes, preserving the failed v1."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import traceback
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'
import numpy as np
sys.path.insert(0, str(ROOT / 'src_s4_candidate_prefix_20261022_v1'))
import candidate_driver as previous
import compact_io as storage

base, r, core = previous.base, previous.r, previous.core
PARENT, FAILED, AUTH = previous.PARENT, previous.RUN, previous.AUTH
RUN = ROOT / 'runs/resume_20261022_0000_candidate_prefix_v2'
PROTOCOL = ROOT / 'protocol_candidate_prefix_20261022_0000_v2.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v15.json'
SESSION = AUTH / 'runtime_sessions/candidate_prefix_launch_v2'
FAILED_CP = '5bcdd75a5a9de62961e39cdffebf80e590b002c1612f44ddbe286be7ad47b484'
FAILED_FILES = AUTH / 'runtime_sessions/candidate_prefix_resource_stop_v1/all_stopped_run_files_sha256.json'
RESERVATION = 480 * 1024**2


def configure():
    previous.configure()
    r.RUN, r.RUN_CAP = RUN, 512 * 1024**2


configure()


def execution():
    try:
        return previous.execution()
    finally:
        configure()


def gate():
    previous.verify()
    previous.gate()
    r.require(r.file_hash(FAILED / 'checkpoint.json') == FAILED_CP, 'Stopped v1 CP changed')
    cp = r.read(FAILED / 'checkpoint.json')
    r.require(cp['status'] == 'stopped_failure_or_deadline' and len(cp['completed']) == 32
              and len(cp['planned_paths']) == 78 and 'Resource admission failed' in cp['failure']
              and not (FAILED / 'acceptance.json').exists() and not (FAILED / 'close_receipt.json').exists(),
              'Only complete saved v1 blocks may be reused; incomplete v1 cannot close')
    return cp


def signature():
    paths = {ROOT / rel for rel in r.read(FAILED / 'source_manifest.json')}
    paths.update(FAILED / name for name in ('checkpoint.json', 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json', FAILED_FILES))
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Lossless continuation source dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Frozen source snapshot differs')
    frozen_files = r.read(RUN / 'failed_v1_files_sha256.json')
    r.require(frozen_files == r.read(FAILED_FILES), 'Stopped full v1 inventory differs')
    r.require({p.relative_to(FAILED).as_posix() for p in FAILED.rglob('*') if p.is_file()} == set(frozen_files),
              'Stopped v1 file inventory gained or lost files')
    for rel, digest in frozen_files.items():
        r.require(r.file_hash(FAILED / rel) == digest, 'Original failed v1 file changed: ' + rel)


def bound_path_audit():
    namespace = dict(previous.run_path.__globals__)
    namespace.update(RUN=RUN, base=types.SimpleNamespace(save_arrays=storage.save_arrays))
    fn = types.FunctionType(previous.run_path.__code__, namespace, previous.run_path.__name__,
                            previous.run_path.__defaults__, previous.run_path.__closure__)
    r.require(fn.__code__ is previous.run_path.__code__, 'Scientific path code object changed')
    return fn


def check_binding(name, spec, candidate, arrays, saved, *, independently):
    xy, indices, time, state, error, vehicle, refined = candidate
    r.require(saved['selection'] == spec and saved['candidate_result_sha256'] ==
              r.file_hash(PARENT / 'paths' / name / 'result.json') and saved['spatial_error_m'] == float(error)
              and saved['truth_asset_promotion_allowed'] is False and len(saved['rows']) == len(xy),
              'Full candidate path/source binding differs')
    broad = core.boxes(time, state, vehicle)
    conservative = core.independent_boxes(state, vehicle, broad) if independently else broad
    expected = {'union_index': indices, 'xy': xy, 'candidate_lower_s': refined['contact_lower_s'],
                'original_time': time, **{'broad__' + k: v for k, v in broad.items()}}
    for i, point in enumerate(xy):
        proof = previous.parent.prefixed(arrays, str(i) + '__')
        expected.update({str(i) + '__' + k: v for k, v in proof.items()})
        if independently:
            core.validate(point, time, state, refined['contact_lower_s'][i], error, vehicle,
                          conservative, proof, saved['rows'][i])
    r.require(base.array_meta(arrays) == base.array_meta(expected), 'Every original index/coordinate/endpoint/broadphase field differs')
    counts = {status: sum(row['status'] == status for row in saved['rows'])
              for status in ('excluded', 'unknown_time_leaf', 'unknown_budget', 'early_contact_witness')}
    summary = {'planned_points': len(xy), 'processed_points': len(xy), 'counts': counts,
        'GEOS_evaluations': sum(row['GEOS_evaluations'] for row in saved['rows']),
        'strict_prefix_gate_passed': counts['excluded'] == len(xy)}
    r.require(summary == saved['summary'] and counts['early_contact_witness'] == 0, 'Changed accounting or early-contact counterexample')
    return summary


def admit():
    cp = gate()
    loaded, groups, selection, candidates = previous.admit()
    reused = [name for name in selection if name in cp['completed']]
    new = [name for name in selection if name not in cp['completed']]
    r.require(len(reused) == 32 and len(new) == 46 and set(cp['planned_paths']) == set(selection), 'Whole fixed partition required')
    for name in reused:
        arrays, record = base.read_arrays(FAILED / 'paths' / name)
        r.require(r.file_hash(FAILED / 'paths' / name / 'result.json') == cp['completed'][name]['result_sha256']
                  and record['summary'] == cp['completed'][name]['summary'], 'Stopped CP/report binding differs')
        check_binding(name, selection[name], candidates[name], arrays, record, independently=False)
    return loaded, groups, selection, candidates, reused, new


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Lossless continuation tests failed: ' + tests.stderr)
        protocol = {**r.read(previous.PROTOCOL), 'version': 'lossless-all-candidate-prefix-continuation-v2',
            'deadline': r.read(AUTH / 'authorization.json')['deadline'],
            'failed_v1': str(FAILED), 'failed_v1_checkpoint_sha256': FAILED_CP,
            'complete_saved_paths_reused': 32, 'new_path_blocks_only': 46,
            'no_recomputation_of_reused_prefix_points': True,
            'compression': 'RAM gzip metadata, exact original JSON bytes roundtrip; original NPZ bytes copied exactly',
            'same_v1_path_audit_code_object_new_namespace_only': True,
            'all_v1_original_files_preserved': True, 'full_independent_geometry_close_all_78': True,
            'truth_asset_promotion_allowed': False, 'full_merge_projection_and_updated_census_required': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v14.json'),
            'version': '20261022-0000-v15-lossless-candidate-prefix', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'strict_all_candidate_prefix_gate_passed': None,
            'new_version_required': False, 'complete_path_blocks': 0, 'planned_path_blocks': 78,
            'exact_reuse_path_blocks_planned': 32, 'new_path_blocks_planned': 46,
            'next_action': 'reuse every saved v1 proof exactly; compute 46 remaining blocks only; independently close all 78'}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'failed_v1_files_sha256.json', FAILED_FILES.read_bytes()),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))]
                + [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('LOSSLESS CANDIDATE PREFIX PREPARED; actual full-input admission still pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'exact_reused_paths': [], 'new_audited_paths': [],
              'source_signature': signature(), 'truth_asset_promotion_allowed': False,
              'corrected_truth_revalidated_prediction_jobs': 0}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, selection, candidates, reused, new = admit()
            cp['planned_paths'] = list(selection)
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'selection': selection,
                'input_files': len(loaded), 'groups': len(groups), 'group_path_points': 3507,
                'reuse_paths': reused, 'new_paths': new, 'all_parent_candidates_and_v1_proofs_fully_decoded': True,
                'execution': idle, 'mutex': mutex, 'resources': r.guard(RESERVATION, RESERVATION)}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='candidate_prefix_lossless_v2_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                running_predictions=False, input_worker_admitted=True, input_worker_admission_pending=False,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'))
            r.mutable(ROOT / 'active_research_run.json', active)
            print('LOSSLESS PREFIX PREFLIGHT PASSED ALL 57 INPUTS / 39 GROUPS / 78 PATHS / 32 EXACT REUSE / NEW 46', flush=True)
            for name in reused:
                r.require(r.before_deadline(), 'No new reuse block after cutoff')
                cp['completed'][name] = storage.reuse(RUN / 'paths' / name, FAILED / 'paths' / name)
                cp['exact_reused_paths'].append(name)
                r.checkpoint(cp)
                print('DONE EXACT PROOF REUSE ' + name, flush=True)
            audit = bound_path_audit()
            for name in new:
                r.require(r.before_deadline(), 'No new candidate prefix path block after cutoff')
                verify()
                print('START NEW LOSSLESS PREFIX ' + name, flush=True)
                cp['completed'][name] = audit(name, selection[name], candidates[name])
                cp['new_audited_paths'].append(name)
                r.checkpoint(cp)
                print('DONE NEW LOSSLESS PREFIX ' + name + ' ' + str(cp['completed'][name]['summary']), flush=True)
                r.require(cp['completed'][name]['summary']['counts']['early_contact_witness'] == 0,
                          'Full early-contact counterexample saved; stop propagation')
            cp['status'] = 'complete_pending_independent_prefix_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('LOSSLESS PREFIX WORKER EXITING; full independent close still required', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_prefix_close'
                  and set(cp['completed']) == set(cp['planned_paths']) and len(cp['exact_reused_paths']) == 32
                  and len(cp['new_audited_paths']) == 46, 'Incomplete continuation batch')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, selection, candidates, reused, new = admit()
            r.require(set(cp['completed']) == set(selection) and cp['exact_reused_paths'] == reused
                      and cp['new_audited_paths'] == new, 'Every reused/new path required exactly once')
            checks = []
            for name, spec in selection.items():
                folder = RUN / 'paths' / name
                arrays, saved = storage.read_arrays(folder)
                r.require(r.file_hash(folder / 'result.json') == cp['completed'][name]['result_sha256']
                          and saved['summary'] == cp['completed'][name]['summary'], 'Full output CP binding differs')
                if name in reused:
                    raw, _ = storage.decode_record(r.read(folder / 'result.json'), (folder / 'metadata.json.gz').read_bytes())
                    r.require(raw == (FAILED / 'paths' / name / 'result.json').read_bytes()
                              and r.file_hash(folder / 'arrays.npz') == r.file_hash(FAILED / 'paths' / name / 'arrays.npz'),
                              'Any changed original proof quantity forbids reuse')
                summary = check_binding(name, spec, candidates[name], arrays, saved, independently=True)
                xy, indices, time, state, error, vehicle, refined = candidates[name]
                geometry = base.validate_path(xy, time, state, refined, error, vehicle)
                checks.append({'name': name, 'origin': 'exact_v1_full_proof' if name in reused else 'new_v2_path',
                               'summary': summary, 'independent_GE0S': geometry})
                print('CLOSE CHECKED FULL PATH ' + name, flush=True)
            strict = all(row['summary']['strict_prefix_gate_passed'] for row in checks)
            value = {'time': r.now(), 'status': 'all_candidate_prefixes_losslessly_reused_or_generated_and_independently_checked',
                'strict_all_candidate_prefix_gate_passed': strict, 'checks': checks, 'exact_reused_paths': 32,
                'new_audited_paths': 46, 'group_path_points': 3507, 'truth_asset_promotion_allowed': False,
                'full_merge_projection_and_updated_census_required': True, 'original_assets_predictions_scores_unchanged': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'failed_v1_checkpoint_sha256': FAILED_CP,
                'source_signature': signature(), 'execution': idle, 'mutex': mutex}
            r.freeze(RUN / 'acceptance.json', r.encoded(value))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261022-0000-v16-lossless-candidate-prefix-closed',
        'stage_status': 'candidate_prefix_v2_closed_not_merged', 'strict_all_candidate_prefix_gate_passed': strict,
        'strict_all_point_prefix_gate_passed': strict,
        'scientific_acceptance_exists': True, 'scientific_acceptance_scope': 'candidate full prefixes only, no truth promotion',
        'complete_path_blocks': 78,
        'next_action': 'new version exact full merges/combined edge sets/all original-order projections/updated census; retain every remaining unknown'}
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(), 'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'),
        'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'), 'execution_after': after,
        'mutex_reacquired_and_released': released})), (ROOT / 'resume_plan_20261022_0000_v16.json', r.encoded(plan)),
        (ROOT / 'reports/candidate_prefix_lossless_20261022_0000_v2.md', ('# Lossless Candidate Prefix Continuation\n\n'
        '32 original full proof bytes reused, 46 new paths only; all 78 independently checked. Strict candidate prefix gate: '
        + str(strict) + '. No truth merge/promotion or repaired score claims. Every unknown retained.\n').encode('utf-8'))])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='candidate_prefix_lossless_v2_closed_not_merged', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v16.json'), next_action=plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('LOSSLESS CANDIDATE PREFIX CLOSED; strict gate=' + str(strict) + '; complete merge still pending', flush=True)


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
    print('LOSSLESS CANDIDATE PREFIX LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
