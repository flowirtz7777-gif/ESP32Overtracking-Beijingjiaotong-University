from __future__ import annotations

import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_geometric_sampling_audit_v1'))
import audit_sampling as geo

base, np, v2 = geo.base, geo.np, geo.v2
PROTOCOL = ROOT / 'protocol_full_sampling_pilot_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_full_sampling_pilot_v1'
COUNTS = ('TP', 'FP', 'ref_FP', 'support', 'negative_opportunities', 'ref_negative_opportunities')
METRICS = ('right_pct', 'negative_fp_pct', 'common_2s_reference_fpr_pct', 'frame_fpr_pct')


def balanced_ids(targets, count, offset):
    parts = []
    for layer in range(3):
        available = np.flatnonzero(targets['group'] == layer)
        order = available[geo.geometric_order(targets['xy'][available])]
        parts.append(geo.systematic_ids(order, count//3+(layer < count % 3), offset))
    return np.concatenate(parts).astype(np.int32)


def projected_summary(data, targets, points, tag, ids):
    if len(np.unique(ids)) != len(ids) or np.any(ids < 0) or np.any(ids >= len(targets['xy'])):
        raise AssertionError('Projection indices must identify unique original points')
    sub = {key: targets[key][ids] for key in ('xy', 'group', 'contact_time', 'edge', 'front_ignored')}
    state = {'first': points[tag+'_first'][ids], 'valid': points[tag+'_valid'][ids],
             'point_counts': {key: points[tag+'_'+key][ids] for key in COUNTS}}
    return v2.pipeline.summarize(data, sub, state)


def missed_right_ids(data, targets, points, tag, ids):
    contact = targets['contact_time'][ids]
    mask = ((~targets['front_ignored'][ids]) & (targets['edge'][ids] == 2) & np.isfinite(contact)
            & (contact >= 2-1e-9) & (contact <= data['time'][-1]-3+1e-9)
            & ~np.isfinite(points[tag+'_valid'][ids]))
    return ids[mask]


def main():
    kernel, mutex = v2.pipeline.core.acquire_lock()
    try:
        if (RUN / 'reports' / 'full_sampling_pilot.json').exists():
            raise RuntimeError('Frozen sampling pilot exists; do not overwrite')
        p = base.read_json(PROTOCOL)
        dependency = ROOT / 'runs' / 'resume_S4_geometric_sampling_audit_v1' / 'reports' / 'sampling_audit.json'
        if base.file_hash(dependency) != p['prior_negative_audit_sha256']:
            raise AssertionError('Completed negative component audit changed')
        v2.pipeline.common.storage_guard.__defaults__ = (p['execution']['reserve_bytes'], p['execution']['research_budget_bytes'])
        v2.pipeline.common.storage_guard()
        source = {path.relative_to(ROOT).as_posix(): base.file_hash(path) for path in
                  [PROTOCOL, geo.PROTOCOL, *sorted(Path(geo.__file__).parent.glob('*.py')), *sorted(Path(__file__).parent.glob('*.py'))]}
        v1 = geo.load_v1()
        source.update(v1.signature())
        source.update(v2.signature())
        masks, data_cache, target_cache, source_shared = {}, {}, {}, {}
        rows, misses, references = [], {}, []
        for module in (v1, v2):
            if base.read_json(module.RUN / 'runner_lock.json')['status'] != 'stopped':
                raise RuntimeError('Wait for prediction runner to stop before reading checkpoint')
            cp = base.read_json(module.RUN / 'checkpoint.json')
            if cp['source_signature'] != module.signature() or len(cp['completed']) != len(module.jobs()):
                raise AssertionError('Incomplete or changed census checkpoint')
            for job in module.jobs():
                v2.pipeline.common.storage_guard()
                _, report = module.verify(job, cp['completed'][job['id']])
                ref = job['reference']
                case = ref['case_id']
                if case not in target_cache:
                    path = module.RUN / 'targets.npz' if module is v1 else module.target_paths(case)[0]
                    with np.load(path) as saved:
                        targets = {key: saved[key] for key in saved.files}
                    target_cache[case] = targets
                    data_cache[case] = module.pipeline.core.load_case(ref['partition'], case)[0]
                    masks[case] = {(count, offset): balanced_ids(targets, count, offset)
                                   for count in p['density_counts'] for offset in p['offsets']}
                targets, data = target_cache[case], data_cache[case]
                shared = (report['target_file_sha256'], report['input_hashes'], report['raw_sensor_hashes'], report['score_start_s'], report['score_end_s'])
                key = (case, ref['condition']['id'])
                if key in source_shared and shared != source_shared[key]:
                    raise AssertionError('Methods do not share raw inputs/targets/scoring times')
                source_shared[key] = shared
                old, _, _ = module.read_reference(ref)
                with np.load(module.RUN / 'jobs' / job['id'] / 'new_negative_results.npz') as saved:
                    delta = {key: saved[key] for key in saved.files}
                full = module.dep.reconstruct_delta(old, delta, targets['reference_ids'], targets['new_ids'], len(targets['xy']))
                if any(base.array_hash(full[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
                    raise AssertionError('Frozen full point arrays changed')
                original_scores = base.read_json(module.dep.RUN / 'jobs' / ref['id'] / 'summary.json')
                for vdict in ref['variants']:
                    variant = module.pipeline.Variant(**vdict)
                    reconstructed = projected_summary(data, targets, full, variant.tag, targets['reference_ids'])
                    original = next(row for row in original_scores if row['target_count'] == 280000
                                    and row['margin_m'] == variant.margin and row['confirmation_s'] == variant.confirmation)
                    if any(original[key] != value for key, value in reconstructed.items()):
                        raise AssertionError('Original balanced 280k summary failed exact reconstruction')
                    for (count, offset), ids in masks[case].items():
                        summary = projected_summary(data, targets, full, variant.tag, ids)
                        row = {'case_id': case, 'core_id': ref['core_id'], 'condition': ref['condition']['id'],
                               'variant': variant.tag, 'density_count': count, 'offset': offset, 'mask_sha256': base.array_hash(ids), **summary}
                        rows.append(row)
                        k = (case, ref['core_id'], ref['condition']['id'], variant.tag, offset, count)
                        misses[k] = missed_right_ids(data, targets, full, variant.tag, ids)
                references.append({'source_run': module.RUN.name, 'job_id': job['id'], 'report_sha256': cp['completed'][job['id']]['report_sha256']})
        blocks = {}
        for row in rows:
            key = tuple(row[k] for k in ('case_id', 'core_id', 'condition', 'variant', 'offset'))
            blocks.setdefault(key, {})[row['density_count']] = row
        pairs, point_pairs = [], []
        for key, block in blocks.items():
            hold = blocks[(key[0], 'hold', *key[2:])]
            low, high = (block[count] for count in p['density_counts'])
            row = dict(zip(('case_id', 'core_id', 'condition', 'variant', 'offset'), key))
            for metric in METRICS:
                row[metric+'_delta_pp'] = high[metric]-low[metric]
                row[metric+'_paired_effect_change_pp'] = (high[metric]-hold[280000][metric])-(low[metric]-hold[140000][metric])
            row['lead_p10_delta_s'] = high['right_lead_p10_s']-low['right_lead_p10_s']
            before, after = (misses[(*key, count)] for count in p['density_counts'])
            new = np.setdiff1d(after, before)
            disappeared = np.setdiff1d(before, after)
            point_pairs.append({**dict(zip(('case_id', 'core_id', 'condition', 'variant', 'offset'), key)),
                                'low_right_window_misses': len(before), 'high_right_window_misses': len(after),
                                'high_only_miss_count': len(new), 'high_only_miss_indices': new.tolist(),
                                'low_only_miss_count': len(disappeared), 'low_only_miss_indices': disappeared.tolist(),
                                'zero_miss_claim_lost': len(before) == 0 and len(after) > 0})
            pairs.append(row)
        if (len(rows), len(pairs), len(point_pairs), len(references)) != (216, 108, 108, 18):
            raise AssertionError('Full-metric sampling pilot design incomplete')
        limits = p['limits']
        numeric = all(abs(value) <= (limits['method_minus_hold_effect_change_pp'] if key.endswith('paired_effect_change_pp')
                                     else limits['absolute_metric_change_pp'])
                      for row in pairs for key, value in row.items() if key.endswith('_pp'))
        numeric = numeric and all(abs(row['lead_p10_delta_s']) <= limits['lead_p10_change_s'] for row in pairs)
        zero_lost = sum(bool(row['zero_miss_claim_lost']) for row in point_pairs)
        RUN.mkdir(parents=True, exist_ok=True)
        for name, sha in source.items():
            saved = RUN / 'source' / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and base.file_hash(saved) != sha:
                raise AssertionError('Frozen sampling pilot source changed')
            if not saved.exists():
                saved.write_bytes((ROOT / name).read_bytes())
        for name, values in (('full_sampling_scores.csv', rows), ('full_sampling_pairs.csv', pairs), ('right_miss_pairs.csv', point_pairs)):
            base.csv_rows(RUN / 'reports' / name, values)
        result = {'status': 'complete_sampling_rule_development_pilot', 'new_prediction_jobs': 0, 'verified_prediction_references': 18,
                  'score_rows': 216, 'density_pairs': 108, 'point_miss_pairs': 108, 'passes_numeric_component_gate': bool(numeric),
                  'zero_miss_claim_lost_rows': zero_lost, 'passes_full_metric_pilot_gate': bool(numeric and zero_lost == 0),
                  'original_280k_summaries_exactly_reconstructed': True, 'original_70000_main_set_and_rankings_unchanged': True,
                  'original_density_failure_overridden': False, 'independent_validation': False,
                  'full_foundation_accepted': False, 'S4_complete': False, 'S5_complete': False, 'physical_validation': False,
                  'source_signature': source, 'captured_at_utc': base.utc_now()}
        base.write_json_retry(RUN / 'reports' / 'full_sampling_pilot.json', result)
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': source, 'references': references,
            'output_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in
                              ('full_sampling_scores.csv', 'full_sampling_pairs.csv', 'right_miss_pairs.csv', 'full_sampling_pilot.json')}})
        base.write_json_retry(RUN / 'checkpoint.json', {'status': result['status'], 'new_prediction_jobs': 0, 'references_verified': 18, 'source_signature': source})
        base.save_checkpoint_gzip(RUN / 'checkpoint.json.gz', (RUN / 'checkpoint.json').read_bytes())
        print(json.dumps({key: value for key, value in result.items() if key != 'source_signature'}), flush=True)
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
