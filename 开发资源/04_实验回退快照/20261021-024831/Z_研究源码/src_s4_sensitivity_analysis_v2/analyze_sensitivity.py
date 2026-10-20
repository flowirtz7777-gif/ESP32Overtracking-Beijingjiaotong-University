from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src_s4_sensitivity_v1'))
import run_sensitivity as run

OUTPUT = run.RUN / 'reports' / 'analysis_v2'


def expected_counts(protocol):
    reference = len(protocol['cases'])*len(protocol['core_configs'])*len(protocol['conditions'])
    variants = len(protocol['variants'])
    tolerance = len(protocol['contact_tolerances_m'])
    density = len(protocol['density_counts'])
    return {'new_prediction_jobs': reference*(tolerance-1), 'reference_jobs': reference,
            'summary_rows': reference*variants*tolerance*density,
            'density_pairs': reference*variants*tolerance,
            'tolerance_pairs': reference*variants*(tolerance-1)}


def main():
    # The parent checkpoint is only inspected after its runner has released the lock.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\InnerWheelResearch20261014')
    owned = False
    try:
        outcome = kernel.WaitForSingleObject(mutex, 0)
        if outcome not in (0, 0x80):
            raise RuntimeError('An experiment is active; do not read its checkpoint or duplicate analysis')
        owned = True
        cp = run.read_json(run.RUN / 'checkpoint.json')
        lock = run.read_json(run.RUN / 'runner_lock.json')
        if lock['status'] != 'stopped' or cp['status'] == 'running':
            raise RuntimeError('Wait for the sensitivity runner to finish')
        if cp['source_signature'] != run.signature():
            raise AssertionError('Prediction source/protocol changed')
        protocol = run.read_json(run.PROTOCOL)
        expected = expected_counts(protocol)
        rows = run.read_json(run.RUN / 'reference_rows.json')
        references = run.reference_records()
        planned = run.jobs()
        groups, by_group, records = {}, {}, []
        for job in planned:
            if job['id'] not in cp['completed']:
                continue
            scores, report = run.verify(job, cp['completed'][job['id']])
            rows.extend(scores)
            key = (job['case_id'], job['condition']['id'], job['contact_tolerance_m'])
            shared = (report['target_coordinates_sha256'], report['contact_label_sha256'], report['score_start_s'],
                      report['score_end_s'], json.dumps(report['raw_sensor_hashes'], sort_keys=True))
            if key in groups and groups[key] != shared:
                raise AssertionError('Cross-method targets/labels/observations/scoring are not shared')
            groups[key] = shared
            by_group[(job['case_id'], job['core_id'], job['condition']['id'], job['contact_tolerance_m'])] = job
            records.append({'id': job['id'], 'report_sha256': cp['completed'][job['id']]['report_sha256']})
        density = run.density_pairs(rows)
        paired = []
        for reference, old_report, folder in references:
            data, original, _ = run.pipeline.core.load_case(reference['partition'], reference['case_id'])
            old_points = run.read_points(folder)
            for tolerance in (.025, .1):
                key = (reference['case_id'], reference['core_id'], reference['condition']['id'], tolerance)
                if key not in by_group:
                    continue
                job = by_group[key]
                new_points = run.read_points(run.RUN / 'jobs' / job['id'])
                with run.np.load(run.label_path(job['case_id'], tolerance)) as saved:
                    current = {**original, **{key: saved[key] for key in saved.files}}
                end = float(data['time'][-1]-3)
                def right_mask(targets):
                    contact = targets['contact_time']
                    return ((~targets['front_ignored']) & (targets['edge'] == 2) & run.np.isfinite(contact)
                            & (contact >= 2-1e-9) & (contact <= end+1e-9))
                old_right, new_right = right_mask(original), right_mask(current)
                cohort = old_right & new_right
                for variant in protocol['variants']:
                    v = run.pipeline.Variant(**variant)
                    a, b = old_points[v.tag+'_valid'], new_points[v.tag+'_valid']
                    old_missed, new_missed = ~run.np.isfinite(a), ~run.np.isfinite(b)
                    new_ids = run.np.flatnonzero(cohort & ~old_missed & new_missed)
                    recovered_ids = run.np.flatnonzero(cohort & old_missed & ~new_missed)
                    paired.append({'case_id': reference['case_id'], 'core_id': reference['core_id'],
                                   'condition': reference['condition']['id'], 'contact_tolerance_m': tolerance,
                                   'margin_m': v.margin, 'confirmation_s': v.confirmation,
                                   'shared_right_cohort': int(cohort.sum()),
                                   'newly_right_eligible': int((new_right & ~old_right).sum()),
                                   'no_longer_right_eligible': int((old_right & ~new_right).sum()),
                                   'new_window_miss_instances': len(new_ids), 'recovered_window_miss_instances': len(recovered_ids),
                                   'new_window_miss_target_indices': new_ids.tolist(),
                                   'recovered_window_miss_target_indices': recovered_ids.tolist()})
        complete = (len(cp['completed']) == expected['new_prediction_jobs'] and len(references) == expected['reference_jobs']
                    and len(rows) == expected['summary_rows'] and len(density) == expected['density_pairs']
                    and len(paired) == expected['tolerance_pairs'])
        limits = protocol['density_limits']
        stable = complete and all(abs(value) <= limits['metric_absolute_and_paired_effect_change_pp']
                                 for r in density for key, value in r.items() if key.endswith('_pp'))
        stable = stable and all(r['lead_p10_delta_s'] is not None and abs(r['lead_p10_delta_s']) <= limits['lead_p10_change_s'] for r in density)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        run.csv_rows(OUTPUT / 'density_pairs.csv', density)
        run.csv_rows(OUTPUT / 'label_tolerance_per_point_pairs.csv', paired)
        run.csv_rows(OUTPUT / 'sensitivity_scores.csv', rows)
        result = {'version': 'sensitivity-analysis-v2', 'status': 'subset_complete' if complete else 'partial_no_acceptance',
                  'prediction_checkpoint_sha256': run.file_hash(run.RUN / 'checkpoint.json'), 'prediction_source_signature': run.signature(),
                  'analysis_source_sha256': run.file_hash(Path(__file__)),
                  'expected_counts': expected, 'new_prediction_jobs_completed': len(cp['completed']),
                  'reference_jobs_reused_without_prediction': len(references), 'summary_rows': len(rows),
                  'density_pair_rows': len(density), 'tolerance_per_point_pair_rows': len(paired),
                  'passes_subset_density_gate': bool(stable), 'new_window_miss_instances_not_offset_by_recoveries': True,
                  'sum_new_window_miss_instances': sum(r['new_window_miss_instances'] for r in paired),
                  'all_prediction_outputs_and_input_hashes_verified': True,
                  'label_tolerance_changes_are_not_algorithm_improvements': True, 'physical_validation': False,
                  'S4_complete': False, 'S5_complete': False, 'captured_at_utc': run.utc_now(),
                  'corrected_frozen_v1_analysis_count': '36 new plus 18 reused jobs produce 216 score rows and 108 density pairs, not 54 pairs',
                  'v1_prediction_results_reused_without_recomputation': True}
        run.write_json_retry(OUTPUT / 'sensitivity_analysis.json', result)
        run.write_json_retry(OUTPUT / 'manifest.json', {'prediction_reports': records,
                             'analysis_script_sha256': run.file_hash(Path(__file__)),
                             'output_sha256': {name: run.file_hash(OUTPUT / name) for name in
                                               ('density_pairs.csv', 'label_tolerance_per_point_pairs.csv', 'sensitivity_scores.csv', 'sensitivity_analysis.json')}})
        source = OUTPUT / 'source' / Path(__file__).name
        if source.exists() and run.file_hash(source) != run.file_hash(Path(__file__)):
            raise AssertionError('Do not overwrite a frozen analysis snapshot')
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(Path(__file__).read_bytes())
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        if owned:
            kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
