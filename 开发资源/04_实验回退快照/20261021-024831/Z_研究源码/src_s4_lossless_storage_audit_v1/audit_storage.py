from __future__ import annotations

import io
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_positive_population_feasibility_v1'))
import run_feasibility as geometry
from packing import pack_points, unpack_points, array_hash

base, np, census, pipeline = geometry.base, geometry.np, geometry.census, geometry.pipeline
RUN = ROOT / 'runs' / 'resume_S4_lossless_storage_audit_v1'
PROTOCOL = ROOT / 'protocol_lossless_storage_audit_v1.json'


def signature():
    result = geometry.signature()
    for p in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]:
        result[p.relative_to(ROOT).as_posix()] = base.file_hash(p)
    return result


def encode(values):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **values)
    return buffer.getvalue()


def main():
    p = base.read_json(PROTOCOL)
    kernel, mutex = pipeline.core.acquire_lock()
    try:
        geometry.worker_init()
        resource = pipeline.common.storage_guard()
        lock = base.read_json(geometry.RUN / 'runner_lock.json')
        if lock['status'] != 'stopped':
            raise AssertionError('Geometry feasibility is still active')
        population_path = geometry.RUN / 'reports' / 'population_feasibility.json'
        population = base.read_json(population_path)
        if population['status'] != 'geometry_label_resource_feasibility_complete' or len(population['cases']) != 3:
            raise AssertionError('Complete geometry/label feasibility is required')
        if (RUN / 'reports' / 'storage_audit.json').exists():
            raise AssertionError('Preserve the existing frozen storage audit')
        for case in population['cases']:
            geometry.verify_case(case)
        references = [ref for ref in census.dep.jobs() if ref['contact_tolerance_m'] == p['contact_tolerance_m']]
        if len(references) != p['reference_groups']:
            raise AssertionError('Expected 18 fixed reference groups')
        rows, dependencies, axis_counts = [], {}, {}
        for ref in references:
            arrays, _, report_hash = census.read_reference(ref)
            data, _, _ = pipeline.core.load_case(ref['partition'], ref['case_id'])
            time = data['time']
            axis_counts[ref['case_id']] = len(time)
            target_path = census.dep.target_path(ref['case_id'], ref['contact_tolerance_m'])
            with np.load(target_path) as saved:
                right_ids = np.flatnonzero(geometry.eligible_right(saved, float(time[-1]-3)))
            dependencies[ref['id']] = {'report_sha256': report_hash, 'time_sha256': array_hash(time),
                                       'point_array_sha256': {key: array_hash(value) for key, value in arrays.items()}}
            for cohort, ids in [('all_old_280000', np.arange(280000)), ('old_eligible_RIGHT', right_ids)]:
                selected = {key: value[ids] for key, value in arrays.items()}
                packed, meta = pack_points(selected, time)
                encoded = encode(packed)
                with np.load(io.BytesIO(encoded)) as archive:
                    decoded = unpack_points({key: archive[key] for key in archive.files}, meta, time)
                if any(array_hash(value) != array_hash(decoded[key]) for key, value in selected.items()):
                    raise AssertionError('Stored compressed roundtrip differs from the reference')
                descriptor_bytes = len(json.dumps(meta, sort_keys=True).encode('utf-8'))
                original_encoded_bytes = len(encode(selected))
                rows.append({'case_id': ref['case_id'], 'core_id': ref['core_id'], 'condition': ref['condition']['id'],
                             'cohort': cohort, 'target_count': len(ids), 'array_count': len(selected),
                             'uncompressed_original_bytes': sum(v.nbytes for v in selected.values()),
                             'uncompressed_packed_bytes': sum(v.nbytes for v in packed.values()),
                             'original_arrays_compressed_in_memory_bytes': original_encoded_bytes,
                             'packed_arrays_and_descriptor_bytes': len(encoded)+descriptor_bytes,
                             'packed_bytes_per_point': (len(encoded)+descriptor_bytes)/len(ids),
                             'all_arrays_byte_exact_after_compressed_roundtrip': True,
                             'old_files_rewritten_or_deleted': False})
            print('DONE LOSSLESS STORAGE AUDIT '+str(len(dependencies))+'/18 '+ref['id'], flush=True)
        if len(rows) != 36 or any(n >= 65535 for n in axis_counts.values()):
            raise AssertionError('Unexpected audit inventory or timestamp/count uint16 bound')
        conservative = []
        for case in population['cases']:
            # Two variants, each with three time indices and six counters.
            raw = case['new_eligible_RIGHT_cells']*36
            quota = raw+(raw+99)//100+1048576
            conservative.append({'case_id': case['case_id'], 'new_RIGHT_targets': case['new_eligible_RIGHT_cells'],
                                 'point_output_uint16_fixed_width_bytes': raw,
                                 'single_job_admission_quota_bytes': quota,
                                 'quota_includes_one_percent_zip_growth_and_1MiB_metadata': True,
                                 'must_measure_encoded_output_before_any_future_write': True})
        resource = pipeline.common.storage_guard()
        result = {'status': 'lossless_storage_reference_audit_complete', 'reference_groups': len(dependencies), 'rows': len(rows),
                  'new_prediction_jobs': 0, 'old_files_rewritten_or_deleted': False, 'reference_array_roundtrip_exact': True,
                  'observation_counts': axis_counts, 'future_single_job_conservative_admission': conservative,
                  'sum_all_18_fixed_width_admission_quotas_bytes': sum(row['single_job_admission_quota_bytes']*6 for row in conservative),
                  'research_remaining_bytes_at_audit': p['research_budget_bytes']-resource['experiment_bytes'],
                  'reference_compression_ratios_do_not_guarantee_future_output_sizes': True,
                  'new_prediction_batch_implemented_or_started': False, 'old_full_density_gate_overridden': False,
                  'formal_jobs_this_cycle_unchanged': 162, 'formal_jobs_total_unchanged': 2238, 'accepted_diagnostic_replays_unchanged': 12,
                  'population_feasibility_sha256': base.file_hash(population_path), 'source_signature': signature()}
        report_dir = RUN / 'reports'
        base.write_json_retry(report_dir / 'storage_audit.json', result)
        base.write_json_retry(report_dir / 'reference_sizes.json', {'rows': rows})
        base.csv_rows(report_dir / 'reference_sizes.csv', rows)
        for name, sha in signature().items():
            target = RUN / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and base.file_hash(target) != sha:
                raise AssertionError('Frozen source snapshot changed')
            if not target.exists():
                target.write_bytes((ROOT / name).read_bytes())
        used = sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file())
        if used > p['run_budget_bytes']:
            raise AssertionError('Storage-audit budget exceeded; preserve outputs')
        base.write_json_retry(report_dir / 'manifest.json', {'source_signature': signature(), 'references': dependencies,
            'population_feasibility_sha256': result['population_feasibility_sha256'],
            'outputs_sha256': {name: base.file_hash(report_dir / name) for name in ('storage_audit.json', 'reference_sizes.json', 'reference_sizes.csv')}})
        pipeline.common.storage_guard()
        print(json.dumps({key: value for key, value in result.items() if key != 'source_signature'}), flush=True)
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
