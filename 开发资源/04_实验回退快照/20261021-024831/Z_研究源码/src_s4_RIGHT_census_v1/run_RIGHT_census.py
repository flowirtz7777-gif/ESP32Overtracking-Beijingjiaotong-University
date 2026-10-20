from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_positive_population_feasibility_v1'))
sys.path.insert(0, str(ROOT / 'src_s4_lossless_storage_audit_v1'))
import run_feasibility as geometry
from packing import pack_points, unpack_points
import shapely
from geometry import complete_geometry, GEOMETRY_EPS
from prediction import rollout

base, np, census, pipeline = geometry.base, geometry.np, geometry.census, geometry.pipeline
PROTOCOL = ROOT / 'protocol_RIGHT_census_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_RIGHT_census_v1'
FIELDS = ('xy', 'group', 'contact_time', 'contact_index', 'edge', 'front_ignored')


def signature():
    result = geometry.signature()
    paths = [PROTOCOL, ROOT / 'protocol_lossless_storage_audit_v1.json',
             ROOT / 'src_s4_lossless_storage_audit_v1' / 'packing.py',
             *sorted(Path(__file__).parent.glob('*.py'))]
    result.update({p.relative_to(ROOT).as_posix(): base.file_hash(p) for p in paths})
    return result


def worker_init():
    p = base.read_json(PROTOCOL)['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def guard():
    measured = pipeline.common.storage_guard()
    used = sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file()) if RUN.exists() else 0
    if used > base.read_json(PROTOCOL)['execution']['new_run_budget_bytes']:
        raise RuntimeError('RIGHT census run budget reached; preserve history')
    return {**measured, 'run_bytes': used}


def block_fits(whole_remaining, run_remaining, quotas, fixed_headroom):
    return min(whole_remaining, run_remaining) >= sum(quotas)+fixed_headroom


def append_targets(old, delta):
    if len(old['xy']) != 280000 or set(delta) != set(FIELDS):
        raise AssertionError('Expected complete frozen 280000 prefix and six delta fields')
    values = {key: np.concatenate((old[key], delta[key])) for key in FIELDS}
    for key in FIELDS:
        if not np.array_equal(values[key][:280000], old[key], equal_nan=True):
            raise AssertionError('Original prefix changed')
    values['main_ids'] = old['main_ids']
    return values


def load_targets(case_id):
    proof_path = geometry.RUN / 'targets' / case_id / 'manifest.json'
    proof = base.read_json(proof_path)
    geometry.verify_case(proof)
    with np.load(ROOT / proof['original_target_path']) as saved, np.load(proof_path.with_name('new_eligible_RIGHT.npz')) as extra:
        old = {key: saved[key] for key in saved.files}
        delta = {key: extra[key] for key in extra.files}
    return append_targets(old, delta), proof, base.file_hash(proof_path)


def merge_outputs(old, delta, full_count):
    return census.dep.reconstruct_delta(old, delta, np.arange(280000, dtype=np.int32),
        np.arange(280000, full_count, dtype=np.int32), full_count)


def projected_summary(data, targets, state, ids):
    selected = {key: targets[key][ids] for key in FIELDS}
    projected = {key: state[key][ids] for key in ('raw', 'first', 'valid')}
    projected['variant'] = state['variant']
    projected['point_counts'] = {key: value[ids] for key, value in state['point_counts'].items()}
    return pipeline.summarize(data, selected, projected)


def jobs():
    p = base.read_json(PROTOCOL)
    references = census.dep.jobs()
    result = []
    for case in p['cases']:
        for core in p['core_ids']:
            matches = [r for r in references if r['case_id'] == case['id'] and r['core_id'] == core
                       and r['condition']['id'] == 'noise100_s1' and r['contact_tolerance_m'] == .05]
            if len(matches) != 1:
                raise AssertionError('Fixed reference matrix differs')
            ref = matches[0]
            if ref['variants'] != p['variants'] or ref['method']['dt'] != p['prediction_dt_s']:
                raise AssertionError('Online method or variants were changed')
            job = {'reference': ref, 'case': case, 'source_signature': signature(), 'stage': 'fixed_full_RIGHT_foundation_diagnostic'}
            digest = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:12]
            job['id'] = case['id']+'__'+core+'__noise100_s1__'+digest
            result.append(job)
    if len(result) != 9:
        raise AssertionError('Expected nine diagnostic predictions')
    return result


def prepare():
    p = base.read_json(PROTOCOL)
    gp = geometry.RUN / 'reports' / 'population_feasibility.json'
    sp = ROOT / 'runs' / 'resume_S4_lossless_storage_audit_v1' / 'reports' / 'storage_audit.json'
    if base.file_hash(gp) != p['geometry_report_sha256'] or base.file_hash(sp) != p['storage_audit_sha256']:
        raise AssertionError('Frozen geometry or storage acceptance changed')
    if base.file_hash(ROOT / 'src_s4_lossless_storage_audit_v1' / 'packing.py') != p['packing_source_sha256']:
        raise AssertionError('Frozen lossless output layer changed')
    proofs = []
    for case in p['cases']:
        guard()
        targets, proof, sha = load_targets(case['id'])
        data, main, mf = pipeline.core.load_case(p['partition'], case['id'])
        cut = float(data['time'][-1]-3)
        if len(targets['xy']) != case['full_target_count'] or int(geometry.eligible_right(targets, cut).sum()) != case['RIGHT_count']:
            raise AssertionError('Complete finite RIGHT population inventory differs')
        keys = census.cell_keys(targets['xy'], .0125)
        if len(np.unique(keys)) != len(keys):
            raise AssertionError('Full targets are not unique')
        for key in FIELDS:
            if not np.array_equal(targets[key][targets['main_ids']], main[key], equal_nan=True):
                raise AssertionError('Original 70000 coordinates/order/labels differ: '+key)
        if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
            raise AssertionError('Truth reference convergence failed')
        _, body, right = complete_geometry(data['fine_state'])
        if not shapely.is_valid(body) or not shapely.is_valid(right):
            raise AssertionError('Truth geometry invalid')
        if not shapely.dwithin(shapely.points(targets['xy'][280000:]), body, .05+GEOMETRY_EPS).all():
            raise AssertionError('New RIGHT labels disagree with continuous truth body')
        cond = next(c for c in pipeline.condition_list() if c['id'] == 'noise100_s1')
        raw, obs = pipeline.load_observation(p['partition'], case['id'], cond)
        if obs['descriptor']['input_hashes'] != mf['files'] or not np.array_equal(raw['time'], data['time']) or len(raw['time']) >= 65535:
            raise AssertionError('Common observation, scoring grid, or uint16 bound failed')
        proofs.append({'id': case['id'], 'target_count': len(targets['xy']), 'main_count': len(targets['main_ids']),
                       'RIGHT_count': case['RIGHT_count'], 'extra_count': case['extra_count'], 'target_manifest_sha256': sha,
                       'target_coordinate_sha256': base.array_hash(targets['xy']), 'input_hashes': mf['files'],
                       'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'], 'score_start_s': 2., 'score_end_s': cut})
        print('FROZEN RIGHT CENSUS INPUT '+case['id'], flush=True)
    return {'status': 'passed', 'cases': proofs, 'source_signature': signature(), 'new_predictions_completed': 0}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def npz_bytes(values):
    stream = io.BytesIO()
    np.savez_compressed(stream, **values)
    return stream.getvalue()


def execute(job):
    guard()
    if signature() != job['source_signature']:
        raise AssertionError('Frozen source changed')
    ref = job['reference']
    old, old_report, old_sha = census.read_reference(ref)
    targets, proof, proof_sha = load_targets(ref['case_id'])
    data, _, mf = pipeline.core.load_case(ref['partition'], ref['case_id'])
    raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    if obs['descriptor']['sensor_array_hashes'] != old_report['raw_sensor_hashes']:
        raise AssertionError('Common raw observations differ')
    inputs = {**data, **raw}
    result = pipeline.evaluate(inputs, targets, pipeline.Method(**ref['method']), [pipeline.Variant(**v) for v in ref['variants']])
    for key, value in result['point_output'].items():
        if not np.array_equal(value[:280000], old[key], equal_nan=True):
            raise AssertionError('Original 280000 point output changed: '+key)
    delta = {key: value[280000:] for key, value in result['point_output'].items()}
    packed, metadata = pack_points(delta, inputs['time'])
    if len(packed) != 18 or any(value.dtype != np.uint16 for value in packed.values()):
        raise AssertionError('Admitted fixed-width uint16 bound not satisfied')
    decoded = unpack_points(packed, metadata, inputs['time'])
    full = merge_outputs(old, decoded, len(targets['xy']))
    hashes = {key: base.array_hash(value) for key, value in result['point_output'].items()}
    if any(base.array_hash(full[key]) != sha for key, sha in hashes.items()):
        raise AssertionError('Full point arrays are not byte-exact after lossless output encoding')
    cohorts = {'original_70000': targets['main_ids'],
               'full_eligible_RIGHT_finite_population': np.flatnonzero(geometry.eligible_right(targets, float(inputs['time'][-1]-3))),
               'original_280000_near_negative_controls': np.flatnonzero(~np.isfinite(targets['contact_time']))}
    rows = []
    for state in result['states']:
        for cohort, ids in cohorts.items():
            row = projected_summary(inputs, targets, state, ids)
            row.update(case_id=ref['case_id'], core_id=ref['core_id'], condition='noise100_s1', variant=state['variant'].tag,
                       cohort=cohort, independent_validation=False, changed_population_not_used_for_old_rankings=True)
            rows.append(row)
    blobs = {'configuration.json': json_bytes(job), 'summary.json': json_bytes(rows),
             'packed_metadata.json': json_bytes(metadata), 'packed_delta.npz': npz_bytes(packed),
             'frame_results.npz': npz_bytes({'time': inputs['time'], 'counts': result['frame_counts'], 'phase': result['observed_phase']}),
             'timing.json': json_bytes({**result['timing'], 'desktop_not_MCU': True})}
    report = {'id': job['id'], 'source_signature': signature(), 'original_280000_all_point_outputs_exact': True,
              'target_manifest_sha256': proof_sha, 'target_delta_sha256': proof['target_delta_file_sha256'],
              'original_target_sha256': proof['original_target_sha256'], 'full_target_count': len(targets['xy']),
              'full_coordinate_sha256': base.array_hash(targets['xy']),
              'full_label_array_sha256': {key: base.array_hash(targets[key]) for key in geometry.LABEL_KEYS},
              'input_hashes': mf['files'], 'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'],
              'estimated_state_sha256': base.array_hash(raw['state']), 'estimated_alpha_sha256': base.array_hash(raw['alpha']),
              'reference_report_sha256': old_sha, 'full_point_arrays_sha256': hashes,
              'score_start_s': 2., 'score_end_s': float(inputs['time'][-1]-3),
              'output_sha256': {name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()}}
    blobs['report.json'] = json_bytes(report)
    total = sum(len(blob) for blob in blobs.values())
    if total > job['case']['single_job_quota_bytes']:
        raise RuntimeError('Encoded output exceeds reserved quota; no job file written')
    guard()
    folder = RUN / 'jobs' / job['id']
    if folder.exists():
        raise AssertionError('Partial prior output exists; preserve it for recovery, never overwrite')
    folder.mkdir(parents=True)
    for name, blob in blobs.items():
        (folder / name).write_bytes(blob)
    return {'report_sha256': base.file_hash(folder / 'report.json'), 'output_bytes': total}


def verify(job, record):
    folder = RUN / 'jobs' / job['id']
    report = base.read_json(folder / 'report.json')
    if base.file_hash(folder / 'report.json') != record['report_sha256'] or base.read_json(folder / 'configuration.json') != job or report['source_signature'] != signature():
        raise AssertionError('Frozen job output/source/configuration changed')
    for name, sha in report['output_sha256'].items():
        if base.file_hash(folder / name) != sha:
            raise AssertionError('Output hash mismatch: '+name)
    ref = job['reference']
    targets, proof, proof_sha = load_targets(ref['case_id'])
    old, old_report, old_sha = census.read_reference(ref)
    data, _, mf = pipeline.core.load_case(ref['partition'], ref['case_id'])
    raw, obs = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    if (proof_sha != report['target_manifest_sha256'] or proof['target_delta_file_sha256'] != report['target_delta_sha256'] or
        proof['original_target_sha256'] != report['original_target_sha256'] or mf['files'] != report['input_hashes'] or
        old_sha != report['reference_report_sha256'] or old_report['raw_sensor_hashes'] != report['raw_sensor_hashes'] or
        obs['descriptor']['sensor_array_hashes'] != report['raw_sensor_hashes']):
        raise AssertionError('Target, reference, or shared observation dependency changed')
    if base.array_hash(raw['state']) != report['estimated_state_sha256'] or base.array_hash(raw['alpha']) != report['estimated_alpha_sha256']:
        raise AssertionError('Common raw estimated state changed')
    if base.array_hash(targets['xy']) != report['full_coordinate_sha256'] or any(base.array_hash(targets[key]) != sha for key, sha in report['full_label_array_sha256'].items()):
        raise AssertionError('Full reconstructed targets/labels changed')
    with np.load(folder / 'packed_delta.npz') as saved:
        delta = unpack_points({key: saved[key] for key in saved.files}, base.read_json(folder / 'packed_metadata.json'), raw['time'])
    full = merge_outputs(old, delta, report['full_target_count'])
    if any(base.array_hash(full[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
        raise AssertionError('Lossless full array reconstruction failed')
    rows = base.read_json(folder / 'summary.json')
    for vdict in ref['variants']:
        v = pipeline.Variant(**vdict)
        state = {key: full[v.tag+'_'+key] for key in ('first', 'raw', 'valid')}
        state['variant'] = v
        state['point_counts'] = {key: full[v.tag+'_'+key] for key in ('TP', 'FP', 'ref_FP', 'support', 'negative_opportunities', 'ref_negative_opportunities')}
        cohorts = {'original_70000': targets['main_ids'],
                   'full_eligible_RIGHT_finite_population': np.flatnonzero(geometry.eligible_right(targets, report['score_end_s'])),
                   'original_280000_near_negative_controls': np.flatnonzero(~np.isfinite(targets['contact_time']))}
        for cohort, ids in cohorts.items():
            saved = next(row for row in rows if row['variant'] == v.tag and row['cohort'] == cohort)
            if any(saved[key] != value for key, value in projected_summary({**data, **raw}, targets, state, ids).items()):
                raise AssertionError('Stored cohort summary cannot be exactly reproduced')
    return rows, report


def save_cp(cp):
    path = RUN / 'checkpoint.json'
    base.write_json_retry(path, cp)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (base.file_hash(path)+'.json.gz'), path.read_bytes())


def probe():
    cases = []
    for case in base.read_json(PROTOCOL)['cases']:
        targets, _, _ = load_targets(case['id'])
        cases.append({'id': case['id'], 'target_count': len(targets['xy']), 'main_count': len(targets['main_ids'])})
    return {'root': str(pipeline.common.ROOT), 'source_signature': signature(), 'cases': cases,
            'resource_defaults': list(pipeline.common.storage_guard.__defaults__)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    p = base.read_json(PROTOCOL)
    deadline = datetime.fromisoformat(p['execution']['deadline_local'])
    if datetime.now(timezone.utc) >= deadline:
        parser.error('Authorized deadline passed')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        worker_init()
        guard()
        proof = prepare()
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=240)
        expected = {'root': str(ROOT), 'source_signature': signature(), 'resource_defaults': [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']],
                    'cases': [{'id': case['id'], 'target_count': case['full_target_count'], 'main_count': 70000} for case in p['cases']]}
        if actual != expected:
            raise AssertionError('Actual Windows worker input/source/resource acceptance failed')
        proof['actual_worker_probe'] = actual
        for name, sha in signature().items():
            target = RUN / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and base.file_hash(target) != sha:
                raise AssertionError('Frozen source snapshot changed')
            if not target.exists():
                target.write_bytes((ROOT / name).read_bytes())
        census.freeze_json(RUN / 'preflight.json', proof)
        if args.check_only:
            print(json.dumps({'status': 'preflight_passed', 'cases': actual['cases'], 'new_predictions_completed': 0}), flush=True)
            return
        cp = base.read_json(RUN / 'checkpoint.json') if (RUN / 'checkpoint.json').exists() else {'completed': {}, 'source_signature': signature()}
        if cp['source_signature'] != signature():
            raise AssertionError('Cannot resume changed source')
        all_jobs = jobs()
        for job in all_jobs:
            if job['id'] in cp['completed']:
                verify(job, cp['completed'][job['id']])
            elif (RUN / 'jobs' / job['id'] / 'report.json').exists():
                record = {'report_sha256': base.file_hash(RUN / 'jobs' / job['id'] / 'report.json')}
                verify(job, record)
                cp['completed'][job['id']] = record
        cp['status'] = 'running_fixed_RIGHT_census_diagnostic'
        started = True
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now(), 'deadline_local': deadline.isoformat()})
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=p['execution']['workers'], initializer=worker_init) as pool:
            for case in p['cases']:
                pending = [job for job in all_jobs if job['case']['id'] == case['id'] and job['id'] not in cp['completed']]
                if not pending:
                    continue
                if (deadline-datetime.now(timezone.utc)).total_seconds() < p['execution']['minimum_seconds_before_case_block']:
                    cp['status'] = 'deadline_checkpoint_saved'
                    break
                measured = guard()
                quotas = [job['case']['single_job_quota_bytes'] for job in pending]
                if not block_fits(p['execution']['experiment_budget_bytes']-measured['experiment_bytes'], p['execution']['new_run_budget_bytes']-measured['run_bytes'], quotas, p['execution']['fixed_report_headroom_bytes']):
                    cp.update(status='resource_checkpoint_saved', blocked_case=case['id'], reserved_block_bytes=sum(quotas))
                    break
                futures = {}
                for job in pending:
                    if datetime.now(timezone.utc) >= deadline:
                        cp['status'] = 'deadline_partial_case_checkpoint_saved'
                        break
                    futures[pool.submit(execute, job)] = job
                    print('SUBMIT RIGHT CENSUS '+job['id'], flush=True)
                for future in as_completed(futures):
                    job = futures[future]
                    record = future.result()
                    verify(job, record)
                    cp['completed'][job['id']] = record
                    save_cp(cp)
                    print('DONE RIGHT CENSUS '+str(len(cp['completed']))+'/9 '+job['id'], flush=True)
                if cp['status'] != 'running_fixed_RIGHT_census_diagnostic':
                    break
        rows, shared = [], {}
        for job in all_jobs:
            if job['id'] not in cp['completed']:
                continue
            scores, report = verify(job, cp['completed'][job['id']])
            rows.extend(scores)
            key = job['case']['id']
            common = (report['full_coordinate_sha256'], report['full_label_array_sha256'], report['raw_sensor_hashes'], report['estimated_state_sha256'], report['estimated_alpha_sha256'], report['score_start_s'], report['score_end_s'])
            if key in shared and shared[key] != common:
                raise AssertionError('Methods did not share exact targets/labels/observations/estimated state/scoring')
            shared[key] = common
        if len(cp['completed']) == 9:
            cp['status'] = 'fixed_RIGHT_census_diagnostic_complete'
        save_cp(cp)
        summary = {'status': cp['status'], 'new_foundation_diagnostic_predictions_completed': len(cp['completed']), 'diagnostic_predictions_expected_max': 9,
                   'formal_jobs_this_cycle_unchanged': 162, 'formal_jobs_total_unchanged': 2238, 'previous_temporal_diagnostic_replays': 12,
                   'all_outputs_inputs_full_array_reconstruction_and_shared_inputs_verified': True,
                   'old_full_density_failure_overridden': False, 'independent_validation': False, 'S4_complete': False, 'S5_complete': False,
                   'checkpoint_sha256': base.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature()}
        base.write_json_retry(RUN / 'reports' / 'RIGHT_census_analysis.json', summary)
        base.write_json_retry(RUN / 'reports' / 'cohort_results.json', {'rows': rows})
        base.csv_rows(RUN / 'reports' / 'cohort_results.csv', rows)
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': signature(), 'jobs': cp['completed'],
            'outputs_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in ('RIGHT_census_analysis.json', 'cohort_results.json', 'cohort_results.csv')}})
        print(json.dumps({key: value for key, value in summary.items() if key != 'source_signature'}), flush=True)
    except BaseException as error:
        if cp is not None:
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
