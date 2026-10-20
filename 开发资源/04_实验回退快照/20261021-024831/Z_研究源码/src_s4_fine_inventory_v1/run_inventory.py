from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_positive_population_feasibility_v1'))
import run_feasibility as dep

base, np, pipeline, shapely = dep.base, dep.np, dep.pipeline, dep.shapely
PROTOCOL = ROOT / 'protocol_fine_inventory_20261016_v1.json'
RUN = ROOT / 'runs' / 'night_20261016_fine_inventory_v1'
LABEL_KEYS = dep.LABEL_KEYS


def quota(points):
    if not isinstance(points, int) or points < 0:
        raise ValueError('Exact nonnegative integer point count required')
    return 3 * ((points * 36 * 101 + 99) // 100 + 1024**2) + 2 * 1024**2


def array_stream(dtype, shape):
    return hashlib.sha256(str((np.dtype(dtype).str, tuple(shape))).encode('ascii'))


def coarse_phase(ix, iy):
    return (np.asarray(ix) % 2 == 0) & (np.asarray(iy) % 2 == 0)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def guard(extra=0):
    p = base.read_json(PROTOCOL)['execution']
    measured = pipeline.common.storage_guard(p['reserve_bytes'], p['experiment_budget_bytes'])
    used = sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file()) if RUN.exists() else 0
    if used + extra > p['new_run_budget_bytes'] or measured['experiment_bytes'] + extra > p['experiment_budget_bytes']:
        raise RuntimeError('Inventory resource checkpoint: preserve history, do not raise quota')
    return {**measured, 'inventory_run_bytes': used}


def put(path, value):
    blob = encode(value)
    guard(len(blob) + 8192)
    base.write_json_retry(path, value)


def signature():
    result = dep.signature()
    result.update({f.relative_to(ROOT).as_posix(): base.file_hash(f) for f in
                   [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]})
    return result


def worker_init():
    p = base.read_json(PROTOCOL)['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def probe():
    return {'root': str(pipeline.common.ROOT), 'python': sys.executable, 'source_signature': signature(),
            'resource_defaults': list(pipeline.common.storage_guard.__defaults__),
            'deadline_local': base.read_json(PROTOCOL)['authorized_until_local'], 'new_prediction_jobs': 0}


def chunks(body, right, p):
    spacing = p['grid_spacing_m']
    minx, miny, maxx, maxy = shapely.bounds(body)
    ix = np.arange(np.floor((minx-.5)/spacing), np.ceil((maxx+.5)/spacing)+1, dtype=np.int32)
    iy = np.arange(np.floor((miny-.5)/spacing), np.ceil((maxy+.5)/spacing)+1, dtype=np.int32)
    if len(ix) > p['chunk_point_budget']:
        raise RuntimeError('A single raster row exceeds fixed memory bound')
    step = max(1, p['chunk_point_budget']//len(ix))
    near = shapely.buffer(body, p['contact_tolerance_m']+.0001, quad_segs=p['buffer_quad_segs'])
    outer = shapely.buffer(body, .5, quad_segs=p['buffer_quad_segs'])
    right_near = shapely.buffer(right, .2, quad_segs=p['buffer_quad_segs'])
    band = shapely.buffer(shapely.boundary(body), .2, quad_segs=p['buffer_quad_segs'])
    for shape in (body, near, outer, right_near, band):
        shapely.prepare(shape)
    for start in range(0, len(iy), step):
        gx, gy = np.meshgrid(ix, iy[start:start+step])
        x, y = gx.ravel(), gy.ravel()
        xy = np.column_stack((x, y)).astype(float)*spacing
        points = shapely.points(xy)
        positive = shapely.covers(body, points)
        shell = ~positive & shapely.covers(near, points)
        positive[shell] = shapely.dwithin(points[shell], body, p['contact_tolerance_m']+dep.GEOMETRY_EPS)
        boundary = positive & shapely.covers(right_near, points) & shapely.covers(band, points)
        masks = (boundary, positive & ~boundary, ~positive & shapely.covers(outer, points))
        coarse = coarse_phase(x, y)
        yield {'row_start': start, 'row_end': min(start+step, len(iy)), 'total_rows': len(iy),
               'capacity': [int(m.sum()) for m in masks],
               'coarse_capacity': [int(np.count_nonzero(m & coarse)) for m in masks],
               'xy': xy[positive], 'group': np.where(boundary[positive], 0, 1).astype(np.int8),
               'coarse_positive': coarse[positive]}


def inventory_case(case):
    p = base.read_json(PROTOCOL)
    guard()
    old_report = base.read_json(ROOT / p['coarse_population_report'])
    previous = next(c for c in old_report['cases'] if c['case_id'] == case)
    data, main, mf = pipeline.core.load_case(p['partition'], case)
    if (mf['summary']['reference_edge_error_005_vs_0025_m'] > .005 or
            not np.allclose(np.diff(data['fine_time']), .005, atol=1e-10, rtol=0) or
            not np.allclose(np.diff(data['time']), .02, atol=1e-10, rtol=0)):
        raise AssertionError('Frozen reference record or time grids differ')
    old_path = ROOT / previous['original_target_path']
    if base.file_hash(old_path) != previous['original_target_sha256']:
        raise AssertionError('Old 280k asset changed')
    with np.load(old_path) as stored:
        old = {key: stored[key] for key in stored.files}
    if (len(old['xy']) != 280000 or len(main['xy']) != 70000 or
            not np.array_equal(old['xy'][old['main_ids']], main['xy']) or
            not np.allclose(old['xy']/p['grid_spacing_m'], np.rint(old['xy']/p['grid_spacing_m']), rtol=0, atol=1e-8)):
        raise AssertionError('Old main prefix or nested grid membership differs')
    segments, body, right = dep.complete_geometry(data['fine_state'])
    if not shapely.is_valid(body) or not shapely.is_valid(right):
        raise AssertionError('Invalid frozen geometry')
    tree = dep.build_temporal_tree(segments, p['temporal_union_leaf_size'])
    reference = {'time': data['fine_time'], 'state': data['fine_state']}
    labels = dep.label_from_tree(old['xy'], reference, segments, tree, p['contact_tolerance_m'])
    if any(not np.array_equal(labels[k], old[k], equal_nan=True) for k in LABEL_KEYS):
        raise AssertionError('Original 280k labels changed')
    print('FINE EXACT OLD LABELS ' + case, flush=True)
    n = previous['all_positive_cells']
    streams = {'xy': array_stream(np.float64, (n, 2)), 'group': array_stream(np.int8, (n,))}
    for k in LABEL_KEYS:
        streams[k] = array_stream(labels[k].dtype, (n,))
    expected_hashes = {'xy': previous['population_coordinates_sha256'], 'group': previous['population_group_sha256'],
                       **previous['population_label_array_sha256']}
    capacity, coarse_capacity = np.zeros(3, np.int64), np.zeros(3, np.int64)
    right_counts, coarse_right = np.zeros(2, np.int64), np.zeros(2, np.int64)
    records, edge_counts = [], {}
    positive_count, coarse_positive_count = 0, 0
    cut = float(data['time'][-1]-3)
    finished = True
    for index, chunk in enumerate(chunks(body, right, p)):
        if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
            finished = False
            break
        capacity += chunk['capacity']
        coarse_capacity += chunk['coarse_capacity']
        xy, group = chunk['xy'], chunk['group']
        values = dep.label_from_tree(xy, reference, segments, tree, p['contact_tolerance_m'])
        if not np.isfinite(values['contact_time']).all():
            raise AssertionError('A geometrically positive fine cell lacks contact label')
        eligible = dep.eligible_right(values, cut)
        coarse = chunk['coarse_positive']
        right_counts += [np.count_nonzero(eligible & (group == k)) for k in range(2)]
        coarse_right += [np.count_nonzero(eligible & coarse & (group == k)) for k in range(2)]
        arrays = {'xy': xy, 'group': group, **values}
        for k, value in arrays.items():
            streams[k].update(np.ascontiguousarray(value[coarse]).tobytes())
        for k in np.unique(values['edge']):
            edge_counts[str(int(k))] = edge_counts.get(str(int(k)), 0) + int(np.count_nonzero(values['edge'] == k))
        positive_count += len(xy)
        coarse_positive_count += int(coarse.sum())
        records.append({'row_start': chunk['row_start'], 'row_end': chunk['row_end'], 'total_rows': chunk['total_rows'],
                        'positive_count': len(xy), 'eligible_RIGHT_count': int(eligible.sum()),
                        'array_hashes': {k: base.array_hash(v) for k, v in arrays.items()}})
        if index % 10 == 0:
            guard(128 * 1024)
            print(f'FINE INVENTORY {case} rows {chunk["row_end"]}/{chunk["total_rows"]} positives {positive_count} RIGHT {int(right_counts.sum())}', flush=True)
    coarse_hashes = {k: sha.hexdigest() for k, sha in streams.items()}
    if finished and (capacity[0]+capacity[1] != positive_count or coarse_capacity.tolist() != previous['stratum_capacity'] or
                     coarse_positive_count != n or coarse_hashes != expected_hashes or
                     coarse_right.tolist() != previous['eligible_RIGHT_stratum_counts']):
        raise AssertionError('Nested coarse phase did not exactly reproduce previous full population and labels')
    resource = guard(128 * 1024)
    new_points = int(right_counts.sum())-previous['all_eligible_RIGHT_cells'] if finished else None
    output_minimum = quota(new_points) if finished else None
    remaining = p['execution']['experiment_budget_bytes']-resource['experiment_bytes']
    return {'case_id': case, 'status': 'complete_geometry_label_inventory' if finished else 'deadline_partial_case_not_complete',
            'new_prediction_jobs': 0, 'grid_spacing_m': p['grid_spacing_m'], 'stratum_capacity_measured': capacity.tolist(),
            'positive_cells_measured': positive_count, 'eligible_RIGHT_strata_measured': right_counts.tolist(),
            'old_280000_coordinate_main_prefix_and_all_label_arrays_exact': True,
            'coarse_population_reproduced_exactly': finished,
            'coarse_positive_count_measured': coarse_positive_count, 'coarse_population_array_hashes': coarse_hashes,
            'new_RIGHT_points_outside_existing_full_coarse_RIGHT_measured': new_points,
            'three_method_output_only_minimum_reservation_bytes': output_minimum,
            'remaining_whole_budget_bytes_at_measurement': remaining,
            'would_fit_ignoring_new_input_assets': finished and output_minimum <= remaining,
            'new_prediction_batch_admitted': False, 'prediction_inputs_saved': False,
            'positive_edge_counts': edge_counts, 'regenerable_chunk_proofs': records,
            'chunk_proof_chain_sha256': hashlib.sha256(encode(records)).hexdigest(),
            'source_signature': signature(), 'original_280000_file_sha256': previous['original_target_sha256'],
            'frozen_truth_input_files_sha256': mf['files'], 'score_start_s': 2., 'score_end_s': cut,
            'not_continuous_space_or_vehicle_safety_proof': True}


def save_cp(cp):
    path = RUN / 'checkpoint.json'
    put(path, cp)
    payload = path.read_bytes()
    guard(len(gzip_bytes(payload)) + 8192)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (base.file_hash(path)+'.json.gz'), payload)


def gzip_bytes(payload):
    import gzip
    return gzip.compress(payload, mtime=0)


def main():
    p = base.read_json(PROTOCOL)
    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
        raise RuntimeError('Today noon authorization ended')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        worker_init()
        guard(256 * 1024)
        for key in ('coarse_population_report', 'previous_authorization_summary'):
            if base.file_hash(ROOT / p[key]) != p[key+'_sha256']:
                raise AssertionError('Frozen dependency changed: ' + key)
        source = signature()
        if (RUN / 'checkpoint.json').exists():
            cp = base.read_json(RUN / 'checkpoint.json')
            if cp['source_signature'] != source or cp['status'].startswith('complete_') or cp['status'].startswith('resource_'):
                raise AssertionError('Frozen/completed/resource-stopped run cannot be blindly restarted')
        else:
            cp = {'source_signature': source, 'completed': {}, 'new_prediction_jobs': 0}
        for name, sha in source.items():
            target = RUN / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and base.file_hash(target) != sha:
                raise AssertionError('Frozen source snapshot differs')
            if not target.exists():
                guard((ROOT / name).stat().st_size + 8192)
                target.write_bytes((ROOT / name).read_bytes())
        put(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        started = True
        cp['status'] = 'geometry_inventory_running_not_prediction'
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=180)
            expected_python = Path(r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe')
            if (Path(actual['python']) != expected_python or actual['root'] != str(ROOT) or
                    actual['source_signature'] != source or actual['resource_defaults'] != [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']]):
                raise AssertionError('Actual Windows inventory worker acceptance failed')
            put(RUN / 'actual_worker.json', actual)
            for case in p['cases']:
                if case in cp['completed']:
                    if base.file_hash(RUN / 'cases' / (case+'.json')) != cp['completed'][case]['report_sha256']:
                        raise AssertionError('Previously completed case changed')
                    continue
                if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
                    break
                result = pool.submit(inventory_case, case).result()
                path = RUN / 'cases' / (case+'.json')
                if path.exists():
                    raise AssertionError('Case evidence already exists; preserve it')
                put(path, result)
                if result['status'] != 'complete_geometry_label_inventory':
                    cp['status'] = 'deadline_partial_case_saved'
                    break
                cp['completed'][case] = {'report_sha256': base.file_hash(path),
                                         'eligible_RIGHT_count': sum(result['eligible_RIGHT_strata_measured']),
                                         'new_RIGHT_points': result['new_RIGHT_points_outside_existing_full_coarse_RIGHT_measured'],
                                         'output_only_minimum_bytes': result['three_method_output_only_minimum_reservation_bytes'],
                                         'would_fit_ignoring_new_input_assets': result['would_fit_ignoring_new_input_assets']}
                save_cp(cp)
                print('DONE FINE INVENTORY '+str(len(cp['completed']))+'/3 '+case, flush=True)
        cp['status'] = 'complete_fine_inventory_no_prediction_admitted' if len(cp['completed']) == 3 else 'deadline_inventory_checkpoint_saved'
        save_cp(cp)
        summary = {'status': cp['status'], 'completed_cases': cp['completed'], 'new_prediction_jobs': 0,
                   'formal_baseline_unchanged': 2238, 'accepted_diagnostics_unchanged': 21,
                   'accepted_numerical_baseline_unchanged': 2259, 'old_full_density_gate_overridden': False,
                   'new_prediction_batch_admitted': False, 'S4_complete': False, 'S5_complete': False,
                   'inventory_assets_not_saved_as_prediction_targets': True, 'resource': guard(),
                   'checkpoint_sha256': base.file_hash(RUN / 'checkpoint.json'), 'source_signature': source}
        put(RUN / 'reports' / 'fine_inventory_summary.json', summary)
        put(RUN / 'reports' / 'manifest.json', {'source_signature': source,
            'outputs_sha256': {'fine_inventory_summary.json': base.file_hash(RUN / 'reports' / 'fine_inventory_summary.json')},
            'case_reports_sha256': {case+'.json': record['report_sha256'] for case, record in cp['completed'].items()},
            'checkpoint_sha256': summary['checkpoint_sha256']})
        print(json.dumps({k: v for k, v in summary.items() if k != 'source_signature'}), flush=True)
    except BaseException as error:
        if cp is not None and started:
            cp.update(status='resource_inventory_checkpoint_saved' if isinstance(error, RuntimeError) and 'resource' in str(error) else 'failed_inventory_checkpoint_saved', error=repr(error))
            save_cp(cp)
        raise
    finally:
        if started:
            put(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
