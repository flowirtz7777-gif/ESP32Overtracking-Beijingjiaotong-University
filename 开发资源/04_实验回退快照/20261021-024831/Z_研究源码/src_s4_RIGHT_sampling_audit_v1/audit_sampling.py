from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_RIGHT_census_v1'))
import run_RIGHT_census as dep

base, np, pipeline = dep.base, dep.np, dep.pipeline
PROTOCOL = ROOT / 'protocol_RIGHT_sampling_audit_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_RIGHT_sampling_audit_v1'
EXPECTED_PROTOCOL_SHA = 'e9415f9a0fa0f944de44dea31e1b5a6d3aa728ac97238172d8782bc06bbe8e13'
EXPECTED_CHECKPOINT_SHA = '97965223250c4ef44b465be2380a425cfb1a9b25a1770992bf4b7fc1e96e9e34'
COUNT_KEYS = ('TP', 'FP', 'ref_FP', 'support', 'negative_opportunities', 'ref_negative_opportunities')
METRICS = ('RIGHT_window_miss_pct', 'RIGHT_insufficient_pct',
           'RIGHT_no_alarm_before_contact_pct', 'RIGHT_valid_lead_P10_s')


def phases(xy):
    cells = np.rint(np.asarray(xy) / .0125).astype(np.int64)
    if not np.allclose(cells * .0125, xy, rtol=0, atol=1e-9):
        raise AssertionError('Targets left the frozen lattice')
    return (cells[:, 0] % 2 + 2 * (cells[:, 1] % 2)).astype(np.int8)


def cohorts(targets, previous_ids, cut):
    eligible = dep.geometry.eligible_right(targets, cut)
    original = {'original_70000_RIGHT': targets['main_ids'],
                'original_140000_RIGHT': previous_ids,
                'original_280000_RIGHT': np.arange(280000, dtype=np.int32)}
    result = {'all_eligible_RIGHT_cells_in_frozen_0.0125m_population': np.flatnonzero(eligible).astype(np.int32)}
    for name, ids in original.items():
        ids = np.asarray(ids, dtype=np.int32)
        result[name] = np.sort(ids[eligible[ids]])
    phase = phases(targets['xy'])
    for value in range(4):
        result[f'0.025m_phase{value}_RIGHT'] = np.flatnonzero(eligible & (phase == value)).astype(np.int32)
    full = result[next(iter(result))]
    pieces = [result[f'0.025m_phase{value}_RIGHT'] for value in range(4)]
    if not np.array_equal(np.sort(np.concatenate(pieces)), full):
        raise AssertionError('Four phases are not a disjoint complete RIGHT partition')
    return result


def metrics(row):
    n = row['right_contacts']
    return {'RIGHT_window_miss_pct': 100 * row['right_miss'] / n if n else None,
            'RIGHT_insufficient_pct': row['right_pct'],
            'RIGHT_no_alarm_before_contact_pct': 100 * row['right_no_before'] / n if n else None,
            'RIGHT_valid_lead_P10_s': row['right_lead_p10_s']}


def difference(subset, reference, protocol):
    values, checks = {}, []
    for name in METRICS:
        a, b = subset[name], reference[name]
        delta = a - b if a is not None and b is not None else None
        limit = protocol['lead_P10_difference_gate_s_unchanged'] if name.endswith('_s') else protocol['rate_difference_gate_pp_unchanged']
        passed = delta is not None and abs(delta) <= limit + 1e-12
        values[name + '_difference'] = delta
        values[name + '_difference_within_reference_limit'] = passed
        checks.append(passed)
    return {**values, 'RIGHT_component_numeric_limits_met': all(checks)}


def encode_omissions(full_misses, subset_ids):
    missing = ~np.isin(full_misses, subset_ids, assume_unique=True)
    packed = np.packbits(missing, bitorder='little')
    recovered = decode_omissions(full_misses, packed, len(missing))
    expected = np.setdiff1d(full_misses, subset_ids, assume_unique=True)
    if base.array_hash(recovered) != base.array_hash(expected):
        raise AssertionError('Added miss indices did not round-trip')
    return packed, recovered


def decode_omissions(full_misses, packed, length):
    if length != len(full_misses) or len(packed) != (length + 7) // 8:
        raise AssertionError('Invalid packed membership shape')
    mask = np.unpackbits(packed, bitorder='little')[:length].astype(bool)
    return np.asarray(full_misses)[mask]


def signature():
    result = dep.signature()
    result.update({path.relative_to(ROOT).as_posix(): base.file_hash(path)
                   for path in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]})
    return result


def resources(extra=0):
    p = base.read_json(PROTOCOL)
    measured = pipeline.common.storage_guard(p['disk_reserve_bytes'], p['whole_research_budget_bytes'])
    used = sum(path.stat().st_size for path in RUN.rglob('*') if path.is_file()) if RUN.exists() else 0
    if used + extra > p['analysis_run_budget_bytes'] or measured['experiment_bytes'] + extra > p['whole_research_budget_bytes']:
        raise RuntimeError('Read-only audit output reservation exceeds unchanged resource budgets')
    return {**measured, 'analysis_run_bytes': used}


def reconstruct(job, report):
    ref = job['reference']
    folder = dep.RUN / 'jobs' / job['id']
    old, _, _ = dep.census.read_reference(ref)
    raw, _ = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    with np.load(folder / 'packed_delta.npz') as saved:
        delta = dep.unpack_points({key: saved[key] for key in saved.files},
                                  base.read_json(folder / 'packed_metadata.json'), raw['time'])
    full = dep.merge_outputs(old, delta, report['full_target_count'])
    if {key: base.array_hash(value) for key, value in full.items()} != report['full_point_arrays_sha256']:
        raise AssertionError('Reconstructed full outputs changed')
    return full


def write_outputs(files):
    blobs = {name: dep.json_bytes(value) for name, value in files.items() if not name.endswith('.npz')}
    stream = io.BytesIO()
    np.savez_compressed(stream, **files['miss_indices.npz'])
    blobs['miss_indices.npz'] = stream.getvalue()
    resources(sum(map(len, blobs.values())) + 256 * 1024)
    for name, blob in blobs.items():
        path = RUN / 'reports' / name
        if path.exists():
            raise AssertionError('Do not overwrite frozen audit outputs')
        if name.endswith('.json'):
            base.write_json_retry(path, json.loads(blob))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)


def main():
    if base.file_hash(PROTOCOL) != EXPECTED_PROTOCOL_SHA:
        raise AssertionError('Pre-specified rules changed')
    p = base.read_json(PROTOCOL)
    kernel, mutex = pipeline.core.acquire_lock()
    started = False
    try:
        lock = base.read_json(dep.RUN / 'runner_lock.json')
        if lock['status'] != 'stopped':
            raise AssertionError('Prediction runner has not stopped')
        cp_path = dep.RUN / 'checkpoint.json'
        if base.file_hash(cp_path) != EXPECTED_CHECKPOINT_SHA:
            raise AssertionError('Closed dependency checkpoint changed')
        cp = base.read_json(cp_path)
        if cp['status'] != 'fixed_RIGHT_census_diagnostic_complete' or len(cp['completed']) != 9:
            raise AssertionError('All nine diagnostics must be complete')
        if (RUN / 'reports' / 'sampling_analysis.json').exists():
            raise AssertionError('Completed audit is frozen; do not rerun')
        initial = resources()
        source = signature()
        for name, sha in source.items():
            path = RUN / 'source' / name
            if path.exists() and base.file_hash(path) != sha:
                raise AssertionError('Analysis source snapshot changed')
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        started = True
        rows, pairs, verified, cohort_proofs, fairness = [], [], [], {}, {}
        index_arrays = {'empty_removed': np.empty(0, dtype=np.int32)}
        index_pairs = []
        for j, job in enumerate(dep.jobs()):
            resources()
            saved_rows, report = dep.verify(job, cp['completed'][job['id']])
            ref = job['reference']
            case, core = ref['case_id'], ref['core_id']
            targets, proof, _ = dep.load_targets(case)
            with np.load(ROOT / proof['original_target_path']) as old_targets:
                previous_ids = old_targets['previous_ids']
            ids_by_cohort = cohorts(targets, previous_ids, report['score_end_s'])
            if list(ids_by_cohort) != [p['reference_cohort'], *p['subset_cohorts']]:
                raise AssertionError('Cohort matrix changed')
            proof_rows = {name: {'count': len(ids), 'index_sha256': base.array_hash(ids),
                'coordinate_sha256': base.array_hash(targets['xy'][ids]),
                'label_sha256': {key: base.array_hash(targets[key][ids]) for key in dep.geometry.LABEL_KEYS},
                'stratum_counts': {str(g): int((targets['group'][ids] == g).sum()) for g in range(3)}}
                for name, ids in ids_by_cohort.items()}
            common = {'cohorts': proof_rows, 'input_hashes': report['input_hashes'],
                      'raw_sensor_hashes': report['raw_sensor_hashes'],
                      'estimated_state_sha256': report['estimated_state_sha256'],
                      'estimated_alpha_sha256': report['estimated_alpha_sha256'],
                      'score_start_s': report['score_start_s'], 'score_end_s': report['score_end_s']}
            if case in fairness and common != fairness[case]:
                raise AssertionError('Cohort indices, labels, observations, estimates or scoring differ across methods')
            fairness[case] = common
            cohort_proofs[case] = proof_rows
            arrays = reconstruct(job, report)
            data, _, _ = pipeline.core.load_case(ref['partition'], case)
            for variant in ref['variants']:
                v = pipeline.Variant(**variant)
                state = {key: arrays[v.tag + '_' + key] for key in ('raw', 'first', 'valid')}
                state.update(variant=v, point_counts={key: arrays[v.tag + '_' + key] for key in COUNT_KEYS})
                group_rows = {}
                for cohort, ids in ids_by_cohort.items():
                    summary = dep.projected_summary(data, targets, state, ids)
                    row = {**summary, **metrics(summary), 'case_id': case, 'core_id': core,
                           'condition': 'noise100_s1', 'variant': v.tag, 'cohort': cohort,
                           'cohort_index_sha256': proof_rows[cohort]['index_sha256'],
                           'same_population_composition_as_reference': not cohort.startswith('original_'),
                           'raw_population_composition_may_differ': cohort.startswith('original_'),
                           'not_old_complete_density_gate_verdict': True}
                    rows.append(row)
                    group_rows[cohort] = row
                full_ids = ids_by_cohort[p['reference_cohort']]
                full_misses = full_ids[~np.isfinite(state['valid'][full_ids])]
                full_key = f'job{j}_{v.tag}_full_misses'
                index_arrays[full_key] = full_misses
                for k, name in enumerate(p['subset_cohorts']):
                    ids = ids_by_cohort[name]
                    a, b = group_rows[name], group_rows[p['reference_cohort']]
                    subset_misses = ids[~np.isfinite(state['valid'][ids])]
                    removed = np.setdiff1d(subset_misses, full_misses, assume_unique=True)
                    if len(removed):
                        raise AssertionError('A common point changed outcome under read-only projection')
                    packed, added = encode_omissions(full_misses, ids)
                    mask_key = f'job{j}_{v.tag}_cohort{k}_added_mask'
                    index_arrays[mask_key] = packed
                    identity = {'case_id': case, 'core_id': core, 'condition': 'noise100_s1', 'variant': v.tag, 'cohort': name}
                    pairs.append({**identity, **difference(a, b, p), 'subset_RIGHT_contacts': a['right_contacts'],
                        'reference_RIGHT_contacts': b['right_contacts'], 'subset_window_misses': len(subset_misses),
                        'reference_window_misses': len(full_misses), 'added_window_misses': len(added),
                        'disappeared_window_misses': 0, 'zero_miss_claim_lost': len(subset_misses) == 0 and len(full_misses) > 0,
                        'raw_population_composition_may_differ': name.startswith('original_'),
                        'not_old_complete_density_gate_verdict': True,
                        'subset_stratified_insufficient_pct': a['stratified_right_pct'],
                        'reference_stratified_insufficient_pct': b['stratified_right_pct'],
                        'subset_stratum_right_rows': a['stratum_right_rows'],
                        'reference_stratum_right_rows': b['stratum_right_rows']})
                    index_pairs.append({**identity, 'full_miss_vector_key': full_key,
                        'full_miss_vector_sha256': base.array_hash(full_misses),
                        'added_membership_key': mask_key, 'membership_bit_length': len(full_misses),
                        'added_count': len(added), 'added_index_sha256': base.array_hash(added),
                        'removed_index_key': 'empty_removed', 'removed_count': 0,
                        'removed_index_sha256': base.array_hash(removed)})
            verified.append({'id': job['id'], **cp['completed'][job['id']],
                             'input_output_and_lossless_full_reconstruction_verified': True})
            print(f'VERIFIED READONLY RIGHT AUDIT {j + 1}/9 {case} {core}', flush=True)
        lookup = {(row['case_id'], row['core_id'], row['variant'], row['cohort']): row for row in rows}
        effects = []
        for case in p['cases_fixed_order']:
            for variant in p['variants']:
                for core in [name for name in p['cores'] if name != 'hold']:
                    for cohort in p['subset_cohorts']:
                        item = {'case_id': case, 'core_id': core, 'variant': variant, 'cohort': cohort,
                                'raw_population_composition_may_differ': cohort.startswith('original_'),
                                'not_old_complete_density_gate_verdict': True}
                        checks = []
                        for metric in METRICS:
                            a, b, c, d = [lookup[(case, method, variant, pop)][metric] for method, pop in
                                [(core, cohort), ('hold', cohort), (core, p['reference_cohort']), ('hold', p['reference_cohort'])]]
                            sub, full = (a - b, c - d) if all(x is not None for x in (a, b, c, d)) else (None, None)
                            error = sub - full if sub is not None else None
                            threshold = p['lead_P10_difference_gate_s_unchanged'] if metric.endswith('_s') else p['rate_difference_gate_pp_unchanged']
                            passed = error is not None and abs(error) <= threshold + 1e-12
                            item.update({metric + '_subset_method_minus_hold': sub,
                                         metric + '_reference_method_minus_hold': full,
                                         metric + '_effect_error': error,
                                         metric + '_effect_error_within_reference_limit': passed})
                            checks.append(passed)
                        item['RIGHT_component_effect_limits_met'] = all(checks)
                        effects.append(item)
        if (len(rows), len(pairs), len(effects)) != (144, 126, 84):
            raise AssertionError('Incomplete pre-specified analysis matrix')
        summary = {'status': 'complete_read_only_RIGHT_sampling_and_point_coverage_audit',
            'summary_rows': len(rows), 'subset_reference_pairs': len(pairs), 'method_minus_hold_effect_rows': len(effects),
            'new_prediction_jobs': 0, 'formal_cycle_jobs_unchanged': 162, 'formal_total_jobs_unchanged': 2238,
            'accepted_temporal_diagnostic_replays': 12, 'accepted_full_RIGHT_diagnostic_jobs': 9,
            'accepted_numerical_jobs_this_cycle': 183, 'accepted_numerical_jobs_total': 2259,
            'all_nine_inputs_outputs_source_and_full_point_arrays_independently_verified': True,
            'three_shared_input_groups_and_geometry_only_cohort_indices_verified': True,
            'zero_miss_claim_lost_rows': sum(row['zero_miss_claim_lost'] for row in pairs),
            'numeric_component_limit_failed_rows': sum(not row['RIGHT_component_numeric_limits_met'] for row in pairs),
            'effect_component_limit_failed_rows': sum(not row['RIGHT_component_effect_limits_met'] for row in effects),
            'groups': {name: {'pairs': sum(row['cohort'] == name for row in pairs),
                'numeric_limit_failed_rows': sum(row['cohort'] == name and not row['RIGHT_component_numeric_limits_met'] for row in pairs),
                'zero_miss_claim_lost_rows': sum(row['cohort'] == name and row['zero_miss_claim_lost'] for row in pairs)} for name in p['subset_cohorts']},
            'raw_original_sample_and_full_population_composition_differ': True,
            'raw_metric_differences_are_descriptive_not_algorithm_improvement_or_old_density_gate_adjudication': True,
            'stratum_rows_and_existing_equal_present_stratum_mean_kept_in_summary_and_pairs_json': True,
            'old_complete_density_failure_overridden': False, 'independent_validation': False,
            'continuous_space_or_frame_between_sample_safety_proved': False, 'S4_complete': False, 'S5_complete': False,
            'dependency_checkpoint_sha256': EXPECTED_CHECKPOINT_SHA, 'protocol_sha256': EXPECTED_PROTOCOL_SHA,
            'resource_measurement_before_analysis': initial, 'source_signature': source}
        files = {'sampling_analysis.json': summary, 'cohort_summaries.json': {'rows': rows},
                 'subset_reference_pairs.json': {'rows': pairs}, 'method_minus_hold_effects.json': {'rows': effects},
                 'cohort_proofs.json': cohort_proofs, 'shared_inputs.json': fairness,
                 'miss_index_manifest.json': {'pairs': index_pairs, 'indices_are_global_frozen_target_indices': True,
                     'packing_bitorder': 'little', 'do_not_net_added_and_removed': True},
                 'miss_indices.npz': index_arrays}
        write_outputs(files)
        with np.load(RUN / 'reports' / 'miss_indices.npz') as saved:
            for item in base.read_json(RUN / 'reports' / 'miss_index_manifest.json')['pairs']:
                full = saved[item['full_miss_vector_key']]
                recovered = decode_omissions(full, saved[item['added_membership_key']], item['membership_bit_length'])
                if (base.array_hash(full) != item['full_miss_vector_sha256'] or
                    base.array_hash(recovered) != item['added_index_sha256'] or
                    base.array_hash(saved[item['removed_index_key']]) != item['removed_index_sha256'] or len(recovered) != item['added_count']):
                    raise AssertionError('Persisted added/removed indices did not round-trip')
        for name, values in [('cohort_summaries.csv', rows), ('subset_reference_pairs.csv', pairs), ('method_minus_hold_effects.csv', effects)]:
            base.csv_rows(RUN / 'reports' / name, values)
        resources()
        manifest = {'status': 'complete', 'source_signature': source, 'dependency_checkpoint_sha256': EXPECTED_CHECKPOINT_SHA,
                    'verified_jobs': verified, 'all_126_added_removed_index_pairs_roundtrip_verified': True,
                    'outputs_sha256': {path.name: base.file_hash(path) for path in sorted((RUN / 'reports').iterdir()) if path.is_file()}}
        base.write_json_retry(RUN / 'reports' / 'manifest.json', manifest)
        base.write_json_retry(RUN / 'checkpoint.json', {'status': 'complete', 'analysis_only_new_predictions': 0,
            'source_signature': source, 'manifest_sha256': base.file_hash(RUN / 'reports' / 'manifest.json')})
        print(json.dumps({key: value for key, value in summary.items() if key not in ('source_signature', 'resource_measurement_before_analysis')}, ensure_ascii=False), flush=True)
    except BaseException as error:
        if started:
            base.write_json_retry(RUN / 'failure.json', {'error': repr(error), 'time': base.utc_now(), 'new_prediction_jobs': 0})
        raise
    finally:
        if started:
            base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
