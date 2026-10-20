"""Administrative validity overlay; never reads active scientific checkpoints."""
from __future__ import annotations
import gzip
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'src_s4_repair_review_20261019_v1'))
import runtime as r

RUN = ROOT/'runs/truth_label_impact_registry_20261019_v1'
r.RUN = RUN
OVERLAY = ROOT/'research_validity_overlay_20261019_v1.json'

def scan_size(root):
    total, stack = 0, [Path(root)]
    while stack:
        path = stack.pop()
        if not path.exists():
            continue
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                else:
                    raise RuntimeError('Nonregular research asset: '+entry.path)
    return total

r.tree_bytes = scan_size

def contains_digest(value, wanted):
    if isinstance(value, dict):
        return any(contains_digest(v, wanted) for v in value.values())
    if isinstance(value, list):
        return any(contains_digest(v, wanted) for v in value)
    return value == wanted

def build():
    r.require(not RUN.exists() and not OVERLAY.exists(), 'Impact overlay already registered')
    original = r.helper().ORIGINAL_PLAN.parent
    geometry_sha = r.file_hash(ROOT/'src_v3/geometry.py')
    datasets, jobs, report_index, errors = [], [], [], []
    for location, base in (('Z', ROOT), ('E', original)):
        for path in sorted((base/'datasets').glob('*/*/manifest.json')):
            try:
                item = r.read(path)
                targets = item.get('files', {}).get('targets.npz')
                if targets:
                    datasets.append({'location': location, 'manifest': str(path),
                        'manifest_sha256': r.file_hash(path), 'target_file_sha256': targets,
                        'coordinates_sha256': item.get('target_coordinates_sha256'),
                        'contact_label_sha256': item.get('contact_label_sha256'),
                        'partition': item.get('partition'), 'case_id': path.parent.name,
                        'shared_geometry_source_exact': contains_digest(item.get('source_sha256'), geometry_sha),
                        'status': 'label_dependent_conclusions_withheld_pending_full_revalidation'})
            except (ValueError, OSError) as exc:
                errors.append({'path': str(path), 'error': str(exc)})
        for run in sorted((base/'runs').iterdir()):
            if not run.is_dir():
                continue
            # Active G1 checkpoints and outputs are deliberately outside this inventory.
            if run.name.startswith('resume_20261019_geometry_labels_'):
                continue
            for path in sorted((run/'jobs').glob('*/report.json')):
                try:
                    item = r.read(path)
                    outputs = item.get('output_sha256', {})
                    if not isinstance(outputs, dict) or 'target_results.npz' not in outputs:
                        continue
                    jobs.append({'location': location, 'run': run.name, 'job_id': item.get('id', path.parent.name),
                        'report': str(path), 'report_sha256': r.file_hash(path),
                        'target_output_sha256': outputs['target_results.npz'],
                        'input_target_file_sha256': item.get('input_hashes', {}).get('targets.npz'),
                        'coordinates_sha256': item.get('target_coordinates_sha256'),
                        'contact_label_sha256': item.get('contact_label_sha256'),
                        'shared_geometry_source_exact': contains_digest(item.get('source_signature'), geometry_sha),
                        'status': 'metrics_and_selection_withheld_pending_dependency_resolution',
                        'alarm_geometry_not_automatically_invalidated': True})
                except (ValueError, OSError) as exc:
                    errors.append({'path': str(path), 'error': str(exc)})
        for path in sorted((base/'reports').iterdir()):
            if path.is_file():
                report_index.append({'location': location, 'path': str(path), 'sha256': r.file_hash(path),
                    'policy': 'any_label_dependent_claim_subject_to_validity_overlay_not_rewritten'})
    by_targets = {}
    for row in datasets:
        by_targets.setdefault(row['target_file_sha256'], []).append(row['manifest'])
    linked, unresolved = 0, 0
    for row in jobs:
        row['matched_dataset_manifests'] = by_targets.get(row['input_target_file_sha256'], [])
        if row['matched_dataset_manifests']:
            linked += 1
        else:
            unresolved += 1
    fingerprint = {(row['job_id'], row['target_output_sha256']) for row in jobs}
    inventory = {'time': r.now(), 'scope': 'E_and_Z_closed_metadata_no_active_checkpoint',
        'datasets': datasets, 'prediction_job_records': jobs, 'reports': report_index, 'errors': errors,
        'dataset_manifest_records': len(datasets), 'prediction_output_records': len(jobs),
        'distinct_job_id_output_hash_pairs': len(fingerprint),
        'exact_target_hash_linked_records': linked, 'unresolved_input_records': unresolved,
        'record_counts_are_not_experiment_counts': True, 'all_unresolved_dependencies_are_withheld': True}
    overlay = {'time': r.now(), 'priority': 'research_truth_and_reliability_before_completion_counts',
        'user_request': 'Correct every experiment affected by the label issue; scientific truth and reliability first.',
        'evidence_status': 'step_sensitive_edge_and_front_labels_observed_on_new_geometries_not_yet_independently_closed',
        'confirmed_old_dataset_metric_changes': 'not_yet_established_do_not_invent_impact_counts',
        'historical_execution_ledger': {'formal': 2238, 'accepted_diagnostics': 66, 'numeric_records': 2304},
        'historical_acceptance_means': 'frozen_file_and_computational_consistency_not_current_recertified_truth',
        'currently_revalidated_prediction_jobs_under_corrected_truth': 0,
        'claims_withheld': ['RIGHT_recall_and_misses', 'FRONT_exclusion', 'contact_timing_and_lateness',
            'label_conditioned_frame_confusions', 'zero_miss_claims', 'algorithm_rankings',
            '84_configuration_feasibility_conclusions', 'deployment_or_safety_recommendations'],
        'not_automatically_invalidated': ['file_integrity_and_execution_history',
            'label_independent_kinematic_reference_convergence', 'label_independent_observation_array_identity'],
        'raw_predictions_reuse_requires': ['same_online_inputs_and_method', 'same_target_coordinates',
            'no_truth_used_online', 'independent_reconstruction_of_changed_label_dependent_scores'],
        'forbidden_shortcuts': ['exclude_changed_points', 'force_labels_to_agree', 'relax_gates',
            'select_fix_by_method_performance', 'silently_overwrite_old_results', 'equate_reproducibility_with_truth'],
        'remediation_order': ['finish_current_label_diagnostic_and_independent_close',
            'freeze_and_validate_label_definition_and_uncertainty_policy',
            'all_affected_datasets_same_coordinates_full_point_audit',
            'propagate_changes_through_every_job_and_report_or_prove_exact_reuse',
            'independent_end_to_end_acceptance_and_traceable_supersession'],
        'inventory': str(RUN/'impact_inventory.json'), 'inventory_sha256': r.sha(r.encoded(inventory)),
        'any_unrepaired_or_unresolved_result_remains_withheld': True,
        'M2_allowed': False, 'S5_allowed': False, 'deadline': '2026-10-19T08:00:00+08:00',
        'authorization_not_automatically_extended': True}
    lines = ['# 接触标签问题影响登记与结论暂缓使用', '',
        '科研真实性和可靠性优先。共享标签代码已在新增几何中表现出步长敏感；旧数据是否以及多少点受影响尚待逐点核验，不能虚构受影响数字。', '',
        '历史正式2238、诊断66、数值记录2304只保留为历史执行及文件一致性验收记录，不等于这些结果已在修正真值下重新认证。修正真值下重新验收的预测作业目前为0。', '',
        '凡依赖RIGHT、FRONT、接触时间、标签条件帧混淆、零漏报、排名、84配置可行性或安全推荐的结论，均先暂停使用。未解析清楚的依赖同样暂停，不能因缺少哈希连接就视为不受影响。', '',
        f'本次登记E/Z数据集manifest记录{len(datasets)}份、预测输出report记录{len(jobs)}份、报告文件{len(report_index)}份；这些是文件记录数，不是新增实验数。',
        f'预测输出按输入目标文件SHA精确连接{linked}条，待进一步解析{unresolved}条；按作业ID和目标输出SHA去重{len(fingerprint)}组，仍不能直接替代原计数账本。', '',
        '先完成当前标签诊断；再冻结不依据算法性能选择的接触/边界/不确定性定义，覆盖全部受影响数据集原坐标逐点修正。不得删除角点、强制标签一致或放宽门限。',
        '所有受波及作业须重算依赖标签的指标；只有完整证明在线输入、方法、坐标与相关计算不变时，才允许精确复用不受影响的预测部分。不能仅修改汇总数字。',
        '旧文件不覆盖，修正结果建立逐项替代关系。无法在截止前修完的明确列为未修复并持续暂停引用，不以计划或计算次数宣布完成。', '',
        '几何参考收敛、原始观测SHA及真实执行历史并不因标签分类问题自动作废。08:00硬截止未改变；M2/S5不准入。']
    report = ('\n'.join(lines)+'\n').encode('utf-8')
    payloads = [(RUN/'impact_inventory.json', r.encoded(inventory)),
        (RUN/'impact_inventory.json.gz', gzip.compress(r.encoded(inventory), mtime=0)),
        (OVERLAY, r.encoded(overlay)), (RUN/'source/impact_registry.py', Path(__file__).read_bytes()),
        (ROOT/'reports/接触标签问题影响登记与结论暂缓使用_20261019_v1.md', report)]
    active = r.read(ROOT/'active_research_run.json')
    active.update(scientific_validity_overlay=str(OVERLAY), label_dependent_claims_status='withheld_pending_full_remediation',
        corrected_truth_revalidated_prediction_jobs=0, historical_counts_are_not_current_truth_recertification=True,
        primary_objective='correct_all_affected_experiments_before_recommending_any_result')
    r.batch(payloads + [(RUN/'active_with_validity_overlay.json', r.encoded(active))])
    r.mutable(ROOT/'active_research_run.json', active)
    print(json.dumps({k: inventory[k] for k in ('dataset_manifest_records', 'prediction_output_records',
        'distinct_job_id_output_hash_pairs', 'exact_target_hash_linked_records', 'unresolved_input_records')}, ensure_ascii=False))

if __name__ == '__main__':
    build()
