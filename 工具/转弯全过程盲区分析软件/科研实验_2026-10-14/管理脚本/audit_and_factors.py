from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import statistics


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def csv_save(path, rows):
    if not rows:
        return
    fields = sorted({k for row in rows for k in row})
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit(run):
    cp_bytes = (run / 'checkpoint.json').read_bytes()
    cp = json.loads(cp_bytes.decode('utf-8-sig'))
    source = cp['source_signature']
    for name, sha in source.items():
        assert digest(run / 'source' / name) == sha, ('snapshot_source', name)
        assert digest(ROOT / 'src_v3' / name) == sha, ('active_source', name)
    shared = {}
    manifests = {}
    job_stages = Counter()
    checkpoint_rows = defaultdict(list)
    for row in cp['summaries']:
        checkpoint_rows[row['job_id']].append(row)
    for identifier, record in cp['completed'].items():
        directory = run / 'jobs' / identifier
        assert digest(directory / 'report.json') == record['report_sha256'], identifier
        report = read(directory / 'report.json')
        config = read(directory / 'configuration.json')
        assert report['id'] == config['id'] == identifier
        assert report['source_signature'] == config['source_signature'] == source
        for name, sha in report['output_sha256'].items():
            assert digest(directory / name) == sha, (identifier, name)
        data_key = (config['partition'], config['case_id'])
        if data_key not in manifests:
            folder = ROOT / 'datasets' / data_key[0] / data_key[1]
            manifest = read(folder / 'manifest.json')
            for name, sha in manifest['files'].items():
                assert digest(folder / name) == sha, (data_key, name)
            manifests[data_key] = manifest
        manifest = manifests[data_key]
        assert report['input_hashes'] == manifest['files']
        assert report['target_coordinates_sha256'] == manifest['target_coordinates_sha256']
        assert report['contact_label_sha256'] == manifest['contact_label_sha256']
        condition = json.dumps(config['condition'], sort_keys=True, separators=(',', ':'))
        key = (*data_key, condition, config['preprocessing'])
        fairness = (report['target_coordinates_sha256'], report['contact_label_sha256'],
                    report['observed_state_sha256'], report['observed_alpha_sha256'],
                    tuple(sorted(report['input_hashes'].items())))
        if key in shared:
            assert shared[key] == fairness, ('cross_method_input_mismatch', key)
        else:
            shared[key] = fairness
        saved_rows = read(directory / 'summary.json')
        assert saved_rows == checkpoint_rows[identifier], ('checkpoint_summary_mismatch', identifier)
        for row in saved_rows:
            assert row['case_id'] == config['case_id'] and row['job_id'] == identifier
        job_stages[config['stage']] += 1
    rows = [row for row in cp['summaries'] if row['stage'] in ('S1_nominal', 'S1_search')]
    metric_counts = Counter(row['job_id'] for row in cp['summaries'])
    assert set(metric_counts) == set(cp['completed']), 'summary_job_set_mismatch'
    captured = datetime.now(timezone.utc).isoformat()
    report = {'status': 'verified_completed_prefix', 'captured_at_utc': captured,
              'run': run.name, 'checkpoint_bytes_sha256': hashlib.sha256(cp_bytes).hexdigest(),
              'source_signature': source, 'completed_jobs': len(cp['completed']),
              'jobs_by_stage': dict(job_stages), 'stages': cp['stages'],
              'input_dataset_count_verified': len(manifests),
              'shared_input_groups_verified': len(shared),
              'all_completed_output_hashes_verified': True,
              'cross_method_coordinates_labels_observations_equal': True,
              'S1_score_count': len(rows), 'S1_complete': bool(cp['stages'].get('S1_search')),
              'physical_validation': False, 'independent_final_validation': False,
              'audit_script_sha256': digest(__file__)}
    out = run / 'reports'
    out.mkdir(exist_ok=True)
    save(out / 'completed_prefix_audit.json', report)
    factors(rows, out, report['S1_complete'])
    partial_s2(cp, out)
    snapshot_reports(cp, out)
    print(json.dumps({k: v for k, v in report.items() if k not in ('source_signature', 'stages')}, ensure_ascii=False))
    return report


def factors(rows, out, complete):
    specs = {item['id']: item for item in read(ROOT / 'scenario_matrix.json')}
    baseline = {row['case_id']: row for row in rows if row['config_id'] == 'hold'}
    paired = []
    for row in rows:
        if row['case_id'] not in baseline:
            continue
        base = baseline[row['case_id']]
        spec = specs[row['case_id']]
        assert row['target_count'] == base['target_count'] >= 20000
        assert row['score_end_s'] == base['score_end_s']
        paired.append({
            'case_id': row['case_id'], 'config_id': row['config_id'],
            'v_B_mps': spec['v_B_mps'], 'base_rate_deg_s': spec['base_rate_deg_s'],
            'template': spec['template'], 'target_count': row['target_count'],
            'right_insufficient_pct': row['right_pct'],
            'right_delta_vs_hold_pp': row['right_pct'] - base['right_pct'],
            'negative_fp_pct': row['negative_fp_pct'],
            'fp_delta_vs_hold_pp': row['negative_fp_pct'] - base['negative_fp_pct'],
            'right_miss': row['right_miss'], 'right_late': row['right_late'],
            'right_no_before': row['right_no_before'],
            'right_lead_p10_s': row['right_lead_p10_s'],
            'exit_right_contacts': row['exit_right_contacts'],
            'exit_right_insufficient_pct': row['exit_right_pct'],
            'S1_complete': complete})
    csv_save(out / 'S1_paired_driving_scores.csv', paired)
    effects = []
    for factor in ('v_B_mps', 'base_rate_deg_s', 'template'):
        groups = defaultdict(list)
        for row in paired:
            groups[(row['config_id'], row[factor])].append(row)
        for (config, level), group in sorted(groups.items(), key=lambda item: str(item[0])):
            effects.append({
                'factor': factor, 'level': level, 'config_id': config,
                'trajectory_count': len(group),
                'mean_right_insufficient_pct': statistics.mean(row['right_insufficient_pct'] for row in group),
                'worst_right_insufficient_pct': max(row['right_insufficient_pct'] for row in group),
                'mean_paired_delta_vs_hold_pp': statistics.mean(row['right_delta_vs_hold_pp'] for row in group),
                'worst_negative_fp_pct': max(row['negative_fp_pct'] for row in group),
                'S1_complete': complete})
    csv_save(out / 'S1_driving_factor_effects.csv', effects)
    save(out / 'S1_factor_interpretation.json', {
        'status': 'complete' if complete else 'partial_no_final_ranking',
        'comparison_unit': 'whole_simulated_trajectory',
        'points_and_frames_are_not_independent_vehicle_trials': True,
        'design_factor_levels': {'v_B_mps': [2, 3, 4], 'base_rate_deg_s': [2, 4, 8],
                                 'template': ['symmetric', 'fast_entry', 'fast_return']},
        'sign_convention': 'negative_right_delta_means_fewer_missed_or_late_RIGHT_contacts',
        'control_parameters': {'W_s': 2, 'margin_m': 0, 'confirmation_s': 0, 'clean_input': True},
        'causal_interpretation': 'factorial_synthetic_design_only; changing_rate_or_speed_also_changes_path',
        'same_path_speed_replay_completed': False, 'physical_validation': False})


def partial_s2(cp, out):
    rows = [row for row in cp['summaries'] if row['stage'] == 'S2']
    if not rows:
        return
    cases = ['v2_r2_symmetric', 'v2_r8_fast_return', 'v3_r4_symmetric',
             'v3_r4_fast_entry', 'v4_r2_fast_return', 'v4_r8_fast_entry']
    selected = [row['config_id'] for row in read(ROOT / 'reports' / 'S1_analysis.json')['finalists']]
    methods = selected + ([] if 'hold' in selected else ['hold'])
    preprocessing = ['raw', 'alpha_lp', 'age_hold']
    conditions = sorted({row['condition'] for row in rows})
    assert len(conditions) == 16, 'partial_export_requires_one_complete_observation_block'
    expected = {(case, method, condition, pp) for case in cases for method in methods
                for condition in conditions for pp in preprocessing}
    actual = {(row['case_id'], row['config_id'], row['condition'], row['preprocessing']) for row in rows}
    assert len(actual) == len(rows) and actual <= expected
    assert len(expected) == 864
    csv_save(out / 'S2_partial_scores.csv', [{key: value for key, value in row.items()
             if not isinstance(value, (list, dict))} for row in rows])
    missing = [{'case_id': case, 'config_id': method, 'condition': condition, 'preprocessing': pp}
               for case, method, condition, pp in sorted(expected - actual)]
    csv_save(out / 'S2_remaining_jobs.csv', missing)
    coverage = []
    for case in cases:
        for method in methods:
            count = sum(row['case_id'] == case and row['config_id'] == method for row in rows)
            coverage.append({'case_id': case, 'config_id': method, 'completed_jobs': count,
                             'expected_jobs': 48, 'complete_block': count == 48})
    csv_save(out / 'S2_block_coverage.csv', coverage)
    grouped = defaultdict(dict)
    for row in rows:
        key = (row['case_id'], row['config_id'], row['condition'])
        grouped[key][row['preprocessing']] = row
    paired = []
    for (case, method, condition), members in sorted(grouped.items()):
        if set(members) != set(preprocessing):
            continue
        base = members['raw']
        for pp in preprocessing[1:]:
            row = members[pp]
            assert row['target_count'] == base['target_count'] and row['score_end_s'] == base['score_end_s']
            paired.append({'case_id': case, 'config_id': method, 'condition': condition,
                           'preprocessing': pp, 'right_delta_vs_raw_pp': row['right_pct'] - base['right_pct'],
                           'point_fp_delta_vs_raw_pp': row['negative_fp_pct'] - base['negative_fp_pct'],
                           'frame_fpr_delta_vs_raw_pp': row['frame_fpr_pct'] - base['frame_fpr_pct'],
                           'complete_three_preprocessing_block': True, 'global_selection_allowed': False})
    csv_save(out / 'S2_partial_preprocessing_pairs.csv', paired)
    save(out / 'S2_partial_coverage.json', {
        'status': 'completed' if cp['stages'].get('S2') else 'partial_not_for_global_selection',
        'checkpoint_status': cp.get('status', 'running'), 'completed_jobs': len(rows),
        'expected_jobs': len(expected), 'remaining_jobs': len(missing),
        'fully_completed_case_method_blocks': sum(row['complete_block'] for row in coverage),
        'expected_case_method_blocks': len(coverage),
        'fully_completed_trajectories': [case for case in cases if all(
            row['complete_block'] for row in coverage if row['case_id'] == case)],
        'preprocessing_paired_rows': len(paired), 'final_preprocessing_selected': False,
        'points_frames_and_noise_seeds_are_not_independent_vehicle_trials': True,
        'physical_validation': False})


def snapshot_reports(cp, out):
    names = ['S0_acceptance.json', 'S0_elementary.json', 'S0_numerical_contact_audit.json',
             'S0_density_n35000.json', 'S0_density_n70000.json', 'S1_analysis.json',
             'S1_all_scores.csv', 'S1_configuration_comparison.csv',
             'S1核心方法结果.md', '夜间实验进度与阶段结论.md',
             'S2_analysis.json', 'S2_all_scores.csv', 'S3_analysis.json',
             'S3_all_scores.csv', 'S3_baseline_scores.csv', 'S3_joint_comparison.csv',
             '续跑实验进度与阶段结论.md']
    for name in names:
        origin = ROOT / 'reports' / name
        if origin.exists():
            shutil.copy2(origin, out / name)
    save(out / 'plan_at_report.json', read(ROOT / 'plan.json'))
    outputs = {path.name: digest(path) for path in sorted(out.iterdir())
               if path.is_file() and path.name != 'phase_report_manifest.json' and not path.name.endswith('.tmp')}
    save(out / 'phase_report_manifest.json', {
        'run': out.parent.name, 'checkpoint_sha256': digest(out.parent / 'checkpoint.json'),
        'source_signature': cp['source_signature'], 'derived_output_sha256': outputs,
        'generated_by_script_sha256': digest(__file__), 'physical_validation': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='overnight_20261014_v3')
    args = parser.parse_args()
    if args.run != 'overnight_20261014_v3':
        parser.error('This audit is restricted to the corrected v3 run.')
    audit(ROOT / 'runs' / args.run)
