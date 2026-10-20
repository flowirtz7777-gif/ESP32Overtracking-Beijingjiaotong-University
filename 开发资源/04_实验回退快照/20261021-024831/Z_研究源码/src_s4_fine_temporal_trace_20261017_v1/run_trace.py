from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src_s4_fine_counterexamples_20261017_v1'))
import collect_counterexamples as c

HELPER = ROOT/'src_s4_temporal_trace_v2/run_trace.py'
spec = importlib.util.spec_from_file_location('frozen_temporal_helpers_20261017', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
base, np, pipeline, f, a = c.base, c.np, c.pipeline, c.f, c.a
Vehicle, GEOMETRY_EPS = helper.Vehicle, helper.GEOMETRY_EPS
confirmation_trace = helper.confirmation_trace
trace_point_outputs = helper.trace_point_outputs
witness_geometry_distance = helper.witness_geometry_distance
PROTOCOL = ROOT/'protocol_fine_temporal_trace_20261017_v1.json'
EXPECTED_PROTOCOL = '78a570b3a3b6799e240006fbfed823acd8e67ace1279663961729af437a2b46a'
RUN = ROOT/'runs/resume_20261017_fine_temporal_trace_v1'
EPS = 1e-9


def protocol():
    return base.read_json(PROTOCOL)


def signature():
    paths = [PROTOCOL, HELPER, ROOT/'管理脚本/test_s4_v1.py', *sorted(Path(__file__).parent.glob('*.py'))]
    return {**c.signature(), **{p.relative_to(ROOT).as_posix(): base.file_hash(p) for p in paths}}


def worker_init():
    p = protocol()['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def resources(extra=0):
    p = protocol()['execution']
    measured = pipeline.common.storage_guard(p['reserve_bytes'], p['experiment_budget_bytes'])
    used = sum(path.stat().st_size for path in RUN.rglob('*') if path.is_file()) if RUN.exists() else 0
    if not fits({**measured, 'run_bytes': used}, extra):
        raise RuntimeError('Temporal resource checkpoint; preserve history and stop')
    return {**measured, 'run_bytes': used}


def fits(measured, extra):
    p = protocol()['execution']
    return (measured['experiment_bytes']+extra <= p['experiment_budget_bytes']
            and measured['run_bytes']+extra <= p['new_run_budget_bytes']
            and measured['free_bytes']-extra >= p['reserve_bytes'])


def quotas(case):
    n, w, frames = (case[k] for k in ('diagnostic_target_count', 'catalog_points', 'observation_frames'))
    if any(type(value) is not int or value < 0 for value in (n, w, frames)):
        raise ValueError('Known nonnegative integer dimensions required')
    return {'input': math.ceil((60*n+8*w)*1.01)+2*1024**2,
            'job': math.ceil((96*n+(30*w+10)*frames+28*w)*1.01)+1024**2}


def freeze(path, payload):
    if path.exists():
        raise AssertionError('Frozen output already exists; do not overwrite')
    resources(len(payload)+8192)
    path.parent.mkdir(parents=True, exist_ok=True)
    until = time.monotonic()+30
    while True:
        try:
            with path.open('xb') as stream:
                stream.write(payload)
            break
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or time.monotonic() >= until or path.exists():
                raise
            time.sleep(.1)
    if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(payload).digest():
        raise AssertionError('Written bytes differ')


def put(path, value):
    resources(len(f.coarse.json_bytes(value))+8192)
    base.write_json_retry(path, value)


def save_cp(cp):
    blob = f.coarse.json_bytes(cp)
    packed = gzip.compress(blob, compresslevel=1, mtime=0)
    resources(len(blob)+len(packed)+16384)
    put(RUN/'checkpoint.json', cp)
    if (RUN/'checkpoint.json').read_bytes() != blob:
        raise AssertionError('Checkpoint serialization differs')
    freeze(RUN/'checkpoint_snapshots'/(hashlib.sha256(blob).hexdigest()+'.json.gz'), packed)


def expired():
    return datetime.now(timezone.utc) >= datetime.fromisoformat(protocol()['execution']['deadline_local'])


def dependencies():
    p = protocol()
    if base.file_hash(PROTOCOL) != EXPECTED_PROTOCOL:
        raise AssertionError('Frozen temporal diagnostic protocol changed')
    if base.read_json(c.RUN/'runner_lock.json')['status'] != 'stopped':
        raise AssertionError('Catalog active; do not read its checkpoint')
    c.dependencies()
    for path, sha in [(c.RUN/'checkpoint.json', p['catalog_checkpoint_sha256']),
                      (c.RUN/'reports/counterexample_catalog.json', p['catalog_summary_sha256']),
                      (c.RUN/'reports/manifest.json', p['catalog_manifest_sha256']),
                      (c.PROTOCOL, p['catalog_protocol_sha256']),
                      (ROOT/'src_s4_fine_counterexamples_20261017_v1/collect_counterexamples.py', p['catalog_source_sha256'])]:
        if base.file_hash(path) != sha:
            raise AssertionError('Frozen catalog dependency changed')
    cp = base.read_json(c.RUN/'checkpoint.json')
    if cp['status'] != 'readonly_counterexample_catalog_complete' or cp['source_signature'] != c.signature():
        raise AssertionError('Closed catalog source/completion differs')
    for name, sha in cp['source_signature'].items():
        if base.file_hash(ROOT/name) != sha or base.file_hash(c.RUN/'source'/name) != sha:
            raise AssertionError('Catalog source/snapshot changed')
    for case, record in cp['completed'].items():
        folder = c.RUN/'cases'/case
        if base.file_hash(folder/'catalog.json') != record['metadata_sha256'] or base.file_hash(folder/'catalog.npz') != record['npz_sha256']:
            raise AssertionError('Catalog array/metadata hash changed')
    receipt = base.read_json(c.RUN/'runtime_sessions/20261017_counterexample_catalog_close/close_receipt.json')
    if not receipt['mutex_reacquired_and_released_after_closure']:
        raise AssertionError('Catalog independent closure missing')
    if helper.pipeline is not pipeline or base.file_hash(HELPER) != base.file_hash(helper.RUN/'source'/HELPER.relative_to(ROOT)):
        raise AssertionError('Pure helper implementation changed from frozen temporal v2')
    return cp


def select_targets(targets, catalog_ids, expected_main=70000):
    main_ids = targets['main_ids']
    if main_ids.dtype != np.int32 or main_ids.shape != (expected_main,) or len(np.unique(main_ids)) != expected_main:
        raise AssertionError('Exact original main order/identity required')
    for ids in (main_ids, catalog_ids):
        if ids.dtype != np.int32 or ids.ndim != 1 or np.any(ids < 0) or np.any(ids >= len(targets['xy'])):
            raise AssertionError('Reference IDs dtype/range differs')
    if len(catalog_ids) and np.any(np.diff(catalog_ids) <= 0):
        raise AssertionError('Catalog must be complete sorted unique union')
    reference = np.concatenate((main_ids, np.setdiff1d(catalog_ids, main_ids, assume_unique=True))).astype(np.int32)
    positions = {int(value): index for index, value in enumerate(reference)}
    result = {key: targets[key][reference] for key in c.TARGET_FIELDS}
    result.update(reference_ids=reference, main_ids=np.arange(expected_main, dtype=np.int32),
                  catalog_reference_ids=catalog_ids.copy(), catalog_positions=np.asarray([positions[int(v)] for v in catalog_ids], np.int32))
    if len(np.unique(result['xy'], axis=0)) != len(reference):
        raise AssertionError('Diagnostic coordinates must be unique')
    return result


def target_paths(case):
    folder = RUN/'targets'/case
    return folder/'targets.npz', folder/'manifest.json'


def common_input(case, target, proof):
    p = protocol()
    case_id = case['id']
    data, main, mf = pipeline.core.load_case(p['partition'], case_id)
    ref_job = next(j for j in f.jobs() if j['case']['id'] == case_id)
    ref = ref_job['coarse_reference']['reference']
    raw, obs = pipeline.load_observation(p['partition'], case_id, ref['condition'])
    if len(raw['time']) != case['observation_frames'] or base.array_hash(raw['time']) != case['time_array_sha256'] or not np.array_equal(raw['time'], data['time']):
        raise AssertionError('Frozen observation grid differs')
    if obs['descriptor']['input_hashes'] != mf['files'] or mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
        raise AssertionError('Common input or frozen reference convergence differs')
    if not np.allclose(np.diff(data['fine_time']), .005, rtol=0, atol=1e-10) or not np.allclose(np.diff(data['time']), .02, rtol=0, atol=1e-10):
        raise AssertionError('Frozen truth/observation discretization changed')
    if len(main['xy']) != 70000 or len(target['xy']) != case['diagnostic_target_count']:
        raise AssertionError('Target dimensions differ')
    for key in c.TARGET_FIELDS:
        if key in main and base.array_hash(target[key][:70000]) != base.array_hash(main[key]):
            raise AssertionError('Original main target/label changed: '+key)
    _, body, right = helper.complete_geometry(data['fine_state'])
    if not helper.shapely.is_valid(body) or not helper.shapely.is_valid(right):
        raise AssertionError('Inherited reference geometry invalid')
    present = helper.shapely.dwithin(helper.shapely.points(target['xy']), body, .05+GEOMETRY_EPS)
    if not np.array_equal(present, np.isfinite(target['contact_time'])):
        raise AssertionError('Frozen contact presence disagrees with reference geometry')
    expected = {key: value for key, value in proof['common_inputs'].items()}
    common = {'input_hashes': mf['files'], 'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'],
              'estimated_state_sha256': base.array_hash(raw['state']), 'estimated_alpha_sha256': base.array_hash(raw['alpha']),
              'score_start_s': 2., 'score_end_s': float(raw['time'][-1]-3)}
    if common != expected:
        raise AssertionError('Shared raw observation/estimate/score identity differs')
    return common


def prepare_case(case):
    case_id = case['id']
    full, old_proof, old_sha = f.load_targets(case_id)
    meta = base.read_json(c.RUN/'cases'/case_id/'catalog.json')
    saved = c.readback((c.RUN/'cases'/case_id/'catalog.npz').read_bytes(), meta['arrays'])
    ids = saved['full_target_index']
    if base.array_hash(ids) != case['catalog_index_sha256'] or len(ids) != case['catalog_points']:
        raise AssertionError('Complete frozen catalog differs')
    for key in c.TARGET_FIELDS:
        if base.array_hash(full[key][ids]) != base.array_hash(saved[key]):
            raise AssertionError('Catalog coordinate/label changed')
    targets = select_targets(full, ids)
    if len(targets['xy']) != case['diagnostic_target_count']:
        raise AssertionError('Actual diagnostic target count differs')
    if not np.array_equal(targets['catalog_reference_ids'], ids):
        raise AssertionError('Catalog order changed')
    job = next(j for j in f.jobs() if j['case']['id'] == case_id)
    old_report = base.read_json(f.RUN/'jobs'/job['id']/'report.json')
    common = {key: old_report[key] for key in ('input_hashes', 'raw_sensor_hashes', 'estimated_state_sha256',
              'estimated_alpha_sha256', 'score_start_s', 'score_end_s')}
    proof = {'case_id': case_id, 'source_signature': signature(), 'full_fine_target_manifest_sha256': old_sha,
             'catalog_metadata_sha256': base.file_hash(c.RUN/'cases'/case_id/'catalog.json'),
             'catalog_checkpoint_sha256': protocol()['catalog_checkpoint_sha256'],
             'target_count': len(targets['xy']), 'main_count': 70000, 'catalog_count': len(ids),
             'arrays': c.descriptors(targets), 'common_inputs': common,
             'reference_geometry_scope': 'inherited_frozen_reference_convergence_and_contact_presence_not_continuous_domain_proof'}
    common_input(case, targets, proof)
    payload = f.coarse.npz_bytes(targets)
    c.readback(payload, proof['arrays'])
    proof['target_file_sha256'] = hashlib.sha256(payload).hexdigest()
    if len(payload)+len(f.coarse.json_bytes(proof)) > quotas(case)['input']:
        raise RuntimeError('Encoded target exceeds frozen input quota')
    resources(len(payload)+len(f.coarse.json_bytes(proof))+16384)
    path, manifest = target_paths(case_id)
    freeze(path, payload)
    c.readback(path.read_bytes(), proof['arrays'])
    freeze(manifest, f.coarse.json_bytes(proof))
    print('FROZEN FINE TEMPORAL TARGET '+case_id, flush=True)
    return proof


def load_targets(case_id):
    path, manifest = target_paths(case_id)
    proof = base.read_json(manifest)
    if base.file_hash(path) != proof['target_file_sha256'] or proof['source_signature'] != signature():
        raise AssertionError('Diagnostic input/source hash changed')
    return c.readback(path.read_bytes(), proof['arrays']), proof


def jobs():
    p, source = protocol(), signature()
    result = []
    for case in p['cases']:
        for core in p['core_ids']:
            ref = next(j for j in f.jobs() if j['case']['id'] == case['id'] and j['core_id'] == core)
            config = ref['coarse_reference']['reference']
            if config['variants'] != p['variants'] or config['method']['dt'] != p['prediction_dt_s'] or config['condition']['id'] != p['condition']:
                raise AssertionError('Original variant/method/condition changed')
            job = {'case': case, 'core_id': core, 'fine_reference_job': ref, 'source_signature': source,
                   'category': 'post_result_fixed_configuration_temporal_diagnostic_not_formal'}
            suffix = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
            job['id'] = case['id']+'__'+core+'__fine_trace__'+suffix
            result.append(job)
    if len(result) != p['diagnostic_prediction_jobs'] or len({j['id'] for j in result}) != len(result):
        raise AssertionError('Exactly nine frozen diagnostic jobs required')
    return result


def reference(job):
    fine_job = job['fine_reference_job']
    cp = base.read_json(f.RUN/'checkpoint.json')
    folder = f.RUN/'jobs'/fine_job['id']
    report = base.read_json(folder/'report.json')
    if (base.file_hash(f.RUN/'checkpoint.json') != protocol()['prediction_checkpoint_sha256']
            or base.file_hash(folder/'report.json') != cp['completed'][fine_job['id']]['report_sha256']
            or base.read_json(folder/'configuration.json') != fine_job or report['source_signature'] != f.signature()):
        raise AssertionError('Frozen full-fine reference binding changed')
    for name, sha in report['output_sha256'].items():
        if base.file_hash(folder/name) != sha:
            raise AssertionError('Frozen fine output changed')
    return a.reconstruct(fine_job, report), report


def describe_trace(trace, variants):
    rows = []
    time_axis = trace['time']
    for variant in variants:
        tag = variant.tag
        for column, index in enumerate(trace['catalog_reference_ids']):
            contact = float(trace['contact_time'][column])
            window = trace[tag+'_support'][:, column] & trace['score_frame']
            hit = trace[tag+'_raw_hit'][:, column]
            confirmed = trace[tag+'_confirmed'][:, column]
            age = trace[tag+'_continuous_age_s'][:, column]
            if (confirmed & window).any():
                diagnosis = 'window_detected'
            elif (hit & window).any():
                diagnosis = 'raw_window_hits_not_sustained_for_confirmation'
            elif (confirmed & (time_axis < contact-2-EPS)).any():
                diagnosis = 'no_geometry_hit_in_effective_window_after_earlier_alarm'
            else:
                diagnosis = 'geometry_hits_only_outside_effective_window_or_absent'
            inside = time_axis[hit & window]
            active_age = age[hit & window]
            before = time_axis[confirmed & (time_axis < contact-2-EPS)]
            rows.append({'full_target_index': int(index), 'variant': tag, 'contact_time_s': contact,
                'support_start_s': contact-2, 'raw_hit_frames_in_window': int((hit & window).sum()),
                'confirmed_frames_in_window': int((confirmed & window).sum()),
                'window_miss': not bool((confirmed & window).any()), 'trace_based_diagnosis': diagnosis,
                'first_raw_hit_in_window_s': float(inside[0]) if len(inside) else None,
                'max_continuous_hit_age_in_window_s': float(active_age.max()) if len(active_age) else None,
                'last_confirmed_before_window_s': float(before[-1]) if len(before) else None})
    return rows


def validate_trace(trace, point, targets, variants, score_end):
    positions = targets['catalog_positions']
    if not np.array_equal(trace['catalog_reference_ids'], targets['catalog_reference_ids']) or not np.array_equal(trace['catalog_xy'], targets['xy'][positions]):
        raise AssertionError('Trace target IDs/coordinates differ')
    if base.array_hash(trace['contact_time']) != base.array_hash(targets['contact_time'][positions]):
        raise AssertionError('Trace labels differ')
    mask = (trace['time'] >= 2-EPS) & (trace['time'] <= score_end+EPS)
    if not np.array_equal(mask, trace['score_frame']):
        raise AssertionError('Trace score frames differ')
    for v in variants:
        hits = trace['distance_m'] <= .05+v.margin+GEOMETRY_EPS
        outputs, confirmed, age, support = trace_point_outputs(trace['time'], hits, trace['contact_time'], v.confirmation, score_end)
        for key, value in [('raw_hit', hits), ('confirmed', confirmed), ('continuous_age_s', age), ('support', support)]:
            if base.array_hash(value) != base.array_hash(trace[v.tag+'_'+key]):
                raise AssertionError('Trace confirmation/age/support differs: '+key)
        for field, value in outputs.items():
            if base.array_hash(value) != base.array_hash(point[v.tag+'_'+field][positions]):
                raise AssertionError('Trace timestamp/count differs from frozen output: '+field)


def main_scores(inputs, targets, point, variants):
    scores = []
    for v in variants:
        state = {k: point[v.tag+'_'+k] for k in ('first', 'raw', 'valid')}
        state.update(variant=v, point_counts={k: point[v.tag+'_'+k] for k in f.COUNT_FIELDS})
        scores.append({'variant': v.tag, **f.coarse.projected_summary(inputs, targets, state, targets['main_ids'])})
    return scores


def execute(job):
    if signature() != job['source_signature']:
        raise AssertionError('Frozen diagnostic source changed')
    targets, proof = load_targets(job['case']['id'])
    config = job['fine_reference_job']['coarse_reference']['reference']
    data, _, _ = pipeline.core.load_case(config['partition'], config['case_id'])
    raw, _ = pipeline.load_observation(config['partition'], config['case_id'], config['condition'])
    inputs = {**data, **raw}
    expected, old_report = reference(job)
    if any(old_report[key] != value for key, value in proof['common_inputs'].items()):
        raise AssertionError('Reference/common observation/estimate/score changed')
    method = pipeline.Method(**config['method'])
    variants = [pipeline.Variant(**v) for v in protocol()['variants']]
    print('START FINE TEMPORAL PREDICTION '+job['id'], flush=True)
    result = pipeline.evaluate(inputs, targets, method, variants, vehicle=Vehicle(), retain_sequence=True)
    for key, array in result['point_output'].items():
        if base.array_hash(array) != base.array_hash(expected[key][targets['reference_ids']]):
            raise AssertionError('Replayed output differs from exact full-fine projection: '+key)
    del expected
    positions = targets['catalog_positions']
    cut = float(raw['time'][-1]-3)
    distance = witness_geometry_distance(result['sequence'], targets['xy'][positions], method.dt, Vehicle())
    trace = {'time': raw['time'], 'score_frame': (raw['time'] >= 2-EPS) & (raw['time'] <= cut+EPS),
        'observed_phase': result['observed_phase'], 'catalog_reference_ids': targets['catalog_reference_ids'],
        'catalog_xy': targets['xy'][positions], 'contact_time': targets['contact_time'][positions], 'distance_m': distance}
    for v in variants:
        hits = distance <= .05+v.margin+GEOMETRY_EPS
        _, confirmed, age, support = trace_point_outputs(raw['time'], hits, trace['contact_time'], v.confirmation, cut)
        trace.update({v.tag+'_raw_hit': hits, v.tag+'_confirmed': confirmed, v.tag+'_continuous_age_s': age, v.tag+'_support': support})
    validate_trace(trace, result['point_output'], targets, variants, cut)
    scores = main_scores(inputs, targets, result['point_output'], variants)
    old_scores = base.read_json(f.RUN/'jobs'/job['fine_reference_job']['id']/'summary.json')
    for row in scores:
        expected_row = next(r for r in old_scores if r['cohort'] == 'original_70000' and r['variant'] == row['variant'])
        if a.numeric_summary(expected_row) != a.numeric_summary(row):
            raise AssertionError('Original main mean changed by diagnostic target suffix')
    rows = describe_trace(trace, variants)
    blobs = {'configuration.json': f.coarse.json_bytes(job), 'main_scores.json': f.coarse.json_bytes(scores),
             'trace_diagnoses.json': f.coarse.json_bytes(rows), 'point_results.npz': f.coarse.npz_bytes(result['point_output']),
             'temporal_trace.npz': f.coarse.npz_bytes(trace)}
    point_desc, trace_desc = c.descriptors(result['point_output']), c.descriptors(trace)
    c.readback(blobs['point_results.npz'], point_desc)
    c.readback(blobs['temporal_trace.npz'], trace_desc)
    report = {'id': job['id'], 'source_signature': signature(), 'common_inputs': proof['common_inputs'],
              'target_manifest_sha256': base.file_hash(target_paths(job['case']['id'])[1]),
              'target_file_sha256': proof['target_file_sha256'], 'reference_report_sha256': base.file_hash(f.RUN/'jobs'/job['fine_reference_job']['id']/'report.json'),
              'point_arrays': point_desc, 'trace_arrays': trace_desc, 'catalog_count': len(positions),
              'main_count': 70000, 'full_fine_projection_exact': True, 'trace_timestamps_and_counts_exact': True,
              'output_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in blobs.items()}}
    blobs['report.json'] = f.coarse.json_bytes(report)
    payload_size = sum(map(len, blobs.values()))
    if payload_size > quotas(job['case'])['job']:
        raise RuntimeError('Actual trace payload exceeds complete frozen output quota')
    resources(payload_size+16384)
    folder = RUN/'jobs'/job['id']
    if folder.exists():
        raise AssertionError('Old diagnostic job output exists; preserve and stop')
    for name, blob in blobs.items():
        freeze(folder/name, blob)
    return {'report_sha256': base.file_hash(folder/'report.json'), 'actual_output_bytes': payload_size}


def verify(job, record):
    folder = RUN/'jobs'/job['id']
    report = base.read_json(folder/'report.json')
    if base.file_hash(folder/'report.json') != record['report_sha256'] or base.read_json(folder/'configuration.json') != job or report['source_signature'] != signature():
        raise AssertionError('Stored diagnostic config/source/report differs')
    for name, sha in report['output_sha256'].items():
        if base.file_hash(folder/name) != sha:
            raise AssertionError('Stored diagnostic output SHA differs')
    targets, proof = load_targets(job['case']['id'])
    if report['target_file_sha256'] != proof['target_file_sha256'] or report['target_manifest_sha256'] != base.file_hash(target_paths(job['case']['id'])[1]):
        raise AssertionError('Stored diagnostic target differs')
    common_input(job['case'], targets, proof)
    point = c.readback((folder/'point_results.npz').read_bytes(), report['point_arrays'])
    trace = c.readback((folder/'temporal_trace.npz').read_bytes(), report['trace_arrays'])
    expected, old_report = reference(job)
    for key, value in point.items():
        if base.array_hash(value) != base.array_hash(expected[key][targets['reference_ids']]):
            raise AssertionError('Stored point output not exact full-fine projection')
    if any(old_report[k] != v for k, v in report['common_inputs'].items()):
        raise AssertionError('Stored diagnostic common input differs')
    variants = [pipeline.Variant(**v) for v in protocol()['variants']]
    validate_trace(trace, point, targets, variants, proof['common_inputs']['score_end_s'])
    rows = describe_trace(trace, variants)
    if rows != base.read_json(folder/'trace_diagnoses.json'):
        raise AssertionError('Stored diagnosis differs from full trace')
    return rows, report


def probe():
    cases = []
    for case in protocol()['cases']:
        targets, proof = load_targets(case['id'])
        common = common_input(case, targets, proof)
        cases.append({'id': case['id'], 'target_count': len(targets['xy']), 'catalog_count': len(targets['catalog_positions']),
                      'array_descriptors': c.descriptors(targets), 'common_inputs': common})
    return {'python': sys.executable, 'root': str(ROOT), 'source_signature': signature(), 'cases': cases,
            'guard_defaults': list(pipeline.common.storage_guard.__defaults__), 'deadline': protocol()['execution']['deadline_local'],
            'blas_threads': {k: os.environ[k] for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
            'predictions_started_in_probe': 0}


def main():
    if expired():
        raise RuntimeError('No new run after today 14:00')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        if (RUN/'checkpoint.json').exists():
            raise AssertionError('Existing diagnostic attempt; never blindly rerun')
        worker_init()
        dependencies()
        p, source = protocol(), signature()
        initial_reserve = sum(quotas(case)['input']+3*quotas(case)['job'] for case in p['cases'])+p['execution']['initial_metadata_headroom_bytes']
        resources(initial_reserve)
        for name, sha in source.items():
            freeze(RUN/'source'/name, (ROOT/name).read_bytes())
        put(RUN/'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now(), 'phase': 'preflight_not_prediction'})
        started = True
        cp = {'status': 'fine_temporal_preflight_not_prediction', 'source_signature': source, 'completed': {}, 'targets_completed': {},
              'new_formal_predictions': 0, 'category': 'fixed_configuration_temporal_diagnostic'}
        save_cp(cp)
        proofs = []
        for case in p['cases']:
            if expired():
                raise RuntimeError('Deadline before new target preflight')
            proof = prepare_case(case)
            proofs.append(proof)
            cp['targets_completed'][case['id']] = base.file_hash(target_paths(case['id'])[1])
            save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=1800)
        expected_cases = [{'id': proof['case_id'], 'target_count': proof['target_count'], 'catalog_count': proof['catalog_count'],
                           'array_descriptors': proof['arrays'], 'common_inputs': proof['common_inputs']} for proof in proofs]
        if (Path(actual['python']) != Path(r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe') or actual['root'] != str(ROOT)
                or actual['source_signature'] != source or actual['cases'] != expected_cases or actual['deadline'] != p['execution']['deadline_local']
                or actual['guard_defaults'] != [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']]
                or set(actual['blas_threads'].values()) != {'1'}):
            raise AssertionError('Actual Windows full-input worker acceptance failed')
        freeze(RUN/'actual_worker.json', f.coarse.json_bytes(actual))
        freeze(RUN/'preflight.json', f.coarse.json_bytes({'status': 'all_three_inputs_actual_worker_and_resources_passed_before_predictions',
            'source_signature': source, 'actual_worker': actual, 'initial_worst_reservation_bytes': initial_reserve}))
        print('PREFLIGHT FINE TEMPORAL PASSED ALL THREE CASES', flush=True)
        cp['status'] = 'fine_temporal_diagnostic_running'
        save_cp(cp)
        rows, all_jobs = [], jobs()
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            for case in p['cases']:
                if expired():
                    break
                resources(3*quotas(case)['job']+p['execution']['case_block_headroom_bytes'])
                for job in [j for j in all_jobs if j['case']['id'] == case['id']]:
                    if expired():
                        break
                    resources(quotas(case)['job']+p['execution']['case_block_headroom_bytes'])
                    print('SUBMIT FINE TEMPORAL '+job['id'], flush=True)
                    record = pool.submit(execute, job).result()
                    got_rows, report = verify(job, record)
                    cp['completed'][job['id']] = record
                    save_cp(cp)
                    rows.extend({'case_id': case['id'], 'core_id': job['core_id'], **r} for r in got_rows)
                    print('DONE FINE TEMPORAL '+str(len(cp['completed']))+'/9 '+job['id'], flush=True)
        complete = len(cp['completed']) == 9
        counts = {tag: sum(r['trace_based_diagnosis'] == tag for r in rows) for tag in p['trace_based_descriptions_all_comparators']}
        summary = {'status': 'fine_temporal_diagnostic_complete' if complete else 'deadline_checkpoint_partial',
            'completed_diagnostic_jobs_pending_independent_close': len(cp['completed']), 'new_formal_predictions': 0,
            'baseline_formal': 2238, 'baseline_accepted_diagnostic': 30, 'baseline_accepted_numeric': 2268,
            'catalog_unique_points': 367, 'trace_comparator_rows': len(rows), 'diagnosis_counts_development_selected_only': counts,
            'complete_foundation_passed': False, 'old_density_failure_overridden': False, 'S4_M2_S5_complete': False,
            'not_causal_intervention_or_unseen_validation_or_vehicle_safety': True}
        if complete and len(rows) != 367*6:
            raise AssertionError('All catalog points across all six comparators required')
        freeze(RUN/'reports/temporal_diagnoses.json', f.coarse.json_bytes({'rows': rows}))
        freeze(RUN/'reports/temporal_summary.json', f.coarse.json_bytes(summary))
        cp['status'] = summary['status']
        save_cp(cp)
        freeze(RUN/'reports/manifest.json', f.coarse.json_bytes({'source_signature': source,
            'checkpoint_sha256': base.file_hash(RUN/'checkpoint.json'), 'jobs': cp['completed'],
            'outputs_sha256': {name: base.file_hash(RUN/'reports'/name) for name in ('temporal_diagnoses.json', 'temporal_summary.json')}}))
    except BaseException as error:
        if cp is not None:
            cp.update(status='fine_temporal_failed_checkpoint_saved', error=repr(error))
            save_cp(cp)
        raise
    finally:
        if started:
            put(RUN/'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
