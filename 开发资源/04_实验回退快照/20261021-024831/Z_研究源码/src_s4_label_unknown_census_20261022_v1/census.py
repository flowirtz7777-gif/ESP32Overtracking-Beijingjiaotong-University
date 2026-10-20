"""Versioned complete unknown-label census, not relabeling or score repair."""
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
sys.path.insert(0, str(ROOT / 'src_s4_prefix_hull_completion_20261022_v1'))
import hull_driver as prior
import census_core as core
import numpy as np

base, r = prior.base, prior.r
p = prior.diagnostic.parent
PARENT, POPULATION, AUTH = prior.RUN, p.POPULATION, prior.AUTH
RUN = ROOT / 'runs/resume_20261022_0000_label_unknown_census_v1'
PROTOCOL = ROOT / 'protocol_label_unknown_census_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v9.json'
SESSION = AUTH / 'runtime_sessions/label_unknown_census_launch_v1'
RESERVATION = 224 * 1024**2
PARENT_HASHES = {
    'checkpoint.json': '2ac921c29da864a404fe9c3e7ffd92aac7ea9aa33c7882af45a2586861a56525',
    'acceptance.json': '0b034b3d6b8e7b30471620df88a6c82bab11049fa158c4c131dec307f9ee2763',
    'close_receipt.json': '830ddd32951d5f88aff3d55ba636d08a3acc5d827b37f10e5d8a0df4054625ea'}


def configure():
    prior.configure()
    r.RUN, r.RUN_CAP = RUN, 256 * 1024**2


configure()


def execution():
    try:
        return prior.execution()
    finally:
        configure()


def gate():
    prior.verify()
    for name, digest in PARENT_HASHES.items():
        r.require(r.file_hash(PARENT / name) == digest, 'Closed full-prefix proof changed')
    accepted = r.read(PARENT / 'acceptance.json')
    r.require(accepted['strict_all_point_prefix_gate_passed'] is True
              and accepted['remaining_prefix_unknown_points'] == 0, 'Complete accepted prefix proof required')


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')}
    paths.update(PARENT / name for name in (*PARENT_HASHES, 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json'))
    return {path.relative_to(ROOT).as_posix(): r.file_hash(path) for path in sorted(paths)}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen census dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Census source snapshot differs')
    for rel, digest in r.read(RUN / 'parent_files_sha256.json').items():
        r.require(r.file_hash(PARENT / rel) == digest, 'Closed hull proof file differs')


def admit():
    gate()
    loaded, groups, assets, _, _, _ = p.load_all()
    cp = r.read(p.RUN / 'checkpoint.json')
    for key in groups:
        p.validate_prefix_group(key, cp['completed'][key], assets[key], loaded, groups, p.RUN)
    r.require(len(loaded) == 57 and len(groups) == 39, 'Whole original population required')
    return loaded, groups, assets


def label_views(asset):
    arrays, _, paths = asset
    combined = {name.split('__', 1)[1]: value for name, value in arrays.items() if name.startswith('combined__')}
    return arrays['xy'], paths, combined


def summarize_projection(paths, combined, index, flags, scope):
    return core.summarize({k: v[index] for k, v in paths['oldpath'].items()},
        {k: v[index] for k, v in paths['independent'].items()}, {k: v[index] for k, v in combined.items()},
        flags[index], scope[index])


def totals(rows, geometry):
    return {'dataset_files': len(rows), 'geometry_groups': len(geometry),
        'point_file_records': sum(row['summary']['points'] for row in rows),
        'combined_status_unknown_point_file_records': sum(row['summary']['combined_status_unknown'] for row in rows),
        'complete_census_point_file_records': sum(row['summary']['census_points'] for row in rows),
        'complete_census_group_unique_points': sum(row['census_points'] for row in geometry.values()),
        'reason_point_file_records_nonexclusive': {name: sum(row['summary']['reason_counts_nonexclusive'][name] for row in rows)
                                                 for name in core.REASONS.values()}}


def prepare():
    r.require(r.before_deadline() and not any(path.exists() for path in (RUN, PROTOCOL, PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Census synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'all-conditional-unknown-label-census-v1', 'deadline': p.parent.DEADLINE_LOCAL,
            'parent': str(PARENT), 'parent_hashes': PARENT_HASHES, 'conditional_population': str(POPULATION),
            'input_files': 57, 'geometry_groups': 39, 'point_file_records': 3360000,
            'previous_combined_status_unknown_point_file_records': 16464,
            'selection': 'all combined status >=2 OR both witnessed but combined edge not singleton OR any model conflict',
            'reason_flags': core.REASONS, 'nonexclusive_reasons_not_summed_as_unique_counts': True,
            'all_original_indices_and_full_mask_padding_bound': True, 'no_label_time_or_prediction_changes': True,
            'independent_close_scalar_classification': True, 'run_cap_bytes': r.RUN_CAP,
            'reservation_bytes': RESERVATION, 'total_E_Z_cap_bytes': r.CAP, 'Z_reserve_bytes': r.RESERVE,
            'workers': 1, 'inflight': 1, 'corrected_truth_revalidated_prediction_jobs': 0,
            'all_label_dependent_claims_withheld': True, 'not_formal_ODE_or_real_vehicle_certificate': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v8.json'),
            'version': '20261022-0000-v9-all-label-unknown-census', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'next_action': 'complete census all contact/status, edge, budget and conflict unknowns; no forced relabeling'}
        hashes = {path.relative_to(PARENT).as_posix(): r.file_hash(path) for path in sorted(PARENT.rglob('*')) if path.is_file()}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'parent_files_sha256.json', r.encoded(hashes)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
                [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('UNKNOWN LABEL CENSUS PREPARED; real input admission still pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'corrected_truth_revalidated_prediction_jobs': 0}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            print('UNKNOWN CENSUS PREFLIGHT: all inputs, conditional assets and complete prefix proofs', flush=True)
            loaded, groups, assets = admit()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'input_files': len(loaded),
                'groups': groups, 'all_conditional_and_prefix_arrays_decoded': True, 'execution': idle, 'mutex': mutex}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='all_label_unknown_census_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'),
                input_worker_admitted=True, input_worker_admission_pending=False)
            r.mutable(ROOT / 'active_research_run.json', active)
            print('UNKNOWN CENSUS PREFLIGHT PASSED ALL 57 INPUTS / 39 GROUPS / 78 PREFIX PATHS', flush=True)
            for key, ids in groups.items():
                r.require(r.before_deadline(), 'New complete census group cutoff')
                xy, paths, combined = label_views(assets[key])
                flags, scope = core.classify(paths['oldpath'], paths['independent'], combined)
                summary = core.summarize(paths['oldpath'], paths['independent'], combined, flags, scope)
                group = base.save_arrays(RUN / 'groups' / key, core.group_payload(xy, paths, combined, flags, scope),
                    {'summary': summary, 'original_dataset_ids': ids,
                     'parent_group_result_sha256': r.file_hash(POPULATION / 'groups' / key / 'result.json')})
                datasets = {}
                for dataset_id in ids:
                    original, _ = base.read_arrays(POPULATION / 'datasets' / dataset_id)
                    index = original['union_index']
                    selected = core.projection_payload(index, xy, loaded[dataset_id]['target']['xy'], flags, scope)
                    datasets[dataset_id] = base.save_arrays(RUN / 'datasets' / dataset_id, selected,
                        {'summary': summarize_projection(paths, combined, index, flags, scope), 'group': key,
                         'parent_result_sha256': r.file_hash(POPULATION / 'datasets' / dataset_id / 'result.json')})
                cp['completed'][key] = {'group': group, 'datasets': datasets}
                r.checkpoint(cp)
                print('DONE UNKNOWN CENSUS GROUP ' + key + ' selected=' + str(summary['census_points']), flush=True)
            rows = [{'summary': value['summary']} for entry in cp['completed'].values() for value in entry['datasets'].values()]
            geometry = {key: value['group']['summary'] for key, value in cp['completed'].items()}
            accounting = totals(rows, geometry)
            r.require(accounting['point_file_records'] == 3360000 and accounting['dataset_files'] == 57
                      and accounting['geometry_groups'] == 39
                      and accounting['combined_status_unknown_point_file_records'] == 16464, 'Full historical unknown ledger differs')
            cp.update(status='complete_pending_independent_close', accounting=accounting)
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('UNKNOWN CENSUS WORKER EXITING; independent close pending; no labels changed', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted close or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_close' and len(cp['completed']) == 39, 'Incomplete census')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets = admit()
            r.require(set(groups) == set(cp['completed']), 'Every group required')
            geometry, rows = {}, []
            for key, ids in groups.items():
                xy, paths, combined = label_views(assets[key])
                flags, scope = core.independent_classify(paths['oldpath'], paths['independent'], combined)
                summary = core.summarize(paths['oldpath'], paths['independent'], combined, flags, scope)
                arrays, saved = base.read_arrays(RUN / 'groups' / key)
                entry = cp['completed'][key]
                r.require(r.file_hash(RUN / 'groups' / key / 'result.json') == entry['group']['result_sha256']
                          and saved['summary'] == entry['group']['summary'] == summary
                          and saved['original_dataset_ids'] == ids
                          and saved['parent_group_result_sha256'] == r.file_hash(POPULATION / 'groups' / key / 'result.json'),
                          'Full group binding or census counts differ')
                r.require(base.array_meta(arrays) == base.array_meta(core.group_payload(xy, paths, combined, flags, scope)),
                          'Every selected group record, reason, full mask or padding differs')
                geometry[key] = summary
                r.require(set(entry['datasets']) == set(ids), 'Every original dataset projection required')
                for dataset_id in ids:
                    original, _ = base.read_arrays(POPULATION / 'datasets' / dataset_id)
                    index = original['union_index']
                    expected = core.projection_payload(index, xy, loaded[dataset_id]['target']['xy'], flags, scope)
                    projected, meta = base.read_arrays(RUN / 'datasets' / dataset_id)
                    expected_summary = summarize_projection(paths, combined, index, flags, scope)
                    r.require(base.array_meta(projected) == base.array_meta(expected)
                              and meta['summary'] == entry['datasets'][dataset_id]['summary'] == expected_summary
                              and meta['group'] == key
                              and r.file_hash(RUN / 'datasets' / dataset_id / 'result.json') == entry['datasets'][dataset_id]['result_sha256']
                              and meta['parent_result_sha256'] == r.file_hash(POPULATION / 'datasets' / dataset_id / 'result.json'),
                              'Original-order projection, mask padding or complete reasons differ')
                    rows.append({'dataset': dataset_id, 'group': key, 'summary': expected_summary})
            accounting = totals(rows, geometry)
            r.require(accounting == cp['accounting'], 'Independent complete accounting differs')
            accepted = {'time': r.now(), 'status': 'all_conditional_label_unknown_records_independently_censused_not_repaired',
                'accounting': accounting, 'geometry': geometry, 'rows': rows, 'reason_flags': core.REASONS,
                'all_labels_times_and_predictions_unchanged': True, 'strict_all_point_prefix_gate_passed': True,
                'all_label_dependent_claims_withheld': True, 'corrected_truth_revalidated_prediction_jobs': 0,
                'not_formal_ODE_or_real_vehicle_certificate': True, 'source_signature': signature(),
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'execution': idle, 'mutex': mutex}
            r.freeze(RUN / 'acceptance.json', r.encoded(accepted))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    next_plan = {**r.read(PLAN), 'version': '20261022-0000-v10-unknown-label-census-closed',
        'stage_status': 'complete_unknown_label_census_closed_no_relabeling',
        'next_action': 'review every unknown category; conservative label treatment and full expanded population/score repair still required'}
    report = ('# Complete Conditional Label Unknown Census\n\nAll 57 original files / 39 geometry groups, full original-order '
        'indices and full mask padding independently checked. Census includes status-unknown and both-witnessed '
        'non-singleton edge sets, plus every model conflict. Reasons overlap and must not be summed as unique samples. '
        'All labels, times, predictions and scores unchanged; no new independent predictions or score recertification. '
        'Full expanded populations, negative controls and every affected score remain pending.\n\n'
        + str(accounting) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v10.json', r.encoded(next_plan)),
        (ROOT / 'reports/label_unknown_census_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='all_label_unknown_census_closed_not_repaired', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v10.json'), next_action=next_plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('UNKNOWN LABEL CENSUS CLOSED: ' + str(accounting), flush=True)


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
    print('UNKNOWN CENSUS LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
