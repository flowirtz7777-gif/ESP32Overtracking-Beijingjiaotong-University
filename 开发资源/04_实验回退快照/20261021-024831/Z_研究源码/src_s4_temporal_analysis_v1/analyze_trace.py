from __future__ import annotations

import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_temporal_trace_v2'))
import run_trace as trace

base, np = trace.base, trace.np
PROTOCOL = ROOT / 'protocol_temporal_analysis_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_temporal_analysis_v1'


def intervals(time, mask):
    ids = np.flatnonzero(mask)
    if not len(ids):
        return []
    starts = np.r_[0, np.flatnonzero(np.diff(ids) != 1)+1]
    ends = np.r_[starts[1:]-1, len(ids)-1]
    return [{'first_frame_s': float(time[ids[a]]), 'last_frame_s': float(time[ids[b]]),
             'frames': int(b-a+1), 'elapsed_s': float(time[ids[b]]-time[ids[a]])}
            for a, b in zip(starts, ends)]


def classify(raw, confirmed, support):
    if np.any(confirmed & support):
        return 'window_detected'
    if np.any(raw & support):
        return 'geometry_hit_but_continuous_confirmation_not_met_in_window'
    return 'no_geometry_hit_within_effective_window'


def source_signature():
    return {p.relative_to(ROOT).as_posix(): base.file_hash(p)
            for p in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]}


def main():
    p = base.read_json(PROTOCOL)
    kernel, mutex = trace.pipeline.core.acquire_lock()
    try:
        trace.worker_init()
        trace.guard()
        lock = base.read_json(trace.RUN / 'runner_lock.json')
        if lock['status'] != 'stopped':
            raise AssertionError('Wait for the trace runner to stop before analysis')
        cp_path = trace.RUN / 'checkpoint.json'
        cp = base.read_json(cp_path)
        if cp['status'] != 'diagnostic_trace_complete' or len(cp['completed']) != p['required_complete_diagnostic_jobs']:
            raise AssertionError('Only a complete closed diagnostic batch can be analyzed')
        if cp['source_signature'] != trace.signature():
            raise AssertionError('Frozen diagnostic source changed')
        if (RUN / 'reports' / 'temporal_mechanisms.json').exists():
            raise AssertionError('Analysis already exists; preserve the frozen report')
        all_rows, focus, shared, dependencies = [], [], {}, {}
        for job in trace.jobs():
            rows, report = trace.verify(job, cp['completed'][job['id']])
            ref = job['census_job']['reference']
            common_key = (ref['case_id'], ref['condition']['id'])
            common_value = (report['input_hashes'], report['raw_sensor_hashes'], report['target_file_sha256'], report['score_start_s'], report['score_end_s'])
            if common_key in shared and shared[common_key] != common_value:
                raise AssertionError('Methods did not share identical targets/raw inputs/scoring')
            shared[common_key] = common_value
            dependencies[job['id']] = cp['completed'][job['id']]
            all_rows.extend(rows)
            if ref['case_id'] != p['focus_case']:
                continue
            folder = trace.RUN / 'jobs' / job['id']
            with np.load(folder / 'temporal_trace.npz') as saved, np.load(folder / 'point_results.npz') as point_saved:
                time = saved['time']
                target_path, _ = trace.target_paths(ref['case_id'])
                with np.load(target_path) as target_saved:
                    positions = target_saved['witness_positions'].copy()
                for index in p['focus_reference_ids']:
                    column = int(np.flatnonzero(saved['witness_reference_ids'] == index)[0])
                    contact = float(saved['contact_time'][column])
                    score = saved['score_frame']
                    domain = (time >= max(0, contact-4)-trace.EPS) & (time <= contact+trace.EPS)
                    for vdict in ref['variants']:
                        v = trace.pipeline.Variant(**vdict)
                        raw = saved[v.tag+'_raw_hit'][:, column]
                        confirmed = saved[v.tag+'_confirmed'][:, column]
                        support = saved[v.tag+'_support'][:, column] & score
                        ages = saved[v.tag+'_continuous_age_s'][:, column]
                        last_before = np.flatnonzero(confirmed & score & (time < contact-2-trace.EPS))
                        first_inside = np.flatnonzero(raw & support)
                        position = positions[column]
                        valid = point_saved[v.tag+'_valid'][position]
                        first = point_saved[v.tag+'_first'][position]
                        first_raw = point_saved[v.tag+'_raw'][position]
                        classification = classify(raw, confirmed, support)
                        if (classification == 'window_detected') != bool(np.isfinite(valid)):
                            raise AssertionError('Focus mechanism differs from frozen valid timestamp')
                        focus.append({'case_id': ref['case_id'], 'core_id': ref['core_id'], 'condition': ref['condition']['id'],
                            'variant': v.tag, 'target_reference_index': index, 'xy_m': saved['witness_xy'][column].tolist(),
                            'contact_time_s': contact, 'effective_window_start_s': contact-2,
                            'first_raw_s': float(first_raw) if np.isfinite(first_raw) else None,
                            'first_scored_confirmation_s': float(first) if np.isfinite(first) else None,
                            'valid_window_confirmation_s': float(valid) if np.isfinite(valid) else None,
                            'last_scored_confirmation_before_window_s': float(time[last_before[-1]]) if len(last_before) else None,
                            'first_raw_hit_inside_window_s': float(time[first_inside[0]]) if len(first_inside) else None,
                            'window_raw_frames': int(np.count_nonzero(raw & support)),
                            'window_confirmed_frames': int(np.count_nonzero(confirmed & support)),
                            'max_continuous_age_in_window_s': float(np.nanmax(ages[raw & support])) if np.any(raw & support) else None,
                            'minimum_window_distance_m': float(saved['distance_m'][support, column].min()),
                            'hit_distance_threshold_m': .05+v.margin+trace.GEOMETRY_EPS,
                            'classification': classification, 'reported_interval_domain_s': [max(0, contact-4), contact],
                            'raw_intervals': intervals(time, raw & domain),
                            'confirmed_intervals': intervals(time, confirmed & domain),
                            'window_raw_intervals': intervals(time, raw & support),
                            'window_confirmed_intervals': intervals(time, confirmed & support)})
        if len(all_rows) != p['expected_witness_outcomes'] or len(focus) != 24:
            raise AssertionError('Missing fixed witness/focus comparisons')
        counts = {}
        for row in all_rows:
            key = row['trace_based_diagnosis']
            counts[key] = counts.get(key, 0)+1
        proof = {'status': 'closed_trace_and_mechanism_analysis_complete', 'trace_checkpoint_sha256': base.file_hash(cp_path),
                 'diagnostic_predictions_accepted': len(cp['completed']), 'new_prediction_jobs_in_this_analysis': 0,
                 'formal_new_prediction_jobs_this_cycle_unchanged': 162, 'formal_corrected_scoring_jobs_total_unchanged': 2238,
                 'witness_outcomes': len(all_rows), 'unique_development_points': 69, 'focus_comparisons': len(focus),
                 'diagnosis_counts_repeated_development_outcomes_not_independent_incidents': counts,
                 'all_source_input_output_point_and_trace_hashes_verified': True, 'common_input_groups_verified': len(shared),
                 'intervals_are_consecutive_sample_frames_not_continuous_geometry_guarantees': True,
                 'independent_validation': False, 'failed_foundation_gate_overridden': False, 'S4_complete': False, 'S5_complete': False,
                 'source_signature': source_signature(), 'trace_source_signature': trace.signature()}
        report_dir = RUN / 'reports'
        for name, value in [('temporal_mechanisms.json', proof), ('focus_point_intervals.json', {'rows': focus}),
                            ('witness_diagnoses.json', {'rows': all_rows})]:
            base.write_json_retry(report_dir / name, value)
        base.csv_rows(report_dir / 'focus_point_summary.csv', focus)
        for name, sha in source_signature().items():
            target = RUN / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and base.file_hash(target) != sha:
                raise AssertionError('Analysis source snapshot already differs')
            if not target.exists():
                target.write_bytes((ROOT / name).read_bytes())
        files = ['temporal_mechanisms.json', 'focus_point_intervals.json', 'witness_diagnoses.json', 'focus_point_summary.csv']
        if sum(f.stat().st_size for f in RUN.rglob('*') if f.is_file()) > p['new_analysis_budget_bytes']:
            raise AssertionError('Analysis budget exceeded; preserve artifacts')
        base.write_json_retry(report_dir / 'manifest.json', {'source_signature': source_signature(), 'trace_source_signature': trace.signature(),
            'trace_checkpoint_sha256': proof['trace_checkpoint_sha256'], 'trace_jobs': dependencies,
            'outputs_sha256': {name: base.file_hash(report_dir / name) for name in files}})
        trace.guard()
        print(json.dumps({key: value for key, value in proof.items() if 'signature' not in key}), flush=True)
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
