"""Pure manifest/group checks for future training; no research file reads or model fitting."""
import re

GATES=('truth_domain_independently_accepted','all_affected_populations_accounted',
    'all_affected_scores_repaired_or_exact_reuse_proved','raw_counts_preserved',
    'selection_preregistered_not_performance_based','training_protocol_frozen',
    'feature_schema_preregistered','final_test_locked','single_worker_idle_proved',
    'fresh_resources_admitted','environment_frozen')
HASHES=('truth_receipt_sha256','corrected_score_receipt_sha256','population_coverage_sha256',
    'selection_protocol_sha256','training_protocol_sha256','split_manifest_sha256','source_manifest_sha256')
FORBIDDEN={'job_id','case_id','trajectory_id','seed','true_contact_time_s','contact_lower_s',
    'contact_upper_s','first_alarm_s','right_pct','right_miss','right_late','right_no_before',
    'future_alpha','future_phi','truth_phase','score','tp','fp','tn','fn'}


def validate(manifest,rows):
    for gate in GATES:
        if manifest.get(gate) is not True: raise ValueError('Admission gate not explicitly passed: '+gate)
    for key in HASHES:
        if not isinstance(manifest.get(key),str) or not re.fullmatch('[0-9a-f]{64}',manifest[key]):
            raise ValueError('Missing exact evidence hash: '+key)
    counts=manifest.get('counts',{})
    keys=('raw_rows','eligible_training_rows','unknown_rows_retained','outside_domain_rows_retained','unknown_or_conflicted_training_rows')
    if any(type(counts.get(k)) is not int or counts[k]<0 for k in keys): raise ValueError('Complete nonnegative integer counts required')
    if counts['unknown_or_conflicted_training_rows']!=0: raise ValueError('Unknown/conflicted targets cannot enter training')
    if counts['raw_rows']!=sum(counts[k] for k in keys[1:4]): raise ValueError('Original population accounting must conserve rows')
    features=manifest.get('features',[])
    allowed=manifest.get('preregistered_features',[])
    if not features or len(set(features))!=len(features) or set(features)!=set(allowed): raise ValueError('Exact nonempty preregistered feature whitelist required')
    if any(f in FORBIDDEN or f.startswith(('truth_','future_','score_')) for f in features): raise ValueError('Future/target/identifier feature leakage')
    if len(rows)!=counts['eligible_training_rows']: raise ValueError('Every eligible training row must appear exactly once')
    by_group={}
    by_lineage={}
    seen=set()
    for row in rows:
        if not isinstance(row.get('row_id'),str) or row['row_id'] in seen: raise ValueError('Unique raw row provenance ID required')
        seen.add(row['row_id'])
        group,lineage,partition=row.get('group'),row.get('lineage'),row.get('partition')
        if not isinstance(group,str) or not group or not isinstance(lineage,str) or not lineage: raise ValueError('Whole-trajectory and lineage grouping required')
        if partition not in ('train','validation'): raise ValueError('Final/unknown data must not be part of training table')
        if group in by_group and by_group[group]!=partition: raise ValueError('Trajectory group crosses train/validation')
        by_group[group]=partition
        if lineage in by_lineage and by_lineage[lineage]!=(group,partition): raise ValueError('Same-origin variants split across groups or partitions')
        by_lineage[lineage]=(group,partition)
        if row.get('target_known') is not True: raise ValueError('Every training target requires accepted known status')
    if not {'train','validation'}<=set(by_group.values()): raise ValueError('At least one entire held-out validation group required')
    return {'eligible_rows':len(rows),'groups':len(by_group),'lineages':len(by_lineage),
        'pure_manifest_check_only_not_scientific_admission':True}
