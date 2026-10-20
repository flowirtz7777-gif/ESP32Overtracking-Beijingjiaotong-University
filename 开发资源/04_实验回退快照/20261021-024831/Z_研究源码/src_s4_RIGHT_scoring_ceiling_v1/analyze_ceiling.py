from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_RIGHT_lead_coverage_v1'))
import analyze_coverage as lead

base, np, EPS = lead.base, lead.np, lead.EPS
PROTOCOL = ROOT / 'protocol_RIGHT_scoring_ceiling_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_RIGHT_scoring_ceiling_v1'
EXPECTED_PROTOCOL_SHA = '5ce3dc6173b70e656e719fbb69072b1bc4460f8e8ae1a59e145251addb0abbc9'
CLASSES = ('no_common_window_frame', 'scoring_start_limit', 'grid_window_phase_limit')


def earliest_support(contact, common):
    contact, common = np.asarray(contact), np.asarray(common)
    if not np.isfinite(contact).all() or not np.isfinite(common).all() or np.any(np.diff(common) <= 0):
        raise AssertionError('Finite contacts and a strictly increasing common time axis are required')
    indices = np.full(len(contact), -1, dtype=np.int32)
    times = np.full(len(contact), np.nan)
    if len(common):
        positions = np.searchsorted(common, contact - 2 - EPS, side='left')
        available = positions < len(common)
        available[available] &= common[positions[available]] <= contact[available] + EPS
        if len(common) >= np.iinfo(np.int32).max:
            raise AssertionError('Common time index exceeds exact int32 storage')
        indices[available] = positions[available].astype(np.int32)
        times[available] = common[positions[available]]
    return indices, times


def unattainability(contact, earliest, common, threshold):
    available = np.isfinite(earliest)
    cap = available & (contact - earliest >= threshold - EPS)
    no_frame = ~available
    start = available & ~cap & (contact - common[0] < threshold - EPS) if len(common) else np.zeros(len(contact), bool)
    phase = ~cap & ~(no_frame | start)
    if not np.array_equal(no_frame.astype(np.int8) + start.astype(np.int8) + phase.astype(np.int8), (~cap).astype(np.int8)):
        raise AssertionError('Unattainability classes do not form a disjoint complete partition')
    return cap, (no_frame, start, phase)


def require_pointwise_subset(actual, ceiling):
    if np.any(actual & ~ceiling):
        raise AssertionError('Actual coverage is not a pointwise subset of the scoring ceiling')


def verify_actual(contact, valid, common, earliest, global_ids, thresholds):
    finite = np.isfinite(valid)
    values = valid[finite]
    if np.isinf(valid).any():
        raise AssertionError('Invalid infinite confirmation timestamp')
    positions = np.searchsorted(common, values)
    if np.any(positions >= len(common)) or not np.array_equal(common[positions], values):
        raise AssertionError('Actual valid confirmation is not exactly on the common scoring time axis')
    if (np.any(values < contact[finite] - 2 - EPS) or np.any(values > contact[finite] + EPS) or
        np.any(~np.isfinite(earliest[finite])) or np.any(values < earliest[finite] - EPS)):
        raise AssertionError('Actual confirmation violates original window support or earliest common support')
    checks = []
    for threshold in thresholds:
        actual = finite & (contact - valid >= threshold - EPS)
        ceiling, _ = unattainability(contact, earliest, common, threshold)
        require_pointwise_subset(actual, ceiling)
        checks.append({'threshold_s': threshold, 'actual_covered_count': int(actual.sum()),
                       'ceiling_covered_count': int(ceiling.sum()), 'pointwise_subset_violations': 0,
                       'actual_covered_global_ids_sha256': base.array_hash(global_ids[actual]),
                       'ceiling_covered_global_ids_sha256': base.array_hash(global_ids[ceiling])})
    return {'finite_valid_count': int(finite.sum()), 'exact_common_timestamp_and_original_window_checks': True,
            'threshold_pointwise_checks': checks}


def population_rows(contact, earliest, groups, ids, common, thresholds):
    c, e, g = contact[ids], earliest[ids], groups[ids]
    if set(np.unique(g)) != {0, 1}:
        raise AssertionError('Both fixed positive-weight strata must be present')
    result = []
    for threshold in thresholds:
        cap, categories = unattainability(c, e, common, threshold)
        current = {}
        for name, selected in [('stratum0', g == 0), ('stratum1', g == 1), ('raw_pooled', np.ones(len(ids), bool))]:
            n = int(selected.sum())
            counts = [int((selected & value).sum()) for value in categories]
            row = {'aggregation': name, 'threshold_s': float(threshold), 'eligible_point_inventory': n,
                   'denominator_count': n, 'ceiling_covered_count': int((selected & cap).sum()),
                   'scoring_ceiling_pct': float(100 * (selected & cap).sum() / n)}
            for key, count in zip(CLASSES, counts):
                row[key + '_count'] = count
                row[key + '_pct'] = float(100 * count / n)
            current[name] = row
            result.append(row)
        row = {'aggregation': 'fixed_equal_strata', 'threshold_s': float(threshold),
               'eligible_point_inventory': len(ids), 'denominator_count': None, 'ceiling_covered_count': None,
               'scoring_ceiling_pct': .5 * (current['stratum0']['scoring_ceiling_pct'] + current['stratum1']['scoring_ceiling_pct'])}
        for key in CLASSES:
            row[key + '_count'] = None
            row[key + '_pct'] = .5 * (current['stratum0'][key + '_pct'] + current['stratum1'][key + '_pct'])
        result.append(row)
    for row in result:
        if abs(row['scoring_ceiling_pct'] + sum(row[key + '_pct'] for key in CLASSES) - 100) > 1e-10:
            raise AssertionError('Ceiling and explicit unattainability categories do not add to 100 percent')
    return result


def dependencies():
    p = base.read_json(PROTOCOL)
    cp = lead.dependencies()
    if base.file_hash(lead.PROTOCOL) != p['dependency_protocol_sha256'] or base.file_hash(lead.RUN / 'checkpoint.json') != p['dependency_checkpoint_sha256']:
        raise AssertionError('Frozen completed lead analysis dependency changed')
    if base.read_json(lead.RUN / 'runner_lock.json')['status'] != 'stopped':
        raise AssertionError('Lead analysis is still active')
    manifest = lead.RUN / 'reports' / 'manifest.json'
    if base.file_hash(manifest) != p['dependency_manifest_sha256']:
        raise AssertionError('Lead analysis manifest changed')
    m = base.read_json(manifest)
    for name, sha in m['source_signature'].items():
        if base.file_hash(ROOT / name) != sha:
            raise AssertionError('Dependency source changed')
    for name, sha in m['outputs_sha256'].items():
        if base.file_hash(lead.RUN / 'reports' / name) != sha:
            raise AssertionError('Dependency output changed')
    return cp


def signature():
    source = lead.signature()
    source.update({path.relative_to(ROOT).as_posix(): base.file_hash(path)
                   for path in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]})
    return source


def guard(extra=0):
    p = base.read_json(PROTOCOL)
    measured = lead.pipeline.common.storage_guard(p['disk_reserve_bytes'], p['whole_research_budget_bytes'])
    used = sum(path.stat().st_size for path in RUN.rglob('*') if path.is_file()) if RUN.exists() else 0
    if used + extra > p['analysis_run_budget_bytes'] or measured['experiment_bytes'] + extra > p['whole_research_budget_bytes']:
        raise RuntimeError('Scoring ceiling output quota/resource admission failed; do not remove history')
    return {**measured, 'analysis_run_bytes': used}


def save_cp(value):
    path = RUN / 'checkpoint.json'
    base.write_json_retry(path, value)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (base.file_hash(path) + '.json.gz'), path.read_bytes())


def main():
    p = base.read_json(PROTOCOL)
    if base.file_hash(PROTOCOL) != EXPECTED_PROTOCOL_SHA:
        raise AssertionError('Frozen ceiling explanatory protocol changed')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
        raise RuntimeError('Do not start a new analysis after the authorized deadline')
    kernel, mutex = lead.pipeline.core.acquire_lock()
    started, progress = False, None
    try:
        if (RUN / 'checkpoint.json').exists():
            raise AssertionError('Prior run exists; preserve it rather than rerunning')
        cp = dependencies()
        before = guard(p['analysis_run_budget_bytes'])
        source = signature()
        for name, sha in source.items():
            path = RUN / 'source' / name
            if path.exists():
                raise AssertionError('Prior frozen source exists')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
            if base.file_hash(path) != sha:
                raise AssertionError('Source snapshot mismatch')
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        started = True
        progress = {'status': 'running_readonly_scoring_ceiling', 'verified_cases': [], 'verified_jobs': [], 'new_prediction_jobs': 0, 'source_signature': source}
        save_cp(progress)
        ceiling_rows, comparisons, derivations, point_proofs, shared = [], [], {}, [], {}
        previous_rows = base.read_json(lead.RUN / 'reports' / 'lead_coverage_rows.json')['rows']
        previous = {tuple(row[key] for key in ('case_id', 'core_id', 'variant', 'cohort', 'aggregation', 'threshold_s')): row for row in previous_rows}
        jobs = lead.audit.dep.jobs()
        lead_protocol = base.read_json(lead.PROTOCOL)
        for case in p['cases']:
            case_jobs = [job for job in jobs if job['reference']['case_id'] == case]
            if [job['reference']['core_id'] for job in case_jobs] != p['cores']:
                raise AssertionError('Incomplete fixed three-method case block')
            ref = case_jobs[0]['reference']
            target, proof, _ = lead.audit.dep.load_targets(case)
            raw, obs = lead.pipeline.load_observation(ref['partition'], case, ref['condition'])
            cut = float(raw['time'][-1] - 3)
            common = raw['time'][(raw['time'] >= 2 - EPS) & (raw['time'] <= cut + EPS)]
            with np.load(ROOT / proof['original_target_path']) as saved:
                populations = lead.audit.cohorts(target, saved['previous_ids'], cut)
            if list(populations) != lead_protocol['cohorts']:
                raise AssertionError('Frozen common cohort matrix changed')
            all_ids = populations[lead_protocol['cohorts'][0]]
            indices, earliest = earliest_support(target['contact_time'][all_ids], common)
            global_earliest = np.full(len(target['xy']), np.nan)
            global_earliest[all_ids] = earliest
            derivations[case] = {'eligible_global_ids_sha256': base.array_hash(all_ids),
                'common_time_sha256': base.array_hash(common), 'common_time_count': len(common),
                'first_common_time_s': float(common[0]) if len(common) else None, 'score_end_s': cut,
                'raw_sensor_hashes': obs['descriptor']['sensor_array_hashes'],
                'earliest_support_common_index_dtype_shape_sha256': [indices.dtype.str, list(indices.shape), base.array_hash(indices)],
                'earliest_support_time_dtype_shape_sha256': [earliest.dtype.str, list(earliest.shape), base.array_hash(earliest)],
                'maximum_scorable_lead_dtype_shape_sha256': [(target['contact_time'][all_ids]-earliest).dtype.str, list(earliest.shape), base.array_hash(target['contact_time'][all_ids]-earliest)],
                'derivation_arrays_regenerable_not_saved_as_prediction_outputs': True,
                'cohort_index_sha256': {name: base.array_hash(ids) for name, ids in populations.items()}}
            for cohort, ids in populations.items():
                for row in population_rows(target['contact_time'], global_earliest, target['group'], ids, common, p['threshold_seconds']):
                    ceiling_rows.append({'case_id': case, 'cohort': cohort, **row})
            cap_lookup = {(row['cohort'], row['aggregation'], row['threshold_s']): row for row in ceiling_rows if row['case_id'] == case}
            for job in case_jobs:
                guard()
                _, report = lead.audit.dep.verify(job, cp['completed'][job['id']])
                descriptor = (report['full_coordinate_sha256'], report['full_label_array_sha256'], report['raw_sensor_hashes'],
                              report['estimated_state_sha256'], report['estimated_alpha_sha256'], report['score_start_s'], report['score_end_s'])
                if case in shared and shared[case] != descriptor:
                    raise AssertionError('Actual methods do not share the same full inputs and scoring')
                shared[case] = descriptor
                if report['raw_sensor_hashes'] != derivations[case]['raw_sensor_hashes'] or report['score_end_s'] != cut:
                    raise AssertionError('Ceiling uses a different observation/scoring axis')
                arrays = lead.audit.reconstruct(job, report)
                for variant in job['reference']['variants']:
                    v = lead.pipeline.Variant(**variant)
                    if v.exit_W != p['horizon_seconds']:
                        raise AssertionError('Both frozen variants must retain W=2')
                    point_proofs.append({'case_id': case, 'core_id': job['reference']['core_id'], 'variant': v.tag,
                        **verify_actual(target['contact_time'][all_ids], arrays[v.tag+'_valid'][all_ids], common, earliest, all_ids, p['threshold_seconds'])})
                    for cohort in populations:
                        for aggregation in p['aggregations']:
                            for threshold in p['threshold_seconds']:
                                actual = previous[(case, job['reference']['core_id'], v.tag, cohort, aggregation, float(threshold))]
                                cap = cap_lookup[(cohort, aggregation, float(threshold))]
                                gap = cap['scoring_ceiling_pct'] - actual['coverage_pct']
                                if gap < -1e-10:
                                    raise AssertionError('Actual aggregate exceeds pointwise proven ceiling')
                                comparisons.append({'case_id': case, 'core_id': job['reference']['core_id'], 'variant': v.tag,
                                    'cohort': cohort, 'aggregation': aggregation, 'threshold_s': float(threshold),
                                    'actual_coverage_pct_unchanged': actual['coverage_pct'],
                                    'actual_window_miss_pct_unchanged': actual['window_miss_pct'],
                                    'scoring_ceiling_pct': cap['scoring_ceiling_pct'], 'ceiling_minus_actual_pp': gap,
                                    'no_common_window_frame_pct': cap['no_common_window_frame_pct'],
                                    'scoring_start_limit_pct': cap['scoring_start_limit_pct'],
                                    'grid_window_phase_limit_pct': cap['grid_window_phase_limit_pct'],
                                    'no_adjusted_score_or_old_gate_override': True})
                progress['verified_jobs'].append({'id': job['id'], **cp['completed'][job['id']]})
                save_cp(progress)
            progress['verified_cases'].append(case)
            save_cp(progress)
            print(f'VERIFIED SCORING CEILING {len(progress["verified_cases"])}/3 {case}', flush=True)
        if (len(ceiling_rows), len(comparisons), len(point_proofs)) != (480, 2880, 18):
            raise AssertionError('Incomplete predeclared ceiling/actual matrix')
        summary = {'status': 'complete_readonly_scoring_grid_reachability_ceiling', 'identity': p['identity'],
            'unique_case_cohort_aggregation_threshold_rows': len(ceiling_rows), 'actual_comparison_rows': len(comparisons),
            'pointwise_method_variant_checks': len(point_proofs), 'threshold_pointwise_checks': 90,
            'all_actual_confirmations_on_exact_common_axis_and_supported_by_original_window': True,
            'actual_coverage_is_pointwise_subset_of_ceiling_not_just_net_count': True,
            'unattainability_categories_disjoint_and_complete': True,
            'upper_bound_ignores_false_alarm_and_confirmation_feasibility_budgets': True,
            'no_scoring_time_window_labels_predictions_or_rankings_changed': True,
            'new_prediction_jobs': 0, 'formal_cycle_total': [162, 2238], 'accepted_diagnostics_temporal_RIGHT': [12, 9],
            'accepted_numeric_cycle_total': [183, 2259], 'old_full_density_failure_overridden': False,
            'new_acceptance_or_algorithm_selection_gate': False, 'S4_complete': False, 'S5_complete': False,
            'resource_measurement_before_analysis': before, 'source_signature': source,
            'dependency_manifest_sha256': p['dependency_manifest_sha256']}
        documents = {'ceiling_analysis.json': summary, 'scoring_ceiling_rows.json': {'rows': ceiling_rows},
                     'actual_vs_ceiling_rows.json': {'rows': comparisons}, 'pointwise_subset_proofs.json': {'rows': point_proofs},
                     'regenerable_derivation_proofs.json': derivations}
        blobs = {name: lead.audit.dep.json_bytes(value) for name, value in documents.items()}
        blobs['scoring_ceiling_rows.csv'] = lead.csv_bytes(ceiling_rows)
        blobs['actual_vs_ceiling_rows.csv'] = lead.csv_bytes(comparisons)
        guard(sum(map(len, blobs.values())) + 256 * 1024)
        for name, blob in blobs.items():
            path = RUN / 'reports' / name
            if path.exists():
                raise AssertionError('Frozen output already exists; do not overwrite')
            if name.endswith('.json'):
                base.write_json_retry(path, json.loads(blob))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': source,
            'dependency_manifest_sha256': p['dependency_manifest_sha256'],
            'outputs_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in blobs}})
        progress.update(status='complete_readonly_scoring_ceiling', manifest_sha256=base.file_hash(RUN / 'reports' / 'manifest.json'))
        save_cp(progress)
        guard()
        print(json.dumps({key: value for key, value in summary.items() if key not in ('source_signature', 'resource_measurement_before_analysis')}, ensure_ascii=False), flush=True)
    except BaseException as error:
        if started:
            progress.update(status='failed_readonly_scoring_ceiling_preserved', error=repr(error))
            save_cp(progress)
        raise
    finally:
        if started:
            base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
