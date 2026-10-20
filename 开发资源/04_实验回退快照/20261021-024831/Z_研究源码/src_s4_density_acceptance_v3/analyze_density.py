from __future__ import annotations

from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_density_repair_v2'))
import run_density_repair_v2 as run

OUTPUT = run.RUN / 'reports' / 'acceptance_v3'


def new_point_misses(targets, valid, score_end):
    contact = targets['contact_time']
    right = ((~targets['front_ignored']) & (targets['edge'] == 2) & run.np.isfinite(contact)
             & (contact >= 2-1e-9) & (contact <= score_end+1e-9))
    ids = targets['new_ids']
    return ids[right[ids] & ~run.np.isfinite(valid[ids])]


def main():
    kernel, mutex = run.pipeline.core.acquire_lock()
    try:
        lock = run.base.read_json(run.RUN / 'runner_lock.json')
        if lock['status'] != 'stopped':
            raise RuntimeError('Wait for the prediction runner to stop before reading its checkpoint')
        cp = run.base.read_json(run.RUN / 'checkpoint.json')
        if cp['source_signature'] != run.signature():
            raise AssertionError('Frozen prediction source/protocol changed')
        p = run.base.read_json(run.PROTOCOL)
        planned = run.jobs()
        rows, paired, reports = [], [], []
        groups = {}
        for job in planned:
            if job['id'] not in cp['completed']:
                continue
            scores, report = run.verify(job, cp['completed'][job['id']])
            rows.extend(scores)
            path = run.target_path(job['case_id'], job['contact_tolerance_m'])
            with run.np.load(path) as saved:
                targets = {key: saved[key] for key in saved.files}
            _, old = run.baseline_for(job)
            with run.np.load(run.RUN / 'jobs' / job['id'] / 'new_target_results.npz') as saved:
                delta = {key: saved[key] for key in saved.files}
            full = run.reconstruct_delta(old, delta, targets['previous_ids'], targets['new_ids'], len(targets['xy']))
            for variant in p['variants']:
                v = run.pipeline.Variant(**variant)
                low = next(r for r in scores if r['target_count'] == 140000 and r['margin_m'] == v.margin and r['confirmation_s'] == v.confirmation)
                high = next(r for r in scores if r['target_count'] == 280000 and r['margin_m'] == v.margin and r['confirmation_s'] == v.confirmation)
                new = new_point_misses(targets, full[v.tag+'_valid'], report['score_end_s'])
                if high['right_miss'] != low['right_miss']+len(new):
                    raise AssertionError('Nested missing-point decomposition differs from summaries')
                paired.append({'job_id': job['id'], 'case_id': job['case_id'], 'core_id': job['core_id'],
                               'condition': job['condition']['id'], 'contact_tolerance_m': job['contact_tolerance_m'],
                               'margin_m': v.margin, 'confirmation_s': v.confirmation,
                               'previous_right_window_miss': low['right_miss'], 'full_right_window_miss': high['right_miss'],
                               'new_right_window_miss_instances': len(new), 'new_right_window_miss_target_indices': new.tolist(),
                               'zero_miss_claim_lost': low['right_miss'] == 0 and len(new) > 0})
            key = (job['case_id'], job['condition']['id'], job['contact_tolerance_m'])
            shared = (report['target_array_sha256'], report['raw_sensor_hashes'], report['score_start_s'], report['score_end_s'])
            if key in groups and groups[key] != shared:
                raise AssertionError('Cross-method shared inputs differ')
            groups[key] = shared
            reports.append({'id': job['id'], 'report_sha256': cp['completed'][job['id']]['report_sha256']})
        density = run.density_pairs(rows)
        complete = len(cp['completed']) == 54 and len(rows) == 216 and len(density) == 108 and len(paired) == 108
        limits = p['density_limits']
        numeric = complete and all(abs(value) <= limits['metric_absolute_and_paired_effect_change_pp']
                                   for r in density for key, value in r.items() if key.endswith('_pp'))
        numeric = numeric and all(r['lead_p10_delta_s'] is not None and abs(r['lead_p10_delta_s']) <= limits['lead_p10_change_s'] for r in density)
        zero_lost = sum(bool(r['zero_miss_claim_lost']) for r in paired)
        result = {'status': 'subset_complete' if complete else 'partial_no_acceptance',
                  'new_prediction_jobs_completed': len(cp['completed']), 'density_pair_rows': len(density),
                  'new_point_miss_pair_rows': len(paired), 'passes_numeric_density_gate': bool(numeric),
                  'zero_miss_claim_lost_rows': zero_lost, 'passes_subset_density_gate': bool(numeric and zero_lost == 0),
                  'prediction_checkpoint_sha256': run.base.file_hash(run.RUN / 'checkpoint.json'),
                  'all_outputs_inputs_and_lossless_reconstruction_verified': True,
                  'original_70000_and_previous_140000_points_preserved': True, 'S4_complete': False, 'S5_complete': False,
                  'physical_validation': False, 'analysis_source_sha256': run.base.file_hash(Path(__file__)),
                  'captured_at_utc': run.base.utc_now()}
        run.base.csv_rows(OUTPUT / 'density_pairs.csv', density)
        run.base.csv_rows(OUTPUT / 'new_point_window_misses.csv', paired)
        run.base.write_json_retry(OUTPUT / 'density_acceptance.json', result)
        run.base.write_json_retry(OUTPUT / 'manifest.json', {'prediction_reports': reports,
                               'analysis_source_sha256': result['analysis_source_sha256'],
                               'outputs_sha256': {name: run.base.file_hash(OUTPUT / name) for name in
                                                 ('density_pairs.csv', 'new_point_window_misses.csv', 'density_acceptance.json')}})
        snapshot = OUTPUT / 'source' / Path(__file__).name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if snapshot.exists() and run.base.file_hash(snapshot) != result['analysis_source_sha256']:
            raise AssertionError('Cannot overwrite frozen analysis source')
        if not snapshot.exists():
            snapshot.write_bytes(Path(__file__).read_bytes())
        import json
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
