from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_RIGHT_sampling_audit_v1'))
import audit_sampling as audit

base, np = audit.base, audit.np
PROTOCOL = ROOT / 'protocol_RIGHT_composition_explanation_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_RIGHT_composition_explanation_v1'


def layers(row):
    result = {value['group']: value for value in row['stratum_right_rows']}
    if (set(result) != {0, 1} or any(value['right_contacts'] <= 0 for value in result.values()) or
        sum(value['right_contacts'] for value in result.values()) != row['right_contacts']):
        raise AssertionError('Expected both fixed RIGHT strata with complete counts; no renormalization')
    return result


def same_composition(a, b):
    left, right = layers(a), layers(b)
    return all(left[g]['right_contacts'] * b['right_contacts'] == right[g]['right_contacts'] * a['right_contacts'] for g in (0, 1))


def decompose(a, b):
    left, right = layers(a), layers(b)
    conditional, mixture = 0., 0.
    details = []
    for group in (0, 1):
        s, r = left[group], right[group]
        sw, rw = s['right_contacts'] / a['right_contacts'], r['right_contacts'] / b['right_contacts']
        sr, rr = s['right_insufficient_pct'], r['right_insufficient_pct']
        conditional += sw * (sr - rr)
        mixture += (sw - rw) * rr
        details.append({'group': group, 'subset_contacts': s['right_contacts'], 'reference_contacts': r['right_contacts'],
            'subset_layer_rate_pct': sr, 'reference_layer_rate_pct': rr, 'layer_rate_difference_pp': sr - rr,
            'subset_population_weight': sw, 'reference_population_weight': rw})
    raw = a['right_pct'] - b['right_pct']
    standardized = sum((left[g]['right_insufficient_pct'] - right[g]['right_insufficient_pct']) * .5 for g in (0, 1))
    if not np.isclose(raw, conditional + mixture, rtol=0, atol=1e-10):
        raise AssertionError('Exact rate decomposition failed')
    return {'raw_insufficient_difference_pp': raw,
            'within_layer_component_using_subset_weights_pp': conditional,
            'composition_component_using_reference_layer_rates_pp': mixture,
            'fixed_equal_layer_standardized_difference_pp': standardized,
            'same_exact_layer_composition': same_composition(a, b), 'layer_rows': details,
            'posthoc_explanation_not_old_complete_density_gate_adjudication': True}


def main():
    p = base.read_json(PROTOCOL)
    kernel, mutex = audit.pipeline.core.acquire_lock()
    started = False
    try:
        dep = ROOT / p['dependency_run']
        if base.read_json(dep / 'runner_lock.json')['status'] != 'stopped':
            raise AssertionError('Dependency analysis is still running')
        manifest_path = dep / 'reports' / 'manifest.json'
        if base.file_hash(manifest_path) != p['dependency_manifest_sha256']:
            raise AssertionError('Frozen audit manifest changed')
        manifest = base.read_json(manifest_path)
        for path, sha in manifest['source_signature'].items():
            if base.file_hash(ROOT / path) != sha:
                raise AssertionError('Frozen dependency source changed')
        for name, sha in manifest['outputs_sha256'].items():
            if base.file_hash(dep / 'reports' / name) != sha:
                raise AssertionError('Frozen audit output changed: ' + name)
        if base.file_hash(dep / 'reports' / 'sampling_analysis.json') != p['dependency_report_sha256']:
            raise AssertionError('Frozen sampling report changed')
        if (RUN / 'reports' / 'explanation.json').exists():
            raise AssertionError('Do not overwrite completed analysis')
        measured = audit.pipeline.common.storage_guard(p['disk_reserve_bytes'], p['whole_research_budget_bytes'])
        if p['whole_research_budget_bytes'] - measured['experiment_bytes'] < p['analysis_run_budget_bytes']:
            raise RuntimeError('Cannot reserve bounded explanation output')
        sources = {path.relative_to(ROOT).as_posix(): base.file_hash(path) for path in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]}
        for name in sources:
            path = RUN / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise AssertionError('Prior source snapshot exists; preserve it')
            path.write_bytes((ROOT / name).read_bytes())
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        started = True
        summaries = base.read_json(dep / 'reports' / 'cohort_summaries.json')['rows']
        pairs = base.read_json(dep / 'reports' / 'subset_reference_pairs.json')['rows']
        effects = base.read_json(dep / 'reports' / 'method_minus_hold_effects.json')['rows']
        reference_name = audit.base.read_json(audit.PROTOCOL)['reference_cohort']
        lookup = {(row['case_id'], row['core_id'], row['variant'], row['cohort']): row for row in summaries}
        corrected, decompositions = [], []
        for row in summaries:
            ref = lookup[(row['case_id'], row['core_id'], row['variant'], reference_name)]
            exact = same_composition(row, ref)
            corrected.append({**row, 'same_population_composition_as_reference': exact,
                'raw_population_composition_may_differ': not exact,
                'composition_metadata_corrected_without_changing_numeric_or_index_outputs': True})
        for row in pairs:
            identity = row['case_id'], row['core_id'], row['variant']
            subset, ref = lookup[(*identity, row['cohort'])], lookup[(*identity, reference_name)]
            decompositions.append({**{key: row[key] for key in ('case_id', 'core_id', 'variant', 'cohort')}, **decompose(subset, ref)})
            row['raw_population_composition_may_differ'] = not same_composition(subset, ref)
        for row in effects:
            identity = row['case_id'], row['core_id'], row['variant']
            subset, ref = lookup[(*identity, row['cohort'])], lookup[(*identity, reference_name)]
            row['raw_population_composition_may_differ'] = not same_composition(subset, ref)
        if (len(corrected), len(decompositions), len(effects)) != (144, 126, 84):
            raise AssertionError('Incomplete explanatory matrix')
        summary = {'status': 'complete_posthoc_composition_explanation_with_metadata_erratum',
            'registration_identity': p['registration_identity'], 'new_prediction_jobs': 0,
            'corrected_summary_rows': len(corrected), 'decomposition_rows': len(decompositions),
            'composition_metadata_changed_rows': sum(a['same_population_composition_as_reference'] != b['same_population_composition_as_reference'] for a, b in zip(summaries, corrected)),
            'counts_rates_quantiles_prediction_arrays_and_miss_indices_changed': False,
            'all_decomposition_identities_verified': True, 'fixed_weights': {'0': .5, '1': .5},
            'new_acceptance_or_algorithm_selection_gate': False, 'weighted_quantiles_implemented': False,
            'old_full_density_failure_overridden': False, 'S4_complete': False, 'S5_complete': False,
            'dependency_manifest_sha256': p['dependency_manifest_sha256'], 'source_signature': sources}
        files = {'explanation.json': summary, 'corrected_cohort_summaries.json': {'rows': corrected},
                 'corrected_subset_reference_pairs.json': {'rows': pairs}, 'corrected_method_minus_hold_effects.json': {'rows': effects},
                 'rate_decompositions.json': {'rows': decompositions}}
        if sum(len(audit.dep.json_bytes(value)) for value in files.values()) > p['analysis_run_budget_bytes'] - 256 * 1024:
            raise RuntimeError('Explanation output exceeds bounded quota')
        for name, value in files.items():
            base.write_json_retry(RUN / 'reports' / name, value)
        base.csv_rows(RUN / 'reports' / 'rate_decompositions.csv', decompositions)
        output_hashes = {path.name: base.file_hash(path) for path in sorted((RUN / 'reports').iterdir()) if path.is_file()}
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': sources,
            'dependency_manifest_sha256': p['dependency_manifest_sha256'], 'outputs_sha256': output_hashes})
        base.write_json_retry(RUN / 'checkpoint.json', {'status': 'complete', 'analysis_only_new_predictions': 0,
            'manifest_sha256': base.file_hash(RUN / 'reports' / 'manifest.json')})
        used = sum(path.stat().st_size for path in RUN.rglob('*') if path.is_file())
        if used > p['analysis_run_budget_bytes']:
            raise AssertionError('Explanation exceeded reserved quota')
        audit.pipeline.common.storage_guard(p['disk_reserve_bytes'], p['whole_research_budget_bytes'])
        print(json.dumps({key: value for key, value in summary.items() if key != 'source_signature'}), flush=True)
    finally:
        if started:
            base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
