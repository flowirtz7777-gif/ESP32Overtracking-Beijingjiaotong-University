from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import io
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_negative_census_v2'))
import run_census as census
import shapely
from geometry import complete_geometry, label_contacts, classify_edges, GEOMETRY_EPS
from common import Vehicle, body_corners

base, np, pipeline = census.base, census.np, census.pipeline
PROTOCOL = ROOT / 'protocol_positive_population_feasibility_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_positive_population_feasibility_v1'
LABEL_KEYS = ('contact_time', 'contact_index', 'edge', 'front_ignored')


def signature():
    result = census.signature()
    for path in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]:
        result[path.relative_to(ROOT).as_posix()] = base.file_hash(path)
    return result


def worker_init():
    p = base.read_json(PROTOCOL)['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def guard():
    measured = pipeline.common.storage_guard()
    used = sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file()) if RUN.exists() else 0
    if used > base.read_json(PROTOCOL)['execution']['new_run_budget_bytes']:
        raise RuntimeError('Feasibility run budget reached; preserve history')
    return {**measured, 'new_run_bytes': used}


def build_temporal_tree(segments, leaf_size):
    if not len(segments) or leaf_size < 1:
        raise ValueError('Nonempty segments and a positive leaf size are required')
    def build(lo, hi):
        if hi-lo <= leaf_size:
            shape = shapely.union_all(segments[lo:hi])
            children = None
        else:
            mid = (lo+hi)//2
            left, right = build(lo, mid), build(mid, hi)
            shape = shapely.union_all([left['shape'], right['shape']])
            children = (left, right)
        shapely.prepare(shape)
        return {'lo': lo, 'hi': hi, 'shape': shape, 'children': children}
    return build(0, len(segments))


def label_from_tree(xy, reference, segments, tree, tolerance=.05, vehicle=Vehicle()):
    points = shapely.points(xy)
    first = np.full(len(xy), -1, np.int32)
    edge = np.zeros(len(xy), np.int8)
    initial = shapely.polygons(body_corners(reference['state'][:1], vehicle))[0]
    inside = shapely.dwithin(points, initial, tolerance+GEOMETRY_EPS)
    first[inside] = 0
    edge[inside] = classify_edges(xy[inside], reference['state'][0], vehicle)
    pending = np.flatnonzero(~inside & shapely.dwithin(points, tree['shape'], tolerance+GEOMETRY_EPS))
    # Time-ordered union nodes locate the earliest matching segment without
    # querying every already-contacted point against every later body polygon.
    def visit(node, ids):
        if not len(ids):
            return
        if node['children'] is None:
            remaining = ids
            for k in range(node['lo'], node['hi']):
                hit = shapely.dwithin(points[remaining], segments[k], tolerance+GEOMETRY_EPS)
                first[remaining[hit]] = k+1
                remaining = remaining[~hit]
                if not len(remaining):
                    break
            if len(remaining):
                raise AssertionError('Union membership has no matching constituent segment')
        else:
            left, right = node['children']
            hit_left = shapely.dwithin(points[ids], left['shape'], tolerance+GEOMETRY_EPS)
            visit(left, ids[hit_left])
            visit(right, ids[~hit_left])
    visit(tree, pending)
    for first_index in np.unique(first[first > 0]):
        ids = np.flatnonzero(first == first_index)
        k = int(first_index)-1
        corners = body_corners(reference['state'][k:k+2], vehicle)
        pairs = [[3, 0], [0, 1], [1, 2], [2, 3]]
        vertices = np.stack([corners[:, pair, :].reshape(4, 2) for pair in pairs])
        faces = shapely.convex_hull(shapely.multipoints(vertices))
        distances = shapely.distance(points[ids, None], faces[None, :])
        order = np.argsort(distances, axis=1)
        classified = (order[:, 0]+1).astype(np.int8)
        tied = np.take_along_axis(distances, order[:, :2], axis=1)
        corner = tied[:, 1]-tied[:, 0] <= .001
        for pair, code in [((0, 1), 5), ((1, 2), 6), ((0, 3), 7), ((2, 3), 8)]:
            selected = corner & (np.sort(order[:, :2], axis=1) == pair).all(axis=1)
            classified[selected] = code
        if np.any(np.min(distances, axis=1) > tolerance+GEOMETRY_EPS+1e-8):
            raise AssertionError('New contact lacks swept-face evidence')
        edge[ids] = classified
    contact = np.full(len(xy), np.nan)
    valid = first >= 0
    contact[valid] = reference['time'][first[valid]]
    return {'contact_time': contact, 'contact_index': first, 'edge': edge, 'front_ignored': np.isin(edge, [1, 5, 7])}


def enumerate_positive(body, right, p):
    spacing = p['grid_spacing_m']
    minx, miny, maxx, maxy = shapely.bounds(body)
    ix = np.arange(np.floor((minx-.5)/spacing), np.ceil((maxx+.5)/spacing)+1, dtype=np.int32)
    iy = np.arange(np.floor((miny-.5)/spacing), np.ceil((maxy+.5)/spacing)+1, dtype=np.int32)
    near = shapely.buffer(body, p['contact_tolerance_m']+.0001, quad_segs=p['buffer_quad_segs'])
    outer = shapely.buffer(body, .5, quad_segs=p['buffer_quad_segs'])
    right_near = shapely.buffer(right, .2, quad_segs=p['buffer_quad_segs'])
    band = shapely.buffer(shapely.boundary(body), .2, quad_segs=p['buffer_quad_segs'])
    for shape in (body, near, outer, right_near, band):
        shapely.prepare(shape)
    rows, groups, capacity = [], [], np.zeros(3, np.int64)
    chunk = max(1, 60000//len(ix))
    for start in range(0, len(iy), chunk):
        gx, gy = np.meshgrid(ix, iy[start:start+chunk])
        xy = np.column_stack((gx.ravel(), gy.ravel())).astype(float)*spacing
        pts = shapely.points(xy)
        positive = shapely.covers(body, pts)
        shell = ~positive & shapely.covers(near, pts)
        positive[shell] = shapely.dwithin(pts[shell], body, p['contact_tolerance_m']+GEOMETRY_EPS)
        boundary = positive & shapely.covers(right_near, pts) & shapely.covers(band, pts)
        masks = (boundary, positive & ~boundary, ~positive & shapely.covers(outer, pts))
        capacity += np.asarray([np.count_nonzero(m) for m in masks])
        rows.append(xy[positive])
        groups.append(np.where(boundary[positive], 0, 1).astype(np.int8))
    return np.concatenate(rows), np.concatenate(groups), capacity.tolist()


def eligible_right(labels, cut):
    return ((labels['edge'] == 2) & ~labels['front_ignored'] &
            (labels['contact_time'] >= 2-1e-9) & (labels['contact_time'] <= cut+1e-9))


def prepare_case(case):
    p = base.read_json(PROTOCOL)
    guard()
    data, main, mf = pipeline.core.load_case(p['partition'], case['id'])
    if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
        raise AssertionError('Reference truth convergence failed')
    if not np.allclose(np.diff(data['fine_time']), .005, atol=1e-10, rtol=0) or not np.allclose(np.diff(data['time']), .02, atol=1e-10, rtol=0):
        raise AssertionError('Truth or observation time grid changed')
    old_path = census.dep.target_path(case['id'], .05)
    old_meta = base.read_json(old_path.with_suffix('.json'))
    if base.file_hash(old_path) != old_meta['file_sha256']:
        raise AssertionError('Frozen old targets changed')
    with np.load(old_path) as saved:
        old = {key: saved[key] for key in saved.files}
    if len(old['xy']) != 280000 or len(main['xy']) != 70000 or not np.array_equal(old['xy'][old['main_ids']], main['xy']):
        raise AssertionError('Original point sets not exactly preserved')
    segments, body, right = complete_geometry(data['fine_state'])
    if not shapely.is_valid(body) or not shapely.is_valid(right):
        raise AssertionError('Truth geometry invalid')
    tree = build_temporal_tree(segments, p['temporal_union_leaf_size'])
    reference = {'time': data['fine_time'], 'state': data['fine_state']}
    check = label_from_tree(old['xy'], reference, segments, tree, p['contact_tolerance_m'])
    for key in LABEL_KEYS:
        if not np.array_equal(check[key], old[key], equal_nan=True):
            raise AssertionError('Hierarchical labeling did not exactly reproduce all old 280k labels: '+key)
    print('EXACT OLD LABELS '+case['id'], flush=True)
    xy, group, capacity = enumerate_positive(body, right, p)
    if capacity != case['expected_stratum_capacity'] or capacity != old_meta['sampling']['capacity']:
        raise AssertionError('Finite raster populations differ from registered truth geometry')
    keys = census.cell_keys(xy, p['grid_spacing_m'])
    if len(np.unique(keys)) != len(keys):
        raise AssertionError('Positive population contains duplicate cells')
    labels = label_from_tree(xy, reference, segments, tree, p['contact_tolerance_m'])
    if not np.isfinite(labels['contact_time']).all():
        raise AssertionError('Enumerated positive cells lack continuous body contact labels')
    cut = float(data['time'][-1]-3)
    selected = eligible_right(labels, cut)
    all_right_xy = xy[selected]
    all_right_keys = keys[selected]
    old_keys = census.cell_keys(old['xy'], p['grid_spacing_m'])
    old_right = eligible_right(old, cut)
    if not np.isin(old_keys[old_right], all_right_keys).all():
        raise AssertionError('Full eligible RIGHT population dropped original eligible RIGHT points')
    is_new = ~np.isin(all_right_keys, old_keys)
    values = {'xy': all_right_xy[is_new], 'group': group[selected][is_new],
              **{key: value[selected][is_new] for key, value in labels.items()}}
    added = len(values['xy'])
    full_count = 280000+added
    inputs = {}
    for condition in ('clean', 'noise100_s1'):
        cond = next(c for c in pipeline.condition_list() if c['id'] == condition)
        _, obs = pipeline.load_observation(p['partition'], case['id'], cond)
        if obs['descriptor']['input_hashes'] != mf['files']:
            raise AssertionError('Common raw observation dependencies changed')
        inputs[condition] = obs['descriptor']['sensor_array_hashes']
    folder = RUN / 'targets' / case['id']
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'new_eligible_RIGHT.npz'
    if path.exists():
        with np.load(path) as saved:
            if set(saved.files) != set(values) or any(not np.array_equal(saved[key], value, equal_nan=True) for key, value in values.items()):
                raise AssertionError('Refusing to modify a frozen population input')
    else:
        buffer = io.BytesIO()
        np.savez_compressed(buffer, **values)
        encoded = buffer.getvalue()
        resource = guard()
        limits = p['execution']
        if resource['new_run_bytes']+len(encoded) > limits['new_run_budget_bytes'] or resource['experiment_bytes']+len(encoded) > limits['experiment_budget_bytes']:
            raise RuntimeError('Lossless target asset would exceed budget; no file written')
        path.write_bytes(encoded)
    with np.load(path) as saved:
        if any(not np.array_equal(saved[key], value, equal_nan=True) for key, value in values.items()):
            raise AssertionError('Lossless geometry population roundtrip failed')
    proof = {'case_id': case['id'], 'status': 'geometry_and_label_feasibility_passed', 'new_prediction_jobs': 0,
             'stratum_capacity': capacity, 'all_positive_cells': len(xy), 'all_eligible_RIGHT_cells': int(selected.sum()),
             'eligible_RIGHT_stratum_counts': [int(np.count_nonzero(selected & (group == k))) for k in range(2)],
             'all_positive_edge_counts': {str(int(k)): int(np.count_nonzero(labels['edge'] == k)) for k in np.unique(labels['edge'])},
             'old_eligible_RIGHT_cells': int(old_right.sum()), 'new_eligible_RIGHT_cells': added,
             'hypothetical_full_target_count': full_count, 'all_old_280k_labels_exact': True,
             'original_70000_and_140000_and_280000_preserved_via_read_only_original': True,
             'population_coordinates_sha256': base.array_hash(xy), 'population_group_sha256': base.array_hash(group),
             'population_label_array_sha256': {key: base.array_hash(value) for key, value in labels.items()},
             'full_positive_intermediate_arrays_regenerable_not_claimed_as_stored_prediction_inputs': True,
             'target_delta_file_sha256': base.file_hash(path), 'target_delta_bytes': path.stat().st_size,
             'target_delta_array_sha256': {key: base.array_hash(value) for key, value in values.items()},
             'original_target_path': str(old_path.relative_to(ROOT)), 'original_target_sha256': old_meta['file_sha256'],
             'input_hashes': mf['files'], 'raw_sensor_array_hashes': inputs, 'score_start_s': 2., 'score_end_s': cut,
             'target_choice_uses_prediction_outputs': False, 'source_signature': signature()}
    census.freeze_json(folder / 'manifest.json', proof)
    guard()
    return proof


def verify_case(proof):
    folder = RUN / 'targets' / proof['case_id']
    if base.read_json(folder / 'manifest.json') != proof or proof['source_signature'] != signature():
        raise AssertionError('Frozen population proof or source changed')
    path = folder / 'new_eligible_RIGHT.npz'
    if base.file_hash(path) != proof['target_delta_file_sha256']:
        raise AssertionError('Frozen population delta changed')
    old_path = ROOT / proof['original_target_path']
    if base.file_hash(old_path) != proof['original_target_sha256']:
        raise AssertionError('Frozen original 280000 changed')
    with np.load(path) as saved, np.load(old_path) as old:
        for key, sha in proof['target_delta_array_sha256'].items():
            if base.array_hash(saved[key]) != sha:
                raise AssertionError('Lossless population array changed')
        if len(saved['xy']) != proof['new_eligible_RIGHT_cells'] or not eligible_right(saved, proof['score_end_s']).all():
            raise AssertionError('Delta includes points outside the fixed eligible RIGHT cohort')
        old_keys = census.cell_keys(old['xy'], .0125)
        new_keys = census.cell_keys(saved['xy'], .0125)
        if len(np.unique(new_keys)) != len(new_keys) or np.isin(new_keys, old_keys).any():
            raise AssertionError('Population delta duplicates or changes an original point')
    _, _, mf = pipeline.core.load_case('development_v2_n70000', proof['case_id'])
    if mf['files'] != proof['input_hashes']:
        raise AssertionError('Frozen trajectory input changed')
    for condition, hashes in proof['raw_sensor_array_hashes'].items():
        cond = next(c for c in pipeline.condition_list() if c['id'] == condition)
        _, obs = pipeline.load_observation('development_v2_n70000', proof['case_id'], cond)
        if obs['descriptor']['sensor_array_hashes'] != hashes:
            raise AssertionError('Frozen shared raw observations changed')


def probe():
    p = base.read_json(PROTOCOL)
    return {'root': str(pipeline.common.ROOT), 'source_signature': signature(),
            'resource_defaults': list(pipeline.common.storage_guard.__defaults__),
            'new_prediction_jobs': 0, 'deadline_local': p['execution']['deadline_local']}


def save_cp(cp):
    path = RUN / 'checkpoint.json'
    base.write_json_retry(path, cp)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (base.file_hash(path)+'.json.gz'), path.read_bytes())


def main():
    p = base.read_json(PROTOCOL)
    deadline = datetime.fromisoformat(p['execution']['deadline_local'])
    if datetime.now(timezone.utc) >= deadline:
        raise RuntimeError('Authorized deadline passed')
    kernel, mutex = pipeline.core.acquire_lock()
    cp = None
    try:
        worker_init()
        guard()
        cp = base.read_json(RUN / 'checkpoint.json') if (RUN / 'checkpoint.json').exists() else {'completed': {}, 'source_signature': signature(), 'new_prediction_jobs': 0}
        if cp['source_signature'] != signature() or len(cp['completed']) == 3:
            raise AssertionError('Changed source or already-complete feasibility run; preserve old outputs')
        for name, sha in signature().items():
            target = RUN / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and base.file_hash(target) != sha:
                raise AssertionError('Frozen feasibility source changed')
            if not target.exists():
                target.write_bytes((ROOT / name).read_bytes())
        cp['status'] = 'geometry_label_resource_feasibility_running'
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=180)
            if actual['root'] != str(ROOT) or actual['source_signature'] != signature() or actual['resource_defaults'] != [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']]:
                raise AssertionError('Actual Windows feasibility worker acceptance failed')
            census.freeze_json(RUN / 'actual_worker.json', actual)
            for case in p['cases']:
                if case['id'] in cp['completed']:
                    verify_case(cp['completed'][case['id']])
                    continue
                if datetime.now(timezone.utc) >= deadline:
                    break
                proof = pool.submit(prepare_case, case).result()
                verify_case(proof)
                cp['completed'][case['id']] = proof
                save_cp(cp)
                print('DONE POPULATION FEASIBILITY '+str(len(cp['completed']))+'/3 '+case['id'], flush=True)
        resource = guard()
        raw_bound = sum(v['hypothetical_full_target_count']*p['raw_storage_upper_bound_point_bytes_per_prediction']*p['hypothetical_predictions_per_case'] for v in cp['completed'].values())
        delta_bound = sum(v['new_eligible_RIGHT_cells']*p['raw_storage_upper_bound_point_bytes_per_prediction']*p['hypothetical_predictions_per_case'] for v in cp['completed'].values())
        available = p['execution']['experiment_budget_bytes']-resource['experiment_bytes']
        cp['status'] = 'geometry_label_resource_feasibility_complete' if len(cp['completed']) == 3 else 'deadline_checkpoint_saved'
        save_cp(cp)
        result = {'status': cp['status'], 'cases': list(cp['completed'].values()), 'new_prediction_jobs': 0,
                  'existing_formal_this_cycle': 162, 'existing_formal_total': 2238, 'existing_accepted_diagnostic_replays': 12,
                  'resource': resource, 'remaining_research_bytes': available, 'hypothetical_18_prediction_raw_point_storage_bytes': raw_bound,
                  'hypothetical_18_prediction_delta_only_raw_point_storage_bytes': delta_bound,
                  'full_batch_uncompressed_point_output_fits_remaining_budget': len(cp['completed']) == 3 and raw_bound <= available,
                  'compressed_prediction_storage_not_measured_or_guaranteed': True, 'new_prediction_batch_authorized_by_this_feasibility': False,
                  'old_density_gate_overridden': False, 'S4_complete': False, 'S5_complete': False,
                  'checkpoint_sha256': base.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature()}
        base.write_json_retry(RUN / 'reports' / 'population_feasibility.json', result)
        base.csv_rows(RUN / 'reports' / 'population_capacities.csv', list(cp['completed'].values()))
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': signature(),
            'outputs_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in ('population_feasibility.json', 'population_capacities.csv')},
            'checkpoint_sha256': result['checkpoint_sha256']})
        print(json.dumps({key: value for key, value in result.items() if key not in ('cases', 'source_signature')}), flush=True)
    except BaseException as error:
        if cp is not None:
            cp.update(status='failed_checkpoint_saved', error=repr(error))
            save_cp(cp)
        raise
    finally:
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
