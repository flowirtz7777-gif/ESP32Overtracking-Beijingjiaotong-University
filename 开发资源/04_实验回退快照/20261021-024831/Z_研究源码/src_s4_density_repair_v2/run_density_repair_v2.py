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
sys.path.insert(0, str(ROOT / 'src_s4_density_repair_v1'))
import run_density_repair as previous
base = previous.base
from geometry import generate_target_pool, subset_indices, complete_geometry, label_contacts, GEOMETRY_EPS

np = base.np
pipeline = base.pipeline
RUN = ROOT / 'runs' / 'morning_S4_density_repair_v2'
PROTOCOL = ROOT / 'protocol_density_repair_v2.json'


def signature():
    result = previous.signature()
    for path in [*sorted(Path(__file__).parent.glob('*.py')), PROTOCOL]:
        result[path.relative_to(ROOT).as_posix()] = base.file_hash(path)
    return result


def worker_init():
    p = base.read_json(PROTOCOL)['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def guard():
    measured = pipeline.common.storage_guard()
    used = sum(p.stat().st_size for p in RUN.rglob('*') if p.is_file()) if RUN.exists() else 0
    if used > base.read_json(PROTOCOL)['execution']['new_run_budget_bytes']:
        raise RuntimeError('Density-repair run budget reached; preserve history and stop')
    return {**measured, 'new_run_bytes': used}


def augment_pool(original, extra_xy, extra_groups, full_count):
    if full_count < len(original['xy']):
        raise ValueError('Supplementary set cannot drop original main targets')
    old = {tuple(row) for row in original['xy']}
    rows, groups = [], []
    for group in range(3):
        existing = original['xy'][original['group'] == group]
        required = full_count//3+(group < full_count % 3)-len(existing)
        selected = []
        for point in extra_xy[extra_groups == group]:
            if required == 0:
                break
            if tuple(point) not in old:
                selected.append(point)
                if len(selected) == required:
                    break
        if required < 0 or len(selected) != required:
            raise AssertionError('Insufficient unique near-field points; do not add far fillers')
        block = np.concatenate((existing, np.asarray(selected).reshape(-1, 2)))
        rows.append(block)
        groups.append(np.full(len(block), group, dtype=np.int8))
    xy, group = np.concatenate(rows), np.concatenate(groups)
    main_ids = subset_indices(group, len(original['xy']))
    if len(xy) != full_count or len(np.unique(xy, axis=0)) != full_count:
        raise AssertionError('Supplementary targets are not unique')
    if not np.array_equal(xy[main_ids], original['xy']) or not np.array_equal(group[main_ids], original['group']):
        raise AssertionError('Original main coordinates or order changed')
    return xy, group, main_ids


def reference_index():
    p = base.read_json(PROTOCOL)
    if base.file_hash(previous.RUN / 'checkpoint.json') != p['previous_checkpoint_sha256']:
        raise AssertionError('Closed 140k density checkpoint changed')
    cp = base.read_json(previous.RUN / 'checkpoint.json')
    analysis_path = previous.RUN / 'reports' / 'density_analysis.json'
    if base.file_hash(analysis_path) != p['previous_analysis_sha256']:
        raise AssertionError('Closed 140k density analysis changed')
    analyzed = base.read_json(analysis_path)
    if analyzed['status'] != 'density_repair_subset_complete' or analyzed['prediction_checkpoint_sha256'] != p['previous_checkpoint_sha256']:
        raise AssertionError('Completed 140k density analysis missing')
    result = {}
    for job in previous.jobs():
        scores, report = previous.verify(job, cp['completed'][job['id']])
        key = (job['case_id'], job['core_id'], job['condition']['id'], job['contact_tolerance_m'])
        folder = previous.RUN / 'jobs' / job['id']
        if not report['original_main_per_point_outputs_exactly_preserved']:
            raise AssertionError('Original main targets were not preserved by the reference')
        result[key] = {'folder': str(folder), 'report_sha256': base.file_hash(folder / 'report.json'), 'method': job['method'], 'report': report}
    if len(result) != 54:
        raise AssertionError('Expected 54 fully verified 140k reference groups')
    return result


def target_path(case, tolerance):
    return RUN / 'targets' / case / f'tol{round(tolerance*1000):03d}.npz'


def prepare():
    p = base.read_json(PROTOCOL)
    reference_index()
    proof = []
    import shapely
    for case in p['cases']:
        guard()
        data, main, mf = pipeline.core.load_case(p['partition'], case)
        if len(main['xy']) != p['main_target_count'] or len(np.unique(main['xy'], axis=0)) != p['main_target_count']:
            raise AssertionError('Original accepted targets not unique')
        with np.load(previous.target_path(case, .05)) as saved:
            original = {key: saved[key] for key in saved.files}
        segments, body, right = complete_geometry(data['fine_state'])
        if not shapely.is_valid(body) or not shapely.is_valid(right):
            raise AssertionError('Independent truth geometry invalid')
        extra_xy, extra_groups, sampling = generate_target_pool(body, right, maximum=p['supplementary_target_count'], spacing=p['supplementary_grid_spacing_m'])
        xy, group, previous_ids = augment_pool(original, extra_xy, extra_groups, p['supplementary_target_count'])
        main_ids = subset_indices(group, p['main_target_count'])
        if not np.array_equal(xy[main_ids], main['xy']) or not np.array_equal(group[main_ids], main['group']):
            raise AssertionError('Original 70000 main coordinates changed')
        new_mask = np.ones(len(xy), dtype=bool)
        new_mask[previous_ids] = False
        new_ids = np.flatnonzero(new_mask).astype(np.int32)
        if len(new_ids) != 140000:
            raise AssertionError('Expected 140000 new unique points')
        if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
            raise AssertionError('Independent reference convergence failed')
        if not np.allclose(np.diff(data['fine_time']), .005, rtol=0, atol=1e-10) or not np.allclose(np.diff(data['time']), .02, rtol=0, atol=1e-10):
            raise AssertionError('Truth/observation/scoring time grid changed')
        ref = {'time': data['fine_time'], 'state': data['fine_state']}
        for tolerance in p['contact_tolerances_m']:
            labels = label_contacts(xy, ref, segments, tolerance=tolerance)
            expected = shapely.dwithin(shapely.points(xy), body, tolerance+GEOMETRY_EPS)
            if not np.array_equal(expected, np.isfinite(labels['contact_time'])):
                raise AssertionError('Supplementary continuous geometry and labels disagree')
            with np.load(previous.target_path(case, tolerance)) as saved:
                if any(not np.array_equal(labels[key][previous_ids], saved[key], equal_nan=True)
                       for key in ('contact_time', 'contact_index', 'edge', 'front_ignored')):
                    raise AssertionError('Previous 140000-point labels changed')
            with np.load(base.label_path(case, tolerance)) as saved:
                if any(not np.array_equal(labels[key][main_ids], saved[key], equal_nan=True) for key in saved.files):
                    raise AssertionError('Original 70000-point labels changed')
            path = target_path(case, tolerance)
            path.parent.mkdir(parents=True, exist_ok=True)
            values = {'xy': xy, 'group': group, 'main_ids': main_ids, 'previous_ids': previous_ids, 'new_ids': new_ids, **labels}
            if path.exists():
                with np.load(path) as saved:
                    if any(not np.array_equal(saved[key], value, equal_nan=True) for key, value in values.items()):
                        raise AssertionError('Cannot overwrite frozen supplementary targets')
            else:
                np.savez_compressed(path, **values)
            meta = {'case_id': case, 'contact_tolerance_m': tolerance, 'file_sha256': base.file_hash(path),
                    'arrays_sha256': {key: base.array_hash(value) for key, value in values.items()},
                    'original_input_hashes': mf['files'], 'original_coordinate_sha256': mf['target_coordinates_sha256'],
                    'main_coordinates_exactly_preserved': True, 'unique_target_count': len(xy), 'sampling': sampling}
            base.write_json_retry(path.with_suffix('.json'), meta)
        for condition in p['conditions']:
            c = next(c for c in pipeline.condition_list() if c['id'] == condition)
            _, obs = pipeline.load_observation(p['partition'], case, c)
            if obs['descriptor']['input_hashes'] != mf['files']:
                raise AssertionError('Shared original observation differs')
        proof.append({'case_id': case, 'original_coordinate_sha256': mf['target_coordinates_sha256'],
                      'full_coordinate_sha256': base.array_hash(xy), 'main_ids_sha256': base.array_hash(main_ids),
                      'previous_ids_sha256': base.array_hash(previous_ids),
                      'unique_main_points': 70000, 'unique_previous_points': 140000, 'unique_supplementary_points': 280000})
        print('FROZEN NESTED TARGETS '+case, flush=True)
    return {'status': 'passed', 'cases': proof, 'source_signature': signature(),
            'main_and_previous_labels_all_three_tolerances_exactly_preserved': True, 'new_prediction_jobs': 0,
            'density_gate_still_pending': True, 'physical_validation': False}


def jobs():
    p, source = base.read_json(PROTOCOL), signature()
    conditions = {c['id']: c for c in pipeline.condition_list()}
    result = []
    for case in p['cases']:
        for core in p['core_configs']:
            for condition in p['conditions']:
                for tolerance in p['contact_tolerances_m']:
                    method = pipeline.Method(core['mode'], gain=core['gain'], decay_s=core['decay_s'], dt=p['predictor_dt_s'])
                    job = {'stage': 'S4_nested_density_repair_280k', 'partition': p['partition'], 'case_id': case,
                           'core_id': core['id'], 'condition': conditions[condition], 'method': asdict(method),
                           'variants': p['variants'], 'contact_tolerance_m': tolerance,
                           'density_counts': p['density_counts'], 'source_signature': source}
                    digest = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
                    job['id'] = f'{case}__{core["id"]}__{condition}__tol{round(tolerance*1000):03d}__{digest}'
                    result.append(job)
    if len(result) != p['prediction_jobs'] or len({j['id'] for j in result}) != len(result):
        raise AssertionError('Density-repair design job count differs')
    return result


def baseline_for(job):
    manifest = base.read_json(RUN / 'reference_manifest.json')
    key = '|'.join((job['case_id'], job['core_id'], job['condition']['id'], str(job['contact_tolerance_m'])))
    reference = manifest['groups'][key]
    if reference['method'] != job['method']:
        raise AssertionError('Main-target reference method differs')
    folder = Path(reference['folder'])
    if base.file_hash(folder / 'report.json') != reference['report_sha256']:
        raise AssertionError('Main-target reference report changed')
    for name, sha in reference['report']['output_sha256'].items():
        if base.file_hash(folder / name) != sha:
            raise AssertionError('Main-target reference output changed')
    return reference, base.read_points(folder)


def execute(job):
    if signature() != job['source_signature']:
        raise AssertionError('Frozen density-repair source/protocol changed')
    guard()
    data, _, mf = pipeline.core.load_case(job['partition'], job['case_id'])
    raw, obs = pipeline.load_observation(job['partition'], job['case_id'], job['condition'])
    path = target_path(job['case_id'], job['contact_tolerance_m'])
    meta = base.read_json(path.with_suffix('.json'))
    if base.file_hash(path) != meta['file_sha256']:
        raise AssertionError('Frozen supplementary targets changed')
    with np.load(path) as saved:
        targets = {key: saved[key] for key in saved.files}
    inputs = {**data, **raw}
    start = time.perf_counter()
    result = pipeline.evaluate(inputs, targets, pipeline.Method(**job['method']), [pipeline.Variant(**v) for v in job['variants']])
    reference, original_points = baseline_for(job)
    for key, current in result['point_output'].items():
        if not np.array_equal(current[targets['previous_ids']], original_points[key], equal_nan=True):
            raise AssertionError('Previous 140k per-point predictions/scores changed')
    rows = []
    for state in result['states']:
        variant = state['variant']
        for count in job['density_counts']:
            rows.append({**pipeline.summarize(inputs, targets, state, count), 'case_id': job['case_id'],
                         'core_id': job['core_id'], 'condition': job['condition']['id'], 'job_id': job['id'],
                         'contact_tolerance_m': job['contact_tolerance_m'], 'margin_m': variant.margin,
                         'confirmation_s': variant.confirmation, 'EXIT_W_s': variant.exit_W})
    folder = RUN / 'jobs' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    base.write_json_retry(folder / 'configuration.json', job)
    base.write_json_retry(folder / 'summary.json', rows)
    base.write_json_retry(folder / 'timing.json', result['timing'])
    delta = {key: value[targets['new_ids']] for key, value in result['point_output'].items()}
    reconstructed = reconstruct_delta(original_points, delta, targets['previous_ids'], targets['new_ids'], len(targets['xy']))
    full_hashes = {key: base.array_hash(value) for key, value in result['point_output'].items()}
    if any(base.array_hash(reconstructed[key]) != sha for key, sha in full_hashes.items()):
        raise AssertionError('Lossless delta reconstruction failed')
    np.savez_compressed(folder / 'new_target_results.npz', **delta)
    np.savez_compressed(folder / 'frame_results.npz', counts=result['frame_counts'], time=data['time'], phase=result['observed_phase'])
    names = ('configuration.json', 'summary.json', 'timing.json', 'new_target_results.npz', 'frame_results.npz')
    report = {'id': job['id'], 'source_signature': signature(), 'input_hashes': mf['files'],
              'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'], 'target_file_sha256': meta['file_sha256'],
              'target_manifest_sha256': base.file_hash(path.with_suffix('.json')), 'target_array_sha256': meta['arrays_sha256'],
              'original_main_per_point_outputs_exactly_preserved': True, 'baseline_report_sha256': reference['report_sha256'],
              'previous_140k_per_point_outputs_exactly_preserved': True,
              'full_point_arrays_sha256': full_hashes, 'storage_schema': 'lossless_delta_plus_frozen_previous_arrays',
              'reference_manifest_sha256': base.file_hash(RUN / 'reference_manifest.json'),
              'score_start_s': 2., 'score_end_s': float(data['time'][-1]-3),
              'output_sha256': {name: base.file_hash(folder / name) for name in names}, 'wall_s': time.perf_counter()-start}
    base.write_json_retry(folder / 'report.json', report)
    return {'report_sha256': base.file_hash(folder / 'report.json')}


def verify(job, record):
    folder = RUN / 'jobs' / job['id']
    if base.file_hash(folder / 'report.json') != record['report_sha256'] or base.read_json(folder / 'configuration.json') != job:
        raise AssertionError('Completed report/configuration changed')
    report = base.read_json(folder / 'report.json')
    if report['source_signature'] != signature():
        raise AssertionError('Completed source signature changed')
    for name, sha in report['output_sha256'].items():
        if base.file_hash(folder / name) != sha:
            raise AssertionError('Completed output changed')
    _, _, mf = pipeline.core.load_case(job['partition'], job['case_id'])
    _, obs = pipeline.load_observation(job['partition'], job['case_id'], job['condition'])
    path = target_path(job['case_id'], job['contact_tolerance_m'])
    if (base.file_hash(path) != report['target_file_sha256'] or base.file_hash(path.with_suffix('.json')) != report['target_manifest_sha256']
        or mf['files'] != report['input_hashes'] or obs['descriptor']['sensor_array_hashes'] != report['raw_sensor_hashes']):
        raise AssertionError('Completed shared inputs changed')
    if base.file_hash(RUN / 'reference_manifest.json') != report['reference_manifest_sha256']:
        raise AssertionError('Main-target reference manifest changed')
    _, old_points = baseline_for(job)
    with np.load(folder / 'new_target_results.npz') as saved:
        delta = {key: saved[key] for key in saved.files}
    with np.load(path) as saved:
        full = reconstruct_delta(old_points, delta, saved['previous_ids'], saved['new_ids'], len(saved['xy']))
    if any(base.array_hash(full[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
        raise AssertionError('Completed full-point reconstruction changed')
    return base.read_json(folder / 'summary.json'), report


def density_pairs(rows):
    blocks = {}
    for r in rows:
        key = tuple(r[k] for k in ('case_id', 'core_id', 'condition', 'contact_tolerance_m', 'margin_m', 'confirmation_s'))
        blocks.setdefault(key, {})[r['target_count']] = r
    pairs = []
    for key, block in blocks.items():
        hold = blocks.get((key[0], 'hold', *key[2:]), {})
        if set(block) != {140000, 280000} or set(hold) != {140000, 280000}:
            continue
        a, b = block[140000], block[280000]
        row = dict(zip(('case_id', 'core_id', 'condition', 'contact_tolerance_m', 'margin_m', 'confirmation_s'), key))
        for metric in ('right_pct', 'negative_fp_pct', 'common_2s_reference_fpr_pct'):
            row[metric+'_delta_pp'] = b[metric]-a[metric]
            row[metric+'_paired_effect_change_pp'] = (b[metric]-hold[280000][metric])-(a[metric]-hold[140000][metric])
        row['lead_p10_delta_s'] = None if a['right_lead_p10_s'] is None or b['right_lead_p10_s'] is None else b['right_lead_p10_s']-a['right_lead_p10_s']
        pairs.append(row)
    return pairs


def conclude(cp, planned):
    rows, groups = [], {}
    for job in planned:
        if job['id'] not in cp['completed']:
            continue
        current, report = verify(job, cp['completed'][job['id']])
        rows.extend(current)
        key = (job['case_id'], job['condition']['id'], job['contact_tolerance_m'])
        shared = (json.dumps(report['target_array_sha256'], sort_keys=True), json.dumps(report['raw_sensor_hashes'], sort_keys=True),
                  report['score_start_s'], report['score_end_s'])
        if key in groups and groups[key] != shared:
            raise AssertionError('Cross-method comparison is not paired')
        groups[key] = shared
    pairs = density_pairs(rows)
    complete = len(cp['completed']) == 54 and len(rows) == 216 and len(pairs) == 108
    limits = base.read_json(PROTOCOL)['density_limits']
    passed = complete and all(abs(v) <= limits['metric_absolute_and_paired_effect_change_pp'] for r in pairs for k, v in r.items() if k.endswith('_pp'))
    passed = passed and all(r['lead_p10_delta_s'] is not None and abs(r['lead_p10_delta_s']) <= limits['lead_p10_change_s'] for r in pairs)
    base.csv_rows(RUN / 'reports' / 'density_pairs.csv', pairs)
    base.csv_rows(RUN / 'reports' / 'density_scores.csv', rows)
    record = {'status': 'density_repair_subset_complete' if complete else 'partial_no_acceptance',
              'new_prediction_jobs_completed': len(cp['completed']), 'expected_prediction_jobs': 54,
              'summary_rows': len(rows), 'density_pair_rows': len(pairs), 'passes_subset_density_gate': bool(passed),
              'original_main_per_point_outputs_preserved': True, 'main_targets_not_replaced': True,
              'previous_140k_point_outputs_preserved': True, 'full_point_arrays_losslessly_reconstructed_and_hashed': True,
              'density_counts': [140000, 280000],
              'all_completed_output_and_input_hashes_verified': True, 'comparison_groups_shared': True,
              'prediction_checkpoint_sha256': base.file_hash(RUN / 'checkpoint.json'),
              'source_signature': signature(), 'S4_complete': False, 'S5_complete': False,
              'physical_validation': False, 'captured_at_utc': base.utc_now()}
    base.write_json_retry(RUN / 'reports' / 'density_analysis.json', record)
    print(json.dumps(record, ensure_ascii=False), flush=True)


def worker_probe():
    worker_init()
    p = base.read_json(PROTOCOL)
    path = target_path(p['cases'][0], .05)
    with np.load(path) as saved:
        n, main_n, previous_n = len(saved['xy']), len(saved['main_ids']), len(saved['previous_ids'])
    return {'root': str(pipeline.common.ROOT), 'source_signature': signature(), 'target_count': n,
            'main_target_count': main_n, 'previous_target_count': previous_n, 'guard_defaults': list(pipeline.common.storage_guard.__defaults__)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    p = base.read_json(PROTOCOL)
    deadline = datetime.fromisoformat(p['execution']['deadline_local'])
    if datetime.now(timezone.utc) >= deadline:
        parser.error('The authorized noon deadline has passed')
    kernel, mutex = pipeline.core.acquire_lock()
    started, cp = False, None
    try:
        worker_init()
        guard()
        RUN.mkdir(parents=True, exist_ok=True)
        proof = prepare()
        refs = reference_index()
        base.write_json_retry(RUN / 'reference_manifest.json', {'groups': {'|'.join((*key[:3], str(key[3]))): value for key, value in refs.items()},
                                                               'new_prediction_jobs': 0})
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(worker_probe).result(timeout=180)
        if (actual['source_signature'] != signature() or Path(actual['root']) != ROOT or actual['target_count'] != 280000
            or actual['main_target_count'] != 70000 or actual['previous_target_count'] != 140000
            or actual['guard_defaults'] != list(pipeline.common.storage_guard.__defaults__)):
            raise AssertionError('Actual Windows worker source/targets/resource acceptance failed')
        proof['actual_worker_probe'] = actual
        for name, sha in signature().items():
            path = RUN / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and base.file_hash(path) != sha:
                raise AssertionError('Frozen source snapshot changed')
            if not path.exists():
                path.write_bytes((ROOT / name).read_bytes())
        base.write_json_retry(RUN / 'preflight.json', proof)
        if args.check_only:
            print(json.dumps(proof, ensure_ascii=False), flush=True)
            return
        cp = base.read_json(RUN / 'checkpoint.json') if (RUN / 'checkpoint.json').exists() else {'completed': {}, 'source_signature': signature()}
        if cp['source_signature'] != signature():
            raise AssertionError('Cannot resume changed numerical source/protocol')
        planned, pending = jobs(), []
        for job in planned:
            if job['id'] in cp['completed']:
                verify(job, cp['completed'][job['id']])
            elif (RUN / 'jobs' / job['id'] / 'report.json').exists():
                record = {'report_sha256': base.file_hash(RUN / 'jobs' / job['id'] / 'report.json')}
                verify(job, record)
                cp['completed'][job['id']] = record
            else:
                pending.append(job)
        started = True
        cp.update(status='running', prediction_jobs_expected=54, previous_completed_new_scoring_jobs=2166)
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'deadline_local': deadline.isoformat(), 'time': base.utc_now()})
        base.write_json_retry(RUN / 'checkpoint.json', cp)
        print(f'STAGE S4_nested_density_repair_280k {len(pending)}/54 remaining', flush=True)
        position = 0
        with ProcessPoolExecutor(max_workers=p['execution']['workers'], initializer=worker_init) as pool:
            futures = {}
            while position < len(pending) or futures:
                while position < len(pending) and len(futures) < p['execution']['submission_window_jobs']:
                    if datetime.now(timezone.utc) >= deadline:
                        position = len(pending)
                        break
                    guard()
                    if datetime.now(timezone.utc) >= deadline:
                        position = len(pending)
                        break
                    job = pending[position]
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
                    base.write_json_retry(RUN / 'checkpoint.json', cp)
                    print(f'DONE DENSITY280 {len(cp["completed"])}/54 {job["id"]}', flush=True)
        cp['status'] = 'density_repair_subset_complete_full_S4_not_complete' if len(cp['completed']) == 54 else 'deadline_checkpoint_saved'
        base.write_json_retry(RUN / 'checkpoint.json', cp)
        conclude(cp, planned)
    except BaseException as exc:
        if cp is not None and started:
            cp.update(status='failed_checkpoint_saved', error=repr(exc))
            base.write_json_retry(RUN / 'checkpoint.json', cp)
        raise
    finally:
        if started:
            if (RUN / 'checkpoint.json').exists():
                base.save_checkpoint_gzip(RUN / 'runtime_sessions' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_ended.json.gz'),
                                          (RUN / 'checkpoint.json').read_bytes())
            base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


def reconstruct_delta(previous_points, delta, previous_ids, new_ids, count):
    if set(previous_points) != set(delta):
        raise AssertionError('Delta keys differ from previous point arrays')
    ids = np.concatenate((previous_ids, new_ids))
    if len(ids) != count or not np.array_equal(np.sort(ids), np.arange(count)):
        raise AssertionError('Reconstruction indices must cover each full target exactly once')
    result = {}
    for key, old in previous_points.items():
        if old.dtype != delta[key].dtype or len(old) != len(previous_ids) or len(delta[key]) != len(new_ids):
            raise AssertionError('Delta shape or dtype differs')
        full = np.empty(count, dtype=old.dtype)
        full[previous_ids] = old
        full[new_ids] = delta[key]
        result[key] = full
    return result


if __name__ == '__main__':
    main()
