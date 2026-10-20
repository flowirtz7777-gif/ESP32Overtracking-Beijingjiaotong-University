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
sys.path.insert(0, str(ROOT / '\u7ba1\u7406\u811a\u672c'))
import pipeline
from common import array_hash, file_hash, read_json, utc_now
from execution_io_v2 import write_json_retry, save_checkpoint_gzip
from geometry import complete_geometry, label_contacts, subset_indices, GEOMETRY_EPS
from reporting import csv_rows

np = pipeline.np
RUN = ROOT / 'runs' / 'morning_S4_sensitivity_v1'
REFERENCE_RUN = ROOT / 'runs' / 'evening_S4_step_stability_v1'
PROTOCOL = ROOT / 'protocol_s4_sensitivity_v1.json'
COUNTS = ('TP', 'FP', 'ref_FP', 'support', 'negative_opportunities', 'ref_negative_opportunities')


def signature():
    result = pipeline.signature()
    paths = [*sorted(Path(__file__).parent.glob('*.py')), PROTOCOL,
             ROOT / '\u7ba1\u7406\u811a\u672c' / 'execution_io_v2.py']
    for path in paths:
        result[path.relative_to(ROOT).as_posix()] = file_hash(path)
    return result


def worker_init():
    policy = read_json(PROTOCOL)['execution']
    pipeline.common.storage_guard.__defaults__ = (policy['reserve_bytes'], policy['experiment_budget_bytes'])


def guard():
    measured = pipeline.common.storage_guard()
    used = sum(p.stat().st_size for p in RUN.rglob('*') if p.is_file()) if RUN.exists() else 0
    if used > read_json(PROTOCOL)['execution']['new_run_budget_bytes']:
        raise RuntimeError('New run storage budget exceeded; preserve history and stop')
    return {**measured, 'new_run_bytes': used}


def jobs():
    p, source = read_json(PROTOCOL), signature()
    conditions = {c['id']: c for c in pipeline.condition_list()}
    result = []
    for case in p['cases']:
        for core in p['core_configs']:
            for condition in p['conditions']:
                for tolerance in (.025, .1):
                    method = pipeline.Method(core['mode'], gain=core['gain'], decay_s=core['decay_s'], dt=p['predictor_dt_s'])
                    job = {'stage': 'S4_density_tolerance', 'case_id': case, 'partition': p['partition'],
                           'core_id': core['id'], 'method': asdict(method), 'processor': p['processor'],
                           'condition': conditions[condition], 'contact_tolerance_m': tolerance,
                           'variants': p['variants'], 'density_counts': p['density_counts'], 'source_signature': source}
                    digest = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
                    job['id'] = f'{case}__{core["id"]}__{condition}__tol{round(tolerance*1000):03d}__{digest}'
                    result.append(job)
    if len(result) != 36 or len({j['id'] for j in result}) != 36:
        raise AssertionError('Frozen sensitivity design must contain 36 new predictions')
    return result


def read_points(folder):
    with np.load(folder / 'target_results.npz') as saved:
        return {key: saved[key] for key in saved.files}


def state_from_saved(points, variant):
    tag = variant.tag + '_'
    return {**{key: points[tag+key] for key in ('first', 'raw', 'valid')},
            'point_counts': {key: points[tag+key] for key in COUNTS}}


def reference_records():
    p = read_json(PROTOCOL)
    path = REFERENCE_RUN / 'checkpoint.json'
    if file_hash(path) != p['step_dependency_checkpoint_sha256']:
        raise AssertionError('Closed step checkpoint changed')
    cp = read_json(path)
    result = []
    for identifier, record in cp['completed'].items():
        folder = REFERENCE_RUN / 'jobs' / identifier
        if file_hash(folder / 'report.json') != record['report_sha256']:
            raise AssertionError('Reference report changed')
        job, report = read_json(folder / 'configuration.json'), read_json(folder / 'report.json')
        if job['method']['dt'] != .02:
            continue
        for name, sha in report['output_sha256'].items():
            if file_hash(folder / name) != sha:
                raise AssertionError('Reference output changed')
        if any(signature().get(name) != sha for name, sha in report['source_signature'].items()
               if name in signature()):
            raise AssertionError('Reference numerical dependency changed')
        result.append((job, report, folder))
    if len(result) != 18:
        raise AssertionError('Expected 18 reusable 0.02s reference jobs')
    expected = {(c, m['id'], n) for c in p['cases'] for m in p['core_configs'] for n in p['conditions']}
    if {(j['case_id'], j['core_id'], j['condition']['id']) for j, _, _ in result} != expected:
        raise AssertionError('Reference comparison groups differ')
    return result


def label_path(case, tolerance):
    return RUN / 'labels' / case / f'tol{round(tolerance*1000):03d}.npz'


def prepare_inputs():
    p = read_json(PROTOCOL)
    if file_hash(pipeline.RUN / 'checkpoint.json') != p['joint_dependency_checkpoint_sha256']:
        raise AssertionError('Completed joint checkpoint changed')
    acceptance = read_json(ROOT / 'reports' / 'S0_acceptance.json')
    if acceptance['status'] != 'passed' or acceptance['target_count'] != 70000:
        raise AssertionError('Main target acceptance missing')
    evidence = []
    for case in p['cases']:
        guard()
        data, targets, mf = pipeline.core.load_case(p['partition'], case)
        if len(targets['xy']) != 70000 or len(np.unique(targets['xy'], axis=0)) != 70000:
            raise AssertionError('Unique main targets failed')
        if array_hash(targets['xy']) != mf['target_coordinates_sha256']:
            raise AssertionError('Target coordinates changed')
        ids = subset_indices(targets['group'], 35000)
        if len(ids) != 35000 or len(np.unique(ids)) != 35000:
            raise AssertionError('Density subset not unique')
        if not np.allclose(np.diff(data['time']), .02, atol=1e-10, rtol=0):
            raise AssertionError('Observation or scoring interval changed')
        if not np.allclose(np.diff(data['fine_time']), .005, atol=1e-10, rtol=0):
            raise AssertionError('Truth label reference interval differs')
        if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
            raise AssertionError('Independent truth convergence failed')
        fine = {'time': data['fine_time'], 'state': data['fine_state']}
        segments, body, right = complete_geometry(fine['state'])
        import shapely
        if not shapely.is_valid(body) or not shapely.is_valid(right):
            raise AssertionError('Truth geometry invalid')
        labels = {tol: label_contacts(targets['xy'], fine, segments, tolerance=tol) for tol in p['contact_tolerances_m']}
        for key in ('contact_time', 'contact_index', 'edge', 'front_ignored'):
            if not np.array_equal(labels[.05][key], targets[key], equal_nan=True):
                raise AssertionError('Reconstructed default truth labels differ: '+key)
        finite = [np.isfinite(labels[t]['contact_time']) for t in p['contact_tolerances_m']]
        if np.any(finite[0] & ~finite[1]) or np.any(finite[1] & ~finite[2]):
            raise AssertionError('Contact tolerance inclusion failed')
        previous = None
        for tolerance, current in labels.items():
            expected = shapely.dwithin(shapely.points(targets['xy']), body, tolerance+GEOMETRY_EPS)
            if not np.array_equal(expected, np.isfinite(current['contact_time'])):
                raise AssertionError('Continuous sweep and tolerance labels disagree')
            if previous is not None:
                both = np.isfinite(previous) & np.isfinite(current['contact_time'])
                if np.any(current['contact_time'][both] > previous[both]+1e-9):
                    raise AssertionError('Larger tolerance produces later first contact')
            previous = current['contact_time']
            path = label_path(case, tolerance)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                with np.load(path) as saved:
                    if any(not np.array_equal(saved[key], val, equal_nan=True) for key, val in current.items()):
                        raise AssertionError('Do not overwrite frozen sensitivity labels')
            else:
                np.savez_compressed(path, **current)
            label_meta = {'case_id': case, 'contact_tolerance_m': tolerance, 'files_sha256': file_hash(path),
                          'array_sha256': {key: array_hash(value) for key, value in current.items()},
                          'target_coordinates_sha256': mf['target_coordinates_sha256'], 'input_hashes': mf['files'],
                          'subset_indices_sha256': array_hash(ids), 'main_target_count': 70000}
            write_json_retry(path.with_suffix('.json'), label_meta)
        for condition in p['conditions']:
            desc = next(c for c in pipeline.condition_list() if c['id'] == condition)
            _, obs = pipeline.load_observation(p['partition'], case, desc)
            if obs['descriptor']['input_hashes'] != mf['files']:
                raise AssertionError('Shared raw observation differs from inputs')
        evidence.append({'case_id': case, 'target_coordinates_sha256': mf['target_coordinates_sha256'],
                         'original_contact_label_sha256': mf['contact_label_sha256'],
                         'subset_indices_sha256': array_hash(ids), 'input_hashes': mf['files']})
        print('FROZEN LABELS '+case, flush=True)
    return {'status': 'passed', 'source_signature': signature(), 'cases': evidence,
            'default_labels_reconstructed_exactly': True, 'continuous_geometry_labels_agree': True,
            'unique_main_points': 70000, 'unique_density_subset_points': 35000,
            'original_coordinates_and_labels_unchanged': True, 'new_prediction_jobs': 0}


def diagnostic_counts(targets, state, end):
    contact = targets['contact_time']
    eligible = (~targets['front_ignored']) & np.isfinite(contact) & (contact >= 2-1e-9) & (contact <= end+1e-9)
    right = eligible & (targets['edge'] == 2)
    negative = ~np.isfinite(contact)
    late = np.isfinite(state['valid']) & (contact-state['valid'] < 1-1e-9)
    missing = ~np.isfinite(state['valid'])
    fp = state['point_counts']['FP']
    total, never, early = int(fp.sum()), int(fp[negative].sum()), int(fp[eligible].sum())
    if total != never+early:
        raise AssertionError('False-alarm mechanisms do not account for all scored FP frames')
    return {'fp_frames_total': total, 'fp_never_contact_frames': never, 'fp_before_own_window_frames': early,
            'right_window_miss': int((right & missing).sum()), 'right_late': int((right & late).sum()),
            'right_late_boundary_group': int((right & late & (targets['group'] == 0)).sum()),
            'right_late_interior_group': int((right & late & (targets['group'] == 1)).sum())}


def reference_analysis():
    rows, diagnostics, provenance = [], [], []
    for job, report, folder in reference_records():
        data, targets, mf = pipeline.core.load_case(job['partition'], job['case_id'])
        _, obs = pipeline.load_observation(job['partition'], job['case_id'], job['condition'])
        if report['raw_sensor_hashes'] != obs['descriptor']['sensor_array_hashes'] or report['input_hashes'] != mf['files']:
            raise AssertionError('Reference shared observations or inputs changed')
        points = read_points(folder)
        old_rows = read_json(folder / 'summary.json')
        for v in read_json(PROTOCOL)['variants']:
            variant = pipeline.Variant(**v)
            state = state_from_saved(points, variant)
            full = pipeline.summarize(data, targets, state)
            old = next(r for r in old_rows if r['margin_m'] == variant.margin and r['confirmation_s'] == variant.confirmation)
            for key, value in full.items():
                if old[key] != value:
                    raise AssertionError('Reference score reconstruction differs: '+key)
            meta = {'case_id': job['case_id'], 'core_id': job['core_id'], 'condition': job['condition']['id'],
                    'EXIT_W_s': variant.exit_W, 'margin_m': variant.margin, 'confirmation_s': variant.confirmation,
                    'contact_tolerance_m': .05, 'reference_reused_without_new_prediction': True, 'job_id': job['id']}
            for count in read_json(PROTOCOL)['density_counts']:
                rows.append({**pipeline.summarize(data, targets, state, count), **meta})
            diagnostics.append({**meta, **diagnostic_counts(targets, state, full['score_end_s'])})
        provenance.append({'job_id': job['id'], 'report_sha256': file_hash(folder / 'report.json'),
                           'output_sha256': report['output_sha256']})
    csv_rows(RUN / 'reports' / 'baseline_failure_mechanisms.csv', diagnostics)
    write_json_retry(RUN / 'reports' / 'reference_reuse_manifest.json', {'reference_jobs': 18, 'new_predictions': 0,
                      'baseline_scores_reconstructed_exactly': True, 'records': provenance})
    write_json_retry(RUN / 'reference_rows.json', rows)
    return rows


def execute(job):
    if signature() != job['source_signature']:
        raise AssertionError('Frozen sensitivity source changed')
    guard()
    data, targets, mf = pipeline.core.load_case(job['partition'], job['case_id'])
    raw, obs = pipeline.load_observation(job['partition'], job['case_id'], job['condition'])
    path = label_path(job['case_id'], job['contact_tolerance_m'])
    label_meta = read_json(path.with_suffix('.json'))
    if file_hash(path) != label_meta['files_sha256']:
        raise AssertionError('Frozen tolerance labels changed')
    with np.load(path) as saved:
        targets = {**targets, **{key: saved[key] for key in saved.files}}
    start = time.perf_counter()
    inputs = {**data, **raw}
    variants = [pipeline.Variant(**v) for v in job['variants']]
    result = pipeline.evaluate(inputs, targets, pipeline.Method(**job['method']), variants)
    rows = []
    for state in result['states']:
        v = state['variant']
        for count in job['density_counts']:
            rows.append({**pipeline.summarize(inputs, targets, state, count), 'case_id': job['case_id'],
                         'core_id': job['core_id'], 'condition': job['condition']['id'], 'job_id': job['id'],
                         'EXIT_W_s': v.exit_W, 'margin_m': v.margin, 'confirmation_s': v.confirmation,
                         'contact_tolerance_m': job['contact_tolerance_m'], 'reference_reused_without_new_prediction': False})
    folder = RUN / 'jobs' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    write_json_retry(folder / 'configuration.json', job)
    write_json_retry(folder / 'summary.json', rows)
    write_json_retry(folder / 'timing.json', result['timing'])
    np.savez_compressed(folder / 'target_results.npz', **result['point_output'])
    np.savez_compressed(folder / 'frame_results.npz', counts=result['frame_counts'], time=data['time'], phase=result['observed_phase'])
    names = ('configuration.json', 'summary.json', 'timing.json', 'target_results.npz', 'frame_results.npz')
    report = {'id': job['id'], 'source_signature': job['source_signature'], 'input_hashes': mf['files'],
              'target_coordinates_sha256': mf['target_coordinates_sha256'], 'label_manifest_sha256': file_hash(path.with_suffix('.json')),
              'contact_label_sha256': array_hash(targets['contact_time']), 'label_file_sha256': file_hash(path),
              'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'], 'estimated_state': 'raw_shared_no_estimator',
              'score_start_s': 2., 'score_end_s': float(data['time'][-1]-3), 'target_count': 70000,
              'output_sha256': {name: file_hash(folder / name) for name in names}, 'wall_s': time.perf_counter()-start}
    write_json_retry(folder / 'report.json', report)
    return {'report_sha256': file_hash(folder / 'report.json')}


def verify(job, record):
    folder = RUN / 'jobs' / job['id']
    report = read_json(folder / 'report.json')
    if read_json(folder / 'configuration.json') != job or file_hash(folder / 'report.json') != record['report_sha256']:
        raise AssertionError('Completed configuration/report changed')
    if report['source_signature'] != signature():
        raise AssertionError('Completed source signature differs')
    for name, sha in report['output_sha256'].items():
        if file_hash(folder / name) != sha:
            raise AssertionError('Completed output hash differs')
    _, _, mf = pipeline.core.load_case(job['partition'], job['case_id'])
    _, obs = pipeline.load_observation(job['partition'], job['case_id'], job['condition'])
    path = label_path(job['case_id'], job['contact_tolerance_m'])
    label = read_json(path.with_suffix('.json'))
    if (report['input_hashes'] != mf['files'] or report['target_coordinates_sha256'] != mf['target_coordinates_sha256']
        or report['raw_sensor_hashes'] != obs['descriptor']['sensor_array_hashes']
        or report['contact_label_sha256'] != label['array_sha256']['contact_time']
        or report['label_file_sha256'] != file_hash(path) or report['label_manifest_sha256'] != file_hash(path.with_suffix('.json'))):
        raise AssertionError('Completed job inputs changed')
    return read_json(folder / 'summary.json'), report


def density_pairs(rows):
    blocks = {}
    for r in rows:
        key = tuple(r[k] for k in ('case_id', 'condition', 'core_id', 'contact_tolerance_m', 'margin_m', 'confirmation_s'))
        blocks.setdefault(key, {})[r['target_count']] = r
    pairs = []
    for key, block in blocks.items():
        if set(block) != {35000, 70000}:
            continue
        a, b = block[35000], block[70000]
        hold = blocks[(key[0], key[1], 'hold', *key[3:])]
        if set(hold) != {35000, 70000}:
            continue
        pair = dict(zip(('case_id', 'condition', 'core_id', 'contact_tolerance_m', 'margin_m', 'confirmation_s'), key))
        for metric in ('right_pct', 'negative_fp_pct', 'common_2s_reference_fpr_pct'):
            pair[metric+'_delta_pp'] = b[metric]-a[metric]
            pair[metric+'_paired_effect_change_pp'] = (b[metric]-hold[70000][metric])-(a[metric]-hold[35000][metric])
        pair['lead_p10_delta_s'] = None if a['right_lead_p10_s'] is None or b['right_lead_p10_s'] is None else b['right_lead_p10_s']-a['right_lead_p10_s']
        pairs.append(pair)
    return pairs


def conclude(cp, planned):
    rows = read_json(RUN / 'reference_rows.json')
    groups = {}
    for job in planned:
        if job['id'] not in cp['completed']:
            continue
        current, report = verify(job, cp['completed'][job['id']])
        rows.extend(current)
        key = (job['case_id'], job['condition']['id'], job['contact_tolerance_m'])
        shared = (report['target_coordinates_sha256'], report['contact_label_sha256'], report['score_start_s'], report['score_end_s'],
                  json.dumps(report['raw_sensor_hashes'], sort_keys=True))
        if key in groups and groups[key] != shared:
            raise AssertionError('Comparison does not share targets/labels/observations/scoring interval')
        groups[key] = shared
    pairs = density_pairs(rows)
    limits = read_json(PROTOCOL)['density_limits']
    complete = len(cp['completed']) == 36 and len(rows) == 216 and len(pairs) == 54
    stable = complete and all(abs(value) <= limits['metric_absolute_and_paired_effect_change_pp']
                             for r in pairs for key, value in r.items() if key.endswith('_pp'))
    stable = stable and all(r['lead_p10_delta_s'] is not None and abs(r['lead_p10_delta_s']) <= limits['lead_p10_change_s'] for r in pairs)
    csv_rows(RUN / 'reports' / 'sensitivity_scores.csv', rows)
    csv_rows(RUN / 'reports' / 'density_pairs.csv', pairs)
    tol_blocks = {}
    for r in rows:
        if r['target_count'] == 70000:
            key = tuple(r[k] for k in ('case_id', 'condition', 'core_id', 'margin_m', 'confirmation_s'))
            tol_blocks.setdefault(key, {})[r['contact_tolerance_m']] = r
    tolerance_pairs = []
    for key, block in tol_blocks.items():
        for tol in (.025, .1):
            if .05 not in block or tol not in block:
                continue
            a, b = block[.05], block[tol]
            pair = dict(zip(('case_id', 'condition', 'core_id', 'margin_m', 'confirmation_s'), key))
            pair.update({'label_tolerance_m': tol, 'right_delta_pp': b['right_pct']-a['right_pct'],
                         'negative_fp_delta_pp': b['negative_fp_pct']-a['negative_fp_pct'],
                         'right_window_miss_change': b['right_miss']-a['right_miss'],
                         'right_no_before_change': b['right_no_before']-a['right_no_before'],
                         'new_label_definition_not_a_new_algorithm': True})
            tolerance_pairs.append(pair)
    csv_rows(RUN / 'reports' / 'label_tolerance_pairs.csv', tolerance_pairs)
    result = {'status': 'subset_complete' if complete else 'partial_no_acceptance', 'completed_prediction_jobs': len(cp['completed']),
              'reference_jobs_reused': 18, 'new_prediction_jobs': len(cp['completed']), 'summary_rows': len(rows),
              'density_pair_rows': len(pairs), 'passes_subset_density_gate': bool(stable), 'default_truth_labels_reconstruction_passed': True,
              'all_completed_output_hashes_checked': True, 'comparison_groups_shared': True,
              'contact_tolerance_is_offline_label_sensitivity_not_online_radius_tuning': True,
              'S4_complete': False, 'S5_complete': False, 'physical_validation': False, 'captured_at_utc': utc_now()}
    write_json_retry(RUN / 'reports' / 'sensitivity_analysis.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def worker_probe():
    worker_init()
    p = read_json(PROTOCOL)
    data, _, _ = pipeline.core.load_case(p['partition'], p['cases'][0])
    return {'root': str(pipeline.common.ROOT), 'source_signature': signature(),
            'guard_defaults': list(pipeline.common.storage_guard.__defaults__), 'main_points': 70000,
            'observation_frames': len(data['time'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    p = read_json(PROTOCOL)
    deadline = datetime.fromisoformat(p['execution']['deadline_local'])
    if datetime.now(timezone.utc) >= deadline:
        parser.error('The authorized noon deadline has passed; do not submit new experiments')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        worker_init()
        guard()
        RUN.mkdir(parents=True, exist_ok=True)
        proof = prepare_inputs()
        reference_analysis()
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(worker_probe).result(timeout=180)
        if actual['source_signature'] != signature() or Path(actual['root']) != ROOT or actual['guard_defaults'] != list(pipeline.common.storage_guard.__defaults__):
            raise AssertionError('Actual Windows worker root/source/resource policy differs')
        proof['actual_worker_probe'] = actual
        for name, sha in signature().items():
            path = RUN / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and file_hash(path) != sha:
                raise AssertionError('Do not overwrite source snapshots')
            if not path.exists():
                path.write_bytes((ROOT / name).read_bytes())
        write_json_retry(RUN / 'preflight.json', proof)
        if args.check_only:
            print(json.dumps(proof, ensure_ascii=False), flush=True)
            return
        cp = read_json(RUN / 'checkpoint.json') if (RUN / 'checkpoint.json').exists() else {'completed': {}, 'source_signature': signature()}
        if cp['source_signature'] != signature():
            raise AssertionError('Cannot resume changed source/protocol')
        planned = jobs()
        remaining = []
        for job in planned:
            if job['id'] in cp['completed']:
                verify(job, cp['completed'][job['id']])
            elif (RUN / 'jobs' / job['id'] / 'report.json').exists():
                record = {'report_sha256': file_hash(RUN / 'jobs' / job['id'] / 'report.json')}
                verify(job, record)
                cp['completed'][job['id']] = record
            else:
                remaining.append(job)
        cp.update(status='running', prediction_jobs_expected=36, reference_jobs_reused=18, previous_completed_new_scoring_jobs=2076)
        started = True
        write_json_retry(RUN / 'runner_lock.json', {'pid': os.getpid(), 'status': 'running', 'deadline_local': deadline.isoformat(), 'time': utc_now()})
        write_json_retry(RUN / 'checkpoint.json', cp)
        print(f'STAGE S4_density_tolerance {len(remaining)}/36 remaining', flush=True)
        position = 0
        with ProcessPoolExecutor(max_workers=p['execution']['workers'], initializer=worker_init) as pool:
            futures = {}
            while position < len(remaining) or futures:
                while position < len(remaining) and len(futures) < p['execution']['submission_window_jobs']:
                    if datetime.now(timezone.utc) >= deadline:
                        position = len(remaining)
                        break
                    guard()
                    job = remaining[position]
                    futures[pool.submit(execute, job)] = job
                    position += 1
                if not futures:
                    break
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    job = futures.pop(future)
                    record = future.result()
                    verify(job, record)
                    cp['completed'][job['id']] = record
                    write_json_retry(RUN / 'checkpoint.json', cp)
                    print(f'DONE SENSITIVITY {len(cp["completed"])}/36 {job["id"]}', flush=True)
        cp['status'] = 'sensitivity_subset_complete_full_S4_not_complete' if len(cp['completed']) == 36 else 'deadline_checkpoint_saved'
        write_json_retry(RUN / 'checkpoint.json', cp)
        conclude(cp, planned)
    except BaseException as exc:
        if cp is not None and started:
            cp.update(status='failed_checkpoint_saved', error=repr(exc))
            write_json_retry(RUN / 'checkpoint.json', cp)
        raise
    finally:
        if started:
            if (RUN / 'checkpoint.json').exists():
                save_checkpoint_gzip(RUN / 'runtime_sessions' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_ended.json.gz'), (RUN / 'checkpoint.json').read_bytes())
            write_json_retry(RUN / 'runner_lock.json', {'pid': os.getpid(), 'status': 'stopped', 'time': utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
