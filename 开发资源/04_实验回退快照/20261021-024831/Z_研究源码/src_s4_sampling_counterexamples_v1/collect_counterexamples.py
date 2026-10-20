from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_full_sampling_pilot_v1'))
import analyze_full_sampling as pilot

base, np, geo, v2 = pilot.base, pilot.np, pilot.geo, pilot.v2
PROTOCOL = ROOT / 'protocol_sampling_counterexamples_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_sampling_counterexamples_v1'


def miss_difference(low, high):
    low, high = np.unique(low), np.unique(high)
    return {'low_right_window_misses': len(low), 'high_right_window_misses': len(high),
            'high_only_miss_count': len(np.setdiff1d(high, low)), 'high_only_miss_indices': np.setdiff1d(high, low).tolist(),
            'low_only_miss_count': len(np.setdiff1d(low, high)), 'low_only_miss_indices': np.setdiff1d(low, high).tolist(),
            'zero_miss_claim_lost': len(low) == 0 and len(high) > 0}


def finite_or_none(value):
    return float(value) if np.isfinite(value) else None


def main():
    kernel, mutex = v2.pipeline.core.acquire_lock()
    try:
        if (RUN / 'reports' / 'counterexample_analysis.json').exists():
            raise RuntimeError('Frozen counterexample audit exists; do not overwrite')
        policy = base.read_json(PROTOCOL)
        if base.file_hash(pilot.RUN / 'reports' / 'full_sampling_pilot.json') != policy['full_sampling_pilot_sha256']:
            raise AssertionError('Frozen full sampling pilot changed')
        v2.pipeline.common.storage_guard.__defaults__ = (policy['execution']['reserve_bytes'], policy['execution']['research_budget_bytes'])
        v2.pipeline.common.storage_guard()
        with (pilot.RUN / 'reports' / 'right_miss_pairs.csv').open(encoding='utf-8-sig', newline='') as stream:
            old_pairs = {(r['case_id'], r['core_id'], r['condition'], r['variant'], float(r['offset'])): r for r in csv.DictReader(stream)}
        design = base.read_json(pilot.PROTOCOL)
        v1 = geo.load_v1()
        source = {path.relative_to(ROOT).as_posix(): base.file_hash(path) for path in
                  [PROTOCOL, pilot.PROTOCOL, *sorted(Path(pilot.__file__).parent.glob('*.py')), *sorted(Path(__file__).parent.glob('*.py'))]}
        source.update(v1.signature())
        source.update(v2.signature())
        cases, stored, pairs, references = {}, [], [], []
        for module in (v1, v2):
            if base.read_json(module.RUN / 'runner_lock.json')['status'] != 'stopped':
                raise RuntimeError('Prediction runner must stop before reading checkpoint')
            cp = base.read_json(module.RUN / 'checkpoint.json')
            for job in module.jobs():
                _, report = module.verify(job, cp['completed'][job['id']])
                ref = job['reference']
                case = ref['case_id']
                if case not in cases:
                    path = module.RUN / 'targets.npz' if module is v1 else module.target_paths(case)[0]
                    with np.load(path) as saved:
                        targets = {key: saved[key] for key in saved.files}
                    data = module.pipeline.core.load_case(ref['partition'], case)[0]
                    masks = {(count, offset): pilot.balanced_ids(targets, count, offset)
                             for count in design['density_counts'] for offset in design['offsets']}
                    cases[case] = {'targets': targets, 'data': data, 'masks': masks, 'union': set(), 'file_sha256': report['target_file_sha256']}
                info = cases[case]
                targets, data, masks = info['targets'], info['data'], info['masks']
                old, _, _ = module.read_reference(ref)
                with np.load(module.RUN / 'jobs' / job['id'] / 'new_negative_results.npz') as saved:
                    delta = {key: saved[key] for key in saved.files}
                full = module.dep.reconstruct_delta(old, delta, targets['reference_ids'], targets['new_ids'], len(targets['xy']))
                if any(base.array_hash(full[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
                    raise AssertionError('Full point arrays changed')
                variants = [module.pipeline.Variant(**v) for v in ref['variants']]
                for variant in variants:
                    all_ids = np.arange(len(targets['xy']), dtype=np.int32)
                    missed = pilot.missed_right_ids(data, targets, full, variant.tag, all_ids)
                    info['union'].update(map(int, missed))
                    for offset in design['offsets']:
                        before, after = (pilot.missed_right_ids(data, targets, full, variant.tag, masks[(count, offset)]) for count in design['density_counts'])
                        row = {'case_id': case, 'core_id': ref['core_id'], 'condition': ref['condition']['id'], 'variant': variant.tag,
                               'offset': offset, **miss_difference(before, after)}
                        original = old_pairs[(case, ref['core_id'], ref['condition']['id'], variant.tag, offset)]
                        for key in ('low_right_window_misses', 'high_right_window_misses', 'high_only_miss_count', 'low_only_miss_count'):
                            if row[key] != int(original[key]):
                                raise AssertionError('Exact point indices disagree with frozen scalar CSV counts')
                        if row['zero_miss_claim_lost'] != (original['zero_miss_claim_lost'] == 'True'):
                            raise AssertionError('Zero miss claim discrepancy')
                        pairs.append(row)
                stored.append({'case_id': case, 'core_id': ref['core_id'], 'condition': ref['condition']['id'], 'variants': variants,
                               'point_output': full, 'report': report})
                references.append({'run': module.RUN.name, 'id': job['id'], 'report_sha256': cp['completed'][job['id']]['report_sha256']})
        points, outcomes = [], []
        for case, info in cases.items():
            targets = info['targets']
            main, previous = set(map(int, targets['main_ids'])), set(map(int, targets['density_140k_ids']))
            for index in sorted(info['union']):
                points.append({'case_id': case, 'target_index': index, 'xy_m': targets['xy'][index].tolist(),
                               'contact_time_s': float(targets['contact_time'][index]), 'edge': int(targets['edge'][index]),
                               'in_original_70000': index in main, 'in_original_140000': index in previous,
                               'in_original_280000': bool(index < 280000), 'target_file_sha256': info['file_sha256']})
        for saved in stored:
            case = saved['case_id']
            targets, full = cases[case]['targets'], saved['point_output']
            for variant in saved['variants']:
                for index in sorted(cases[case]['union']):
                    contact = float(targets['contact_time'][index])
                    first, raw, valid = (full[variant.tag+'_'+key][index] for key in ('first', 'raw', 'valid'))
                    missing = not np.isfinite(valid)
                    if missing and np.isfinite(first) and contact-2-1e-9 <= first <= contact+1e-9:
                        raise AssertionError('Scored confirmation in support window lacks valid detection')
                    diagnosis = ('no_scored_confirmation' if not np.isfinite(first) else
                                 'first_scored_confirmation_after_contact' if first > contact+1e-9 else
                                 'scored_confirmation_but_none_in_support_window') if missing else 'window_detected'
                    outcomes.append({'case_id': case, 'core_id': saved['core_id'], 'condition': saved['condition'], 'variant': variant.tag,
                                     'target_index': index, 'contact_time_s': contact, 'raw_first_s': finite_or_none(raw),
                                     'scored_first_s': finite_or_none(first), 'valid_first_s': finite_or_none(valid),
                                     'window_miss': missing, 'diagnosis_from_saved_timestamps_only': diagnosis,
                                     'TP_frames': int(full[variant.tag+'_TP'][index]), 'support_frames': int(full[variant.tag+'_support'][index])})
        zero_lost = sum(bool(row['zero_miss_claim_lost']) for row in pairs)
        if len(references) != policy['expected_prediction_references'] or len(pairs) != policy['expected_density_pairs'] or zero_lost != policy['expected_zero_miss_claim_lost_rows']:
            raise AssertionError('Counterexample audit design/count mismatch')
        RUN.mkdir(parents=True, exist_ok=True)
        for name, sha in source.items():
            destination = RUN / 'source' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and base.file_hash(destination) != sha:
                raise AssertionError('Frozen counterexample source changed')
            if not destination.exists():
                destination.write_bytes((ROOT / name).read_bytes())
        base.write_json_retry(RUN / 'reports' / 'density_miss_indices.json', {'pairs': pairs})
        base.write_json_retry(RUN / 'reports' / 'development_counterexamples.json', {'scope': policy['witness_scope'], 'points': points, 'outcomes': outcomes})
        roundtrip = base.read_json(RUN / 'reports' / 'density_miss_indices.json')['pairs']
        if roundtrip != pairs or any(len(row['high_only_miss_indices']) != row['high_only_miss_count'] for row in roundtrip):
            raise AssertionError('Lossless JSON point-index roundtrip failed')
        result = {'status': 'complete_read_only_counterexample_audit', 'new_prediction_jobs': 0, 'verified_references': len(references),
                  'density_pairs_with_exact_indices': len(pairs), 'zero_miss_claim_lost_rows': zero_lost,
                  'unique_development_counterexample_points': len(points), 'counterexample_outcomes': len(outcomes),
                  'all_json_indices_roundtrip_exact': True, 'old_scalar_counts_exactly_reproduced': True,
                  'original_failed_gates_and_rankings_unchanged': True, 'independent_validation': False,
                  'S4_complete': False, 'S5_complete': False, 'source_signature': source, 'captured_at_utc': base.utc_now()}
        base.write_json_retry(RUN / 'reports' / 'counterexample_analysis.json', result)
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'references': references, 'source_signature': source,
            'outputs_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in
                              ('density_miss_indices.json', 'development_counterexamples.json', 'counterexample_analysis.json')}})
        base.write_json_retry(RUN / 'checkpoint.json', {'status': result['status'], 'new_prediction_jobs': 0, 'source_signature': source})
        base.save_checkpoint_gzip(RUN / 'checkpoint.json.gz', (RUN / 'checkpoint.json').read_bytes())
        print(json.dumps({key: value for key, value in result.items() if key != 'source_signature'}), flush=True)
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
