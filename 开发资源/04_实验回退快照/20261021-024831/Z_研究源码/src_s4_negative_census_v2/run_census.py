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
sys.path.insert(0, str(ROOT / 'src_s4_density_repair_v2'))
import run_density_repair_v2 as dep
import shapely
from geometry import complete_geometry, GEOMETRY_EPS

base, np, pipeline = dep.base, dep.np, dep.pipeline
PROTOCOL = ROOT / 'protocol_negative_census_v2.json'
RUN = ROOT / 'runs' / 'resume_S4_negative_census_v2'


def signature():
    result = dep.signature()
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
        raise RuntimeError('Census run budget reached; preserve history')
    if submitting:
        total = sum(f.stat().st_size for f in ROOT.rglob('*') if f.is_file())
        if total+p['minimum_free_research_headroom_before_submit_bytes'] > p['experiment_budget_bytes']:
            raise RuntimeError('Insufficient reserved research headroom; do not submit')


def cell_keys(xy, spacing):
    cells = np.rint(xy/spacing).astype(np.int64)
    if not np.allclose(cells*spacing, xy, rtol=0, atol=1e-10) or np.any(np.abs(cells) >= 2**31):
        raise AssertionError('Coordinates not on accepted finite raster')
    shifted = (cells+2**31).astype(np.uint64)
    return (shifted[:, 0] << np.uint64(32)) | shifted[:, 1]


def enumerate_negative(body, spacing, tolerance, outer_distance, quad_segs):
    minx, miny, maxx, maxy = shapely.bounds(body)
    ix = np.arange(np.floor((minx-outer_distance)/spacing), np.ceil((maxx+outer_distance)/spacing)+1, dtype=np.int32)
    iy = np.arange(np.floor((miny-outer_distance)/spacing), np.ceil((maxy+outer_distance)/spacing)+1, dtype=np.int32)
    outer = shapely.buffer(body, outer_distance, quad_segs=quad_segs)
    near = shapely.buffer(body, tolerance+.0001, quad_segs=quad_segs)
    for shape in (body, outer, near):
        shapely.prepare(shape)
    selected = []
    chunk = max(1, 60000//len(ix))
    for start in range(0, len(iy), chunk):
        gx, gy = np.meshgrid(ix, iy[start:start+chunk])
        xy = np.column_stack((gx.ravel(), gy.ravel())).astype(float)*spacing
        points = shapely.points(xy)
        inside = shapely.covers(body, points)
        positive = inside.copy()
        shell = ~inside & shapely.covers(near, points)
        positive[shell] = shapely.dwithin(points[shell], body, tolerance+GEOMETRY_EPS)
        ids = ~positive & shapely.covers(outer, points)
        selected.append(xy[ids])
    return np.concatenate(selected)


def extend_targets(old, census, spacing):
    keys = cell_keys(census, spacing)
    old_keys = cell_keys(old['xy'], spacing)
    if len(np.unique(keys)) != len(keys):
        raise AssertionError('Census contains duplicates')
    old_negative = old['group'] == 2
    if not np.isin(old_keys[old_negative], keys).all():
        raise AssertionError('Census dropped original negative points')
    extra = census[~np.isin(keys, old_keys)]
    n, m = len(old['xy']), len(extra)
    values = {'xy': np.concatenate((old['xy'], extra)), 'group': np.concatenate((old['group'], np.full(m, 2, np.int8))),
              'contact_time': np.concatenate((old['contact_time'], np.full(m, np.nan))),
              'contact_index': np.concatenate((old['contact_index'], np.full(m, -1, np.int32))),
              'edge': np.concatenate((old['edge'], np.zeros(m, np.int8))),
              'front_ignored': np.concatenate((old['front_ignored'], np.zeros(m, bool))),
              'reference_ids': np.arange(n, dtype=np.int32), 'new_ids': np.arange(n, n+m, dtype=np.int32),
              'main_ids': old['main_ids'], 'density_140k_ids': old['previous_ids']}
    if len(np.unique(cell_keys(values['xy'], spacing))) != n+m:
        raise AssertionError('Supplemental targets are not unique')
    if int((values['group'] == 2).sum()) != len(census):
        raise AssertionError('Negative census incomplete')
    return values


def freeze_json(path, value):
    if path.exists():
        if base.read_json(path) != value:
            raise AssertionError('Refusing to overwrite frozen input: '+str(path))
    else:
        base.write_json_retry(path, value)


def target_paths(case):
    folder = RUN / 'targets' / case
    return folder / 'targets.npz', folder / 'target_manifest.json'


def prepare_case(case):
    p = base.read_json(PROTOCOL)
    if base.file_hash(dep.RUN / 'checkpoint.json') != p['dependency_checkpoint_sha256']:
        raise AssertionError('Closed 280k checkpoint changed')
    acceptance = dep.RUN / 'reports' / 'acceptance_v3' / 'density_acceptance.json'
    diagnostic = ROOT / 'runs' / 'resume_S4_sampling_diagnostic_v1' / 'reports' / 'sampling_diagnosis.json'
    if base.file_hash(acceptance) != p['dependency_acceptance_sha256'] or base.file_hash(diagnostic) != p['sampling_diagnostic_sha256']:
        raise AssertionError('Accepted read-only dependencies changed')
    case_id = case['id']
    data, main, mf = pipeline.core.load_case(p['partition'], case_id)
    if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
        raise AssertionError('Reference truth convergence failed')
    if not np.allclose(np.diff(data['fine_time']), .005, atol=1e-10, rtol=0) or not np.allclose(np.diff(data['time']), .02, atol=1e-10, rtol=0):
        raise AssertionError('Truth or observation time grid changed')
    old_path = dep.target_path(case_id, p['contact_tolerance_m'])
    meta = base.read_json(old_path.with_suffix('.json'))
    if base.file_hash(old_path) != meta['file_sha256']:
        raise AssertionError('Frozen reference targets changed')
    with np.load(old_path) as saved:
        old = {key: saved[key] for key in saved.files}
    _, body, right = complete_geometry(data['fine_state'])
    if not shapely.is_valid(body) or not shapely.is_valid(right):
        raise AssertionError('Reference geometry invalid')
    census = enumerate_negative(body, p['grid_spacing_m'], p['contact_tolerance_m'], p['negative_outer_buffer_m'], p['buffer_quad_segs'])
    if len(census) != case['negative_census_count'] or len(census) != meta['sampling']['capacity'][2]:
        raise AssertionError('Census differs from frozen raster population')
    targets = extend_targets(old, census, p['grid_spacing_m'])
    if len(targets['xy']) != case['full_target_count']:
        raise AssertionError('Census target count differs')
    extra = shapely.points(targets['xy'][targets['new_ids']])
    if shapely.dwithin(extra, body, .05+GEOMETRY_EPS).any() or not shapely.dwithin(extra, body, .5+GEOMETRY_EPS).all():
        raise AssertionError('New targets must be unique near-field continuous noncontacts')
    for key in ('xy', 'group', 'contact_time', 'contact_index', 'edge', 'front_ignored'):
        if not np.array_equal(targets[key][targets['reference_ids']], old[key], equal_nan=True):
            raise AssertionError('Original 280k coordinates or labels changed')
    if not np.array_equal(targets['xy'][targets['main_ids']], main['xy']):
        raise AssertionError('Original 70k coordinates changed')
    for condition in p['conditions']:
        c = next(c for c in pipeline.condition_list() if c['id'] == condition)
        _, obs = pipeline.load_observation(p['partition'], case_id, c)
        if obs['descriptor']['input_hashes'] != mf['files']:
            raise AssertionError('Common observation inputs changed')
    path, manifest_path = target_paths(case_id)
    if path.exists():
        with np.load(path) as saved:
            if set(saved.files) != set(targets) or any(not np.array_equal(saved[key], value, equal_nan=True) for key, value in targets.items()):
                raise AssertionError('Frozen census targets changed')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **targets)
    proof = {'status': 'passed', 'case_id': case_id, 'target_count': len(targets['xy']), 'negative_census_count': len(census),
             'original_280000_preserved': True, 'original_70000_preserved': True, 'continuous_noncontact_labels_verified': True,
             'target_file_sha256': base.file_hash(path), 'target_array_sha256': {key: base.array_hash(v) for key, v in targets.items()},
             'input_hashes': mf['files'], 'source_signature': signature(), 'new_prediction_jobs': 0,
             'online_numerical_code': 'frozen_src_s4_v1_with_identical_raw_observations', 'density_gate_override': False}
    freeze_json(manifest_path, proof)
    return proof


def prepare():
    p = base.read_json(PROTOCOL)
    prior = ROOT / 'runs' / 'resume_S4_negative_census_v1' / 'checkpoint.json'
    if base.file_hash(prior) != p['prior_single_case_census_checkpoint_sha256']:
        raise AssertionError('Previous single-case census checkpoint changed')
    proof = []
    for case in p['cases']:
        guard()
        proof.append(prepare_case(case))
        print('FROZEN NEGATIVE CENSUS '+case['id'], flush=True)
    return {'status': 'passed', 'cases': proof, 'source_signature': signature(), 'new_prediction_jobs': 0}


def references():
    p = base.read_json(PROTOCOL)
    cases = {case['id'] for case in p['cases']}
    result = [j for j in dep.jobs() if j['case_id'] in cases and j['core_id'] in p['core_ids']
              and j['condition']['id'] in p['conditions'] and j['contact_tolerance_m'] == p['contact_tolerance_m']]
    if len(result) != p['prediction_jobs']:
        raise AssertionError('Registered census method/observation count differs')
    return result


def jobs():
    result = []
    for ref in references():
        job = {'reference': ref, 'source_signature': signature(), 'stage': 'negative_census_failure_diagnostic'}
        job['id'] = ref['case_id']+'__'+ref['core_id']+'__'+ref['condition']['id']+'__'+hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
        result.append(job)
    return result


def read_reference(ref):
    cp = base.read_json(dep.RUN / 'checkpoint.json')
    _, report = dep.verify(ref, cp['completed'][ref['id']])
    _, previous = dep.baseline_for(ref)
    with np.load(dep.RUN / 'jobs' / ref['id'] / 'new_target_results.npz') as saved:
        delta = {key: saved[key] for key in saved.files}
    with np.load(dep.target_path(ref['case_id'], ref['contact_tolerance_m'])) as saved:
        full = dep.reconstruct_delta(previous, delta, saved['previous_ids'], saved['new_ids'], len(saved['xy']))
    if any(base.array_hash(full[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
        raise AssertionError('Frozen reference point arrays changed')
    return full, report, cp['completed'][ref['id']]['report_sha256']


def execute(job):
    guard()
    if signature() != job['source_signature']:
        raise AssertionError('Frozen census source changed')
    ref = job['reference']
    old, old_report, old_sha = read_reference(ref)
    data, _, mf = pipeline.core.load_case(ref['partition'], ref['case_id'])
    raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    if obs['descriptor']['sensor_array_hashes'] != old_report['raw_sensor_hashes']:
        raise AssertionError('Raw observations differ from reference')
    target_path, manifest_path = target_paths(ref['case_id'])
    proof = base.read_json(manifest_path)
    if base.file_hash(target_path) != proof['target_file_sha256']:
        raise AssertionError('Frozen census targets changed')
    with np.load(target_path) as saved:
        targets = {key: saved[key] for key in saved.files}
    result = pipeline.evaluate({**data, **raw}, targets, pipeline.Method(**ref['method']), [pipeline.Variant(**v) for v in ref['variants']])
    for key, array in result['point_output'].items():
        if not np.array_equal(array[targets['reference_ids']], old[key], equal_nan=True):
            raise AssertionError('Original 280k per-point predictions/counts changed')
    delta = {key: array[targets['new_ids']] for key, array in result['point_output'].items()}
    reconstructed = dep.reconstruct_delta(old, delta, targets['reference_ids'], targets['new_ids'], len(targets['xy']))
    hashes = {key: base.array_hash(array) for key, array in result['point_output'].items()}
    if any(base.array_hash(reconstructed[key]) != sha for key, sha in hashes.items()):
        raise AssertionError('Full census arrays failed lossless reconstruction')
    rows = []
    phases = np.rint(targets['xy']/.0125).astype(np.int64)
    phases = phases[:, 0] % 2+2*(phases[:, 1] % 2)
    cut = float(data['time'][-1]-3)
    groups = {'original_70000': targets['main_ids'], 'previous_140000': targets['density_140k_ids'],
              'reference_280000': targets['reference_ids'], 'added_negative_census': targets['new_ids'],
              'full_negative_census': np.flatnonzero(targets['group'] == 2)}
    for q in range(4):
        groups['negative_grid_phase_'+str(q)] = np.flatnonzero((targets['group'] == 2) & (phases == q))
    for state in result['states']:
        variant = state['variant']
        first = state['first']
        false = np.isfinite(first) & (first >= 2-1e-9) & (first <= cut+1e-9)
        for cohort, ids in groups.items():
            negative = ids[~np.isfinite(targets['contact_time'][ids])]
            n, f = len(negative), int(false[negative].sum())
            rows.append({'case_id': ref['case_id'], 'core_id': ref['core_id'], 'condition': ref['condition']['id'], 'variant': variant.tag,
                         'cohort': cohort, 'negative_count': n, 'false_positive_points': f, 'negative_fp_pct': 100*f/n if n else None,
                         'score_start_s': 2., 'score_end_s': cut})
    folder = RUN / 'jobs' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    base.write_json_retry(folder / 'configuration.json', job)
    base.write_json_retry(folder / 'negative_rates.json', rows)
    np.savez_compressed(folder / 'new_negative_results.npz', **delta)
    np.savez_compressed(folder / 'frame_results.npz', counts=result['frame_counts'], time=data['time'], phase=result['observed_phase'])
    report = {'id': job['id'], 'source_signature': signature(), 'original_280k_point_outputs_exact': True,
              'target_manifest_sha256': base.file_hash(manifest_path), 'target_file_sha256': proof['target_file_sha256'],
              'input_hashes': mf['files'], 'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'],
              'reference_report_sha256': old_sha, 'full_point_arrays_sha256': hashes,
              'score_start_s': 2., 'score_end_s': cut,
              'output_sha256': {name: base.file_hash(folder / name) for name in ('configuration.json', 'negative_rates.json', 'new_negative_results.npz', 'frame_results.npz')}}
    base.write_json_retry(folder / 'report.json', report)
    guard()
    return {'report_sha256': base.file_hash(folder / 'report.json')}


def verify(job, record):
    folder = RUN / 'jobs' / job['id']
    if base.file_hash(folder / 'report.json') != record['report_sha256'] or base.read_json(folder / 'configuration.json') != job:
        raise AssertionError('Census report/configuration changed')
    report = base.read_json(folder / 'report.json')
    if report['source_signature'] != signature():
        raise AssertionError('Census numerical source changed')
    for name, sha in report['output_sha256'].items():
        if base.file_hash(folder / name) != sha:
            raise AssertionError('Census output changed')
    target_path, manifest_path = target_paths(job['reference']['case_id'])
    if base.file_hash(target_path) != report['target_file_sha256'] or base.file_hash(manifest_path) != report['target_manifest_sha256']:
        raise AssertionError('Census target input changed')
    old, old_report, sha = read_reference(job['reference'])
    if sha != report['reference_report_sha256'] or old_report['raw_sensor_hashes'] != report['raw_sensor_hashes'] or old_report['input_hashes'] != report['input_hashes']:
        raise AssertionError('Census reference inputs changed')
    with np.load(target_path) as saved, np.load(folder / 'new_negative_results.npz') as delta:
        full = dep.reconstruct_delta(old, {key: delta[key] for key in delta.files}, saved['reference_ids'], saved['new_ids'], len(saved['xy']))
    if any(base.array_hash(full[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
        raise AssertionError('Census full arrays failed stored hash verification')
    return base.read_json(folder / 'negative_rates.json'), report


def save_cp(cp):
    path = RUN / 'checkpoint.json'
    base.write_json_retry(path, cp)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (base.file_hash(path)+'.json.gz'), path.read_bytes())


def probe():
    cases = []
    for case in base.read_json(PROTOCOL)['cases']:
        path, _ = target_paths(case['id'])
        with np.load(path) as saved:
            cases.append({'id': case['id'], 'target_count': len(saved['xy']), 'negative_count': int((saved['group'] == 2).sum()),
                          'reference_count': len(saved['reference_ids'])})
    return {'source_signature': signature(), 'root': str(pipeline.common.ROOT), 'cases': cases,
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
        if actual != {'source_signature': signature(), 'root': str(ROOT),
                      'cases': [{'id': c['id'], 'target_count': c['full_target_count'], 'negative_count': c['negative_census_count'], 'reference_count': 280000} for c in p['cases']],
                      'resource_defaults': [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']]}:
            raise AssertionError('Actual Windows worker input/resource/source acceptance failed')
        proof['actual_worker_probe'] = actual
        for name, sha in signature().items():
            saved = RUN / 'source' / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and base.file_hash(saved) != sha:
                raise AssertionError('Frozen source snapshot changed')
            if not saved.exists():
                saved.write_bytes((ROOT / name).read_bytes())
        freeze_json(RUN / 'preflight.json', proof)
        if args.check_only:
            print(json.dumps({'status': 'preflight_passed', 'actual_worker': actual, 'new_prediction_jobs': 0}), flush=True)
            return
        cp = base.read_json(RUN / 'checkpoint.json') if (RUN / 'checkpoint.json').exists() else {'completed': {}, 'source_signature': signature()}
        if cp['source_signature'] != signature():
            raise AssertionError('Cannot resume changed census source')
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
        cp.update(status='running', prediction_jobs_expected=p['prediction_jobs'], previous_completed_new_scoring_jobs=p['previous_completed_new_scoring_jobs'])
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
                    print(f'DONE CENSUS2 {len(cp["completed"])}/{p["prediction_jobs"]} {job["id"]}', flush=True)
        rows, shared = [], {}
        for job in jobs():
            if job['id'] not in cp['completed']:
                continue
            values, report = verify(job, cp['completed'][job['id']])
            rows.extend(values)
            key = (job['reference']['case_id'], job['reference']['condition']['id'])
            common = (report['input_hashes'], report['raw_sensor_hashes'], report['target_file_sha256'], report['score_start_s'], report['score_end_s'])
            if key in shared and shared[key] != common:
                raise AssertionError('Census methods did not share the same experiment inputs')
            shared[key] = common
        cp['status'] = 'census_subset_complete' if len(cp['completed']) == p['prediction_jobs'] else 'deadline_checkpoint_saved'
        save_cp(cp)
        base.csv_rows(RUN / 'reports' / 'negative_census_rates.csv', rows)
        summary = {'status': cp['status'], 'new_prediction_jobs_completed': len(cp['completed']), 'prediction_jobs_expected': p['prediction_jobs'],
                   'cases': p['cases'],
                   'original_280k_per_point_outputs_preserved': True, 'all_outputs_and_inputs_verified': True,
                   'density_gate_override': False, 'S4_complete': False, 'S5_complete': False, 'physical_validation': False,
                   'scope': p['scope'], 'checkpoint_sha256': base.file_hash(RUN / 'checkpoint.json')}
        base.write_json_retry(RUN / 'reports' / 'census_analysis.json', summary)
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': signature(), 'jobs': cp['completed'],
            'output_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in ('negative_census_rates.csv', 'census_analysis.json')}})
        print(json.dumps(summary), flush=True)
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
