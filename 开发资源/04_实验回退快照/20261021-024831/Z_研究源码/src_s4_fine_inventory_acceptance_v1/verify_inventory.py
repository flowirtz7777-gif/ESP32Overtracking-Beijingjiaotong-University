from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import itertools
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_fine_inventory_v1'))
import run_inventory as inventory

base, np, pipeline = inventory.base, inventory.np, inventory.pipeline
PROTOCOL = ROOT / 'protocol_fine_inventory_acceptance_20261016_v1.json'
RUN = ROOT / 'runs' / 'night_20261016_fine_inventory_acceptance_v1'


def reservation(new_points):
    if type(new_points) is not int or new_points < 0:
        raise ValueError('Measured integer point count required')
    each = (36 * new_points * 101 + 99) // 100 + 1024**2
    return 3 * each + 2 * 1024**2


def validate_metadata(proof, coarse):
    rows = proof['regenerable_chunk_proofs']
    if hashlib.sha256(inventory.encode(rows)).hexdigest() != proof['chunk_proof_chain_sha256']:
        raise AssertionError('Chunk chain changed')
    last = 0
    total_positive = total_right = 0
    for row in rows:
        if row['row_start'] != last or row['row_end'] <= last or row['row_end'] > row['total_rows']:
            raise AssertionError('Raster row gap/overlap')
        last = row['row_end']
        total_positive += row['positive_count']
        total_right += row['eligible_RIGHT_count']
    if not rows or last != rows[-1]['total_rows'] or total_positive != proof['positive_cells_measured'] or total_right != sum(proof['eligible_RIGHT_strata_measured']):
        raise AssertionError('Incomplete raster count')
    expected = {'xy': coarse['population_coordinates_sha256'], 'group': coarse['population_group_sha256'],
                **coarse['population_label_array_sha256']}
    if proof['status'] != 'complete_geometry_label_inventory' or proof['coarse_population_array_hashes'] != expected:
        raise AssertionError('Coarse complete population changed')
    new = total_right - coarse['all_eligible_RIGHT_cells']
    if new != proof['new_RIGHT_points_outside_existing_full_coarse_RIGHT_measured'] or reservation(new) != proof['three_method_output_only_minimum_reservation_bytes']:
        raise AssertionError('Measured resource count/reservation differs')
    return new


def guard(extra=0):
    p = base.read_json(PROTOCOL)['execution']
    measured = pipeline.common.storage_guard(p['reserve_bytes'], p['experiment_budget_bytes'])
    used = sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file()) if RUN.exists() else 0
    if used + extra > p['new_run_budget_bytes'] or measured['experiment_bytes'] + extra > p['experiment_budget_bytes']:
        raise RuntimeError('Acceptance resource checkpoint; retain history')
    return {**measured, 'acceptance_run_bytes': used}


def put(path, value):
    guard(len(inventory.encode(value)) + 8192)
    base.write_json_retry(path, value)


def signature():
    result = inventory.signature()
    result.update({f.relative_to(ROOT).as_posix(): base.file_hash(f) for f in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]})
    return result


def dependencies():
    p = base.read_json(PROTOCOL)
    if base.read_json(inventory.RUN / 'runner_lock.json')['status'] != 'stopped':
        raise AssertionError('Inventory still running; do not open its checkpoint')
    for file, key in [('checkpoint.json', 'inventory_checkpoint_sha256'), ('reports/manifest.json', 'inventory_manifest_sha256'), ('reports/fine_inventory_summary.json', 'inventory_summary_sha256')]:
        if base.file_hash(inventory.RUN / file) != p[key]:
            raise AssertionError('Inventory dependency changed: '+file)
    cp = base.read_json(inventory.RUN / 'checkpoint.json')
    manifest = base.read_json(inventory.RUN / 'reports' / 'manifest.json')
    if set(cp['completed']) != set(p['cases']) or cp['source_signature'] != inventory.signature():
        raise AssertionError('Incomplete/changed inventory')
    for name, sha in cp['source_signature'].items():
        if base.file_hash(ROOT / name) != sha or base.file_hash(inventory.RUN / 'source' / name) != sha:
            raise AssertionError('Dependency source/snapshot changed')
    for name, sha in manifest['case_reports_sha256'].items():
        if base.file_hash(inventory.RUN / 'cases' / name) != sha:
            raise AssertionError('Case report changed')
    for path in (inventory.RUN / 'checkpoint_snapshots').glob('*.json.gz'):
        if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != path.name.split('.')[0]:
            raise AssertionError('Inventory snapshot changed')
    return cp


def worker_init():
    p = base.read_json(PROTOCOL)['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def probe():
    return {'python': sys.executable, 'source_signature': signature(), 'resource_defaults': list(pipeline.common.storage_guard.__defaults__),
            'deadline_local': base.read_json(PROTOCOL)['authorized_until_local'], 'new_prediction_jobs': 0}


def rebuild_case(case):
    p, original = base.read_json(PROTOCOL), base.read_json(inventory.PROTOCOL)
    proof = base.read_json(inventory.RUN / 'cases' / (case+'.json'))
    old_summary = base.read_json(ROOT / original['coarse_population_report'])
    coarse = next(c for c in old_summary['cases'] if c['case_id'] == case)
    new_points = validate_metadata(proof, coarse)
    data, main, mf = pipeline.core.load_case(original['partition'], case)
    if mf['files'] != proof['frozen_truth_input_files_sha256']:
        raise AssertionError('Truth inputs changed')
    old_path = ROOT / coarse['original_target_path']
    if base.file_hash(old_path) != proof['original_280000_file_sha256']:
        raise AssertionError('Old target file changed')
    with np.load(old_path) as stored:
        old = {key: stored[key] for key in stored.files}
    if len(old['xy']) != 280000 or not np.array_equal(old['xy'][old['main_ids']], main['xy']):
        raise AssertionError('Old main coordinates changed')
    segments, body, right = inventory.dep.complete_geometry(data['fine_state'])
    tree = inventory.dep.build_temporal_tree(segments, original['temporal_union_leaf_size'])
    ref = {'time': data['fine_time'], 'state': data['fine_state']}
    old_labels = inventory.dep.label_from_tree(old['xy'], ref, segments, tree, original['contact_tolerance_m'])
    if any(not np.array_equal(old_labels[k], old[k], equal_nan=True) for k in inventory.LABEL_KEYS):
        raise AssertionError('Old 280k labels do not reconstruct')
    n = coarse['all_positive_cells']
    dtypes = {'xy': np.dtype('float64'), 'group': np.dtype('int8'), **{k: old_labels[k].dtype for k in inventory.LABEL_KEYS}}
    hashes = {k: hashlib.sha256(str((np.dtype(dtype).str, (n, 2) if k == 'xy' else (n,))).encode('ascii')) for k, dtype in dtypes.items()}
    capacity, coarse_capacity = np.zeros(3, np.int64), np.zeros(3, np.int64)
    eligible_count = np.zeros(2, np.int64)
    edge_counts, checked = {}, 0
    positive = coarse_n = 0
    chunks = inventory.chunks(body, right, original)
    for saved, chunk in itertools.zip_longest(proof['regenerable_chunk_proofs'], chunks):
        if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
            return {'case_id': case, 'status': 'deadline_partial_rebuild_not_complete', 'chunks_rebuilt': checked, 'new_prediction_jobs': 0}
        if saved is None or chunk is None:
            raise AssertionError('Chunk number changed')
        xy, group = chunk['xy'], chunk['group']
        values = inventory.dep.label_from_tree(xy, ref, segments, tree, original['contact_tolerance_m'])
        arrays = {'xy': xy, 'group': group, **values}
        if (any(saved[k] != chunk[k] for k in ('row_start', 'row_end', 'total_rows')) or
                {k: base.array_hash(v) for k, v in arrays.items()} != saved['array_hashes']):
            raise AssertionError('Rebuilt fine chunk bytes/dtype/shape differ')
        eligible = ((values['edge'] == 2) & ~values['front_ignored'] &
                    (values['contact_time'] >= 2-1e-9) & (values['contact_time'] <= proof['score_end_s']+1e-9))
        if saved['positive_count'] != len(xy) or saved['eligible_RIGHT_count'] != int(eligible.sum()):
            raise AssertionError('Rebuilt fine chunk counts differ')
        capacity += chunk['capacity']
        coarse_capacity += chunk['coarse_capacity']
        eligible_count += [np.count_nonzero(eligible & (group == k)) for k in range(2)]
        positive += len(xy)
        coarse_n += int(chunk['coarse_positive'].sum())
        for key, value in arrays.items():
            hashes[key].update(np.ascontiguousarray(value[chunk['coarse_positive']]).tobytes())
        for k in np.unique(values['edge']):
            edge_counts[str(int(k))] = edge_counts.get(str(int(k)), 0) + int(np.count_nonzero(values['edge'] == k))
        checked += 1
        if checked % 100 == 0:
            guard(65536)
            print(f'VERIFY FINE CHUNKS {case} {checked}/{len(proof["regenerable_chunk_proofs"])}', flush=True)
    if (capacity.tolist() != proof['stratum_capacity_measured'] or coarse_capacity.tolist() != coarse['stratum_capacity'] or
            eligible_count.tolist() != proof['eligible_RIGHT_strata_measured'] or edge_counts != proof['positive_edge_counts'] or
            positive != proof['positive_cells_measured'] or coarse_n != coarse['all_positive_cells'] or
            {k: h.hexdigest() for k, h in hashes.items()} != proof['coarse_population_array_hashes']):
        raise AssertionError('Full reconstructed totals/coarse phase differ')
    remaining = 12*1024**3 - guard()['experiment_bytes']
    return {'case_id': case, 'status': 'all_fine_chunks_rebuilt_exactly_and_resource_reservation_verified',
            'case_report_sha256': base.file_hash(inventory.RUN / 'cases' / (case+'.json')),
            'chunks_rebuilt': checked, 'fine_positive_points_rebuilt': positive,
            'fine_eligible_RIGHT_count': int(eligible_count.sum()), 'fine_RIGHT_strata': eligible_count.tolist(),
            'new_RIGHT_points_beyond_existing_full_coarse': new_points, 'old_280k_labels_rebuilt_exactly': True,
            'all_chunk_array_hashes_exact': True, 'all_nested_coarse_population_hashes_exact': True,
            'three_method_output_only_reservation_bytes': reservation(new_points), 'live_remaining_research_bytes': remaining,
            'fits_even_without_new_input_assets': reservation(new_points) <= remaining,
            'new_prediction_batch_admitted': False, 'new_prediction_jobs': 0}


def save_cp(cp):
    put(RUN / 'checkpoint.json', cp)
    payload = (RUN / 'checkpoint.json').read_bytes()
    guard(len(gzip.compress(payload, mtime=0)) + 8192)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (base.file_hash(RUN / 'checkpoint.json')+'.json.gz'), payload)


def main():
    p = base.read_json(PROTOCOL)
    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
        raise RuntimeError('Authorization ended; do not start verification')
    kernel, mutex = pipeline.core.acquire_lock()
    cp, started = None, False
    try:
        worker_init()
        dependencies()
        if (RUN / 'checkpoint.json').exists():
            raise AssertionError('Prior acceptance attempt exists; preserve it')
        source = signature()
        for name in (PROTOCOL.relative_to(ROOT).as_posix(), *(f.relative_to(ROOT).as_posix() for f in sorted(Path(__file__).parent.glob('*.py')))):
            path = RUN / 'source' / name
            guard((ROOT / name).stat().st_size + 8192)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        cp = {'status': 'full_chunk_rebuild_running_not_prediction', 'source_signature': source, 'completed': {}, 'new_prediction_jobs': 0}
        put(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        started = True
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            worker = pool.submit(probe).result(timeout=180)
            if (worker['source_signature'] != source or Path(worker['python']) != Path(r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe') or
                    worker['resource_defaults'] != [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']]):
                raise AssertionError('Windows verification worker differs')
            put(RUN / 'actual_worker.json', worker)
            for case in p['cases']:
                if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
                    break
                result = pool.submit(rebuild_case, case).result()
                put(RUN / 'cases' / (case+'.json'), result)
                if result['status'] != 'all_fine_chunks_rebuilt_exactly_and_resource_reservation_verified':
                    break
                cp['completed'][case] = result
                save_cp(cp)
                print('DONE FINE REBUILD '+str(len(cp['completed']))+'/3 '+case, flush=True)
        cp['status'] = 'complete_full_chunk_rebuild_no_prediction_admitted' if len(cp['completed']) == 3 else 'deadline_verification_checkpoint_saved'
        save_cp(cp)
        summary = {'status': cp['status'], 'verified_cases': cp['completed'], 'new_prediction_jobs': 0,
                   'formal_baseline_unchanged': 2238, 'accepted_diagnostics_unchanged': 21, 'accepted_numerical_baseline_unchanged': 2259,
                   'old_full_density_failure_overridden': False, 'new_prediction_batch_admitted': False,
                   'coarse_and_fine_counts_are_geometry_verification_not_algorithm_performance': True,
                   'not_independent_labeling_method': True, 'S4_complete': False, 'S5_complete': False,
                   'budget_increase_not_approved_by_this_stage': True, 'source_signature': source,
                   'checkpoint_sha256': base.file_hash(RUN / 'checkpoint.json'), 'resource': guard()}
        put(RUN / 'reports' / 'fine_inventory_acceptance.json', summary)
        put(RUN / 'reports' / 'manifest.json', {'source_signature': source,
            'original_inventory_checkpoint_sha256': p['inventory_checkpoint_sha256'],
            'outputs_sha256': {'fine_inventory_acceptance.json': base.file_hash(RUN / 'reports' / 'fine_inventory_acceptance.json')},
            'case_reports_sha256': {c+'.json': base.file_hash(RUN / 'cases' / (c+'.json')) for c in cp['completed']},
            'checkpoint_sha256': summary['checkpoint_sha256']})
        print({k: v for k, v in summary.items() if k not in ('source_signature', 'verified_cases')}, flush=True)
    except BaseException as error:
        if cp is not None and started:
            cp.update(status='failed_verification_checkpoint_saved', error=repr(error))
            save_cp(cp)
        raise
    finally:
        if started:
            put(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
