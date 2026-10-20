"""Two fixed cross cells on the already frozen complete fine target populations."""
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src_s4_fine_factorial_20261017_1900_v1'))
import run_factorial as q
import factorial_analysis as factors

np, base, f, pipeline = q.np, q.base, q.f, q.pipeline
PROTOCOL = ROOT/'protocol_full_fine_cross_20261018_v1.json'
EXPECTED = '86d561fd5d5f8bbc348f494cc079faf8bbe7e3aaa52632b54c54edddd8e54cfc'
RUN = ROOT/'runs/resume_20261018_full_fine_cross_v1'
MATCHED = ROOT/'runs/resume_20261017_matched_factorial_2400_v1'
REPORT = ROOT/'reports/完整细栅格两交叉格覆盖补验_20261018_v1.md'
PYTHON = Path(r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe')


def require(value, message):
    if not value:
        raise AssertionError(message)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def protocol():
    require(base.file_hash(PROTOCOL) == EXPECTED, 'Frozen cross protocol differs')
    return base.read_json(PROTOCOL)


def expired():
    return datetime.now(timezone.utc) >= datetime.fromisoformat(protocol()['execution']['deadline_local'])


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def admin():
    path = ROOT/'管理脚本/register_20261017_2400_authorization_v1.py'
    require(path.read_bytes() == (ROOT/'runs/resume_20261017_2400_authorization_v1/source'/path.name).read_bytes(),
            'Bounded administrative helper differs')
    return module_at('bounded_writes_cross_only', path)


def execution_helper():
    path = ROOT/'管理脚本/close_authorization_20261017_1400_v3.py'
    require(path.read_bytes() == (ROOT/'runs/authorization_close_20261017_1400_v3/source'/path.name).read_bytes(),
            'Process/mutex evidence helper differs')
    return module_at('execution_cross_only', path)


def signature():
    require(base.read_json(MATCHED/'runner_lock.json')['status'] == 'stopped', 'Matched reference active')
    require(base.file_hash(MATCHED/'checkpoint.json') == protocol()['reference_matched_checkpoint_sha256'],
            'Closed matched CP changed')
    old = base.read_json(MATCHED/'checkpoint.json')['source_signature']
    paths = {ROOT/name for name in old}
    paths.update([PROTOCOL, ROOT/protocol()['authorization_file'],
                  ROOT/'管理脚本/register_20261018_1200_authorization_v1.py',
                  ROOT/'管理脚本/launch_full_fine_cross_20261018_v1.py',
                  ROOT/'管理脚本/close_authorization_20261017_1400_v3.py',
                  *Path(__file__).parent.glob('*.py')])
    return {p.relative_to(ROOT).as_posix(): base.file_hash(p) for p in sorted(paths)}


def resources(extra=0):
    d = admin().guard(extra)
    used = sum(p.stat().st_size for p in RUN.rglob('*') if p.is_file()) if RUN.exists() else 0
    require(used+extra <= protocol()['execution']['run_cap_bytes'], 'Cross run cap exceeded; preserve history')
    return {**d, 'run_bytes': used}


def freeze(path, payload):
    if path.exists():
        require(path.read_bytes() == payload, 'Immutable output differs; create a new version')
        return
    resources(len(payload)+16384)
    admin().freeze(path, payload)


def put(path, value):
    resources(len(encoded(value))+16384)
    base.write_json_retry(path, value)


def save_cp(cp):
    blob = f.coarse.json_bytes(cp)
    packed = gzip.compress(blob, mtime=0)
    resources(len(blob)+len(packed)+16384)
    put(RUN/'checkpoint.json', cp)
    require((RUN/'checkpoint.json').read_bytes() == blob, 'Checkpoint serialization differs')
    freeze(RUN/'checkpoint_snapshots'/(hashlib.sha256(blob).hexdigest()+'.json.gz'), packed)


def quota(n):
    require(type(n) is int and n >= 0, 'Measured integer target count required')
    return math.ceil(36*n*1.01)+2*1024**2


def worker_init():
    p = protocol()['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def dependencies():
    p = protocol()
    require(Path(sys.executable) == PYTHON, 'Exact Python required')
    require(base.file_hash(ROOT/p['authorization_file']) == p['authorization_sha256'], 'Human authorization differs')
    for run, expected in [(f.RUN, p['reference_fine_checkpoint_sha256']),
                          (q.RUN, p['reference_factorial_checkpoint_sha256']),
                          (MATCHED, p['reference_matched_checkpoint_sha256'])]:
        for path in run.glob('*runner_lock.json'):
            require(base.read_json(path)['status'] == 'stopped', 'Closed reference runner active')
        require(base.file_hash(run/'checkpoint.json') == expected, 'Closed reference CP changed')
    require(base.file_hash(Path(q.__file__)) == p['reference_factorial_source_sha256'], 'Frozen factorial source differs')
    audit = q.RUN/'runtime_sessions/20261017_1900_factorial_output_recheck/acceptance.json'
    require(base.file_hash(audit) == p['reference_factorial_output_audit_sha256'], 'Frozen output audit differs')
    bound = base.read_json(audit)['all_existing_run_file_sha256']
    for name, sha in bound.items():
        require(base.file_hash(q.RUN/name) == sha, 'Frozen factorial file differs: '+name)
    inherited = base.read_json(MATCHED/'checkpoint.json')['source_signature']
    for name, sha in inherited.items():
        require(base.file_hash(ROOT/name) == sha == base.file_hash(MATCHED/'source'/name),
                'Inherited source or source snapshot changed')
    return {'reference_files_verified': len(bound), 'inherited_source_files_verified': len(inherited)}


def reference_job(case_id, method):
    found = [j for j in q.jobs() if j['case']['id'] == case_id and j['core_id'] == method]
    require(len(found) == 1, 'Exactly one frozen factorial reference required')
    return found[0]


def jobs():
    result = []
    for case in protocol()['cases']:
        for method in protocol()['core_ids']:
            ref = reference_job(case['id'], method)
            conf = ref['fine_reference_job']['coarse_reference']['reference']
            require(conf['method']['dt'] == .02 and conf['condition']['id'] == 'noise100_s1'
                    and conf['variants'] == protocol()['old_control_variants_reused_without_prediction'],
                    'Frozen online method or observations differ')
            job = {'case': case, 'core_id': method, 'factorial_reference_job': ref,
                   'source_signature': signature(), 'category': 'fixed_two_cross_full_fine_development_diagnostic'}
            suffix = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
            job['id'] = case['id']+'__'+method+'__cross_full__'+suffix
            result.append(job)
    require(len(result) == 9 and len({x['id'] for x in result}) == 9, 'Fixed complete nine-job matrix required')
    return result


def load_inputs(case, geometry=False):
    full, proof, sha = f.load_targets(case['id'])
    target, old = q.load_targets(case['id'])
    require(len(full['xy']) == case['full_target_count'] and len(target['xy']) == case['diagnostic_target_count'],
            'Actual full or diagnostic population count differs')
    for field in f.FIELDS:
        require(base.array_hash(full[field][target['reference_ids']]) == base.array_hash(target[field]),
                'Complete original diagnostic coordinate/label projection differs')
    common = q.common_input(next(c for c in q.protocol()['cases'] if c['id'] == case['id']), target, old)
    data, main, mf = pipeline.core.load_case(protocol()['partition'], case['id'])
    ref = reference_job(case['id'], protocol()['core_ids'][0])['fine_reference_job']['coarse_reference']['reference']
    raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    require(len(raw['time']) == case['observation_frames'] < 65535, 'Observation uint16 index range differs')
    require(base.array_hash(raw['time']) == case['time_array_sha256'], 'Exact observation times differ')
    for field in f.FIELDS:
        if field in main:
            require(base.array_hash(full[field][full['main_ids']]) == base.array_hash(main[field]),
                    'Original main coordinates/labels/order changed')
    right = f.coarse.geometry.eligible_right(full, float(raw['time'][-1]-3))
    require(int(right.sum()) == case['fine_RIGHT_count'], 'Frozen complete RIGHT population differs')
    if geometry:
        require(len(np.unique(full['xy'], axis=0)) == len(full['xy']), 'Full coordinates not unique')
        _, body, edge = q.helper.complete_geometry(data['fine_state'])
        require(q.helper.shapely.is_valid(body) and q.helper.shapely.is_valid(edge), 'Reference geometry invalid')
        present = q.helper.shapely.dwithin(q.helper.shapely.points(full['xy']), body, .05+q.GEOMETRY_EPS)
        require(np.array_equal(present, np.isfinite(full['contact_time'])), 'Full contact presence/geometry differs')
    inputs = {**data, **raw}
    manifest = {'case_id': case['id'], 'source_signature': signature(),
                'frozen_full_target_manifest_sha256': sha, 'target_delta_sha256': proof['delta_file_sha256'],
                'full_target_array_sha256': proof['full_target_array_sha256'],
                'full_target_count': len(full['xy']), 'coarse_prefix_count': case['coarse_prefix_count'],
                'fine_RIGHT_count': int(right.sum()), 'main_ids_sha256': base.array_hash(full['main_ids']),
                'diagnostic_reference_ids_sha256': base.array_hash(target['reference_ids']),
                'common_inputs': common, 'target_storage': 'frozen_lossless_full_prefix_and_suffix_regeneration_reference'}
    require(common['input_hashes'] == mf['files'] and common['raw_sensor_hashes'] == obs['descriptor']['sensor_array_hashes'],
            'Raw observation input fairness differs')
    return full, target, inputs, manifest


def probe():
    dep = dependencies()
    manifests = []
    for case in protocol()['cases']:
        full, target, inputs, manifest = load_inputs(case, geometry=True)
        manifests.append(manifest)
    return {'python': sys.executable, 'root': str(ROOT), 'source_signature': signature(),
            'deadline': protocol()['execution']['deadline_local'],
            'guard_defaults': list(pipeline.common.storage_guard.__defaults__), 'cases': manifests,
            'dependency_checks': dep, 'resources': resources(protocol()['execution']['whole_batch_reservation_bytes']),
            'new_predictions_completed': 0}


def projection_check(job, full, target, point, inputs):
    ref = job['factorial_reference_job']
    folder = q.RUN/'jobs'/ref['id']
    report = base.read_json(folder/'report.json')
    old = q.c.readback((folder/'point_results.npz').read_bytes(), report['point_arrays'])
    require(base.file_hash(folder/'point_results.npz') == report['output_sha256']['point_results.npz'],
            'Frozen diagnostic point file differs')
    for key, value in point.items():
        require(base.array_hash(value[target['reference_ids']]) == base.array_hash(old[key]),
                'New full output not exact old diagnostic projection: '+key)
    variants = [pipeline.Variant(**v) for v in protocol()['variants']]
    rows = q.main_scores(inputs, full, point, variants)
    old_scores = base.read_json(folder/'main_scores.json')
    require(rows == [x for x in old_scores if x['variant'] in {v.tag for v in variants}],
            'Original 70000 new-cross summary differs')
    return rows


def independent_decode(packed, metadata, times):
    restored = {}
    require(set(packed) == set(metadata['arrays']) and len(packed) == 18, 'Exactly 18 packed point arrays required')
    for name, record in metadata['arrays'].items():
        code = packed[name]
        require(code.dtype == np.uint16 and list(code.shape) == record['shape'], 'uint16 shape/range contract differs')
        if name.endswith(('_first', '_raw', '_valid')):
            valid = code != 65535
            require(np.all(code[valid] < len(times)), 'Exact observation index out of range')
            value = np.full(code.shape, np.nan, np.dtype(record['dtype']))
            value[valid] = times[code[valid].astype(np.int64)]
        else:
            require(np.all(code <= len(times)), 'Per-point count outside observed-frame bound')
            value = code.astype(np.dtype(record['dtype']))
        require(base.array_hash(value) == record['array_sha256'], 'Independent decoded dtype/shape/bytes differ')
        restored[name] = value
    return restored


def execute(job):
    if expired():
        return {'not_submitted_prediction': True}
    require(signature() == job['source_signature'], 'New frozen source differs')
    full, target, inputs, manifest = load_inputs(job['case'])
    require(manifest == base.read_json(RUN/'inputs'/job['case']['id']/'manifest.json'), 'Admitted complete inputs differ')
    conf = job['factorial_reference_job']['fine_reference_job']['coarse_reference']['reference']
    print('START FULL FINE CROSS PREDICTION '+job['id'], flush=True)
    result = pipeline.evaluate(inputs, full, pipeline.Method(**conf['method']),
                               [pipeline.Variant(**v) for v in protocol()['variants']], vehicle=q.Vehicle())
    point = result['point_output']
    main = projection_check(job, full, target, point, inputs)
    packed, metadata = f.coarse.pack_points(point, inputs['time'])
    require(len(packed) == 18 and all(v.dtype == np.uint16 for v in packed.values()), 'Proven uint16 quota differs')
    independent_decode(packed, metadata, inputs['time'])
    blob = f.coarse.npz_bytes(packed)
    with np.load(__import__('io').BytesIO(blob)) as saved:
        reread = {k: saved[k] for k in saved.files}
    independent_decode(reread, metadata, inputs['time'])
    rows = f.summaries(inputs, full, result['states'], job)
    payloads = {'configuration.json': encoded(job), 'packed_points.npz': blob,
                'packed_metadata.json': encoded(metadata), 'summary.json': encoded(rows), 'main_scores.json': encoded(main),
                'frame_results.npz': f.coarse.npz_bytes({'time': inputs['time'], 'counts': result['frame_counts'],
                                                       'phase': result['observed_phase']}),
                'timing.json': encoded({**result['timing'], 'desktop_not_MCU': True})}
    report = {'id': job['id'], 'source_signature': signature(), 'input_manifest_sha256':
              base.file_hash(RUN/'inputs'/job['case']['id']/'manifest.json'), 'common_inputs': manifest['common_inputs'],
              'full_target_count': len(full['xy']), 'full_point_arrays': q.c.descriptors(point),
              'original_diagnostic_projection_exact': True, 'original_70000_summary_exact': True,
              'frame_arrays': q.c.descriptors({'time': inputs['time'], 'counts': result['frame_counts'],
                                              'phase': result['observed_phase']}),
              'output_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()}}
    payloads['report.json'] = encoded(report)
    require(sum(map(len, payloads.values())) <= quota(len(full['xy'])), 'Measured complete output exceeds quota')
    resources(sum(map(len, payloads.values()))+16384)
    folder = RUN/'jobs'/job['id']
    require(not folder.exists(), 'Job already exists; preserve it')
    for name, value in payloads.items():
        freeze(folder/name, value)
    return {'report_sha256': base.file_hash(folder/'report.json'), 'output_bytes': sum(map(len, payloads.values()))}


def verify_job(job, record):
    folder = RUN/'jobs'/job['id']
    require(base.file_hash(folder/'report.json') == record['report_sha256'], 'Closed job report differs')
    report = base.read_json(folder/'report.json')
    require(report['source_signature'] == signature() and base.read_json(folder/'configuration.json') == job,
            'Stored new source/configuration differs')
    for name, sha in report['output_sha256'].items():
        require(base.file_hash(folder/name) == sha, 'Stored new output differs: '+name)
    full, target, inputs, manifest = load_inputs(job['case'])
    require(manifest == base.read_json(RUN/'inputs'/job['case']['id']/'manifest.json')
            and report['common_inputs'] == manifest['common_inputs'], 'Stored common inputs differ')
    with np.load(folder/'packed_points.npz') as saved:
        packed = {k: saved[k] for k in saved.files}
    metadata = base.read_json(folder/'packed_metadata.json')
    point = independent_decode(packed, metadata, inputs['time'])
    require(q.c.descriptors(point) == report['full_point_arrays'], 'Original complete array dtype/shape/SHA differs')
    projection_check(job, full, target, point, inputs)
    variants = [pipeline.Variant(**v) for v in protocol()['variants']]
    states = [state_for(point, v) for v in variants]
    require(f.summaries(inputs, full, states, job) == base.read_json(folder/'summary.json'), 'Stored complete summaries differ')
    q.c.readback((folder/'frame_results.npz').read_bytes(), report['frame_arrays'])
    return full, target, inputs, point, report


def state_for(point, variant):
    state = {k: point[variant.tag+'_'+k] for k in ('first', 'raw', 'valid')}
    return {**state, 'variant': variant, 'point_counts': {k: point[variant.tag+'_'+k] for k in f.COUNT_FIELDS}}


def mask_encode(indices, length):
    indices = np.asarray(indices)
    require(indices.dtype == np.int32 and indices.ndim == 1 and np.all(indices >= 0)
            and np.all(indices < length) and (not len(indices) or np.all(np.diff(indices) > 0)),
            'Sorted unique in-range int32 indices required')
    mask = np.zeros(length, bool)
    mask[indices] = True
    packed = np.packbits(mask, bitorder='little')
    meta = {'length': length, 'index_count': len(indices), 'indices_sha256': base.array_hash(indices),
            'packed_sha256': base.array_hash(packed), 'bitorder': 'little'}
    require(np.array_equal(mask_decode(packed, meta), indices), 'Miss-index packbits readback differs')
    return packed, meta


def mask_decode(packed, meta):
    require(packed.dtype == np.uint8 and packed.shape == ((meta['length']+7)//8,), 'Packbits dimension differs')
    require(base.array_hash(packed) == meta['packed_sha256'], 'Packed miss mask differs')
    bits = np.unpackbits(packed, bitorder='little')
    require(not bits[meta['length']:].any(), 'Nonzero padding bits')
    ids = np.flatnonzero(bits[:meta['length']]).astype(np.int32)
    require(len(ids) == meta['index_count'] and base.array_hash(ids) == meta['indices_sha256'],
            'Exact miss indices differ')
    return ids


def main():
    require(not expired() and not RUN.exists(), 'Expired or already existing new batch; do not duplicate')
    worker_init()
    kernel, mutex = pipeline.core.acquire_lock()
    cp = {'status': 'preflight_not_prediction', 'source_signature': signature(), 'completed': {}, 'new_formal_predictions': 0}
    try:
        resources(protocol()['execution']['whole_batch_reservation_bytes'])
        put(RUN/'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now(),
                                    'phase': 'complete_input_preflight_not_prediction'})
        for name in signature():
            freeze(RUN/'source'/name, (ROOT/name).read_bytes())
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result()
            require(actual['source_signature'] == signature() and Path(actual['python']) == PYTHON
                    and actual['root'] == str(ROOT) and len(actual['cases']) == 3
                    and actual['deadline'] == protocol()['execution']['deadline_local']
                    and actual['guard_defaults'] == [3*1024**3, 16*1024**3], 'Actual complete Windows worker rejected')
            for manifest in actual['cases']:
                require(len(encoded(manifest)) < 1024**2, 'Input reference manifest exceeds quota')
                freeze(RUN/'inputs'/manifest['case_id']/'manifest.json', encoded(manifest))
            freeze(RUN/'actual_worker.json', encoded(actual))
            freeze(RUN/'preflight.json', encoded({'status': 'passed_all_three_complete_inputs_no_prediction_yet',
                                                'actual_worker': actual, 'new_predictions_completed': 0}))
            print('PREFLIGHT FULL FINE CROSS PASSED ALL THREE CASES', flush=True)
            cp['status'] = 'running_full_fine_cross_diagnostic'
            save_cp(cp)
            matrix = jobs()
            for case in protocol()['cases']:
                block = [j for j in matrix if j['case']['id'] == case['id']]
                resources(sum(quota(case['full_target_count']) for _ in block)+2*1024**2+256*1024**2)
                for job in block:
                    if expired():
                        cp['status'] = 'deadline_checkpoint_saved'
                        break
                    print('SUBMIT FULL FINE CROSS '+job['id'], flush=True)
                    record = pool.submit(execute, job).result()
                    if record.get('not_submitted_prediction'):
                        cp['status'] = 'deadline_checkpoint_saved'
                        break
                    cp['completed'][job['id']] = record
                    save_cp(cp)
                    print('DONE FULL FINE CROSS '+job['id'], flush=True)
                if cp['status'] != 'running_full_fine_cross_diagnostic':
                    break
        if len(cp['completed']) == 9:
            cp['status'] = 'full_fine_cross_predictions_complete_pending_independent_acceptance'
        save_cp(cp)
        freeze(RUN/'reports/prediction_manifest.json', encoded({'checkpoint_sha256': base.file_hash(RUN/'checkpoint.json'),
               'jobs': cp['completed'], 'source_signature': signature(), 'accepted_new_diagnostics': 0}))
    except BaseException as error:
        cp.update(status='failed_preserved_checkpoint', error=repr(error))
        save_cp(cp)
        raise
    finally:
        put(RUN/'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


def close():
    require(not expired(), 'No new independent scientific analysis after noon')
    require(not (RUN/'acceptance.json').exists() and not REPORT.exists(), 'New stage already closed; do not rerun')
    h = execution_helper()
    with h.exclusive() as mutex:
        processes = h.execution_evidence()
        require(base.read_json(RUN/'runner_lock.json')['status'] == 'stopped', 'Actual prediction runner not stopped')
        dependencies()
        cp = base.read_json(RUN/'checkpoint.json')
        require(cp['status'] == 'full_fine_cross_predictions_complete_pending_independent_acceptance'
                and len(cp['completed']) == 9 and cp['source_signature'] == signature(), 'All nine closed jobs required')
        for name, sha in signature().items():
            require(base.file_hash(RUN/'source'/name) == sha, 'New frozen source snapshot differs')
        all_rows, all_effects, files = [], [], {}
        new_tags = {pipeline.Variant(**v).tag for v in protocol()['variants']}
        for job in jobs():
            full, target, inputs, point, report = verify_job(job, cp['completed'][job['id']])
            old_point, old_report = q.reference(job['factorial_reference_job'])
            require(not set(old_point) & set(point), 'Original and crossed cells overlap')
            both = {**old_point, **point}
            variants = [pipeline.Variant(**v) for v in q.protocol()['variants']]
            q.validate_factorial(both)
            states = [state_for(both, v) for v in variants]
            rows = f.summaries(inputs, full, states, job)
            all_rows.extend(rows)
            aliases = {**full, 'reference_ids': np.arange(len(full['xy']), dtype=np.int32)}
            packed, descriptors, effects = {}, {}, []
            cut = float(inputs['time'][-1]-3)
            for cohort, positions in f.cohorts(full, job['case']['coarse_prefix_count'], cut).items():
                summaries = [r for r in rows if r['cohort'] == cohort]
                misses = {v.tag: factors.miss_indices(both, aliases, positions, v.tag, cut) for v in variants}
                contrasts, indices = factors.contrasts(summaries, misses, case=job['case']['id'],
                                                       method=job['core_id'], cohort=cohort, prefix=job['id'])
                for name, ids in {**{cohort+'__miss__'+tag: v for tag, v in misses.items()}, **indices}.items():
                    packed[name], descriptors[name] = mask_encode(ids, len(full['xy']))
                for name, before, after in factors.PAIRS:
                    left, right = factors.CELLS[before], factors.CELLS[after]
                    expected_added = np.array(sorted(set(map(int, misses[right]))-set(map(int, misses[left]))), np.int32)
                    expected_removed = np.array(sorted(set(map(int, misses[left]))-set(map(int, misses[right]))), np.int32)
                    prefix = job['id']+'__'+cohort+'__'+name
                    for suffix, expect in [('added', expected_added), ('removed', expected_removed)]:
                        key = prefix+'__'+suffix
                        require(np.array_equal(mask_decode(packed[key], descriptors[key]), expect),
                                'Independent set difference disagrees with saved miss indices')
                effects.extend(contrasts)
            blob = f.coarse.npz_bytes(packed)
            with np.load(__import__('io').BytesIO(blob)) as saved:
                for key in saved.files:
                    mask_decode(saved[key], descriptors[key])
            payloads = {'miss_indices.npz': blob, 'index_metadata.json': encoded(descriptors),
                        'cohort_summaries.json': encoded(rows), 'factorial_effects.json': encoded(effects)}
            require(sum(map(len, payloads.values())) <= 28*1024**2, 'Measured independent analysis quota exceeded')
            resources(sum(map(len, payloads.values()))+16384)
            for name, value in payloads.items():
                path = RUN/'analysis'/job['id']/name
                freeze(path, value)
                files[path.relative_to(RUN).as_posix()] = hashlib.sha256(value).hexdigest()
            all_effects.extend(effects)
        require(len(all_rows) == 144 and len(all_effects) == 180, 'Complete four-cell/cohort matrix required')
        acceptance = {'status': 'nine_full_fine_cross_diagnostics_independently_accepted', 'time': base.utc_now(),
                      'source_signature': signature(), 'checkpoint_sha256': base.file_hash(RUN/'checkpoint.json'),
                      'new_formal_predictions': 0, 'new_diagnostic_predictions': 9, 'formal_total': 2238,
                      'accepted_diagnostic_total': 57, 'accepted_numeric_total': 2295,
                      'independent_complete_arrays_decoded': 162, 'four_cell_cohort_rows': 144, 'effect_rows': 180,
                      'analysis_files_sha256': files, 'processes': processes, 'mutex': mutex,
                      'foundation_passed': False, 'RIGHT_spatial_component_passed': False,
                      'new_cross_complete_fine_rows': [r for r in all_rows if r['cohort'] == 'complete_fine_RIGHT'
                                                       and r['variant'] in new_tags]}
        text = '# 完整细栅格两个固定交叉格覆盖补验\n\n'
        text += '本轮9项新基础诊断预测已停机后独立验收，新正式0、新诊断9；累计正式2238、已验诊断57、数值2295。原两格完整细结果仅复用，不重计。\n\n'
        text += '| 轨迹 | 原方法 | 新固定处理 | 完整细RIGHT点数 | 窗口漏报 | 迟报 |\n| --- | --- | --- | ---: | ---: | ---: |\n'
        for r in acceptance['new_cross_complete_fine_rows']:
            text += f"| {r['case_id']} | {r['core_id']} | {r['variant']} | {r['right_contacts']} | {r['right_miss']} | {r['right_late']} |\n"
        text += '\n原7万、完整粗RIGHT、全细RIGHT、原28万近场负控制分开报告；144项队列摘要、180对比/交互、全部新增/消失漏报索引及无损packbits证据见本run/analysis。18逐点数组×9项已独立解码，原dtype/shape/SHA、原70072/70277/70000投影和原7万均值精确一致。\n\n完整细栅格覆盖不抵消原误报代价失败，不覆盖原完整基础/密度/空间门失败；84配置0可行，不宣称修复、最优或安全，不选择参数，不启动M2/S5。静态开发轨迹不是未见验证，有限栅格低速运动学仿真不是连续空间或实车安全证明。条件提前量分位数不是同一幸存集因果效应，未定义量保持null。\n'
        payloads = [(RUN/'acceptance.json', encoded(acceptance)),
                    (RUN/'reports/all_cohort_summaries.json', encoded(all_rows)),
                    (RUN/'reports/all_factorial_effects.json', encoded(all_effects)), (REPORT, text.encode('utf-8'))]
        resources(sum(len(v) for _, v in payloads)+16384)
        for path, value in payloads:
            freeze(path, value)
    with h.exclusive():
        h.execution_evidence()
    freeze(RUN/'close_receipt.json', encoded({'status': 'closed', 'time': base.utc_now(),
           'acceptance_sha256': base.file_hash(RUN/'acceptance.json'), 'report_sha256': base.file_hash(REPORT),
           'mutex_reacquired_and_released_after_close': True, 'new_accepted_diagnostics': 9}))
    print(json.dumps({k:v for k,v in acceptance.items() if k not in ('source_signature', 'processes', 'new_cross_complete_fine_rows',
                                                                  'analysis_files_sha256')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    close() if args.close else main()
