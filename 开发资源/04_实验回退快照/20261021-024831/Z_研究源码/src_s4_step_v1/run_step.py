from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
sys.path.insert(0, str(ROOT / 'src_s4_v1'))
sys.path.insert(0, str(ROOT / '管理脚本'))
import pipeline
from common import array_hash, file_hash, read_json, utc_now
from execution_io_v2 import write_json_retry, save_checkpoint_gzip
from reporting import csv_rows

RUN = ROOT / 'runs' / 'evening_S4_step_stability_v1'
PROTOCOL = ROOT / 'protocol_step_stability_v1.json'


def signature():
    result = pipeline.signature()
    for path in [Path(__file__), PROTOCOL, ROOT / '管理脚本' / 'execution_io_v2.py']:
        result[path.relative_to(ROOT).as_posix()] = file_hash(path)
    return result


def jobs():
    p, source = read_json(PROTOCOL), signature()
    conditions = {c['id']: c for c in pipeline.condition_list()}
    result = []
    for case in p['cases']:
        for core in p['core_configs']:
            for condition in p['conditions']:
                for dt in p['predictor_dt_s']:
                    method = pipeline.Method(core['mode'], gain=core['gain'], decay_s=core['decay_s'], dt=dt)
                    job = {'stage': 'S4_prediction_step_pilot', 'partition': p['partition'], 'case_id': case,
                           'core_id': core['id'], 'method': asdict(method), 'processor': p['processor'],
                           'condition': conditions[condition], 'variants': p['variants'], 'source_signature': source}
                    digest = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
                    job['id'] = f'{case}__{core["id"]}__{condition}__dt{round(dt*1000):04d}__{digest}'
                    result.append(job)
    if len(result) != 36 or len({j['id'] for j in result}) != 36:
        raise AssertionError('Step diagnostic design must contain 36 distinct jobs')
    return result


def preflight():
    p = read_json(PROTOCOL)
    if file_hash(pipeline.RUN / 'checkpoint.json') != p['dependency_checkpoint_sha256']:
        raise AssertionError('Closed joint dependency checkpoint differs')
    dependency = read_json(pipeline.RUN / 'checkpoint.json')
    if not dependency['stages'].get('joint_refinement', {}).get('done') or dependency['source_signature'] != pipeline.signature():
        raise AssertionError('Joint refinement is incomplete or its source changed')
    acceptance = read_json(ROOT / 'reports' / 'S0_acceptance.json')
    if acceptance['status'] != 'passed' or acceptance['target_count'] != 70000:
        raise AssertionError('Frozen target density acceptance is missing')
    inputs = []
    for case in p['cases']:
        data, targets, mf = pipeline.core.load_case(p['partition'], case)
        if len(targets['xy']) != 70000 or len(pipeline.np.unique(targets['xy'], axis=0)) != 70000:
            raise AssertionError('Formal target uniqueness failed')
        if array_hash(targets['xy']) != mf['target_coordinates_sha256'] or array_hash(targets['contact_time']) != mf['contact_label_sha256']:
            raise AssertionError('Target or contact label array differs')
        if not pipeline.np.allclose(pipeline.np.diff(data['time']), .02, rtol=0, atol=1e-10):
            raise AssertionError('Observation and scoring frequency must stay fixed')
        if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
            raise AssertionError('Independent truth convergence gate failed')
        for c in jobs():
            if c['case_id'] == case:
                _, obs = pipeline.load_observation(c['partition'], case, c['condition'])
                if obs['descriptor']['input_hashes'] != mf['files']:
                    raise AssertionError('Shared observation does not match the frozen inputs')
        inputs.append({'case_id': case, 'manifest_sha256': file_hash(ROOT / 'datasets' / p['partition'] / case / 'manifest.json'),
                       'target_coordinates_sha256': mf['target_coordinates_sha256'], 'contact_label_sha256': mf['contact_label_sha256']})
    return {'status': 'passed', 'dataset_inputs': inputs, 'shared_unique_points_per_case': 70000,
            'observation_dt_s': .02, 'score_dt_s': .02, 'new_prediction_jobs': 0,
            'source_signature': signature(), 'physical_validation': False}


def execute(job):
    if signature() != job['source_signature']:
        raise AssertionError('Frozen step diagnostic source changed')
    pipeline.common.storage_guard()
    data, targets, mf = pipeline.core.load_case(job['partition'], job['case_id'])
    raw, obs = pipeline.load_observation(job['partition'], job['case_id'], job['condition'])
    start = time.perf_counter()
    result = pipeline.evaluate({**data, **raw}, targets, pipeline.Method(**job['method']),
                               [pipeline.Variant(**v) for v in job['variants']])
    rows = [{**row, 'job_id': job['id'], 'case_id': job['case_id'], 'core_id': job['core_id'],
             'condition': job['condition']['id'], 'predictor_dt_s': job['method']['dt'], 'processor': 'raw'}
            for row in result['summaries']]
    folder = RUN / 'jobs' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    write_json_retry(folder / 'configuration.json', job)
    write_json_retry(folder / 'summary.json', rows)
    write_json_retry(folder / 'timing.json', result['timing'])
    pipeline.np.savez_compressed(folder / 'target_results.npz', **result['point_output'])
    pipeline.np.savez_compressed(folder / 'frame_results.npz', counts=result['frame_counts'], time=data['time'], phase=result['observed_phase'])
    names = ('configuration.json', 'summary.json', 'timing.json', 'target_results.npz', 'frame_results.npz')
    report = {'id': job['id'], 'source_signature': job['source_signature'], 'input_hashes': mf['files'],
              'target_coordinates_sha256': mf['target_coordinates_sha256'], 'contact_label_sha256': mf['contact_label_sha256'],
              'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'],
              'score_start_s': 2., 'score_end_s': float(data['time'][-1]-3), 'target_count': len(targets['xy']),
              'output_sha256': {name: file_hash(folder / name) for name in names}, 'wall_s': time.perf_counter()-start}
    write_json_retry(folder / 'report.json', report)
    return {'id': job['id'], 'report_sha256': file_hash(folder / 'report.json'), 'summaries': rows}


def worker_probe():
    pipeline.worker_init()
    return {'root': str(pipeline.common.ROOT), 'source_signature': signature(),
            'guard_defaults': list(pipeline.common.storage_guard.__defaults__)}


def verify(job, record):
    folder = RUN / 'jobs' / job['id']
    if read_json(folder / 'configuration.json') != job or file_hash(folder / 'report.json') != record['report_sha256']:
        raise AssertionError('Effective configuration or completed report changed')
    report = read_json(folder / 'report.json')
    if report['source_signature'] != signature():
        raise AssertionError('Completed source signature changed')
    for name, sha in report['output_sha256'].items():
        if file_hash(folder / name) != sha:
            raise AssertionError('Output hash changed')
    _, _, mf = pipeline.core.load_case(job['partition'], job['case_id'])
    _, obs = pipeline.load_observation(job['partition'], job['case_id'], job['condition'])
    if (report['input_hashes'] != mf['files'] or report['target_coordinates_sha256'] != mf['target_coordinates_sha256']
            or report['contact_label_sha256'] != mf['contact_label_sha256']
            or report['raw_sensor_hashes'] != obs['descriptor']['sensor_array_hashes']):
        raise AssertionError('Frozen shared inputs changed')
    return read_json(folder / 'summary.json'), report


def conclude(cp, planned):
    rows, groups = [], {}
    for job in planned:
        if job['id'] not in cp['completed']:
            continue
        current, report = verify(job, cp['completed'][job['id']])
        rows.extend(current)
        key = (job['case_id'], job['condition']['id'])
        shared = (report['target_coordinates_sha256'], report['contact_label_sha256'], report['score_start_s'],
                  report['score_end_s'], json.dumps(report['raw_sensor_hashes'], sort_keys=True))
        if key in groups and groups[key] != shared:
            raise AssertionError('Cross-step or cross-method comparison is not paired')
        groups[key] = shared
    pairs = []
    indexed = {}
    for row in rows:
        key = (row['case_id'], row['core_id'], row['condition'], row['margin_m'], row['confirmation_s'])
        indexed.setdefault(key, {})[row['predictor_dt_s']] = row
    for key, block in indexed.items():
        if set(block) != {.01, .02}:
            continue
        a, b = block[.02], block[.01]
        lead = None if a['right_lead_p10_s'] is None or b['right_lead_p10_s'] is None else b['right_lead_p10_s']-a['right_lead_p10_s']
        _, targets, _ = pipeline.core.load_case(read_json(PROTOCOL)['partition'], key[0])
        contact = targets['contact_time']
        eligible = (~targets['front_ignored']) & (targets['edge'] == 2) & pipeline.np.isfinite(contact)
        eligible &= (contact >= 2-1e-9) & (contact <= a['score_end_s']+1e-9)
        tag = pipeline.Variant(a['EXIT_W_s'], a['margin_m'], a['confirmation_s']).tag
        with pipeline.np.load(RUN / 'jobs' / a['job_id'] / 'target_results.npz') as saved:
            valid_a = saved[tag+'_valid']
        with pipeline.np.load(RUN / 'jobs' / b['job_id'] / 'target_results.npz') as saved:
            valid_b = saved[tag+'_valid']
        newly_missed = int((eligible & pipeline.np.isfinite(valid_a) & ~pipeline.np.isfinite(valid_b)).sum())
        pairs.append({'case_id': key[0], 'core_id': key[1], 'condition': key[2], 'margin_m': key[3], 'confirmation_s': key[4],
                      'right_delta_pp': b['right_pct']-a['right_pct'],
                      'stratified_right_delta_pp': b['stratified_right_pct']-a['stratified_right_pct'],
                      'point_fp_delta_pp': b['negative_fp_pct']-a['negative_fp_pct'],
                      'common_fpr_delta_pp': b['common_2s_reference_fpr_pct']-a['common_2s_reference_fpr_pct'],
                      'lead_p10_delta_s': lead, 'window_miss_delta': b['right_miss']-a['right_miss'],
                      'no_before_delta': b['right_no_before']-a['right_no_before'],
                      'new_window_miss_instances': newly_missed})
    complete = len(cp['completed']) == 36
    limits = read_json(PROTOCOL)['comparison_limits']
    passed = complete and len(pairs) == 36 and all(abs(r['right_delta_pp']) <= limits['right_absolute_delta_pp']
                and abs(r['point_fp_delta_pp']) <= limits['point_fp_absolute_delta_pp']
                and (r['lead_p10_delta_s'] is None or abs(r['lead_p10_delta_s']) <= limits['lead_p10_absolute_delta_s'])
                and r['new_window_miss_instances'] == 0 for r in pairs)
    csv_rows(RUN / 'reports' / 'step_paired_differences.csv', pairs)
    csv_rows(RUN / 'reports' / 'step_scores.csv', rows)
    record = {'status': 'complete_step_pilot_only' if complete else 'partial_no_acceptance', 'completed_jobs': len(cp['completed']),
              'prediction_jobs_expected': 36, 'paired_rows': len(pairs), 'shared_groups': len(groups),
              'all_completed_output_and_input_hashes_verified': True, 'same_target_label_observation_scoring_times': True,
              'passes_this_subset_step_gate': passed, 'full_S4_acceptance': False, 'S5_completed': False,
              'source_signature': signature(), 'checkpoint_sha256': file_hash(RUN / 'checkpoint.json'),
              'physical_validation': False, 'captured_at_utc': utc_now(),
              'max_abs_right_delta_pp': max((abs(r['right_delta_pp']) for r in pairs), default=None),
              'max_abs_point_fp_delta_pp': max((abs(r['point_fp_delta_pp']) for r in pairs), default=None),
              'max_abs_lead_p10_delta_s': max((abs(r['lead_p10_delta_s']) for r in pairs if r['lead_p10_delta_s'] is not None), default=None)}
    write_json_retry(RUN / 'reports' / 'step_analysis.json', record)
    print(json.dumps(record, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    p = read_json(PROTOCOL)
    end = datetime.fromisoformat(p['execution']['deadline_local'])
    if datetime.now(timezone.utc) >= end:
        parser.error('Do not start after the authorized 21:00 deadline')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        pipeline.worker_init()
        pipeline.common.storage_guard()
        proof = preflight()
        with ProcessPoolExecutor(max_workers=1, initializer=pipeline.worker_init) as pool:
            actual = pool.submit(worker_probe).result(timeout=180)
        if (actual['source_signature'] != signature() or Path(actual['root']) != ROOT
                or actual['guard_defaults'] != list(pipeline.common.storage_guard.__defaults__)):
            raise AssertionError('Actual Windows worker source/root/resource policy differs')
        proof['actual_worker_probe'] = actual
        planned = jobs()
        RUN.mkdir(parents=True, exist_ok=True)
        for name, sha in signature().items():
            target = RUN / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and file_hash(target) != sha:
                raise AssertionError('Source snapshot changed')
            if not target.exists():
                target.write_bytes((ROOT / name).read_bytes())
        write_json_retry(RUN / 'preflight.json', proof)
        if args.check_only:
            print(json.dumps(proof, ensure_ascii=False), flush=True)
            return
        cp = read_json(RUN / 'checkpoint.json') if (RUN / 'checkpoint.json').exists() else {'completed': {}, 'summaries': [], 'source_signature': signature()}
        if cp['source_signature'] != signature():
            raise AssertionError('Do not resume changed step source/protocol')
        cp['status'] = 'running'
        started = True
        write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'deadline_local': end.isoformat(), 'time': utc_now()})
        write_json_retry(RUN / 'checkpoint.json', cp)
        pending = []
        for job in planned:
            if job['id'] in cp['completed']:
                verify(job, cp['completed'][job['id']])
            elif (RUN / 'jobs' / job['id'] / 'report.json').exists():
                record = {'report_sha256': file_hash(RUN / 'jobs' / job['id'] / 'report.json')}
                restored, _ = verify(job, record)
                cp['completed'][job['id']] = record
                cp['summaries'].extend(restored)
            else:
                pending.append(job)
        iterator = iter(pending)
        with ProcessPoolExecutor(max_workers=6, initializer=pipeline.worker_init) as pool:
            active = {}
            def send():
                if datetime.now(timezone.utc) >= end:
                    return
                job = next(iterator, None)
                if job is not None:
                    pipeline.common.storage_guard()
                    active[pool.submit(execute, job)] = job
            for _ in range(6):
                send()
            while active:
                ready, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
                for future in ready:
                    result = future.result()
                    active.pop(future)
                    cp['completed'][result['id']] = {'report_sha256': result['report_sha256']}
                    cp['summaries'].extend(result['summaries'])
                    write_json_retry(RUN / 'checkpoint.json', cp)
                    print(f'DONE STEP {len(cp["completed"])}/36 {result["id"]}', flush=True)
                    send()
        cp['status'] = 'step_pilot_complete_full_S4_not_complete' if len(cp['completed']) == 36 else 'deadline_saved'
        write_json_retry(RUN / 'checkpoint.json', cp)
        conclude(cp, planned)
    except Exception as error:
        if started:
            cp.update(status='needs_repair', error=repr(error))
            write_json_retry(RUN / 'checkpoint.json', cp)
        raise
    finally:
        try:
            if started:
                save_checkpoint_gzip(RUN / 'runtime_sessions' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_ended.json.gz'),
                                     (RUN / 'checkpoint.json').read_bytes())
                write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'deadline_local': end.isoformat(), 'time': utc_now()})
        finally:
            kernel.ReleaseMutex(mutex)
            kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
