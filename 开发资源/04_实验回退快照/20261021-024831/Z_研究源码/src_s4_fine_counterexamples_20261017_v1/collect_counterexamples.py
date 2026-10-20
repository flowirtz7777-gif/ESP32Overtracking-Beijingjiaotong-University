from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import io
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src_s4_fine_RIGHT_acceptance_20261017_v1'))
import analyze_fine_RIGHT as a

f, base, np, pipeline = a.f, a.base, a.np, a.pipeline
RUN = ROOT/'runs/resume_20261017_fine_counterexamples_v1'
PROTOCOL = ROOT/'protocol_fine_counterexamples_20261017_v1.json'
EXPECTED_PROTOCOL = '8fd81a1558ecc3a6217d207d1f3cc43de3ca6e6c1a84e1fec4ad7836fff0cdc3'
LOST_FIVE_SHA = '1636ff0b46616c4e6b06e5bd68797adfa04f5e54cc8405ee112e5ffd068a31c1'
RESULT_FIELDS = ('first', 'raw', 'valid', *f.COUNT_FIELDS)
TARGET_FIELDS = ('xy', 'group', 'contact_time', 'contact_index', 'edge', 'front_ignored')


def protocol():
    return base.read_json(PROTOCOL)


def signature():
    paths = [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]
    return {**a.signature(), **{p.relative_to(ROOT).as_posix(): base.file_hash(p) for p in paths}}


def worker_init():
    p = protocol()['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def resources(extra=0):
    p = protocol()['execution']
    result = pipeline.common.storage_guard(p['reserve_bytes'], p['experiment_budget_bytes'])
    used = sum(x.stat().st_size for x in RUN.rglob('*') if x.is_file()) if RUN.exists() else 0
    if (used+extra > p['new_run_budget_bytes'] or result['experiment_bytes']+extra > p['experiment_budget_bytes']
            or result['free_bytes']-extra < p['reserve_bytes']):
        raise RuntimeError('Catalog resource checkpoint; preserve history and stop')
    return {**result, 'catalog_run_bytes': used}


def freeze(path, payload):
    if path.exists():
        raise AssertionError('Frozen output exists; do not overwrite')
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
        raise AssertionError('Frozen write SHA differs')


def put(path, value):
    resources(len(f.coarse.json_bytes(value))+8192)
    base.write_json_retry(path, value)


def save_cp(cp):
    payload = f.coarse.json_bytes(cp)
    packed = gzip.compress(payload, compresslevel=1, mtime=0)
    resources(len(payload)+len(packed)+16384)
    put(RUN/'checkpoint.json', cp)
    blob = (RUN/'checkpoint.json').read_bytes()
    if blob != payload:
        raise AssertionError('Checkpoint serialization changed')
    freeze(RUN/'checkpoint_snapshots'/(hashlib.sha256(blob).hexdigest()+'.json.gz'), packed)


def dependencies():
    p = protocol()
    if base.file_hash(PROTOCOL) != EXPECTED_PROTOCOL:
        raise AssertionError('Frozen post-result protocol changed')
    if base.read_json(a.RUN/'runner_lock.json')['status'] != 'stopped':
        raise AssertionError('Spatial analysis still active; do not open checkpoint')
    pred = a.frozen_dependency()
    paths = {a.RUN/'checkpoint.json': p['spatial_acceptance_checkpoint_sha256'],
             a.RUN/'reports/fine_spatial_acceptance.json': p['spatial_acceptance_report_sha256'],
             a.RUN/'reports/manifest.json': p['spatial_acceptance_manifest_sha256']}
    for path, sha in paths.items():
        if base.file_hash(path) != sha:
            raise AssertionError('Closed spatial evidence changed: '+str(path))
    cp = base.read_json(a.RUN/'checkpoint.json')
    manifest = base.read_json(a.RUN/'reports/manifest.json')
    if (cp['status'] != 'readonly_spatial_acceptance_complete' or cp['source_signature'] != a.signature()
            or len(cp['completed']) != 9 or manifest['jobs'] != cp['completed']
            or manifest['checkpoint_sha256'] != p['spatial_acceptance_checkpoint_sha256']):
        raise AssertionError('Spatial acceptance dependency incomplete')
    for name, sha in cp['source_signature'].items():
        if base.file_hash(ROOT/name) != sha or base.file_hash(a.RUN/'source'/name) != sha:
            raise AssertionError('Frozen analysis source/snapshot changed')
    for name, sha in manifest['outputs_sha256'].items():
        if base.file_hash(a.RUN/'reports'/name) != sha:
            raise AssertionError('Frozen spatial output changed')
    for job_id, record in cp['completed'].items():
        for path, sha in [(a.RUN/'jobs'/(job_id+'.json'), record['report_sha256']),
                          (a.RUN/'miss_masks'/(job_id+'.npz'), record['mask_file_sha256'])]:
            if base.file_hash(path) != sha:
                raise AssertionError('Frozen spatial job or mask changed')
    for path in (a.RUN/'checkpoint_snapshots').glob('*.json.gz'):
        if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != path.name.split('.')[0]:
            raise AssertionError('Spatial gzip snapshot changed')
    return pred, cp


def sorted_union(parts, upper_bound):
    if len(parts) != 6:
        raise AssertionError('All three methods and both variants required')
    for ids in parts:
        if ids.dtype != np.int32 or ids.ndim != 1 or (len(ids) and (ids[0] < 0 or np.any(np.diff(ids) <= 0))):
            raise AssertionError('Sorted unique int32 indices required')
    result = np.unique(np.concatenate(parts)).astype(np.int32)
    if len(result) > upper_bound:
        raise AssertionError('Union exceeded frozen upper bound; never truncate')
    return result


def member_flags(ids, main_ids, previous_ids, prefix, old_count=280000, expected=(70000, 140000)):
    for values, count in zip((main_ids, previous_ids), expected):
        if (values.dtype != np.int32 or values.shape != (count,) or len(np.unique(values)) != count
                or np.any(values < 0) or np.any(values >= old_count)):
            raise AssertionError('Original subset identity/count/range differs')
    if not np.isin(main_ids, previous_ids).all() or prefix < old_count:
        raise AssertionError('Original nested memberships differ')
    return {'in_original_70000': np.isin(ids, main_ids),
            'in_original_140000': np.isin(ids, previous_ids),
            'in_original_280000': ids < old_count, 'in_full_coarse_prefix': ids < prefix}


def descriptors(arrays):
    return {key: {'dtype': v.dtype.str, 'shape': list(v.shape), 'sha256': base.array_hash(v)}
            for key, v in arrays.items()}


def readback(blob, expected):
    with np.load(io.BytesIO(blob), allow_pickle=False) as saved:
        arrays = {key: saved[key] for key in saved.files}
    if descriptors(arrays) != expected:
        raise AssertionError('NPZ dtype/shape/array SHA readback differs')
    return arrays


def select_outcomes(full, ids, variants):
    return {field: np.stack([full[tag+'_'+field][ids] for tag in variants], axis=1)
            for field in RESULT_FIELDS}


def check_misses(full, targets, cohorts, record, variant, prefix):
    full_ids = cohorts['full_fine_RIGHT']
    ids = full_ids[~np.isfinite(full[variant+'_valid'][full_ids])]
    meta = record['mask_metadata'][variant]
    if len(ids) != meta['miss_count'] or base.array_hash(ids) != meta['sorted_index_array_sha256']:
        raise AssertionError('Full reconstructed valid result differs from frozen miss indices')
    proofs = []
    for cohort, chosen in cohorts.items():
        subset = np.intersect1d(ids, chosen, assume_unique=True).astype(np.int32)
        row = next(r for r in record['rows'] if r['variant'] == variant and r['cohort'] == cohort)
        if row['right_miss'] != len(subset) or row['right_contacts'] != len(chosen):
            raise AssertionError('Frozen full/phase miss or denominator count differs')
        proof = {'variant': variant, 'cohort': cohort, 'miss_count': len(subset),
                 'sorted_miss_index_sha256': base.array_hash(subset), 'cohort_index_sha256': base.array_hash(chosen)}
        if cohort != 'full_fine_RIGHT':
            pair = next(r for r in record['pairs'] if r['variant'] == variant and r['cohort'] == cohort)
            rebuilt = a.miss_pair(ids, chosen, prefix)
            if any(pair[k] != value for k, value in rebuilt.items()):
                raise AssertionError('Frozen added/removed/phase miss indices differ')
            proof['pair'] = rebuilt
        proofs.append(proof)
    return ids, proofs


def collect_case(case_id, prediction_cp, acceptance_cp):
    p = protocol()
    jobs = [j for j in f.jobs() if j['case']['id'] == case_id]
    if [j['core_id'] for j in jobs] != p['core_ids']:
        raise AssertionError('Three fixed methods required in frozen order')
    targets, target_manifest, target_sha = f.load_targets(case_id)
    prefix = jobs[0]['case']['coarse_prefix_count']
    old, old_proof, _ = f.coarse.load_targets(case_id)
    original_path = ROOT/old_proof['original_target_path']
    if (base.file_hash(original_path) != old_proof['original_target_sha256']
            or str(original_path) != str(ROOT/target_manifest['old_140000_ids_reference'])):
        raise AssertionError('Original 140000 member source binding differs')
    with np.load(original_path, allow_pickle=False) as original:
        previous_ids = original['previous_ids']
        if not np.array_equal(original['main_ids'], targets['main_ids']):
            raise AssertionError('Original main membership differs')
    del old
    misses, proofs, inputs, shared = {}, [], [], None
    cohorts, phase = None, None
    for job in jobs:
        path = a.RUN/'jobs'/(job['id']+'.json')
        record = base.read_json(path)
        if record['predictor_record'] != prediction_cp['completed'][job['id']]:
            raise AssertionError('Spatial job predictor binding differs')
        rows, report = f.verify(job, prediction_cp['completed'][job['id']])
        a.verify_controls(job, rows)
        common = {key: report[key] for key in ('full_target_array_sha256', 'input_hashes', 'raw_sensor_hashes',
                  'estimated_state_sha256', 'estimated_alpha_sha256', 'score_start_s', 'score_end_s')}
        if shared is not None and common != shared:
            raise AssertionError('Common coordinates/labels/observations/estimates/scoring differ')
        shared = common
        if cohorts is None:
            cohorts, phase = a.cohorts(targets, report['score_end_s'], prefix)
        for name, ids in cohorts.items():
            expected = record['cohort_proofs'][name]
            if (base.array_hash(ids) != expected['index_sha256'] or len(ids) != expected['count']
                    or base.array_hash(targets['xy'][ids]) != expected['coordinate_sha256']
                    or {k: base.array_hash(targets[k][ids]) for k in f.coarse.geometry.LABEL_KEYS} != expected['label_sha256']):
                raise AssertionError('Cohort coordinates/labels/index identity differs')
        full = a.reconstruct(job, report)
        with np.load(a.RUN/'miss_masks'/(job['id']+'.npz'), allow_pickle=False) as saved:
            for variant in p['variants']:
                decoded = a.decode_miss_mask(saved[variant], record['mask_metadata'][variant])
                actual, checks = check_misses(full, targets, cohorts, record, variant, prefix)
                if not np.array_equal(decoded, actual):
                    raise AssertionError('Full valid arrays and saved miss masks differ')
                misses[(job['core_id'], variant)] = actual
                proofs.extend({'core_id': job['core_id'], **check} for check in checks)
        inputs.append({'job_id': job['id'], 'prediction_record': prediction_cp['completed'][job['id']],
                       'spatial_record': acceptance_cp['completed'][job['id']]})
        del full
        print('CATALOG VERIFIED SIX-OUTCOME INPUT '+job['id'], flush=True)
    ids = sorted_union(list(misses.values()), p['per_case_union_upper_bounds_from_frozen_miss_counts'][case_id])
    arrays = {'full_target_index': ids, **{k: targets[k][ids] for k in TARGET_FIELDS}, 'fine_phase': phase[ids],
              **member_flags(ids, targets['main_ids'], previous_ids, prefix)}
    selected = []
    for job in jobs:
        report = base.read_json(f.RUN/'jobs'/job['id']/'report.json')
        full = a.reconstruct(job, report)
        selected.append(select_outcomes(full, ids, p['variants']))
        del full
    for field in RESULT_FIELDS:
        arrays['result_'+field] = np.stack([s[field] for s in selected], axis=1)
    # Every method/variant is projected on exactly the same ordered union, including empty cases.
    observed_miss = ~np.isfinite(arrays['result_valid'])
    if len(ids) and not observed_miss.any(axis=(1, 2)).all():
        raise AssertionError('Catalog contains a point that never misses')
    for i, core in enumerate(p['core_ids']):
        for j, variant in enumerate(p['variants']):
            if not np.array_equal(ids[observed_miss[:, i, j]], misses[(core, variant)]):
                raise AssertionError('Catalog projection lost or added window-miss indices')
    lost = []
    if case_id == p['cases'][0]:
        lost_ids = misses[('linear_g0625', 'w2000_m20_c100')]
        if len(lost_ids) != 5 or base.array_hash(lost_ids) != LOST_FIVE_SHA or not np.isin(lost_ids, ids).all() or np.any(phase[lost_ids] == 1):
            raise AssertionError('Unique phase1 zero-claim-loss five indices not preserved')
        lost = lost_ids.tolist()
    descriptor = descriptors(arrays)
    payload = f.coarse.npz_bytes(arrays)
    resources(len(payload)+len(f.coarse.json_bytes(descriptor))+65536)
    readback(payload, descriptor)
    meta = {'case_id': case_id, 'identity': p['identity'], 'unique_union_count': len(ids),
            'frozen_union_upper_bound': p['per_case_union_upper_bounds_from_frozen_miss_counts'][case_id],
            'sum_method_variant_miss_counts_not_unique': sum(map(len, misses.values())),
            'source_signature': signature(), 'target_manifest_sha256': target_sha,
            'original_140000_membership_source': str(original_path.relative_to(ROOT)),
            'original_140000_membership_file_sha256': base.file_hash(original_path),
            'original_140000_previous_ids_array_sha256': base.array_hash(previous_ids),
            'axes_for_result_arrays': ['catalog_point', 'core_id', 'variant'],
            'core_ids': p['core_ids'], 'variants': p['variants'], 'arrays': descriptor,
            'shared_input_proof': shared, 'dependency_jobs': inputs, 'full_phase_miss_proofs': proofs,
            'unique_phase1_lost_five_indices': lost,
            'counts_by_membership': {k: int(v.sum()) for k, v in arrays.items() if k.startswith('in_')},
            'counts_by_layer': {str(k): int((arrays['group'] == k).sum()) for k in range(3)},
            'counts_by_phase': {str(k): int((arrays['fine_phase'] == k).sum()) for k in range(4)},
            'all_six_comparisons_share_exact_catalog_ids': True, 'npz_readback_verified': True,
            'confirmation_chain_localized': False, 'new_predictions': 0, 'foundation_passed': False}
    return arrays, payload, meta


def probe():
    return {'python': sys.executable, 'root': str(ROOT), 'source_signature': signature(),
            'guard_defaults': list(pipeline.common.storage_guard.__defaults__),
            'deadline': protocol()['execution']['deadline_local'], 'read_only_new_predictions': 0,
            'blas_threads': {k: os.environ[k] for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}}


def main():
    p = protocol()
    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['execution']['deadline_local']):
        raise RuntimeError('No new analysis after today 14:00')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        if (RUN/'checkpoint.json').exists():
            raise AssertionError('Prior attempt exists; do not repeat')
        worker_init()
        resources(6*1024**2)
        prediction_cp, acceptance_cp = dependencies()
        source = signature()
        for name, sha in source.items():
            freeze(RUN/'source'/name, (ROOT/name).read_bytes())
        put(RUN/'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now(), 'readonly_catalog': True})
        started = True
        cp = {'status': 'readonly_counterexample_catalog_running', 'source_signature': source, 'completed': {},
              'prediction_checkpoint_sha256': p['prediction_checkpoint_sha256'],
              'spatial_acceptance_checkpoint_sha256': p['spatial_acceptance_checkpoint_sha256'], 'new_predictions': 0}
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=180)
        if (Path(actual['python']) != Path(r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe')
                or actual['root'] != str(ROOT) or actual['source_signature'] != source
                or actual['guard_defaults'] != [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']]
                or actual['deadline'] != p['execution']['deadline_local'] or set(actual['blas_threads'].values()) != {'1'}):
            raise AssertionError('Actual Windows catalog worker acceptance failed')
        freeze(RUN/'actual_worker.json', f.coarse.json_bytes(actual))
        print('WINDOWS READONLY CATALOG WORKER ACCEPTED; ZERO NEW PREDICTIONS', flush=True)
        cases = []
        for case in p['cases']:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(p['execution']['deadline_local']):
                raise RuntimeError('Deadline checkpoint before new case analysis')
            arrays, payload, meta = collect_case(case, prediction_cp, acceptance_cp)
            folder = RUN/'cases'/case
            metadata_payload = f.coarse.json_bytes(meta)
            resources(len(payload)+len(metadata_payload)+65536)
            freeze(folder/'catalog.npz', payload)
            readback((folder/'catalog.npz').read_bytes(), meta['arrays'])
            freeze(folder/'catalog.json', metadata_payload)
            cp['completed'][case] = {'npz_sha256': base.file_hash(folder/'catalog.npz'),
                'metadata_sha256': base.file_hash(folder/'catalog.json'), 'unique_union_count': len(arrays['full_target_index'])}
            save_cp(cp)
            cases.append({'case_id': case, **cp['completed'][case], 'counts_by_membership': meta['counts_by_membership'],
                          'counts_by_layer': meta['counts_by_layer'], 'counts_by_phase': meta['counts_by_phase']})
            print('DONE READONLY COUNTEREXAMPLE CASE '+case+' unique='+str(meta['unique_union_count']), flush=True)
        summary = {'status': 'readonly_counterexample_catalog_complete', 'identity': p['identity'], 'cases': cases,
                   'measured_unique_points': sum(c['unique_union_count'] for c in cases),
                   'sum_frozen_miss_count_upper_bounds_not_unique': sum(p['per_case_union_upper_bounds_from_frozen_miss_counts'].values()),
                   'full_phase_miss_proofs': 90, 'phase_added_removed_index_proofs': 72,
                   'new_formal_predictions': 0, 'new_diagnostic_predictions': 0, 'current_authorization_new_diagnostics': 9,
                   'formal_total': 2238, 'accepted_diagnostic_total': 30, 'accepted_numeric_total': 2268,
                   'foundation_or_S4_or_M2_or_S5_accepted': False, 'confirmation_chain_localized': False,
                   'not_unbiased_population_or_independent_validation': True, 'old_density_failure_overridden': False}
        freeze(RUN/'reports/counterexample_catalog.json', f.coarse.json_bytes(summary))
        cp['status'] = 'readonly_counterexample_catalog_complete'
        save_cp(cp)
        manifest = {'source_signature': source, 'checkpoint_sha256': base.file_hash(RUN/'checkpoint.json'),
                    'cases': cp['completed'], 'outputs_sha256': {'counterexample_catalog.json': base.file_hash(RUN/'reports/counterexample_catalog.json')}}
        freeze(RUN/'reports/manifest.json', f.coarse.json_bytes(manifest))
        dependencies()
        print('DONE READONLY COUNTEREXAMPLE CATALOG unique='+str(summary['measured_unique_points']), flush=True)
    except BaseException as error:
        if cp is not None:
            cp.update(status='readonly_catalog_failed_checkpoint_saved', error=repr(error))
            save_cp(cp)
        raise
    finally:
        if started:
            put(RUN/'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
