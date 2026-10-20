from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src_s4_RIGHT_census_v1'))
sys.path.insert(0, str(ROOT/'src_s4_fine_inventory_acceptance_v1'))
import run_RIGHT_census as coarse
import verify_inventory as acceptance

base, np, pipeline = coarse.base, coarse.np, coarse.pipeline
inventory = acceptance.inventory
PROTOCOL = ROOT/'protocol_fine_RIGHT_census_20261017_v1.json'
RUN = ROOT/'runs/resume_20261017_fine_RIGHT_census_v1'
FIELDS = coarse.FIELDS
COUNT_FIELDS = ('TP', 'FP', 'ref_FP', 'support', 'negative_opportunities', 'ref_negative_opportunities')


def protocol():
    return base.read_json(PROTOCOL)


def expired():
    return datetime.now(timezone.utc) >= datetime.fromisoformat(protocol()['execution']['deadline_local'])


def signature():
    result = {**coarse.signature(), **acceptance.signature()}
    p = protocol()
    paths = [PROTOCOL, ROOT/p['execution_authorization'], ROOT/p['resource_authorization'],
             *sorted(Path(__file__).parent.glob('*.py'))]
    result.update({path.relative_to(ROOT).as_posix(): base.file_hash(path) for path in paths})
    return result


def worker_init():
    p = protocol()['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def guard(extra=0):
    p = protocol()['execution']
    resource = pipeline.common.storage_guard(p['reserve_bytes'], p['experiment_budget_bytes'])
    used = sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file()) if RUN.exists() else 0
    if used+extra > p['new_run_budget_bytes'] or resource['experiment_bytes']+extra > p['experiment_budget_bytes'] or resource['free_bytes']-extra < p['reserve_bytes']:
        raise RuntimeError('Resource checkpoint: preserve history, do not submit or write oversized payload')
    return {**resource, 'run_bytes': used}


def quotas(n):
    if type(n) is not int or n < 0:
        raise ValueError('Measured nonnegative integer population required')
    return {'input': (48*n*101+99)//100+2*1024**2, 'job': (36*n*101+99)//100+1024**2}


def fits(resource, reservation):
    p = protocol()['execution']
    return min(p['experiment_budget_bytes']-resource['experiment_bytes'],
               p['new_run_budget_bytes']-resource['run_bytes'],
               resource['free_bytes']-p['reserve_bytes']) >= reservation


def put(path, value):
    guard(len(coarse.json_bytes(value))+8192)
    base.write_json_retry(path, value)


def freeze_bytes(path, payload):
    if path.exists():
        if path.read_bytes() != payload:
            raise AssertionError('Immutable asset differs; preserve it and version changes')
        return
    guard(len(payload)+8192)
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
        raise AssertionError('Written asset differs')


def dependencies():
    p = protocol()
    for run, sha in [(coarse.RUN, p['coarse_checkpoint_sha256']), (acceptance.RUN, p['fine_acceptance_checkpoint_sha256'])]:
        if base.read_json(run/'runner_lock.json')['status'] != 'stopped':
            raise AssertionError('Frozen dependency is running; do not read checkpoint')
        if base.file_hash(run/'checkpoint.json') != sha:
            raise AssertionError('Frozen checkpoint differs')
    acceptance.dependencies()
    cp = base.read_json(acceptance.RUN/'checkpoint.json')
    if cp['source_signature'] != acceptance.signature():
        raise AssertionError('Frozen reconstruction source binding differs')
    for case, record in cp['completed'].items():
        if base.read_json(acceptance.RUN/'cases'/(case+'.json')) != record:
            raise AssertionError('Closed full reconstruction proof differs')
    if base.read_json(coarse.RUN/'checkpoint.json')['source_signature'] != coarse.signature():
        raise AssertionError('Frozen coarse prediction source binding differs')
    for key in ('execution_authorization', 'resource_authorization'):
        if base.file_hash(ROOT/p[key]) != p[key+'_sha256']:
            raise AssertionError('Explicit authorization differs')
    auth = base.read_json(ROOT/p['execution_authorization'])
    if auth['authorized_until_local'] != p['execution']['deadline_local'] or auth['whole_research_budget_bytes'] != 16*1024**3:
        raise AssertionError('New time or resource authorization differs')
    if base.file_hash(ROOT/'src_s4_lossless_storage_audit_v1/packing.py') != p['packing_source_sha256']:
        raise AssertionError('Lossless packing source changed')


def append_targets(old, delta):
    if set(delta) != set(FIELDS) or any(delta[k].dtype != old[k].dtype for k in FIELDS):
        raise AssertionError('Six exact-dtype target fields required')
    values = {k: np.concatenate((old[k], delta[k])) for k in FIELDS}
    values['main_ids'] = old['main_ids']
    for key in FIELDS:
        if base.array_hash(values[key][:len(old['xy'])]) != base.array_hash(old[key]):
            raise AssertionError('Complete coarse prefix changed')
    return values


def merge_outputs(old, delta, full_count):
    prefix = len(next(iter(old.values())))
    return coarse.census.dep.reconstruct_delta(old, delta, np.arange(prefix, dtype=np.int32),
        np.arange(prefix, full_count, dtype=np.int32), full_count)


def target_path(case):
    return RUN/'targets'/case/'new_fine_RIGHT.npz'


def geometry_delta_mask(arrays, coarse_phase, cut):
    if len(coarse_phase) != len(arrays['xy']):
        raise AssertionError('Coarse phase mask has wrong length')
    return coarse.geometry.eligible_right(arrays, cut) & ~coarse_phase


def load_targets(case):
    path = target_path(case)
    proof = base.read_json(path.with_name('manifest.json'))
    if proof['source_signature'] != signature() or base.file_hash(path) != proof['delta_file_sha256']:
        raise AssertionError('Frozen fine target source/file differs')
    old, old_proof, old_sha = coarse.load_targets(case)
    if old_sha != proof['coarse_target_manifest_sha256']:
        raise AssertionError('Coarse prefix provenance differs')
    with np.load(path) as saved:
        delta = {key: saved[key] for key in saved.files}
    if {k: base.array_hash(v) for k, v in delta.items()} != proof['delta_array_sha256']:
        raise AssertionError('Fine target arrays differ')
    targets = append_targets(old, delta)
    if {k: base.array_hash(targets[k]) for k in FIELDS} != proof['full_target_array_sha256']:
        raise AssertionError('Full target array reconstruction differs')
    return targets, proof, base.file_hash(path.with_name('manifest.json'))


def build_targets(case):
    p = protocol()
    folder = target_path(case['id']).parent
    if (folder/'manifest.json').exists():
        return load_targets(case['id'])[1]
    if folder.exists():
        raise AssertionError('Partial target assets exist; preserve, do not overwrite')
    required = quotas(case['new_count'])['input']+3*quotas(case['new_count'])['job']+p['execution']['fixed_report_headroom_bytes']
    if not fits(guard(), required):
        raise RuntimeError('Resource checkpoint before complete target/case block')
    old, old_proof, old_sha = coarse.load_targets(case['id'])
    proof_path = inventory.RUN/'cases'/(case['id']+'.json')
    proof = base.read_json(proof_path)
    accepted = base.read_json(acceptance.RUN/'cases'/(case['id']+'.json'))
    if base.file_hash(proof_path) != accepted['case_report_sha256'] or not accepted['all_chunk_array_hashes_exact']:
        raise AssertionError('Closed fine inventory proof differs')
    data, main, mf = pipeline.core.load_case(p['partition'], case['id'])
    if mf['files'] != proof['frozen_truth_input_files_sha256'] or mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
        raise AssertionError('Frozen truth/reference convergence differs')
    if len(old['xy']) != case['coarse_prefix_count'] or any(base.array_hash(old[k][old['main_ids']]) != base.array_hash(main[k]) for k in FIELDS):
        raise AssertionError('Original 70000 or complete coarse prefix differs')
    segments, body, right = inventory.dep.complete_geometry(data['fine_state'])
    if not coarse.shapely.is_valid(body) or not coarse.shapely.is_valid(right):
        raise AssertionError('Invalid truth geometry')
    tree = inventory.dep.build_temporal_tree(segments, base.read_json(inventory.PROTOCOL)['temporal_union_leaf_size'])
    reference = {'time': data['fine_time'], 'state': data['fine_state']}
    parts = {k: [] for k in FIELDS}
    rebuilt = eligible_count = 0
    for index, (saved, chunk) in enumerate(itertools.zip_longest(proof['regenerable_chunk_proofs'], inventory.chunks(body, right, base.read_json(inventory.PROTOCOL))), 1):
        if expired():
            raise RuntimeError('Deadline checkpoint during target construction; no prediction submitted')
        if saved is None or chunk is None:
            raise AssertionError('Geometry chunk count differs')
        labels = inventory.dep.label_from_tree(chunk['xy'], reference, segments, tree, p['contact_tolerance_m'])
        arrays = {'xy': chunk['xy'], 'group': chunk['group'], **labels}
        if any(saved[k] != chunk[k] for k in ('row_start', 'row_end', 'total_rows')) or {k: base.array_hash(v) for k, v in arrays.items()} != saved['array_hashes']:
            raise AssertionError('Fine chunk coordinates/layers/labels differ from frozen geometry inventory')
        eligible = coarse.geometry.eligible_right(arrays, proof['score_end_s'])
        if int(eligible.sum()) != saved['eligible_RIGHT_count']:
            raise AssertionError('Fine RIGHT predicate differs')
        selected = geometry_delta_mask(arrays, chunk['coarse_positive'], proof['score_end_s'])
        for key in FIELDS:
            parts[key].append(arrays[key][selected])
        rebuilt += len(chunk['xy'])
        eligible_count += int(eligible.sum())
        if index % 100 == 0:
            print(f'BUILD FINE RIGHT {case["id"]} chunks {index}/{len(proof["regenerable_chunk_proofs"])}', flush=True)
    delta = {k: np.concatenate(v) for k, v in parts.items()}
    del parts
    if rebuilt != proof['positive_cells_measured'] or eligible_count != case['fine_RIGHT_count'] or len(delta['xy']) != case['new_count']:
        raise AssertionError('Measured complete fine population count differs')
    if sum(v.nbytes for v in delta.values()) > 48*case['new_count']:
        raise RuntimeError('Target array byte bound not satisfied')
    targets = append_targets(old, delta)
    keys = coarse.census.cell_keys(targets['xy'], p['grid_spacing_m'])
    if len(np.unique(keys)) != len(keys) or len(targets['xy']) != case['full_target_count']:
        raise AssertionError('Duplicate points or wrong full population')
    if int(coarse.geometry.eligible_right(targets, proof['score_end_s']).sum()) != eligible_count:
        raise AssertionError('Full fine RIGHT coverage is incomplete')
    ix = np.rint(delta['xy']/p['grid_spacing_m']).astype(np.int64)
    if np.any((ix[:, 0] % 2 == 0) & (ix[:, 1] % 2 == 0)):
        raise AssertionError('New target includes a frozen coarse-phase point')
    blob = coarse.npz_bytes(delta)
    metadata = {'case_id': case['id'], 'source_signature': signature(), 'new_count': len(delta['xy']),
        'full_target_count': len(targets['xy']), 'coarse_prefix_count': len(old['xy']),
        'fine_RIGHT_count': eligible_count, 'geometry_chunks_rebuilt': index,
        'inventory_case_sha256': base.file_hash(proof_path), 'coarse_target_manifest_sha256': old_sha,
        'delta_file_sha256': hashlib.sha256(blob).hexdigest(),
        'delta_array_sha256': {k: base.array_hash(v) for k, v in delta.items()},
        'full_target_array_sha256': {k: base.array_hash(targets[k]) for k in FIELDS},
        'input_hashes': mf['files'], 'score_start_s': 2., 'score_end_s': proof['score_end_s'],
        'all_new_points_selected_only_by_geometry': True, 'prefix_preserved_exactly': True,
        'old_140000_ids_reference': old_proof['original_target_path'], 'new_predictions_completed': 0}
    if len(blob)+len(coarse.json_bytes(metadata)) > quotas(case['new_count'])['input']:
        raise RuntimeError('Measured target payload exceeds reserved input quota')
    freeze_bytes(target_path(case['id']), blob)
    freeze_bytes(folder/'manifest.json', coarse.json_bytes(metadata))
    print('FROZEN FINE RIGHT INPUT '+case['id']+' '+str(len(targets['xy'])), flush=True)
    return metadata


def jobs():
    p, refs = protocol(), coarse.jobs()
    result = []
    for case in p['cases']:
        for core in p['core_ids']:
            matches = [r for r in refs if r['case']['id'] == case['id'] and r['reference']['core_id'] == core]
            if len(matches) != 1:
                raise AssertionError('Fixed coarse reference matrix differs')
            ref = matches[0]
            if ref['reference']['variants'] != p['variants'] or ref['reference']['method']['dt'] != p['prediction_dt_s']:
                raise AssertionError('Original online parameters differ')
            job = {'case': case, 'core_id': core, 'coarse_reference': ref, 'source_signature': signature(),
                   'category': 'new_fine_spatial_foundation_diagnostic_not_formal_ranking'}
            tag = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
            job['id'] = case['id']+'__'+core+'__fine00625__'+tag
            result.append(job)
    if len(result) != 9:
        raise AssertionError('Expected nine spatial diagnostic jobs')
    return result


def read_coarse(job):
    ref = job['coarse_reference']
    cp = base.read_json(coarse.RUN/'checkpoint.json')
    rows, report = coarse.verify(ref, cp['completed'][ref['id']])
    old, _, _ = coarse.census.read_reference(ref['reference'])
    folder = coarse.RUN/'jobs'/ref['id']
    raw, _ = pipeline.load_observation(protocol()['partition'], job['case']['id'], ref['reference']['condition'])
    with np.load(folder/'packed_delta.npz') as stored:
        delta = coarse.unpack_points({k: stored[k] for k in stored.files}, base.read_json(folder/'packed_metadata.json'), raw['time'])
    return coarse.merge_outputs(old, delta, ref['case']['full_target_count']), report, base.file_hash(folder/'report.json')


def cohorts(targets, prefix, cut):
    right = coarse.geometry.eligible_right(targets, cut)
    old_right = right.copy()
    old_right[prefix:] = False
    return {'original_70000': targets['main_ids'], 'complete_coarse_RIGHT': np.flatnonzero(old_right),
            'complete_fine_RIGHT': np.flatnonzero(right),
            'old_280000_near_negative_controls': np.flatnonzero(~np.isfinite(targets['contact_time'][:280000]))}


def summaries(data, targets, states, job):
    rows = []
    for state in states:
        for name, ids in cohorts(targets, job['case']['coarse_prefix_count'], float(data['time'][-1]-3)).items():
            row = coarse.projected_summary(data, targets, state, ids)
            row.update(case_id=job['case']['id'], core_id=job['core_id'], condition='noise100_s1',
                variant=state['variant'].tag, cohort=name, independent_validation=False,
                changed_population_not_ranked_with_old_weighting=True)
            rows.append(row)
    return rows


def execute(job):
    if expired():
        return {'not_submitted_prediction': True, 'reason': 'deadline'}
    guard()
    if signature() != job['source_signature']:
        raise AssertionError('Frozen numerical source changed')
    targets, proof, proof_sha = load_targets(job['case']['id'])
    old, old_report, old_sha = read_coarse(job)
    ref = job['coarse_reference']['reference']
    data, _, mf = pipeline.core.load_case(ref['partition'], ref['case_id'])
    raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    inputs = {**data, **raw}
    if obs['descriptor']['sensor_array_hashes'] != old_report['raw_sensor_hashes']:
        raise AssertionError('Frozen common observation differs')
    print('START FINE RIGHT PREDICTION '+job['id'], flush=True)
    result = pipeline.evaluate(inputs, targets, pipeline.Method(**ref['method']), [pipeline.Variant(**v) for v in ref['variants']])
    prefix = job['case']['coarse_prefix_count']
    for key, value in result['point_output'].items():
        if base.array_hash(value[:prefix]) != base.array_hash(old[key]):
            raise AssertionError('Frozen complete coarse point output changed: '+key)
    packed, metadata = coarse.pack_points({k: v[prefix:] for k, v in result['point_output'].items()}, inputs['time'])
    if len(packed) != 18 or any(v.dtype != np.uint16 for v in packed.values()):
        raise AssertionError('Lossless uint16 quota bound not satisfied')
    delta = coarse.unpack_points(packed, metadata, inputs['time'])
    full = merge_outputs(old, delta, len(targets['xy']))
    hashes = {k: base.array_hash(v) for k, v in result['point_output'].items()}
    if any(base.array_hash(full[k]) != sha for k, sha in hashes.items()):
        raise AssertionError('Full dtype/shape/array-SHA reconstruction differs')
    rows = summaries(inputs, targets, result['states'], job)
    blobs = {'configuration.json': coarse.json_bytes(job), 'summary.json': coarse.json_bytes(rows),
        'packed_delta.npz': coarse.npz_bytes(packed), 'packed_metadata.json': coarse.json_bytes(metadata),
        'frame_results.npz': coarse.npz_bytes({'time': raw['time'], 'counts': result['frame_counts'], 'phase': result['observed_phase']}),
        'timing.json': coarse.json_bytes({**result['timing'], 'desktop_not_MCU': True})}
    report = {'id': job['id'], 'source_signature': signature(), 'prefix_all_point_outputs_exact': True,
        'target_manifest_sha256': proof_sha, 'target_delta_sha256': proof['delta_file_sha256'],
        'full_target_array_sha256': proof['full_target_array_sha256'], 'full_target_count': len(targets['xy']),
        'reference_report_sha256': old_sha, 'full_point_arrays_sha256': hashes,
        'input_hashes': mf['files'], 'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'],
        'estimated_state_sha256': base.array_hash(raw['state']), 'estimated_alpha_sha256': base.array_hash(raw['alpha']),
        'score_start_s': 2., 'score_end_s': float(raw['time'][-1]-3),
        'output_sha256': {name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()}}
    blobs['report.json'] = coarse.json_bytes(report)
    if sum(map(len, blobs.values())) > quotas(job['case']['new_count'])['job']:
        raise RuntimeError('Actual encoded job exceeds complete reserved quota')
    folder = RUN/'jobs'/job['id']
    if folder.exists():
        raise AssertionError('Prior output exists; preserve and verify, never recompute over it')
    guard(sum(map(len, blobs.values()))+8192)
    folder.mkdir(parents=True)
    for name, blob in blobs.items():
        freeze_bytes(folder/name, blob)
    return {'report_sha256': base.file_hash(folder/'report.json'), 'output_bytes': sum(map(len, blobs.values()))}


def verify(job, record):
    folder = RUN/'jobs'/job['id']
    report = base.read_json(folder/'report.json')
    if base.file_hash(folder/'report.json') != record['report_sha256'] or base.read_json(folder/'configuration.json') != job or report['source_signature'] != signature():
        raise AssertionError('New output/config/source differs')
    for name, sha in report['output_sha256'].items():
        if base.file_hash(folder/name) != sha:
            raise AssertionError('New output hash differs: '+name)
    targets, proof, proof_sha = load_targets(job['case']['id'])
    old, old_report, old_sha = read_coarse(job)
    ref = job['coarse_reference']['reference']
    data, _, mf = pipeline.core.load_case(ref['partition'], ref['case_id'])
    raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    if proof_sha != report['target_manifest_sha256'] or old_sha != report['reference_report_sha256'] or mf['files'] != report['input_hashes'] or obs['descriptor']['sensor_array_hashes'] != report['raw_sensor_hashes']:
        raise AssertionError('Frozen inputs/reference differ')
    if report['full_target_array_sha256'] != proof['full_target_array_sha256'] or report['target_delta_sha256'] != proof['delta_file_sha256'] or report['estimated_state_sha256'] != base.array_hash(raw['state']) or report['estimated_alpha_sha256'] != base.array_hash(raw['alpha']):
        raise AssertionError('Target or shared estimate differs')
    with np.load(folder/'packed_delta.npz') as saved:
        delta = coarse.unpack_points({k: saved[k] for k in saved.files}, base.read_json(folder/'packed_metadata.json'), raw['time'])
    full = merge_outputs(old, delta, len(targets['xy']))
    if any(base.array_hash(full[k]) != sha for k, sha in report['full_point_arrays_sha256'].items()):
        raise AssertionError('Stored full point output cannot be reconstructed exactly')
    states = []
    for vdict in ref['variants']:
        variant = pipeline.Variant(**vdict)
        state = {key: full[variant.tag+'_'+key] for key in ('raw', 'first', 'valid')}
        state.update(variant=variant, point_counts={k: full[variant.tag+'_'+k] for k in COUNT_FIELDS})
        states.append(state)
    rows = summaries({**data, **raw}, targets, states, job)
    if rows != base.read_json(folder/'summary.json'):
        raise AssertionError('Stored cohort summaries differ from exact arrays')
    return rows, report


def probe():
    cases = []
    for case in protocol()['cases']:
        targets, proof, _ = load_targets(case['id'])
        data, _, mf = pipeline.core.load_case(protocol()['partition'], case['id'])
        ref = next(j for j in coarse.jobs() if j['case']['id'] == case['id'])['reference']
        raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
        if len(raw['time']) >= 65535 or not np.array_equal(raw['time'], data['time']) or obs['descriptor']['input_hashes'] != mf['files']:
            raise AssertionError('Common observation/time/uint16 bound differs')
        if len(targets['main_ids']) != 70000 or len(targets['xy']) != case['full_target_count']:
            raise AssertionError('Actual Windows worker target count differs')
        cases.append({'id': case['id'], 'count': len(targets['xy']), 'main_count': 70000,
            'coordinate_sha256': base.array_hash(targets['xy']), 'input_hashes': mf['files'],
            'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes']})
    return {'python': sys.executable, 'source_signature': signature(), 'root': str(ROOT), 'cases': cases,
        'guard_defaults': list(pipeline.common.storage_guard.__defaults__), 'deadline': protocol()['execution']['deadline_local']}


def identity_probe():
    return {'python': sys.executable, 'source_signature': signature(), 'root': str(ROOT),
        'guard_defaults': list(pipeline.common.storage_guard.__defaults__),
        'deadline': protocol()['execution']['deadline_local'], 'new_predictions_completed': 0}


def accept_identity(actual, source, p):
    if actual['python'].lower() != r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe'.lower() or actual['root'] != str(ROOT) or actual['source_signature'] != source or actual['guard_defaults'] != [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']] or actual['deadline'] != p['execution']['deadline_local']:
        raise AssertionError('Actual Windows worker source/resource/deadline acceptance failed')


def save_cp(cp):
    put(RUN/'checkpoint.json', cp)
    payload = (RUN/'checkpoint.json').read_bytes()
    packed = gzip.compress(payload, compresslevel=1, mtime=0)
    freeze_bytes(RUN/'checkpoint_snapshots'/(base.file_hash(RUN/'checkpoint.json')+'.json.gz'), packed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if expired():
        parser.error('New execution deadline passed')
    kernel, mutex = pipeline.core.acquire_lock()
    cp = None
    started = False
    try:
        worker_init()
        dependencies()
        if (RUN/'checkpoint.json').exists():
            raise AssertionError('Existing attempt: inspect stopped checkpoints; do not blindly rerun')
        p, source = protocol(), signature()
        reserve = sum(quotas(c['new_count'])['input']+3*quotas(c['new_count'])['job'] for c in p['cases'])+p['execution']['initial_metadata_headroom_bytes']
        if not fits(guard(), reserve):
            raise RuntimeError('Full stage worst-case input/output reservation not available')
        cp = {'status': 'preflight_building_frozen_targets_not_prediction', 'source_signature': source,
              'completed': {}, 'targets_completed': {}, 'new_formal_jobs': 0}
        put(RUN/'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now(), 'phase': 'preflight_not_prediction', 'deadline': p['execution']['deadline_local']})
        started = True
        for name, sha in source.items():
            freeze_bytes(RUN/'source'/name, (ROOT/name).read_bytes())
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            identity = pool.submit(identity_probe).result(timeout=180)
        accept_identity(identity, source, p)
        freeze_bytes(RUN/'actual_worker_identity.json', coarse.json_bytes(identity))
        print('WINDOWS FINE RIGHT WORKER IDENTITY ACCEPTED; TARGET PREFLIGHT NOT COMPLETE', flush=True)
        for case in p['cases']:
            proof = build_targets(case)
            cp['targets_completed'][case['id']] = {'target_manifest_sha256': base.file_hash(target_path(case['id']).with_name('manifest.json')), 'full_count': proof['full_target_count']}
            save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=1800)
        accept_identity(actual, source, p)
        freeze_bytes(RUN/'actual_worker.json', coarse.json_bytes(actual))
        freeze_bytes(RUN/'preflight.json', coarse.json_bytes({'status': 'all_preconditions_passed_no_predictions_yet', 'source_signature': source, 'actual_worker': actual, 'reserved_worst_case_bytes': reserve}))
        print('PREFLIGHT FINE RIGHT PASSED ALL THREE CASES', flush=True)
        if args.check_only:
            cp['status'] = 'check_only_complete_zero_predictions'
            save_cp(cp)
            return
        all_jobs = jobs()
        cp['status'] = 'running_fine_RIGHT_spatial_diagnostic'
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=p['execution']['workers'], initializer=worker_init) as pool:
            for case in p['cases']:
                pending = [job for job in all_jobs if job['case']['id'] == case['id']]
                needed = len(pending)*quotas(case['new_count'])['job']+p['execution']['fixed_report_headroom_bytes']
                if expired():
                    cp['status'] = 'deadline_checkpoint_saved'
                    break
                if not fits(guard(), needed):
                    cp.update(status='resource_checkpoint_saved', blocked_case=case['id'], reserved_block_bytes=needed)
                    break
                for job in pending:
                    if expired():
                        cp['status'] = 'deadline_partial_case_checkpoint_saved'
                        break
                    print('SUBMIT FINE RIGHT '+job['id'], flush=True)
                    record = pool.submit(execute, job).result()
                    if record.get('not_submitted_prediction'):
                        cp['status'] = 'deadline_partial_case_checkpoint_saved'
                        break
                    verify(job, record)
                    cp['completed'][job['id']] = record
                    save_cp(cp)
                    print('DONE FINE RIGHT '+str(len(cp['completed']))+'/9 '+job['id'], flush=True)
                if cp['status'] != 'running_fine_RIGHT_spatial_diagnostic':
                    break
        rows, common = [], {}
        for job in all_jobs:
            if job['id'] not in cp['completed']:
                continue
            scored, report = verify(job, cp['completed'][job['id']])
            rows.extend(scored)
            key = job['case']['id']
            shared = {k: report[k] for k in ('full_target_array_sha256', 'input_hashes', 'raw_sensor_hashes', 'estimated_state_sha256', 'estimated_alpha_sha256', 'score_start_s', 'score_end_s')}
            if key in common and common[key] != shared:
                raise AssertionError('Methods did not share all target/label/observation/estimate/scoring inputs')
            common[key] = shared
        if len(cp['completed']) == 9:
            cp['status'] = 'fine_RIGHT_spatial_diagnostic_complete'
        save_cp(cp)
        summary = {'status': cp['status'], 'new_diagnostic_predictions_completed': len(cp['completed']),
            'new_formal_predictions': 0, 'formal_total_unchanged': 2238, 'previous_accepted_diagnostics': 21,
            'accepted_numeric_total_with_this_run': 2259+len(cp['completed']),
            'source_signature': source, 'checkpoint_sha256': base.file_hash(RUN/'checkpoint.json'),
            'shared_case_inputs_verified': len(common), 'old_density_failure_overridden': False,
            'full_foundation_passed': False, 'S4_complete': False, 'S5_complete': False,
            'independent_sampling_acceptance_still_required': True}
        freeze_bytes(RUN/'reports/fine_RIGHT_analysis.json', coarse.json_bytes(summary))
        freeze_bytes(RUN/'reports/cohort_results.json', coarse.json_bytes({'rows': rows}))
        freeze_bytes(RUN/'reports/manifest.json', coarse.json_bytes({'source_signature': source, 'jobs': cp['completed'],
            'checkpoint_sha256': summary['checkpoint_sha256'], 'outputs_sha256': {n: base.file_hash(RUN/'reports'/n) for n in ('fine_RIGHT_analysis.json', 'cohort_results.json')}}))
        print(json.dumps({k:v for k,v in summary.items() if k != 'source_signature'}), flush=True)
    except BaseException as error:
        if cp is not None:
            status = 'deadline_checkpoint_saved' if 'Deadline' in str(error) else 'resource_checkpoint_saved' if 'Resource checkpoint' in str(error) else 'failed_checkpoint_saved'
            cp.update(status=status, error=repr(error))
            save_cp(cp)
        raise
    finally:
        if started:
            put(RUN/'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
