from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_negative_census_v2'))
import run_census as census
import shapely
from geometry import complete_geometry, edge_union, GEOMETRY_EPS
from common import Vehicle, right_edge
from prediction import rollout

base, np, pipeline = census.base, census.np, census.pipeline
PROTOCOL = ROOT / 'protocol_temporal_trace_v2.json'
RUN = ROOT / 'runs' / 'resume_S4_temporal_trace_v2'
REGISTRY = ROOT / 'runs' / 'resume_S4_sampling_counterexamples_v1' / 'reports' / 'development_counterexamples.json'
COUNTS = ('TP', 'FP', 'ref_FP', 'support', 'negative_opportunities', 'ref_negative_opportunities')
EPS = 1e-9


def signature():
    result = census.signature()
    for path in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]:
        result[path.relative_to(ROOT).as_posix()] = base.file_hash(path)
    return result


def worker_init():
    p = base.read_json(PROTOCOL)['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def guard(submitting=False):
    pipeline.common.storage_guard()
    p = base.read_json(PROTOCOL)['execution']
    used = sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file()) if RUN.exists() else 0
    if used > p['new_run_budget_bytes']:
        raise RuntimeError('Trace run budget reached; preserve history')
    if submitting:
        total = sum(f.stat().st_size for f in ROOT.rglob('*') if f.is_file())
        if total+p['minimum_research_headroom_before_submit_bytes'] > p['experiment_budget_bytes']:
            raise RuntimeError('Insufficient research headroom; preserve checkpoint')


def target_paths(case):
    folder = RUN / 'targets' / case
    return folder / 'targets.npz', folder / 'manifest.json'


def confirmation_trace(time, hits, confirmation):
    hits = np.asarray(hits, dtype=bool)
    starts = np.full(hits.shape[1], np.nan)
    last = np.full(hits.shape[1], -2, dtype=np.int32)
    confirmed = np.zeros_like(hits)
    age = np.full(hits.shape, np.nan)
    for k, t in enumerate(time):
        active = hits[k]
        restarted = active & (last != k-1)
        starts[restarted] = t
        last[active] = k
        age[k, active] = t-starts[active]
        confirmed[k] = active & (t-starts >= confirmation-EPS)
    return confirmed, age


def trace_point_outputs(time, hits, contact, confirmation, score_end):
    confirmed, age = confirmation_trace(time, hits, confirmation)
    support = (contact[None, :] >= time[:, None]-EPS) & (contact[None, :] <= time[:, None]+2+EPS)
    started = time >= 2-EPS
    scoring = started & (time <= score_end+EPS)
    def first(mask):
        out = np.full(mask.shape[1], np.nan)
        present = mask.any(axis=0)
        out[present] = time[np.argmax(mask[:, present], axis=0)]
        return out
    before = contact[None, :] >= time[:, None]-EPS
    outputs = {'raw': first(hits), 'first': first(confirmed & started[:, None]),
               'valid': first(confirmed & started[:, None] & support)}
    outputs['TP'] = (confirmed & support & scoring[:, None]).sum(axis=0).astype(np.int32)
    outputs['FP'] = (confirmed & before & ~support & scoring[:, None]).sum(axis=0).astype(np.int32)
    outputs['ref_FP'] = outputs['FP'].copy()
    outputs['support'] = (support & scoring[:, None]).sum(axis=0).astype(np.int32)
    opportunities = (before & ~support & scoring[:, None]).sum(axis=0).astype(np.int32)
    outputs['negative_opportunities'] = opportunities
    outputs['ref_negative_opportunities'] = opportunities.copy()
    return outputs, confirmed, age, support


def witness_geometry_distance(sequence, xy, dt, vehicle):
    edge = right_edge(sequence, vehicle)
    points = shapely.points(xy)
    distance = np.empty((len(sequence), len(xy)))
    for k in range(len(sequence)):
        shape = edge_union(edge[k, :round(2/dt)+1])
        distance[k] = shapely.distance(points, shape)
    return distance


def prepare():
    p = base.read_json(PROTOCOL)
    if base.file_hash(REGISTRY) != p['counterexample_registry_sha256']:
        raise AssertionError('Frozen counterexample registry changed')
    if base.file_hash(REGISTRY.with_name('counterexample_analysis.json')) != p['counterexample_analysis_sha256']:
        raise AssertionError('Counterexample acceptance changed')
    if base.file_hash(census.RUN / 'checkpoint.json') != p['census_v2_checkpoint_sha256']:
        raise AssertionError('Closed census checkpoint changed')
    registry = base.read_json(REGISTRY)
    proofs = []
    for case in p['cases']:
        guard()
        data, main, mf = pipeline.core.load_case('development_v2_n70000', case)
        old_path, old_meta = census.target_paths(case)
        meta = base.read_json(old_meta)
        if base.file_hash(old_path) != meta['target_file_sha256']:
            raise AssertionError('Frozen reference targets changed')
        with np.load(old_path) as saved:
            old = {key: saved[key] for key in saved.files}
        witnesses = [point for point in registry['points'] if point['case_id'] == case]
        witness_ids = np.asarray(sorted(point['target_index'] for point in witnesses), dtype=np.int32)
        original_ids = old['main_ids']
        added = np.setdiff1d(witness_ids, original_ids)
        reference_ids = np.concatenate((original_ids, added)).astype(np.int32)
        if np.any(reference_ids >= 280000):
            raise AssertionError('Diagnostic references must belong to the preserved 280k arrays')
        targets = {key: old[key][reference_ids] for key in ('xy', 'group', 'contact_time', 'contact_index', 'edge', 'front_ignored')}
        positions = {int(index): k for k, index in enumerate(reference_ids)}
        targets.update(reference_ids=reference_ids, main_ids=np.arange(70000, dtype=np.int32),
                       witness_reference_ids=witness_ids,
                       witness_positions=np.asarray([positions[int(index)] for index in witness_ids], dtype=np.int32))
        if len(np.unique(targets['xy'], axis=0)) != len(reference_ids) or len(main['xy']) != 70000:
            raise AssertionError('Diagnostic targets must preserve 70000 unique main points')
        for key in ('xy', 'group', 'contact_time', 'edge', 'front_ignored'):
            if not np.array_equal(targets[key][:70000], main[key], equal_nan=True):
                raise AssertionError('Original 70000 coordinates/labels/order changed')
        for point in witnesses:
            k = positions[point['target_index']]
            if targets['xy'][k].tolist() != point['xy_m'] or targets['contact_time'][k] != point['contact_time_s'] or targets['edge'][k] != 2:
                raise AssertionError('Counterexample coordinate or label changed')
        cut = data['time'][-1]-3
        w = targets['witness_positions']
        if not np.all((targets['contact_time'][w] >= 2-EPS) & (targets['contact_time'][w] <= cut+EPS) & ~targets['front_ignored'][w]):
            raise AssertionError('Witnesses outside common eligible RIGHT interval')
        if not np.allclose(np.diff(data['fine_time']), .005, rtol=0, atol=1e-10) or not np.allclose(np.diff(data['time']), .02, rtol=0, atol=1e-10):
            raise AssertionError('Truth or observation time grid changed')
        if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
            raise AssertionError('Truth reference convergence failed')
        _, body, right = complete_geometry(data['fine_state'])
        if not shapely.is_valid(body) or not shapely.is_valid(right):
            raise AssertionError('Reference geometry invalid')
        expected = shapely.dwithin(shapely.points(targets['xy']), body, .05+GEOMETRY_EPS)
        if not np.array_equal(expected, np.isfinite(targets['contact_time'])):
            raise AssertionError('Continuous geometry and frozen contact labels disagree')
        for condition in p['conditions']:
            c = next(c for c in pipeline.condition_list() if c['id'] == condition)
            _, obs = pipeline.load_observation('development_v2_n70000', case, c)
            if obs['descriptor']['input_hashes'] != mf['files']:
                raise AssertionError('Common raw observations differ')
        path, manifest_path = target_paths(case)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with np.load(path) as saved:
                if set(saved.files) != set(targets) or any(not np.array_equal(saved[key], value, equal_nan=True) for key, value in targets.items()):
                    raise AssertionError('Frozen diagnostic inputs changed')
        else:
            np.savez_compressed(path, **targets)
        proof = {'case_id': case, 'target_count': len(reference_ids), 'main_count': 70000, 'witness_count': len(w),
                 'target_file_sha256': base.file_hash(path), 'arrays_sha256': {key: base.array_hash(v) for key, v in targets.items()},
                 'input_hashes': mf['files'], 'reference_target_sha256': meta['target_file_sha256'],
                 'registry_sha256': p['counterexample_registry_sha256'], 'source_signature': signature()}
        census.freeze_json(manifest_path, proof)
        proofs.append(proof)
        print('FROZEN TRACE TARGETS '+case, flush=True)
    return {'status': 'passed', 'cases': proofs, 'source_signature': signature(), 'diagnostic_predictions_completed': 0}


def jobs():
    p = base.read_json(PROTOCOL)
    result = []
    for reference in census.jobs():
        ref = reference['reference']
        if ref['case_id'] not in p['cases'] or ref['core_id'] not in p['core_ids'] or ref['condition']['id'] not in p['conditions']:
            continue
        if ref['variants'] != p['variants'] or ref['method']['dt'] != p['prediction_dt_s']:
            raise AssertionError('Diagnostic replay must keep all frozen parameters unchanged')
        job = {'census_job': reference, 'source_signature': signature(), 'stage': 'fixed_configuration_temporal_trace'}
        job['id'] = ref['case_id']+'__'+ref['core_id']+'__'+ref['condition']['id']+'__'+hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
        result.append(job)
    if len(result) != p['diagnostic_prediction_jobs'] or len({j['id'] for j in result}) != len(result):
        raise AssertionError('Trace job matrix differs from registered design')
    return result


def reference_points(job):
    reference = job['census_job']
    cp = base.read_json(census.RUN / 'checkpoint.json')
    _, report = census.verify(reference, cp['completed'][reference['id']])
    points, _, _ = census.read_reference(reference['reference'])
    return points, report, cp['completed'][reference['id']]['report_sha256']


def trace_rows(time, targets, arrays, variant):
    tag = variant.tag
    rows = []
    for column, index in enumerate(targets['witness_reference_ids']):
        position = targets['witness_positions'][column]
        contact = float(targets['contact_time'][position])
        support = arrays[tag+'_support'][:, column] & arrays['score_frame']
        hit = arrays[tag+'_raw_hit'][:, column]
        confirmed = arrays[tag+'_confirmed'][:, column]
        age = arrays[tag+'_continuous_age_s'][:, column]
        detected = bool((confirmed & support).any())
        if detected:
            diagnosis = 'window_detected'
        elif (hit & support).any():
            diagnosis = 'raw_window_hits_not_sustained_for_confirmation'
        elif (confirmed & (time < contact-2-EPS)).any():
            diagnosis = 'no_geometry_hit_in_effective_window_after_earlier_alarm'
        else:
            diagnosis = 'geometry_hits_only_outside_effective_window_or_absent'
        before = time[confirmed & (time < contact-2-EPS)]
        raw_inside = time[hit & support]
        active_age = age[hit & support]
        rows.append({'target_reference_index': int(index), 'variant': tag, 'contact_time_s': contact,
                     'support_start_s': contact-2, 'raw_hit_frames_in_window': int((hit & support).sum()),
                     'confirmed_frames_in_window': int((confirmed & support).sum()), 'window_miss': not detected,
                     'last_confirmed_before_window_s': float(before[-1]) if len(before) else None,
                     'first_raw_hit_in_window_s': float(raw_inside[0]) if len(raw_inside) else None,
                     'max_continuous_hit_age_in_window_s': float(active_age.max()) if len(active_age) else None,
                     'trace_based_diagnosis': diagnosis})
    return rows


def execute(job):
    guard()
    if signature() != job['source_signature']:
        raise AssertionError('Frozen trace source changed')
    ref = job['census_job']['reference']
    expected, old_report, ref_sha = reference_points(job)
    data, _, mf = pipeline.core.load_case(ref['partition'], ref['case_id'])
    raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    if obs['descriptor']['sensor_array_hashes'] != old_report['raw_sensor_hashes']:
        raise AssertionError('Raw inputs differ from frozen census')
    path, manifest_path = target_paths(ref['case_id'])
    meta = base.read_json(manifest_path)
    if base.file_hash(path) != meta['target_file_sha256']:
        raise AssertionError('Frozen trace targets changed')
    with np.load(path) as saved:
        targets = {key: saved[key] for key in saved.files}
    inputs = {**data, **raw}
    method = pipeline.Method(**ref['method'])
    variants = [pipeline.Variant(**v) for v in ref['variants']]
    vehicle = Vehicle()
    result = pipeline.evaluate(inputs, targets, method, variants, vehicle=vehicle, retain_sequence=True)
    for key, array in result['point_output'].items():
        if not np.array_equal(array, expected[key][targets['reference_ids']], equal_nan=True):
            raise AssertionError('Diagnostic per-point outputs differ from frozen reference: '+key)
    positions = targets['witness_positions']
    contact = targets['contact_time'][positions]
    time = inputs['time']
    cut = float(time[-1]-3)
    distance = witness_geometry_distance(result['sequence'], targets['xy'][positions], method.dt, vehicle)
    trace = {'time': time, 'witness_reference_ids': targets['witness_reference_ids'], 'witness_xy': targets['xy'][positions],
             'contact_time': contact, 'distance_m': distance, 'score_frame': (time >= 2-EPS) & (time <= cut+EPS),
             'observed_phase': result['observed_phase']}
    rows = []
    main_scores = []
    for v, state in zip(variants, result['states']):
        if v.exit_W != 2:
            raise AssertionError('Trace design fixes W=2 for both variants')
        hits = distance <= .05+v.margin+GEOMETRY_EPS
        outputs, confirmed, age, support = trace_point_outputs(time, hits, contact, v.confirmation, cut)
        for key, array in outputs.items():
            if not np.array_equal(array, result['point_output'][v.tag+'_'+key][positions], equal_nan=True):
                raise AssertionError('Saved trace logic does not reproduce evaluator: '+key)
        trace.update({v.tag+'_raw_hit': hits, v.tag+'_confirmed': confirmed, v.tag+'_continuous_age_s': age, v.tag+'_support': support})
        rows.extend({**row, 'case_id': ref['case_id'], 'core_id': ref['core_id'], 'condition': ref['condition']['id']}
                    for row in trace_rows(time, targets, trace, v))
        main_scores.append({**pipeline.summarize(inputs, targets, state, 70000), 'variant': v.tag,
                            'scope': 'original_70000_only_counterexamples_excluded_from_population_mean'})
    folder = RUN / 'jobs' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    base.write_json_retry(folder / 'configuration.json', job)
    base.write_json_retry(folder / 'main_scores.json', main_scores)
    base.write_json_retry(folder / 'trace_diagnoses.json', rows)
    np.savez_compressed(folder / 'point_results.npz', **result['point_output'])
    np.savez_compressed(folder / 'temporal_trace.npz', **trace)
    report = {'id': job['id'], 'source_signature': signature(), 'input_hashes': mf['files'],
              'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'], 'target_file_sha256': meta['target_file_sha256'],
              'target_manifest_sha256': base.file_hash(manifest_path), 'reference_report_sha256': ref_sha,
              'registry_sha256': base.file_hash(REGISTRY), 'all_original_and_witness_outputs_exact': True,
              'all_trace_point_counts_and_timestamps_exact': True, 'score_start_s': 2., 'score_end_s': cut,
              'point_array_sha256': {key: base.array_hash(v) for key, v in result['point_output'].items()},
              'trace_array_sha256': {key: base.array_hash(v) for key, v in trace.items()},
              'output_sha256': {name: base.file_hash(folder / name) for name in
                               ('configuration.json', 'main_scores.json', 'trace_diagnoses.json', 'point_results.npz', 'temporal_trace.npz')}}
    base.write_json_retry(folder / 'report.json', report)
    guard()
    return {'report_sha256': base.file_hash(folder / 'report.json')}


def verify(job, record):
    folder = RUN / 'jobs' / job['id']
    if base.file_hash(folder / 'report.json') != record['report_sha256'] or base.read_json(folder / 'configuration.json') != job:
        raise AssertionError('Trace configuration/report changed')
    report = base.read_json(folder / 'report.json')
    if report['source_signature'] != signature() or base.file_hash(REGISTRY) != report['registry_sha256']:
        raise AssertionError('Trace source/registry changed')
    for name, sha in report['output_sha256'].items():
        if base.file_hash(folder / name) != sha:
            raise AssertionError('Trace output changed')
    ref = job['census_job']['reference']
    expected, old_report, ref_sha = reference_points(job)
    if ref_sha != report['reference_report_sha256'] or old_report['input_hashes'] != report['input_hashes'] or old_report['raw_sensor_hashes'] != report['raw_sensor_hashes']:
        raise AssertionError('Trace shared reference inputs changed')
    path, manifest_path = target_paths(ref['case_id'])
    if base.file_hash(path) != report['target_file_sha256'] or base.file_hash(manifest_path) != report['target_manifest_sha256']:
        raise AssertionError('Trace targets changed')
    with np.load(path) as saved, np.load(folder / 'point_results.npz') as point_data, np.load(folder / 'temporal_trace.npz') as trace_data:
        targets = {key: saved[key] for key in saved.files}
        for key in point_data.files:
            if base.array_hash(point_data[key]) != report['point_array_sha256'][key] or not np.array_equal(point_data[key], expected[key][targets['reference_ids']], equal_nan=True):
                raise AssertionError('Stored trace point results changed')
        trace = {key: trace_data[key] for key in trace_data.files}
        if any(base.array_hash(trace[key]) != sha for key, sha in report['trace_array_sha256'].items()):
            raise AssertionError('Stored trace arrays changed')
        if not np.array_equal(trace['witness_reference_ids'], targets['witness_reference_ids']) or not np.array_equal(trace['witness_xy'], targets['xy'][targets['witness_positions']]):
            raise AssertionError('Trace point coordinates differ')
        for vdict in ref['variants']:
            v = pipeline.Variant(**vdict)
            hits = trace['distance_m'] <= .05+v.margin+GEOMETRY_EPS
            outputs, confirmed, age, support = trace_point_outputs(trace['time'], hits, trace['contact_time'], v.confirmation, report['score_end_s'])
            for suffix, value in (('raw_hit', hits), ('confirmed', confirmed), ('continuous_age_s', age), ('support', support)):
                if not np.array_equal(value, trace[v.tag+'_'+suffix], equal_nan=True):
                    raise AssertionError('Stored confirmation/geometry logic differs')
            for key, value in outputs.items():
                if not np.array_equal(value, point_data[v.tag+'_'+key][targets['witness_positions']], equal_nan=True):
                    raise AssertionError('Stored trace timestamps/counts differ')
    return base.read_json(folder / 'trace_diagnoses.json'), report


def save_cp(cp):
    path = RUN / 'checkpoint.json'
    base.write_json_retry(path, cp)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (base.file_hash(path)+'.json.gz'), path.read_bytes())


def probe():
    cases = []
    for case in base.read_json(PROTOCOL)['cases']:
        path, _ = target_paths(case)
        with np.load(path) as saved:
            cases.append({'id': case, 'target_count': len(saved['xy']), 'main_count': len(saved['main_ids']), 'witness_count': len(saved['witness_positions'])})
    return {'root': str(pipeline.common.ROOT), 'source_signature': signature(), 'cases': cases,
            'resource_defaults': list(pipeline.common.storage_guard.__defaults__)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    p = base.read_json(PROTOCOL)
    deadline = datetime.fromisoformat(p['execution']['deadline_local'])
    if datetime.now(timezone.utc) >= deadline:
        parser.error('Authorized 18:00 deadline passed')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        worker_init()
        guard()
        proof = prepare()
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=180)
        expected_cases = [{key: item[key] for key in ('case_id', 'target_count', 'main_count', 'witness_count')} for item in proof['cases']]
        expected_cases = [{'id': c.pop('case_id'), **c} for c in expected_cases]
        if actual != {'root': str(ROOT), 'source_signature': signature(), 'cases': expected_cases,
                      'resource_defaults': [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']]}:
            raise AssertionError('Actual Windows trace worker acceptance failed')
        proof['actual_worker_probe'] = actual
        for name, sha in signature().items():
            saved = RUN / 'source' / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and base.file_hash(saved) != sha:
                raise AssertionError('Frozen trace source snapshot changed')
            if not saved.exists():
                saved.write_bytes((ROOT / name).read_bytes())
        census.freeze_json(RUN / 'preflight.json', proof)
        if args.check_only:
            print(json.dumps({'status': 'preflight_passed', 'actual_worker': actual, 'diagnostic_predictions_completed': 0}), flush=True)
            return
        cp = base.read_json(RUN / 'checkpoint.json') if (RUN / 'checkpoint.json').exists() else {'completed': {}, 'source_signature': signature()}
        if cp['source_signature'] != signature():
            raise AssertionError('Cannot resume changed trace source')
        pending = []
        for job in jobs():
            if job['id'] in cp['completed']:
                verify(job, cp['completed'][job['id']])
            elif (RUN / 'jobs' / job['id'] / 'report.json').exists():
                record = {'report_sha256': base.file_hash(RUN / 'jobs' / job['id'] / 'report.json')}
                verify(job, record)
                cp['completed'][job['id']] = record
            else:
                pending.append(job)
        cp.update(status='running_diagnostic_trace', diagnostic_jobs_expected=12, formal_new_prediction_jobs_this_cycle=162,
                  formal_corrected_scoring_jobs_total=2238)
        started = True
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'deadline_local': deadline.isoformat(), 'time': base.utc_now()})
        save_cp(cp)
        position = 0
        with ProcessPoolExecutor(max_workers=p['execution']['workers'], initializer=worker_init) as pool:
            futures = {}
            while position < len(pending) or futures:
                while position < len(pending) and len(futures) < p['execution']['submission_window_jobs']:
                    if datetime.now(timezone.utc) >= deadline:
                        position = len(pending)
                        break
                    guard(submitting=True)
                    if datetime.now(timezone.utc) >= deadline:
                        position = len(pending)
                        break
                    job = pending[position]
                    futures[pool.submit(execute, job)] = job
                    print('SUBMIT TRACE '+job['id'], flush=True)
                    position += 1
                if not futures:
                    break
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    job = futures.pop(future)
                    record = future.result()
                    verify(job, record)
                    cp['completed'][job['id']] = record
                    save_cp(cp)
                    print(f'DONE TRACE {len(cp["completed"])}/12 {job["id"]}', flush=True)
        rows, shared = [], {}
        for job in jobs():
            if job['id'] not in cp['completed']:
                continue
            result, report = verify(job, cp['completed'][job['id']])
            rows.extend(result)
            ref = job['census_job']['reference']
            key = (ref['case_id'], ref['condition']['id'])
            common = (report['input_hashes'], report['raw_sensor_hashes'], report['target_file_sha256'], report['score_start_s'], report['score_end_s'])
            if key in shared and shared[key] != common:
                raise AssertionError('Trace methods did not share identical inputs/scoring')
            shared[key] = common
        cp['status'] = 'diagnostic_trace_complete' if len(cp['completed']) == 12 else 'deadline_checkpoint_saved'
        save_cp(cp)
        base.csv_rows(RUN / 'reports' / 'trace_diagnoses.csv', rows)
        base.write_json_retry(RUN / 'reports' / 'trace_diagnoses.json', {'rows': rows})
        result = {'status': cp['status'], 'diagnostic_predictions_completed': len(cp['completed']), 'diagnostic_jobs_expected': 12,
                  'formal_new_prediction_jobs_this_cycle_unchanged': 162, 'formal_corrected_scoring_jobs_total_unchanged': 2238,
                  'all_point_outputs_and_traces_verified': True, 'independent_validation': False,
                  'failed_foundation_gate_overridden': False, 'S4_complete': False, 'S5_complete': False,
                  'source_signature': signature(), 'checkpoint_sha256': base.file_hash(RUN / 'checkpoint.json')}
        base.write_json_retry(RUN / 'reports' / 'trace_analysis.json', result)
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': signature(), 'jobs': cp['completed'],
            'outputs_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in ('trace_diagnoses.csv', 'trace_diagnoses.json', 'trace_analysis.json')}})
        print(json.dumps({key: value for key, value in result.items() if key != 'source_signature'}), flush=True)
    except BaseException as error:
        if cp is not None and started:
            cp.update(status='failed_checkpoint_saved', error=repr(error))
            save_cp(cp)
        raise
    finally:
        if started:
            base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
