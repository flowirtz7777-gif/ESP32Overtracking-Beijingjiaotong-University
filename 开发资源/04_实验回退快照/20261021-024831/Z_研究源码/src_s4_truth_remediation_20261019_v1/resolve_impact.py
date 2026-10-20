"""Add packed populations and exact inherited-input links to the validity registry."""
import gzip
import json
from pathlib import Path
import impact_registry as base

r, ROOT = base.r, base.ROOT
RUN = ROOT/'runs/truth_label_dependency_resolution_20261019_v1'
r.RUN = RUN

def main():
    r.require(not RUN.exists(), 'Resolution already registered')
    first = r.read(ROOT/'runs/truth_label_impact_registry_20261019_v1/impact_inventory.json')
    by_hash = {}
    for row in first['datasets']:
        by_hash.setdefault(row['target_file_sha256'], []).append(row['manifest'])
    records, assets, errors = [], [], []
    for location, root in (('Z', ROOT), ('E', r.helper().ORIGINAL_PLAN.parent)):
        for run in sorted((root/'runs').iterdir()):
            if not run.is_dir() or run.name.startswith('resume_20261019_geometry_labels_'):
                continue
            for path in sorted((run/'jobs').rglob('report.json')):
                try:
                    report = r.read(path)
                    point_outputs = {key: value for key, value in report.get('output_sha256', {}).items()
                                     if key.endswith('.npz') and any(t in key for t in ('target', 'point', 'packed'))}
                    if not point_outputs:
                        continue
                    trace = []
                    hashes = report.get('input_hashes', report.get('common_inputs', {}).get('input_hashes', {}))
                    if not hashes:
                        config = r.read(path.parent/'configuration.json')
                        old_folder = config.get('old_folder')
                        if old_folder:
                            inherited = Path(old_folder)/'report.json'
                            r.require(r.file_hash(inherited) == config['old_report_sha256'], 'Inherited report changed')
                            hashes = r.read(inherited).get('input_hashes', {})
                            trace.append({'path': str(inherited), 'sha256': config['old_report_sha256']})
                    matches = by_hash.get(hashes.get('targets.npz'), [])
                    records.append({'report': str(path), 'report_sha256': r.file_hash(path),
                        'location': location, 'run': run.name, 'job_id': report.get('id', path.parent.name),
                        'point_outputs': point_outputs, 'input_hashes': hashes,
                        'matched_base_dataset_manifests': matches, 'inherited_input_trace': trace,
                        'expanded_population_requires_full_relabel': any('packed' in key for key in point_outputs),
                        'target_manifest_sha256': report.get('target_manifest_sha256', report.get('input_manifest_sha256')),
                        'target_delta_sha256': report.get('target_delta_sha256'),
                        'full_target_count': report.get('full_target_count', report.get('target_count')),
                        'full_target_array_sha256': report.get('full_target_array_sha256'),
                        'scientific_validity': 'withheld_until_full_truth_and_score_revalidation'})
                except (ValueError, OSError, RuntimeError) as exc:
                    errors.append({'path': str(path), 'error': str(exc)})
            for name in ('inputs', 'targets', 'target_cache', 'analysis', 'reports'):
                for path in sorted((run/name).rglob('*.json')):
                    if 'source' not in path.relative_to(run).parts:
                        assets.append({'path': str(path), 'sha256': r.file_hash(path),
                            'status': 'derived_or_referenced_asset_requires_dependency_and_claim_review'})
    linked = sum(bool(x['matched_base_dataset_manifests']) for x in records)
    packed = sum(x['expanded_population_requires_full_relabel'] for x in records)
    result = {'time': r.now(), 'scope': 'metadata_only_including_packed_full_populations',
        'parent_inventory_sha256': r.file_hash(ROOT/'runs/truth_label_impact_registry_20261019_v1/impact_inventory.json'),
        'prediction_output_records': records, 'closed_derived_asset_records': assets, 'errors': errors,
        'output_record_count': len(records), 'exact_or_inherited_input_linked_records': linked,
        'unresolved_records': len(records)-linked, 'packed_population_records': packed,
        'counts_are_file_records_not_experiments': True,
        'base_input_link_does_not_certify_expanded_target_labels': True,
        'completed_corrected_predictions': 0}
    overlay = r.read(ROOT/'research_validity_overlay_20261019_v1.json')
    overlay.update(time=r.now(), previous_overlay='research_validity_overlay_20261019_v1.json',
        dependency_resolution=str(RUN/'dependency_resolution.json'),
        dependency_resolution_sha256=r.sha(r.encoded(result)),
        all_packed_expanded_populations_explicitly_in_scope=True,
        any_reused_original_labels_or_projection_only_validation_insufficient=True)
    report = ('# 接触标签影响范围补充：完整细总体与继承输入\n\n'
        f'本次登记{len(records)}条E/Z预测输出文件记录，其中{packed}条含packed扩展总体输出。'
        f'原始或继承输入目标SHA连接{linked}条，未解析{len(records)-linked}条。'
        '这些不是新增实验数，也不证明已经修正任何一个结果。\n\n'
        '范围包括原主集、密度扩展、完整粗/细RIGHT总体、两交叉格、反例与由它们生成的比较、交互和排名。'
        '仅复核原7万点投影或基线标签不能解除完整数百万点总体的待复核状态。'
        '标签改变可能同时影响评分支持窗口、FRONT排除、帧混淆及首次有效报警，不能只改RIGHT汇总。\n\n'
        '所有尚未逐点修正或证明不受影响的依赖结论继续暂停引用。旧报告保持原样，必须连同有效性overlay阅读。\n').encode('utf-8')
    r.batch([(RUN/'dependency_resolution.json', r.encoded(result)),
        (RUN/'dependency_resolution.json.gz', gzip.compress(r.encoded(result), mtime=0)),
        (RUN/'source/resolve_impact.py', Path(__file__).read_bytes()),
        (ROOT/'research_validity_overlay_20261019_v2.json', r.encoded(overlay)),
        (ROOT/'reports/接触标签影响范围补充与继承输入核定_20261019_v1.md', report)])
    active = r.read(ROOT/'active_research_run.json')
    active['scientific_validity_overlay'] = str(ROOT/'research_validity_overlay_20261019_v2.json')
    r.mutable(ROOT/'active_research_run.json', active)
    print(json.dumps({k:result[k] for k in ('output_record_count','exact_or_inherited_input_linked_records',
        'unresolved_records','packed_population_records')}))

if __name__ == '__main__':
    main()
