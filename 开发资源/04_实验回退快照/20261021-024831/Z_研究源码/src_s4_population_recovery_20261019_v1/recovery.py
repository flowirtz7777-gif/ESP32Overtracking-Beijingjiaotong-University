"""New-version population continuation; exact unchanged kernel, no old entrypoints."""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src_s4_prefix_completion_20261019_v2'))
import completion as follow
import numpy as np
base, r = follow.base, follow.r
PARENT = follow.old.OLD
AUDIT = follow.RUN
AUTH = follow.AUTH
RUN = ROOT / 'runs/resume_20261019_2400_population_recovery_v1'
PROTOCOL = ROOT / 'protocol_population_recovery_20261019_2400_v1.json'
PLAN = ROOT / 'resume_plan_20261019_2400_v3.json'
SESSION = AUTH / 'runtime_sessions/population_recovery_launch_v1'
RESERVATION = 480 * 1024**2


def configure():
    r.RUN, r.AUTH, r.RUN_CAP = RUN, AUTH, 512 * 1024**2
    r.DEADLINE = dt.datetime(2026, 10, 19, 16, tzinfo=dt.timezone.utc)


configure()


def execution():
    try:
        h, evidence = follow.execution()
    finally:
        configure()
    for p in RUN.glob('*runner_lock.json'):
        r.require(r.read(p)['status'] == 'stopped', 'Recovery worker/analysis still active')
    return h, evidence


def check_gate(value):
    r.require(value.get('strict_all_point_prefix_gate_passed') is True and
              value.get('generated_groups_audited') == 12 and value.get('generated_dataset_files') == 30,
              'All existing full-point prefix gates must pass before propagation')


def gate():
    follow.verify()
    value = r.read(AUDIT / 'acceptance.json')
    check_gate(value)
    r.require(value['source_signature'] == follow.signature(), 'Closed audit source differs')
    receipt = r.read(AUDIT / 'close_receipt.json')
    r.require(receipt['acceptance_sha256'] == r.file_hash(AUDIT / 'acceptance.json') and
              receipt['checkpoint_sha256'] == r.file_hash(AUDIT / 'checkpoint.json'), 'Closed audit receipt differs')
    return value


def bound_group_kernel(function=base.process_group, destination=RUN):
    # Only the output directory changes; the frozen numerical kernel/code remains identical.
    namespace = dict(function.__globals__, RUN=destination)
    return types.FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)


def partition(groups, completed):
    r.require(set(completed) <= set(groups), 'Reuse cannot add unknown groups')
    return [k for k in groups if k in completed], [k for k in groups if k not in completed]


def signature():
    paths = [ROOT / rel for rel in r.read(AUDIT / 'source_manifest.json')]
    paths += [*SOURCE.glob('*.py'), PROTOCOL, PLAN, AUDIT / 'acceptance.json', AUDIT / 'close_receipt.json',
        AUDIT / 'source_manifest.json', AUTH / 'authorization.json']
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(set(paths))}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Recovery frozen source/protocol differs')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Recovery source snapshot differs')
    for rel, digest in r.read(RUN / 'parent_files_sha256.json').items():
        r.require(r.file_hash(PARENT / rel) == digest, 'Preserved population file differs')


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN)), 'Prepared or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        cp = follow.old.verify_parent()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin',
            capture_output=True, encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Recovery tests failed: ' + tests.stderr)
        protocol = {**r.read(base.PROTOCOL), 'version': 'exact-reuse-and-missing-baseline-continuation-v1',
            'deadline': '2026-10-20T00:00:00+08:00', 'parent_run': str(PARENT),
            'parent_cp_sha256': follow.old.OLD_CP, 'reuse_complete_group_ids': list(cp['completed']),
            'strict_prefix_gate_acceptance_sha256': r.file_hash(AUDIT / 'acceptance.json'),
            'new_group_selection': 'every previously ungenerated geometry group in original fixed order',
            'numerical_kernel_code_unchanged_only_new_output_directory': True,
            'reuse_full_groups_and_original_order_dataset_outputs_without_recomputation': True,
            'no_new_experimental_sample_from_recovery': True, 'run_cap_bytes': r.RUN_CAP,
            'reservation_bytes': RESERVATION, 'new_groups_first_time_prefix_audit_still_required': True}
        plan = {**r.read(ROOT / 'resume_plan_20261019_2400_v2.json'),
            'version': '20261019-2400-v3-population-recovery', 'previous_plan': 'resume_plan_20261019_2400_v2.json',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'stage_status': 'prepared_not_admitted', 'next_action': 'actual full input admission, exact reuse 12 groups, generate missing groups only',
            'new_group_prefix_independent_audit_pending': True, 'scientific_remediation_complete': False}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'test_stdout': tests.stdout, 'test_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)})),
            (RUN / 'parent_files_sha256.json', r.encoded({p.relative_to(PARENT).as_posix(): r.file_hash(p)
                for p in PARENT.rglob('*') if p.is_file()}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
                [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
        active = r.read(ROOT / 'active_research_run.json')
        active.update(status='midnight_population_recovery_prepared', run_directory=str(RUN), protocol=str(PROTOCOL),
            plan=str(PLAN), entrypoint=str(Path(__file__)), pid=None, running_analysis=False, running_preflight=False,
            input_worker_admitted=False, input_worker_admission_pending=True,
            stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'), next_action=plan['next_action'])
        r.mutable(ROOT / 'active_research_run.json', active)
    print('POPULATION RECOVERY PREPARED; actual full input admission pending', flush=True)


def copy_complete_group(key, entry):
    paths = [PARENT / 'groups' / key / name for name in ('arrays.npz', 'result.json')]
    for dataset_id in entry['datasets']:
        paths += [PARENT / 'datasets' / dataset_id / name for name in ('arrays.npz', 'result.json')]
    payload = [(RUN / p.relative_to(PARENT), p.read_bytes()) for p in paths]
    r.batch(payload)
    for p, blob in payload:
        r.require(r.file_hash(p) == r.sha(blob), 'Exact reuse copy differs')
    return entry


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Run already attempted or cutoff')
    h, _ = execution()
    cp = {'status': 'preflight', 'completed': {}, 'exact_reused_groups': [], 'new_generated_groups': [],
        'new_predictions': 0, 'corrected_truth_revalidated_prediction_jobs': 0, 'source_signature': signature()}
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        gate()
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, prior_prefix = follow.load_all()
            matrix = base.specifications()
            r.require(matrix == r.read(PROTOCOL)['matrix'] and len(loaded) == 57, 'Original complete input matrix differs')
            parent_cp = follow.old.verify_parent()
            reused, missing = partition(groups, parent_cp['completed'])
            r.require(len(reused) == 12 and len(missing) == 27, 'Recovery must preserve every generated group and original remaining order')
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'python': sys.executable,
                'loaded_baseline_datasets': len(loaded), 'point_records': sum(v['spec']['count'] for v in loaded.values()),
                'groups': groups, 'reuse_groups': reused, 'missing_groups': missing,
                'all_existing_12_groups_and_30_projections_fully_decoded': True,
                'all_original_array_metadata': {k: {'target': base.array_meta(v['target']),
                    'trajectory': base.array_meta(v['trajectory'])} for k, v in loaded.items()},
                'accepted_prefix_sha256': r.file_hash(AUDIT / 'acceptance.json'),
                'execution': idle, 'mutex': mutex, 'resources': r.guard(RESERVATION, RESERVATION)}))
            print('RECOVERY PREFLIGHT PASSED ALL 57 ORIGINAL DATASETS; EXACT 12 GROUPS / MISSING 27 GROUPS', flush=True)
            for key in reused:
                r.require(r.before_deadline(), '24:00 new reuse block submission cutoff')
                remaining = max(0, RESERVATION - base.scan_size(RUN))
                r.guard(remaining, remaining)
                cp['completed'][key] = copy_complete_group(key, parent_cp['completed'][key])
                cp['exact_reused_groups'].append(key)
                # Full decode of copied files proves exact coordinate/array reuse, not just metadata identity.
                arrays, _ = base.read_arrays(RUN / 'groups' / key)
                r.require(base.array_meta(arrays) == base.array_meta(assets[key][0]), 'Every reused group array differs')
                for dataset_id in groups[key]:
                    new, _ = base.read_arrays(RUN / 'datasets' / dataset_id)
                    previous, _ = base.read_arrays(PARENT / 'datasets' / dataset_id)
                    r.require(base.array_meta(new) == base.array_meta(previous), 'Every reused original-order projection differs')
                r.checkpoint(cp)
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='midnight_population_recovery_running', pid=os.getpid(), running_analysis=True,
                input_worker_admission_pending=False, input_worker_admitted=True)
            r.mutable(ROOT / 'active_research_run.json', active)
            generate = bound_group_kernel()
            for key in missing:
                r.require(r.before_deadline(), '24:00 new population group submission cutoff')
                verify()
                remaining = max(0, RESERVATION - base.scan_size(RUN))
                r.guard(remaining, remaining)
                print('START MISSING POPULATION GROUP ' + key, flush=True)
                cp['completed'][key] = generate(key, groups[key], loaded)
                cp['new_generated_groups'].append(key)
                r.checkpoint(cp)
            cp['status'] = 'complete_pending_independent_acceptance'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('RECOVERY EXITING; corrected prediction jobs zero', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Already accepted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_acceptance', 'Not all baseline groups complete')
        loaded, groups = base.load_inputs(r.read(PROTOCOL)['matrix'])
        r.require(set(cp['completed']) == set(groups), 'Full 57-file matrix incomplete')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            rows, geometry = [], {}
            for key, ids in groups.items():
                arrays, record = base.read_arrays(RUN / 'groups' / key)
                r.require(r.file_hash(RUN / 'groups' / key / 'result.json') == cp['completed'][key]['group']['result_sha256'], 'Group CP/report differs')
                first = loaded[ids[0]]
                vehicle = base.common.Vehicle(**first['profile']['vehicle'])
                trajectory = first['trajectory']
                paths = {tag: {k.split('__', 1)[1]: v for k, v in arrays.items() if k.startswith(tag + '__')}
                    for tag in ('oldpath', 'independent')}
                combined = base.combine(paths['oldpath'], paths['independent'])
                r.require(base.array_meta(combined) == base.array_meta({k.split('__', 1)[1]: v for k, v in arrays.items()
                    if k.startswith('combined__')}), 'Complete paired combination differs')
                geometry[key] = {}
                for tag, time, state, error in (
                    ('oldpath', trajectory['fine_time'], trajectory['fine_state'], record['reference_meta']['old_path_spatial_envelope_m']),
                    ('independent', arrays['independent_time'], arrays['independent_state'], record['reference_meta']['independent_path_spatial_envelope_m'])):
                    geometry[key][tag] = base.validate_path(arrays['xy'], time, state, paths[tag], error, vehicle)
                for dataset_id in ids:
                    out, meta = base.read_arrays(RUN / 'datasets' / dataset_id)
                    r.require(r.file_hash(RUN / 'datasets' / dataset_id / 'result.json') == cp['completed'][key]['datasets'][dataset_id]['result_sha256'], 'Dataset CP/report differs')
                    target = loaded[dataset_id]['target']
                    index = out['union_index']
                    r.require(np.array_equal(arrays['xy'][index], target['xy']), 'Full coordinate order differs')
                    projected = {k: v[index] for k, v in combined.items()}
                    r.require(base.array_meta(projected) == base.array_meta({k.split('__', 1)[1]: v for k, v in out.items()
                        if k.startswith('combined__')}), 'Full per-point projection differs')
                    for name, mask in base.old_discrepancies(target, projected).items():
                        r.require(np.array_equal(np.unpackbits(out[name + '__packbits'], count=len(index), bitorder='little'), mask)
                            and int(mask.sum()) == meta['summary'][name], 'All change/unknown/conflict indices differ')
                    rows.append(meta['summary'])
            value = {'time': r.now(), 'status': 'all_57_conditional_assets_decoded_and_GE0S_checked_prefix_extension_pending',
                'rows': rows, 'geometry': geometry, 'new_group_prefix_audit_still_required': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'all_label_dependent_claims_withheld': True,
                'not_formal_ODE_truth': True, 'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'),
                'source_signature': signature(), 'execution': idle, 'mutex': mutex}
            blob = r.encoded(value)
            r.batch([(RUN / 'acceptance.json', blob), (RUN / 'acceptance.json.gz', gzip.compress(blob, mtime=0))])
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261019-2400-v4-population-recovery-conditional-close',
        'stage_status': 'conditional_asset_close_new_group_prefix_and_all_scores_pending',
        'next_action': 'new-version all-new-group first-contact prefix audit; expanded populations and dependent scores pending'}
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261019_2400_v4.json', r.encoded(plan)),
        (ROOT / 'reports/基线条件区间资产续算独立核验_20261019_2400_v1.md',
            ('# 基线条件区间资产续算核验\n\n完整57份条件资产全数组/投影/GEOS核验；原12组逐数组精确复用，'
             '仅新增缺失组。新组首次时间前缀独立审计、扩展总体及全部评分仍待修，修正真值预测重验0，旧结论继续暂停。\n').encode('utf-8'))])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='midnight_population_recovery_conditionally_closed', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261019_2400_v4.json'), next_action=plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('ALL 57 CONDITIONAL ASSETS CLOSED; new-group prefix audit and scoring remain pending', flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Already launched or deadline')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(__file__)), 'run']
        r.freeze(SESSION / 'policy.json', r.encoded({'time': r.now(), 'argv': argv, 'cwd': r'C:\Users\Admin',
            'execution': idle, 'mutex': mutex, 'parent_mutex_released_before_Popen': True,
            'resources': r.guard(RESERVATION, RESERVATION)}))
    with (SESSION / 'stdout.log').open('xb') as stdout, (SESSION / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=stderr, env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_admission_proof': True}))
    print('POPULATION RECOVERY LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
