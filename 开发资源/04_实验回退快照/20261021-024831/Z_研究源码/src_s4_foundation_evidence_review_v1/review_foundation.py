from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_RIGHT_scoring_ceiling_v1'))
import analyze_ceiling as dep

base, np, pipeline = dep.base, dep.np, dep.lead.pipeline
PROTOCOL = ROOT / 'protocol_foundation_evidence_review_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_foundation_evidence_review_v1'
EXPECTED_PROTOCOL_SHA = 'd77c17d12aeacdcffcbec7e627bad0188df4d91471013c1b9c8a0a6fc6ece0c6'


def job_quota(points):
    if points is None or not isinstance(points, int) or points < 0:
        return None
    return (points * 36 * 101 + 99) // 100 + 1024**2


def three_method_block_fits(points, whole_remaining, prospective_run_remaining=128*1024**2):
    quota = job_quota(points)
    return quota is not None and 3*quota + 2*1024**2 <= min(whole_remaining, prospective_run_remaining)


def optimistic_output_only_max_points(remaining):
    lo, hi = 0, max(1, remaining)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if three_method_block_fits(mid, remaining):
            lo = mid
        else:
            hi = mid - 1
    return lo if three_method_block_fits(lo, remaining) else None


def can_advance(matrix):
    required = [row for row in matrix if row['required_for_simulation_stage_advance']]
    return bool(required) and all(row['full_gate_status'] == 'passed' for row in required)


def source_is_current(recorded, current):
    return recorded == current


def guard(extra=0):
    p = base.read_json(PROTOCOL)
    measured = pipeline.common.storage_guard(p['disk_reserve_bytes'], p['whole_research_budget_bytes'])
    used = sum(path.stat().st_size for path in RUN.rglob('*') if path.is_file()) if RUN.exists() else 0
    if used+extra > p['analysis_run_budget_bytes'] or measured['experiment_bytes']+extra > p['whole_research_budget_bytes']:
        raise RuntimeError('Review quota reached; preserve history')
    return {**measured, 'review_bytes': used}


def signature():
    result = dep.signature()
    result.update({path.relative_to(ROOT).as_posix(): base.file_hash(path) for path in
                   [PROTOCOL, ROOT/'管理脚本'/'test_s4_v1.py', *sorted(Path(__file__).parent.glob('*.py'))]})
    return result


def evidence():
    p = base.read_json(PROTOCOL)
    canonical = Path(p['canonical_plan_path'])
    if base.file_hash(canonical) != p['canonical_plan_sha256'] or base.file_hash(canonical.with_name('实验总计划.md')) != p['canonical_document_sha256']:
        raise AssertionError('Preserved E plan/document changed')
    dep.dependencies()
    manifest_path = dep.RUN/'reports'/'manifest.json'
    if base.read_json(dep.RUN/'runner_lock.json')['status'] != 'stopped' or base.file_hash(manifest_path) != p['dependency_ceiling_manifest_sha256']:
        raise AssertionError('Latest analysis not closed or changed')
    manifest = base.read_json(manifest_path)
    for name, sha in manifest['source_signature'].items():
        if base.file_hash(ROOT/name) != sha:
            raise AssertionError('Frozen source changed')
    for name, sha in manifest['outputs_sha256'].items():
        if base.file_hash(dep.RUN/'reports'/name) != sha:
            raise AssertionError('Frozen ceiling output changed')
    records = {}
    for relative, sha in p['evidence_sources_sha256'].items():
        if base.file_hash(ROOT/relative) != sha:
            raise AssertionError('Bound evidence changed: '+relative)
        records[relative] = base.read_json(ROOT/relative)
    if base.file_hash(ROOT/'管理脚本'/'test_s4_v1.py') != p['frozen_management_test_sha256']:
        raise AssertionError('Existing unit suite changed')
    return base.read_json(canonical), records


def inventory():
    p = base.read_json(PROTOCOL)
    rows, observations = [], 0
    for partition, expected in p['fresh_input_inventory_partitions'].items():
        folders = sorted(path.parent for path in (ROOT/'datasets'/partition).glob('*/manifest.json'))
        if len(folders) != expected:
            raise AssertionError('Input trajectory inventory differs')
        for folder in folders:
            data, target, mf = pipeline.core.load_case(partition, folder.name)
            xy = target['xy']
            if len(xy) != 70000 or len(np.unique(xy, axis=0)) != 70000 or not np.isfinite(xy).all():
                raise AssertionError('Formal original target coordinates are not 70000 unique finite points')
            if base.array_hash(xy) != mf['target_coordinates_sha256'] or base.array_hash(target['contact_time']) != mf['contact_label_sha256']:
                raise AssertionError('Coordinate/label hash differs from frozen manifest')
            if np.isfinite(target['contact_time'][target['group'] == 2]).any():
                raise AssertionError('Frozen negative layer contains contacts')
            if mf['summary']['reference_edge_error_005_vs_0025_m'] > .005:
                raise AssertionError('Recorded frozen reference convergence exceeds original gate')
            source_bindings = {}
            for name, sha in mf['source_sha256'].items():
                candidates = [ROOT/'src'/name, ROOT/'src_v3'/name]
                source_bindings[name] = [path.relative_to(ROOT).as_posix() for path in candidates if path.exists() and base.file_hash(path) == sha]
            linked = []
            for condition in pipeline.condition_list():
                raw, obs = pipeline.load_observation(partition, folder.name, condition)
                descriptor = obs['descriptor']
                if (descriptor['input_hashes'] != mf['files'] or descriptor['target_coordinates_sha256'] != mf['target_coordinates_sha256'] or
                    descriptor['contact_label_sha256'] != mf['contact_label_sha256'] or not np.array_equal(raw['time'], data['time'])):
                    raise AssertionError('Raw observation does not link to the same frozen target/truth/scoring time axis')
                linked.append({'condition': condition['id'], 'sensors_file_sha256': obs['sensors_file_sha256'],
                               'sensor_array_hashes': descriptor['sensor_array_hashes']})
                observations += 1
            rows.append({'partition': partition, 'case_id': folder.name, 'manifest_sha256': base.file_hash(folder/'manifest.json'),
                'target_count': 70000, 'unique_coordinates_verified_now': True, 'input_files_sha256': mf['files'],
                'target_coordinate_sha256': mf['target_coordinates_sha256'], 'contact_label_sha256': mf['contact_label_sha256'],
                'recorded_reference_edge_error_m': mf['summary']['reference_edge_error_005_vs_0025_m'],
                'reference_not_reintegrated_by_this_review': True, 'generator_source_saved_binding_candidates': source_bindings,
                'raw_observations': linked})
            print(f'REVIEW INPUT {len(rows)}/39 {partition}/{folder.name}', flush=True)
    if len(rows) != 39 or observations != p['expected_common_raw_observation_files']:
        raise AssertionError('Expected 39 trajectories and 312 shared raw observation files')
    return rows


def current_tests():
    suite = unittest.TestSuite()
    for folder, pattern in [(Path(__file__).parent, 'test_review.py'), (ROOT/'管理脚本', 'test_s4_v1.py')]:
        suite.addTests(unittest.TestLoader().discover(str(folder), pattern=pattern))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful() or result.testsRun != 22:
        raise AssertionError(stream.getvalue())
    return {'tests_passed': result.testsRun, 'new_review_tests': 8, 'frozen_S4_tests_rerun': 14,
            'test_log': stream.getvalue(), 'unit_tests_not_new_scientific_prediction_jobs': True}


def save_cp(value):
    path = RUN/'checkpoint.json'
    base.write_json_retry(path, value)
    base.save_checkpoint_gzip(RUN/'checkpoint_snapshots'/(base.file_hash(path)+'.json.gz'), path.read_bytes())


def main():
    p = base.read_json(PROTOCOL)
    if base.file_hash(PROTOCOL) != EXPECTED_PROTOCOL_SHA:
        raise AssertionError('Frozen review protocol changed')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['authorized_until_local']):
        raise RuntimeError('Deadline reached; do not start a new review')
    kernel, mutex = pipeline.core.acquire_lock()
    started, progress = False, None
    try:
        if (RUN/'checkpoint.json').exists():
            raise AssertionError('Review already attempted; preserve prior evidence')
        canonical, records = evidence()
        before = guard(p['analysis_run_budget_bytes'])
        source = signature()
        for name, sha in source.items():
            path = RUN/'source'/name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise AssertionError('Prior source snapshot exists')
            path.write_bytes((ROOT/name).read_bytes())
            if base.file_hash(path) != sha:
                raise AssertionError('Source snapshot differs')
        base.write_json_retry(RUN/'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now()})
        started = True
        progress = {'status': 'running_readonly_foundation_evidence_review', 'new_prediction_jobs': 0, 'source_signature': source}
        save_cp(progress)
        tests = current_tests()
        inputs = inventory()
        by_name = {Path(name).name: value for name, value in records.items()}
        elementary = by_name['S0_elementary.json']
        historical_mismatches = {name: {'reported_sha256': sha, 'current_runtime_sha256': base.file_hash(ROOT/'src_v3'/name)}
            for name, sha in elementary['source_signature'].items() if not source_is_current(sha, base.file_hash(ROOT/'src_v3'/name))}
        numerical = by_name['S0_numerical_contact_audit.json']
        if numerical['validation_prediction_source_sha256'] != base.file_hash(ROOT/'src_v3'/'prediction.py'):
            raise AssertionError('Numerical contact audit is not bound to current prediction code')
        density = by_name['density_acceptance.json']
        sensitivity = by_name['sensitivity_analysis.json']
        full_pilot = by_name['full_sampling_pilot.json']
        step = by_name['step_analysis.json']
        joint = by_name['S4_joint_analysis.json']
        if (density['passes_subset_density_gate'] or full_pilot['passes_full_metric_pilot_gate'] or
            joint['feasible_family_configurations'] != 0 or len(joint['ranked']) != 84 or any(row['passes_research_budget'] for row in joint['ranked'])):
            raise AssertionError('Expected preserved failure/candidate evidence differs; do not silently reinterpret')
        matrix = []
        def row(key, implementation, full_status, scope, evidence_ids, required=True):
            matrix.append({'gate_id': key, 'implementation_or_local_evidence': implementation, 'full_gate_status': full_status,
                           'scope_and_remaining_requirement': scope, 'evidence_ids': ';'.join(evidence_ids),
                           'required_for_simulation_stage_advance': required})
        row('truth_reference', '39 frozen convergence records and files checked; existing 3-case contact audit source matches', 'frozen_record_scope_only',
            'No reference reintegration this review; boundary error records meet 0.005m; not a new all-domain proof', ['S0_numerical_contact_audit.json', 'input_inventory.json'])
        row('geometry_labels', 'Existing 3-case full RIGHT preflight and source-bound label preservation verified', 'three_case_preflight_only',
            'Finite 0.0125m geometry/labels accepted in 3 registered cases; finer spatial convergence not completed', ['preflight.json', 'population_feasibility.json'])
        row('causality', 'Fresh current 4-core prefix test plus existing estimator/scoring tests pass', 'unit_scope_only',
            '22 total tests; historical elementary source mismatch retained, not inherited as current proof', ['unit_checks.json', 'historical_source_binding.json'])
        row('shared_inputs', '39 input trajectories and all 312 raw observation file/array hashes rechecked', 'passed',
            'Frozen development and tuning inputs; actual full-RIGHT 3-method pairing already closed, not new test trajectories', ['input_inventory.json', 'ceiling_analysis.json'])
        row('unique_targets', 'All 39 original coordinate sets contain exactly 70000 unique finite points', 'passed',
            'No coordinate replacement or duplication; original label hashes retained; density convergence is a separate gate', ['input_inventory.json'])
        row('density_and_rare_coverage', 'Results and pointwise counterexamples preserved', 'failed',
            '28万 independent numeric gate false; full sampling pilot loses 2 zero-miss claims; RIGHT audit loses 7 subset claims', ['density_acceptance.json', 'full_sampling_pilot.json', 'sampling_analysis.json'])
        row('prediction_timestep', '36 completed 0.02/0.01 pilot predictions report subset pass', 'passed_subset_only',
            '3 registered trajectories and 2 conditions do not certify all refined configurations or full S4', ['step_analysis.json'])
        row('contact_tolerance', 'Three offline tolerances evaluated; 112 added window-miss instances retained', 'sensitive_subset_only',
            'Tolerance changes labels; no mixing with main ranking and no stable full-range claim', ['sensitivity_analysis.json'])
        row('scoring', 'Current 2s start/warmup semantics tested; lead and pointwise ceiling tables checked', 'corrected_implementation_scope_only',
            'Strict 2s ceiling around 25% is not an exemption for 1s lateness, misses or FP', ['unit_checks.json', 'coverage_analysis.json', 'ceiling_analysis.json'])
        row('algorithm_budget', '84 joint configurations completed; 4 shared-input processors explored', 'failed',
            'Zero configurations meet all registered budgets; raw and two method families remain exploratory', ['S4_joint_analysis.json', 'S4_processor_analysis.json'])
        row('execution_integrity', 'Frozen snapshots/hash chain and live 12GiB/3GiB guards checked', 'passed',
            'Execution correctness is not algorithm safety or MCU timing validation', ['resource_feasibility.json', 'manifest.json'])
        row('same_path_speed_replay', 'Explicitly absent from current S4 executor', 'not_implemented',
            '3 paths by 3 speeds require separately frozen source, target coordinates and speed-specific contact labels', ['protocol_s4_v1.json', 'plan.json'])
        row('unseen_final_validation', 'No feasible frozen final candidate or completed S5 input design', 'not_implemented',
            'Candidate/evaluator and at least 18 unseen trajectories must be frozen before S5', ['S4_joint_analysis.json', 'plan.json'])
        row('real_vehicle_validation', 'Simulation design parameters only', 'not_performed_outside_current_scope',
            'No load/friction/tire dynamics/moving targets/calibrated vehicle or real safety certification', ['plan.json'], required=False)
        if can_advance(matrix):
            raise AssertionError('Review must not turn incomplete/failed foundation evidence into a pass')
        measured = guard()
        remaining = p['whole_research_budget_bytes']-measured['experiment_bytes']
        right_protocol = base.read_json(ROOT/'protocol_RIGHT_census_v1.json')
        known = [{'case_id': case['id'], 'already_completed_no_rerun': True, 'extra_points_in_completed_batch': case['extra_count'],
                  'three_method_output_reservation_plus_headroom_bytes': 3*job_quota(case['extra_count'])+2*1024**2,
                  'would_fit_output_only_now_not_new_admission': three_method_block_fits(case['extra_count'], remaining)} for case in right_protocol['cases']]
        resources = {'measured_at_utc': base.utc_now(), **measured, 'research_budget_remaining_bytes': remaining,
            'research_budget_remaining_MiB': remaining/1024**2,
            'disk_free_GiB': measured['free_bytes']/1024**3, 'directory_budget_not_physical_disk_full': True,
            'output_only_optimistic_max_new_points_per_three_method_case_block': optimistic_output_only_max_points(remaining),
            'output_only_estimate_excludes_new_input_assets_and_is_not_batch_admission': True,
            'known_old_case_blocks': known, 'finer_grid_unique_point_inventory': None,
            'finer_grid_batch_resource_admitted': False, 'new_prediction_batch_implemented_or_admitted': False}
        successor = {'status': 'design_only_not_implemented_or_run', 'new_prediction_jobs': 0,
            'work_packages': [
                {'id': 'F1', 'topic': 'freeze estimand and geometry-only successor target design', 'requirements': 'Keep original 70000 and old labels/results; report fixed stratum metrics and point coverage separately; preserve all old failures; no result-driven selection of known witness points'},
                {'id': 'F2', 'topic': 'bounded finer spatial inventory and geometry/label feasibility first', 'requirements': 'A prospective 0.00625m lattice is a candidate design, not enumerated data; enumerate/count with truth only, prove uniqueness and old prefix/label consistency, then hash/freeze inventory before numerical prediction'},
                {'id': 'F3', 'topic': 'admit a whole fixed three-method case block only after resources known', 'requirements': 'Same existing 3 cores/noisy condition/2 variants/dt/tolerance; preserve full point outputs by lossless delta; reserve new input assets plus ceil(36*n*1.01)+1MiB per job for all three plus 2MiB; no assumed compression ratio'},
                {'id': 'F4', 'topic': 'independent stability and rare-miss review before any algorithm search', 'requirements': 'Absolute metrics and method-minus-hold effects with original 0.2pp/0.05s limits; retain added/removed miss indices, no cancellation; gate failure cannot be overwritten; S4/S5 remain incomplete'}],
            'requires_new_protocol_source_preflight_and_actual_worker_acceptance': True,
            'if_not_resource_admissible': 'save evidence and checkpoint; do not delete/move history, raise budget, launch partial-case ranking or pretend still computing'}
        summary = {'status': 'complete_readonly_foundation_evidence_and_successor_feasibility_review',
            'matrix_rows': len(matrix), 'original_trajectories_rechecked': len(inputs), 'unique_targets_per_trajectory': 70000,
            'shared_raw_observations_rechecked': sum(len(row['raw_observations']) for row in inputs),
            'historical_elementary_runtime_source_mismatches': list(historical_mismatches), 'new_current_code_tests_passed': tests['tests_passed'],
            'historical_S0_pass_is_not_current_full_foundation_acceptance': True,
            'full_foundation_accepted': False, 'algorithm_search_admitted': False,
            'new_prediction_batch_implemented_or_admitted': False, 'new_prediction_jobs': 0,
            'formal_cycle_total': [162, 2238], 'diagnostics_temporal_RIGHT': [12, 9], 'accepted_numeric_cycle_total': [183, 2259],
            'old_density_failure_overridden': False, 'S4_complete': False, 'S5_complete': False,
            'review_does_not_reintegrate_reference_or_relabel_dense_targets': True, 'source_signature': source,
            'canonical_plan_sha256': p['canonical_plan_sha256'], 'resource_measurement_before_review': before}
        records_out = {'foundation_review.json': summary, 'evidence_matrix.json': {'rows': matrix},
            'input_inventory.json': {'rows': inputs, 'new_predictions': 0}, 'unit_checks.json': tests,
            'historical_source_binding.json': {'elementary_mismatches': historical_mismatches, 'old_report_preserved': True,
                'current_causal_tests_bound_to_current_prediction_sha256': base.file_hash(ROOT/'src_v3'/'prediction.py'),
                'old_S0_scoring_pass_not_current_density_acceptance': True},
            'resource_feasibility.json': resources, 'successor_foundation_design.json': successor,
            'evidence_bindings.json': {'external_plan': p['canonical_plan_path'], 'external_plan_sha256': p['canonical_plan_sha256'],
                                       'external_document_sha256': p['canonical_document_sha256'], 'reports': p['evidence_sources_sha256']}}
        blobs = {name: dep.lead.audit.dep.json_bytes(value) for name, value in records_out.items()}
        blobs['evidence_matrix.csv'] = dep.lead.csv_bytes(matrix)
        guard(sum(map(len, blobs.values()))+128*1024)
        for name, blob in blobs.items():
            path = RUN/'reports'/name
            if path.exists():
                raise AssertionError('Prior frozen output exists')
            if name.endswith('.json'):
                base.write_json_retry(path, json.loads(blob))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
        base.write_json_retry(RUN/'reports'/'manifest.json', {'source_signature': source,
            'evidence_reports_sha256': p['evidence_sources_sha256'], 'canonical_plan_sha256': p['canonical_plan_sha256'],
            'outputs_sha256': {name: base.file_hash(RUN/'reports'/name) for name in blobs}})
        progress.update(status='complete_readonly_foundation_review_no_prediction_admitted', manifest_sha256=base.file_hash(RUN/'reports'/'manifest.json'))
        save_cp(progress)
        guard()
        print(json.dumps({key: value for key, value in summary.items() if key not in ('source_signature', 'resource_measurement_before_review')}, ensure_ascii=False), flush=True)
    except BaseException as error:
        if started:
            progress.update(status='failed_readonly_review_preserved', error=repr(error))
            save_cp(progress)
        raise
    finally:
        if started:
            base.write_json_retry(RUN/'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
