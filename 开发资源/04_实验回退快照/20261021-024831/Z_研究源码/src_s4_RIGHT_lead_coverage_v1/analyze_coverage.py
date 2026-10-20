from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_RIGHT_sampling_audit_v1'))
import audit_sampling as audit

base, np, pipeline = audit.base, audit.np, audit.pipeline
PROTOCOL = ROOT / 'protocol_RIGHT_lead_coverage_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_RIGHT_lead_coverage_v1'
EXPECTED_PROTOCOL_SHA = 'b79ff6b596184dde459666d1dd6550e73c55bc4d8d0bfd25d3565eaa824f7307'
EPS = pipeline.summarize.__globals__['EPS']
THRESHOLDS = (0., .3, 1., 1.5, 2.)
AGGREGATIONS = ('stratum0', 'stratum1', 'raw_pooled', 'fixed_equal_strata')


def coverage(contact, valid, groups, ids, thresholds=THRESHOLDS):
    ids = np.asarray(ids)
    if len(np.unique(ids)) != len(ids):
        raise AssertionError('Duplicated cohort points')
    c, v, g = contact[ids], valid[ids], groups[ids]
    if not np.isfinite(c).all() or not np.isin(g, [0, 1]).all() or np.isinf(v).any():
        raise AssertionError('Expected eligible RIGHT labels and finite-or-NaN confirmation timestamps')
    hit = np.isfinite(v)
    leads = c[hit] - v[hit]
    if np.any(leads < -EPS):
        raise AssertionError('Valid-window confirmation occurs after contact')
    counts = {}
    for name, mask in [('stratum0', g == 0), ('stratum1', g == 1), ('raw_pooled', np.ones(len(ids), dtype=bool))]:
        n = int(mask.sum())
        if not n:
            raise AssertionError('A fixed positive-weight stratum is empty; do not renormalize')
        valid_mask = mask & hit
        count = int(valid_mask.sum())
        counts[name] = (n, count, c[valid_mask] - v[valid_mask])
    rows = []
    for threshold in thresholds:
        current = {}
        for name in AGGREGATIONS[:3]:
            n, valid_n, lead = counts[name]
            numerator = int(np.count_nonzero(lead >= threshold - EPS))
            row = {'aggregation': name, 'threshold_s': float(threshold), 'eligible_point_inventory': n,
                'denominator_count': n, 'numerator_count': numerator, 'valid_alarm_count': valid_n,
                'window_miss_count': n - valid_n, 'coverage_pct': float(100 * numerator / n),
                'window_miss_pct': float(100 * (n - valid_n) / n), 'estimator': 'count_over_all_eligible_points'}
            current[name] = row
            rows.append(row)
        rows.append({'aggregation': 'fixed_equal_strata', 'threshold_s': float(threshold),
            'eligible_point_inventory': len(ids), 'denominator_count': None, 'numerator_count': None,
            'valid_alarm_count': None, 'window_miss_count': None,
            'coverage_pct': float(.5 * (current['stratum0']['coverage_pct'] + current['stratum1']['coverage_pct'])),
            'window_miss_pct': float(.5 * (current['stratum0']['window_miss_pct'] + current['stratum1']['window_miss_pct'])),
            'estimator': 'half_each_stratum_rate_not_integer_counts'})
    for aggregation in AGGREGATIONS:
        values = [row['coverage_pct'] for row in rows if row['aggregation'] == aggregation]
        if np.any(np.diff(values) > 1e-10):
            raise AssertionError('Lead coverage is not monotone')
    return rows


def verify_summary(curves, summary):
    lookup = {(row['aggregation'], row['threshold_s']): row for row in curves}
    n = summary['right_contacts']
    zero, one = lookup[('raw_pooled', 0.)], lookup[('raw_pooled', 1.)]
    if zero['denominator_count'] != n or zero['window_miss_count'] != summary['right_miss']:
        raise AssertionError('Window-miss counts disagree with frozen scoring')
    if abs(zero['coverage_pct'] - 100 * (n - summary['right_miss']) / n) > 1e-10:
        raise AssertionError('Zero-threshold coverage does not retain misses in denominator')
    if abs(one['coverage_pct'] - (100 - summary['right_pct'])) > 1e-10:
        raise AssertionError('One-second coverage disagrees with frozen insufficient/late scoring')
    for layer in summary['stratum_right_rows']:
        row = lookup[(f"stratum{layer['group']}", 1.)]
        if row['denominator_count'] != layer['right_contacts'] or abs(row['coverage_pct'] - (100 - layer['right_insufficient_pct'])) > 1e-10:
            raise AssertionError('Layer counts/rates disagree with frozen summary')


def signature():
    result = audit.signature()
    explanation = ROOT / 'runs' / 'resume_S4_RIGHT_composition_explanation_v1' / 'reports' / 'manifest.json'
    result.update(base.read_json(explanation)['source_signature'])
    result.update({path.relative_to(ROOT).as_posix(): base.file_hash(path)
                   for path in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]})
    return result


def guard(extra=0):
    p = base.read_json(PROTOCOL)
    measured = pipeline.common.storage_guard(p['disk_reserve_bytes'], p['whole_research_budget_bytes'])
    used = sum(path.stat().st_size for path in RUN.rglob('*') if path.is_file()) if RUN.exists() else 0
    if used + extra > p['analysis_run_budget_bytes'] or measured['experiment_bytes'] + extra > p['whole_research_budget_bytes']:
        raise RuntimeError('Bounded coverage analysis resource admission failed; preserve all history')
    return {**measured, 'analysis_run_bytes': used}


def dependencies():
    p = base.read_json(PROTOCOL)
    for relative, sha in p['dependency_runs'].items():
        run = ROOT / relative
        if base.read_json(run / 'runner_lock.json')['status'] != 'stopped':
            raise AssertionError('Dependency process has not closed')
        manifest_path = run / 'reports' / 'manifest.json'
        if base.file_hash(manifest_path) != sha:
            raise AssertionError('Frozen dependency manifest changed')
        manifest = base.read_json(manifest_path)
        for name, expected in manifest['source_signature'].items():
            if base.file_hash(ROOT / name) != expected:
                raise AssertionError('Frozen dependency source changed: ' + name)
        for name, expected in manifest['outputs_sha256'].items():
            if base.file_hash(run / 'reports' / name) != expected:
                raise AssertionError('Frozen dependency output changed: ' + name)
    cp_path = audit.dep.RUN / 'checkpoint.json'
    if base.file_hash(cp_path) != p['RIGHT_checkpoint_sha256'] or base.file_hash(audit.PROTOCOL) != p['sampling_protocol_sha256']:
        raise AssertionError('Closed prediction checkpoint or sampling rules changed')
    cp = base.read_json(cp_path)
    if cp['status'] != 'fixed_RIGHT_census_diagnostic_complete' or len(cp['completed']) != 9:
        raise AssertionError('All nine frozen diagnostics are required')
    return cp


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def save_cp(value):
    path = RUN / 'checkpoint.json'
    base.write_json_retry(path, value)
    sha = base.file_hash(path)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (sha + '.json.gz'), path.read_bytes())


def main():
    if base.file_hash(PROTOCOL) != EXPECTED_PROTOCOL_SHA:
        raise AssertionError('Frozen explanatory design changed')
    p = base.read_json(PROTOCOL)
    if list(THRESHOLDS) != p['threshold_seconds'] or list(AGGREGATIONS) != p['aggregations'] or p['fixed_layer_weights'] != [.5, .5]:
        raise AssertionError('Coverage design differs from frozen protocol')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
        raise RuntimeError('Authorization deadline reached; do not start a new analysis')
    kernel, mutex = pipeline.core.acquire_lock()
    started, progress = False, None
    try:
        if (RUN / 'checkpoint.json').exists():
            raise AssertionError('Preserve prior attempt; never repeat/overwrite a completed or failed run')
        cp = dependencies()
        before = guard(p['analysis_run_budget_bytes'])
        source = signature()
        for name, sha in source.items():
            path = RUN / 'source' / name
            if path.exists():
                raise AssertionError('Prior source snapshot exists')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
            if base.file_hash(path) != sha:
                raise AssertionError('Source snapshot verification failed')
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        started = True
        progress = {'status': 'running_readonly_lead_coverage', 'verified_jobs': [], 'new_prediction_jobs': 0, 'source_signature': source}
        save_cp(progress)
        cohort_proofs = base.read_json(audit.RUN / 'reports' / 'cohort_proofs.json')
        frozen_rows = base.read_json(ROOT / 'runs/resume_S4_RIGHT_composition_explanation_v1/reports/corrected_cohort_summaries.json')['rows']
        saved_lookup = {(row['case_id'], row['core_id'], row['variant'], row['cohort']): row for row in frozen_rows}
        curves, fair = [], {}
        for j, job in enumerate(audit.dep.jobs()):
            guard()
            _, report = audit.dep.verify(job, cp['completed'][job['id']])
            ref = job['reference']
            case, core = ref['case_id'], ref['core_id']
            targets, proof, _ = audit.dep.load_targets(case)
            with np.load(ROOT / proof['original_target_path']) as saved:
                previous_ids = saved['previous_ids']
            populations = audit.cohorts(targets, previous_ids, report['score_end_s'])
            if list(populations) != p['cohorts']:
                raise AssertionError('All eight cohorts, including all phases, must be retained')
            common = {'input_hashes': report['input_hashes'], 'raw_sensor_hashes': report['raw_sensor_hashes'],
                      'estimated_state_sha256': report['estimated_state_sha256'],
                      'estimated_alpha_sha256': report['estimated_alpha_sha256'],
                      'score_start_s': report['score_start_s'], 'score_end_s': report['score_end_s'], 'cohort_indices': {}}
            for name, ids in populations.items():
                expected = cohort_proofs[case][name]
                if (len(ids) != expected['count'] or base.array_hash(ids) != expected['index_sha256'] or
                    base.array_hash(targets['xy'][ids]) != expected['coordinate_sha256'] or
                    any(base.array_hash(targets[key][ids]) != sha for key, sha in expected['label_sha256'].items())):
                    raise AssertionError('Frozen cohort coordinates, labels, or indices differ')
                common['cohort_indices'][name] = expected['index_sha256']
            if case in fair and fair[case] != common:
                raise AssertionError('Methods do not share exact cohort inputs/estimates/scoring')
            fair[case] = common
            arrays = audit.reconstruct(job, report)
            for variant in ref['variants']:
                tag = pipeline.Variant(**variant).tag
                valid = arrays[tag + '_valid']
                for cohort, ids in populations.items():
                    values = coverage(targets['contact_time'], valid, targets['group'], ids)
                    verify_summary(values, saved_lookup[(case, core, tag, cohort)])
                    for value in values:
                        curves.append({'case_id': case, 'core_id': core, 'variant': tag, 'cohort': cohort, **value})
            progress['verified_jobs'].append({'id': job['id'], **cp['completed'][job['id']],
                'all_input_output_full_point_arrays_and_cohort_labels_verified': True})
            save_cp(progress)
            print(f'VERIFIED LEAD COVERAGE {j + 1}/9 {case} {core}', flush=True)
        lookup = {(row['case_id'], row['core_id'], row['variant'], row['cohort'], row['aggregation'], row['threshold_s']): row for row in curves}
        effects, subset_pairs = [], []
        identity_keys = ('case_id', 'core_id', 'variant', 'cohort', 'aggregation', 'threshold_s')
        for row in curves:
            identity = {key: row[key] for key in identity_keys}
            if row['core_id'] != 'hold':
                hold = lookup[(row['case_id'], 'hold', row['variant'], row['cohort'], row['aggregation'], row['threshold_s'])]
                if row['eligible_point_inventory'] != hold['eligible_point_inventory']:
                    raise AssertionError('Method contrast denominator inventories differ')
                effects.append({**identity, 'method_coverage_pct': row['coverage_pct'], 'hold_coverage_pct': hold['coverage_pct'],
                    'method_minus_hold_coverage_pp': row['coverage_pct'] - hold['coverage_pct'],
                    'method_minus_hold_window_miss_pp': row['window_miss_pct'] - hold['window_miss_pct']})
            if row['cohort'] != p['cohorts'][0]:
                full = lookup[(row['case_id'], row['core_id'], row['variant'], p['cohorts'][0], row['aggregation'], row['threshold_s'])]
                subset_pairs.append({**identity, 'subset_coverage_pct': row['coverage_pct'], 'reference_coverage_pct': full['coverage_pct'],
                    'subset_minus_reference_coverage_pp': row['coverage_pct'] - full['coverage_pct'],
                    'subset_minus_reference_window_miss_pp': row['window_miss_pct'] - full['window_miss_pct'],
                    'pooled_mixture_composition_can_differ': row['aggregation'] == 'raw_pooled',
                    'not_old_complete_density_gate_adjudication': True})
        if (len(curves), len(effects), len(subset_pairs)) != (p['expected_coverage_rows'], p['expected_method_minus_hold_rows'], p['expected_subset_minus_full_reference_rows']):
            raise AssertionError('Coverage/effect/subset matrix is incomplete')
        summary = {'status': 'complete_readonly_layer_conditional_effective_lead_coverage', 'identity': p['identity'],
            'coverage_rows': len(curves), 'method_minus_hold_rows': len(effects), 'subset_reference_rows': len(subset_pairs),
            'fixed_threshold_seconds': list(THRESHOLDS), 'frozen_scoring_EPS': EPS,
            'all_144_cohort_zero_and_one_second_counts_match_frozen_miss_and_late_summaries': True,
            'all_curves_monotone_all_missing_confirmations_retained_in_denominator': True,
            'no_NaN_lead_imputation_or_success_only_denominator': True,
            'all_nine_input_output_source_and_full_array_reconstructions_verified': True,
            'all_three_common_input_groups_and_all_24_cohort_indices_verified': True,
            'new_prediction_jobs': 0, 'formal_cycle_jobs_unchanged': 162, 'formal_total_jobs_unchanged': 2238,
            'accepted_temporal_diagnostics': 12, 'accepted_RIGHT_diagnostics': 9,
            'accepted_numeric_cycle_jobs_unchanged': 183, 'accepted_numeric_total_jobs_unchanged': 2259,
            'new_acceptance_or_algorithm_selection_gate': False, 'old_full_density_failure_overridden': False,
            'weighted_quantiles_implemented': False, 'S4_complete': False, 'S5_complete': False,
            'resource_measurement_before_analysis': before, 'protocol_sha256': EXPECTED_PROTOCOL_SHA,
            'dependency_manifests_sha256': p['dependency_runs'], 'source_signature': source}
        documents = {'coverage_analysis.json': summary, 'lead_coverage_rows.json': {'rows': curves},
                     'method_minus_hold_rows.json': {'rows': effects}, 'subset_reference_rows.json': {'rows': subset_pairs},
                     'shared_inputs_and_cohort_index_proofs.json': fair}
        blobs = {name: audit.dep.json_bytes(value) for name, value in documents.items()}
        for name, rows in [('lead_coverage_rows.csv', curves), ('method_minus_hold_rows.csv', effects), ('subset_reference_rows.csv', subset_pairs)]:
            blobs[name] = csv_bytes(rows)
        guard(sum(map(len, blobs.values())) + 256 * 1024)
        for name, blob in blobs.items():
            path = RUN / 'reports' / name
            if path.exists():
                raise AssertionError('Preserve any prior output; do not overwrite')
            if name.endswith('.json'):
                base.write_json_retry(path, json.loads(blob))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
        manifest = {'source_signature': source, 'dependency_manifests_sha256': p['dependency_runs'],
                    'outputs_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in blobs}}
        base.write_json_retry(RUN / 'reports' / 'manifest.json', manifest)
        progress.update(status='complete_readonly_lead_coverage', manifest_sha256=base.file_hash(RUN / 'reports' / 'manifest.json'))
        save_cp(progress)
        guard()
        print(json.dumps({key: value for key, value in summary.items() if key not in ('source_signature', 'resource_measurement_before_analysis', 'dependency_manifests_sha256')}, ensure_ascii=False), flush=True)
    except BaseException as error:
        if started:
            progress.update(status='failed_readonly_analysis_preserved', error=repr(error))
            save_cp(progress)
        raise
    finally:
        if started:
            base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
