"""Versioned all-baseline prefix audit; accepted exclusions are copied, not rerun."""
from __future__ import annotations
import argparse
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
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'
sys.path.insert(0, str(ROOT / 'src_s4_population_extension_20261022_v1'))
import extension as parent
import numpy as np

base, r, follow = parent.base, parent.r, parent.previous.follow
POPULATION = parent.RUN
ACCEPTED = follow.RUN
RUN = ROOT / 'runs/resume_20261022_0000_population_prefix_v1'
AUTH = parent.AUTH
PROTOCOL = ROOT / 'protocol_population_prefix_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v3.json'
SESSION = AUTH / 'runtime_sessions/population_prefix_launch_v1'
RESERVATION = 480 * 1024**2
ACCEPTED_CP = '44396f02a4f2b1a6015b41d8697d4c02849daa6e18a9ba42a223bd17e6df81bb'
ACCEPTED_SHA = 'aa25b6c22232e37173af5e051ebd1ab1a871225410ed6fa8d4a07eccfbf68f99'
ACCEPTED_RECEIPT = 'e1d70b04294f0ea33c85d6fa366b49ee9951544e483a509416813850383d069d'


def configure():
    parent.configure()
    r.RUN, r.AUTH, r.RUN_CAP = RUN, AUTH, 512 * 1024**2


configure()


def execution():
    try:
        result = parent.execution()
    finally:
        configure()
    for folder in (POPULATION, RUN):
        for path in folder.glob('*runner_lock.json'):
            lock = r.read(path)
            r.require(lock['status'] == 'stopped' or lock.get('pid') == os.getpid(), 'Scientific runner still active')
    return result


def parent_gate():
    parent.verify()
    follow.verify()
    for filename, digest in (('checkpoint.json', ACCEPTED_CP), ('acceptance.json', ACCEPTED_SHA),
                             ('close_receipt.json', ACCEPTED_RECEIPT)):
        r.require(r.file_hash(ACCEPTED / filename) == digest, 'Accepted original prefix proof changed')
    accepted = r.read(ACCEPTED / 'acceptance.json')
    r.require(accepted['strict_all_point_prefix_gate_passed'] is True and
              accepted['checkpoint_sha256'] == ACCEPTED_CP, 'Original all-point prefix gate not passed')
    cp = r.read(POPULATION / 'checkpoint.json')
    acceptance = r.read(POPULATION / 'acceptance.json')
    receipt = r.read(POPULATION / 'close_receipt.json')
    digest = r.file_hash(POPULATION / 'checkpoint.json')
    r.require(cp['status'] == 'complete_pending_independent_acceptance' and len(cp['completed']) == 39,
              'Complete stopped population required')
    r.require(acceptance['checkpoint_sha256'] == receipt['checkpoint_sha256'] == digest and
              receipt['acceptance_sha256'] == r.file_hash(POPULATION / 'acceptance.json'), 'Population close binding differs')
    r.require(acceptance['new_27_group_first_contact_prefix_audit_still_required'] is True and
              len(acceptance['rows']) == 57 and len(acceptance['geometry']) == 39,
              'Whole conditional population acceptance required')
    return cp, r.read(ACCEPTED / 'checkpoint.json')


def signature():
    paths = set()
    for folder in (POPULATION, ACCEPTED):
        paths.update(ROOT / rel for rel in r.read(folder / 'source_manifest.json'))
        paths.update(folder / name for name in ('checkpoint.json', 'acceptance.json', 'close_receipt.json', 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json'))
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen prefix source or parents changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Prefix source snapshot differs')
    for folder, name in ((POPULATION, 'population_files.json'), (ACCEPTED, 'accepted_prefix_files.json')):
        for rel, digest in r.read(RUN / name).items():
            r.require(r.file_hash(folder / rel) == digest, 'Frozen parent file differs: ' + rel)


def partition(groups, reused):
    r.require(set(reused).issubset(groups) and len(groups) == 39 and len(reused) == 12, 'Prefix population partition differs')
    new = [key for key in groups if key not in reused]
    r.require(len(new) == 27, 'Every new group must be audited')
    return [key for key in groups if key in reused], new


def validate_prefix_group(key, entry, asset, loaded, groups, folder):
    arrays, saved = follow.read_prefix(folder / 'groups' / key)
    r.require(r.file_hash(folder / 'groups' / key / 'result.json') == entry['result_sha256'], 'Prefix CP/report differs')
    r.require(saved['summary'] == entry['summary'] and saved['original_dataset_ids'] == groups[key], 'Prefix membership/summary differs')
    r.require(saved['original_group_result_sha256'] == r.file_hash(POPULATION / 'groups' / key / 'result.json'),
              'Prefix proof is not bound to the current population')
    for tag, time, state, error, vehicle, labels in follow.paths_for(key, loaded, groups, asset):
        final = follow.path_arrays(arrays, tag)
        indices = final.pop('refined_indices')
        seed = follow.path_arrays(arrays, 'seed_' + tag)
        refined = follow.path_arrays(arrays, 'refined_' + tag)
        merged = follow.merge_refinement(seed, refined, indices)
        r.require(base.array_meta(final) == base.array_meta(merged), 'Full refinement merge differs')
        end = np.where(np.isnan(labels['contact_lower_s']), time[-1], labels['contact_lower_s'])
        summary = follow.validate_prefix(final, end)
        r.require(summary == saved['summary'][tag]['prefix'], 'Full prefix statistics differ')
        r.require(follow.old.summarize_prefix(seed) == saved['summary'][tag]['seed'] and
                  len(indices) == saved['summary'][tag]['all_unknown_points_refined'], 'Seed/refinement accounting differs')
        for field in follow.FIELDS:
            r.require(np.array_equal(arrays[tag + '__' + field + '__packbits'],
                      np.packbits(final[field], bitorder='little')), 'Prefix packbits or padding differs')
    return arrays, saved


def load_all():
    cp, accepted_cp = parent_gate()
    loaded, groups = base.load_inputs(r.read(parent.PROTOCOL)['matrix'])
    r.require(len(loaded) == 57 and set(cp['completed']) == set(groups), 'Whole original input matrix required')
    assets = {key: parent.validate_asset(key, cp['completed'][key], loaded, groups, POPULATION) for key in groups}
    reused, new = partition(groups, accepted_cp['completed'])
    for key in reused:
        original = follow.old.OLD
        paths = [('groups', key)] + [('datasets', dataset_id) for dataset_id in groups[key]]
        for kind, name in paths:
            for filename in ('result.json', 'arrays.npz'):
                r.require(r.file_hash(POPULATION / kind / name / filename) == r.file_hash(original / kind / name / filename),
                          'Any changed original quantity forbids prefix reuse')
        validate_prefix_group(key, accepted_cp['completed'][key], assets[key], loaded, groups, ACCEPTED)
    return loaded, groups, assets, accepted_cp, reused, new


def bound_audit():
    namespace = dict(follow.audit_group.__globals__)
    proxy = types.SimpleNamespace(OLD=POPULATION, audit_prefixes=follow.old.audit_prefixes,
                                  summarize_prefix=follow.old.summarize_prefix)
    namespace.update(RUN=RUN, old=proxy)
    function = types.FunctionType(follow.audit_group.__code__, namespace, follow.audit_group.__name__,
                                  follow.audit_group.__defaults__, follow.audit_group.__closure__)
    r.require(function.__code__ is follow.audit_group.__code__, 'Prefix computation code object differs')
    return function


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN)), 'Already attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        _, accepted_cp = parent_gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True, encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Prefix tests failed: ' + tests.stderr)
        protocol = {'version': 'all-baseline-prefix-v1', 'deadline': parent.DEADLINE_LOCAL,
            'matrix': r.read(parent.PROTOCOL)['matrix'], 'population': str(POPULATION), 'accepted_prefix': str(ACCEPTED),
            'exact_reuse_groups': list(accepted_cp['completed']), 'new_groups': 27, 'all_groups': 39, 'all_files': 57,
            'seed_budget': 8192, 'all_unknown_refinement_budget': follow.REFINE_BUDGET, 'time_resolution_s': 1e-8,
            'tolerance_m': base.TOLERANCE, 'empirical_pose_bounds_unchanged': True, 'all_unknowns_preserved': True,
            'workers': 1, 'inflight': 1, 'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION,
            'total_E_Z_cap_bytes': parent.CAP, 'Z_reserve_bytes': r.RESERVE,
            'no_prediction_or_score_recertification': True, 'not_formal_ODE_or_real_vehicle_certificate': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v2.json'), 'version': '20261022-0000-v3-all-baseline-prefix',
            'stage_status': 'prepared_not_admitted', 'run_directory': str(RUN), 'protocol': str(PROTOCOL),
            'entrypoint': str(Path(__file__)), 'next_action': 'prove exact reuse original 12 groups; all-point prefix audit remaining 27'}
        hashes = [(RUN / name, r.encoded({p.relative_to(folder).as_posix(): r.file_hash(p)
                    for p in sorted(folder.rglob('*')) if p.is_file()}))
                  for folder, name in ((POPULATION, 'population_files.json'), (ACCEPTED, 'accepted_prefix_files.json'))]
        r.batch(hashes + [(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
                [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('ALL-BASELINE PREFIX PREPARED; actual input admission still required', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Already attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'exact_reused_groups': [], 'new_audited_groups': [],
              'new_predictions': 0, 'corrected_truth_revalidated_prediction_jobs': 0, 'source_signature': signature()}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, accepted_cp, reused, new = load_all()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'all_original_files': len(loaded),
                'all_groups': len(groups), 'groups': groups, 'exact_reuse_groups': reused, 'new_groups': new,
                'all_assets_fully_decoded': True, 'all_old_proof_inputs_exactly_unchanged': True,
                'execution': idle, 'mutex': mutex, 'resources': r.guard(RESERVATION, RESERVATION)}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='all_baseline_prefix_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                running_predictions=False, input_worker_admitted=True, input_worker_admission_pending=False,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'))
            r.mutable(ROOT / 'active_research_run.json', active)
            print('PREFIX PREFLIGHT PASSED ALL 57 INPUTS / 39 GROUPS / EXACT 12 PREFIX PROOFS / NEW 27 GROUPS', flush=True)
            for key in reused:
                r.require(r.before_deadline(), 'New prefix reuse block cutoff')
                folder = ACCEPTED / 'groups' / key
                r.batch([(RUN / 'groups' / key / name, (folder / name).read_bytes())
                         for name in ('prefix_audit.npz', 'result.json')])
                entry = accepted_cp['completed'][key]
                validate_prefix_group(key, entry, assets[key], loaded, groups, RUN)
                cp['completed'][key] = entry
                cp['exact_reused_groups'].append(key)
                r.checkpoint(cp)
            audit = bound_audit()
            for key in new:
                r.require(r.before_deadline(), 'New full-prefix group submission cutoff')
                verify()
                remaining = max(0, RESERVATION - base.scan_size(RUN))
                r.guard(remaining, remaining)
                cp['completed'][key] = audit(key, loaded, groups, assets[key], None)
                cp['new_audited_groups'].append(key)
                r.checkpoint(cp)
                r.require(not any(v['prefix']['early_contact_witness'] for v in cp['completed'][key]['summary'].values()),
                          'Early contact counterexample saved; stop propagation')
            cp['status'] = 'complete_pending_independent_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('PREFIX WORKER EXITING; independent close and every affected score still pending', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Already accepted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_close' and len(cp['completed']) == 39 and
                  len(cp['exact_reused_groups']) == 12 and len(cp['new_audited_groups']) == 27, 'Incomplete prefix batch')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, accepted_cp, reused, new = load_all()
            r.require(set(cp['completed']) == set(groups), 'All groups required')
            rows, geometry = [], {}
            for key, entry in cp['completed'].items():
                arrays, saved = validate_prefix_group(key, entry, assets[key], loaded, groups, RUN)
                if key in reused:
                    for name in ('prefix_audit.npz', 'result.json'):
                        r.require(r.file_hash(RUN / 'groups' / key / name) == r.file_hash(ACCEPTED / 'groups' / key / name),
                                  'Accepted full prefix proof not copied exactly')
                geometry[key] = {}
                for tag, time, state, error, vehicle, labels in follow.paths_for(key, loaded, groups, assets[key]):
                    r.require(saved['summary'][tag]['prefix']['early_contact_witness'] == 0, 'Early witness forbids acceptance')
                    geometry[key][tag] = base.validate_path(assets[key][0]['xy'], time, state, labels, error, vehicle)
                rows.append({'group': key, 'dataset_files': len(groups[key]), 'summary': saved['summary']})
            strict = all(v['prefix']['strict_prefix_gate_passed'] for row in rows for v in row['summary'].values())
            value = {'time': r.now(), 'status': 'all_baseline_conditional_prefix_arrays_and_GE0S_checked',
                'strict_all_point_prefix_gate_passed': strict, 'groups': 39, 'dataset_files': 57,
                'exact_reused_groups': 12, 'new_audited_groups': 27, 'rows': rows, 'geometry': geometry,
                'all_unknowns_preserved': True, 'all_label_dependent_claims_withheld': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex}
            blob = r.encoded(value)
            r.batch([(RUN / 'acceptance.json', blob), (RUN / 'acceptance.json.gz', gzip.compress(blob, mtime=0))])
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    next_plan = {**r.read(PLAN), 'version': '20261022-0000-v4-all-baseline-prefix-closed',
        'stage_status': 'conditional_prefix_closed_unknowns_and_all_affected_scores_retained',
        'strict_all_point_prefix_gate_passed': strict,
        'next_action': 'inspect all remaining label unknowns; full expanded populations and every affected score still pending'}
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v4.json', r.encoded(next_plan)),
        (ROOT / 'reports/57份基线首次接触前缀独立核验_20261022_0000_v1.md',
         ('# 57份基线首次接触前缀独立核验\n\n39组57份，原12组完整证明精确复用、新27组全点及全部未定点追加核验。'
          + '严格全点前缀门：' + str(strict) + '。标签未定、经验空间界、非形式ODE及非实车证书限制保留。'
          + '完整扩展总体与波及评分仍待修，修正真值重验预测0，相关旧结论继续暂停。\n').encode('utf-8'))])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='all_baseline_prefix_conditionally_closed', pid=None, running_analysis=False,
                  plan=str(ROOT / 'resume_plan_20261022_0000_v4.json'), next_action=next_plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print(json.dumps({'groups': 39, 'dataset_files': 57, 'strict_all_point_prefix_gate_passed': strict}), flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Already launched or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(__file__)), 'run']
        r.freeze(SESSION / 'policy.json', r.encoded({'time': r.now(), 'argv': argv, 'execution': idle,
            'mutex': mutex, 'resources': r.guard(RESERVATION, RESERVATION), 'cwd': r'C:\Users\Admin'}))
    for name in ('stdout.log', 'stderr.log'):
        r.guard(0, 0)
        with (SESSION / name).open('xb'):
            pass
    with (SESSION / 'stdout.log').open('ab') as stdout, (SESSION / 'stderr.log').open('ab') as stderr:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_admission_proof': True}))
    print('ALL-BASELINE PREFIX LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
