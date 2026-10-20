"""Metadata lineage only. No corrected labels, scores or independent experiments."""
import hashlib
import io
import json
from pathlib import PureWindowsPath
import zipfile


def digest(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def descriptor(path,sha,value):
    if not digest(sha): raise ValueError('Signed JSON descriptor required')
    kind=type(value).__name__
    if not isinstance(value,dict):
        return dict(path=path,sha256=sha,json_kind=kind,
            declared_counts_not_verified_array_lengths={},declared_array_hashes_not_repaired_labels={},
            declared_file_hashes={},field_names=[],scientific_truth_accepted=False)
    counts={k:v for k,v in value.items() if isinstance(v,int) and not isinstance(v,bool)
        and any(t in k for t in ('count','records','chunks'))}
    arrays={k:v for k,v in value.items() if k.endswith('_sha256') and isinstance(v,dict)
        and all(isinstance(a,str) and digest(b) for a,b in v.items()) and k!='source_signature'}
    files={k:v for k,v in value.items() if k.endswith('_sha256') and digest(v)}
    return dict(path=path,sha256=sha,json_kind=kind,declared_counts_not_verified_array_lengths=counts,
        declared_array_hashes_not_repaired_labels=arrays,declared_file_hashes=files,
        declared_case_id=value.get('case_id',value.get('id')),declared_contact_tolerance_m=value.get('contact_tolerance_m'),
        field_names=sorted(value),scientific_truth_accepted=False)


def index_descriptors(values):
    by_manifest={}; by_xy={}; by_file={}
    for row in values:
        by_manifest.setdefault(row['sha256'],[]).append(row['path'])
        for key,fields in row['declared_array_hashes_not_repaired_labels'].items():
            if 'xy' in fields:
                by_xy.setdefault(fields['xy'],[]).append(dict(path=row['path'],field=key+'.xy',sha256=row['sha256']))
        for key,sha in row['declared_file_hashes'].items():
            by_file.setdefault(sha,[]).append(dict(path=row['path'],field=key,sha256=row['sha256']))
    return by_manifest,by_xy,by_file


def record(number,registered,report,configuration,indices):
    manifest,xy_index,file_index=indices
    points=registered['point_outputs']
    if not points or any(not digest(v) for v in points.values()): raise ValueError('Every signed point output required')
    if any(report.get('output_sha256',{}).get(k)!=v for k,v in points.items()):
        raise ValueError('Frozen registry/output binding differs')
    full=report.get('full_target_array_sha256',{})
    xy=full.get('xy') if isinstance(full,dict) else None
    if xy is not None and not digest(xy): raise ValueError('Explicit full coordinate digest is malformed')
    links=[]
    for key,sha in report.items():
        if key.endswith('_sha256') and digest(sha):
            if sha in manifest: links.extend(dict(report_field=key,descriptor_path=p,kind='exact_descriptor_file_sha') for p in manifest[sha])
            if sha in file_index: links.extend(dict(report_field=key,descriptor=v,kind='declared_referenced_file_sha') for v in file_index[sha])
    coordinate_links=xy_index.get(xy,[]) if xy else []
    full_links=[v for v in coordinate_links if v['field']=='full_target_array_sha256.xy']
    expanded=registered['expanded_population_requires_full_relabel']
    count=report.get('full_target_count',report.get('target_count'))
    if count is not None and (not isinstance(count,int) or isinstance(count,bool) or count<0):
        raise ValueError('Declared count must be a nonnegative integer or absent')
    return dict(registry_index=number,report=registered['report'],report_sha256=registered['report_sha256'],
        location=registered['location'],run=registered['run'],job_id=registered['job_id'],
        verified_point_output_file_sha256=points,input_hashes=registered['input_hashes'],
        inherited_input_trace=registered['inherited_input_trace'],matched_base_dataset_manifests=registered['matched_base_dataset_manifests'],
        configuration_case=configuration.get('case_id'),configuration_stage=configuration.get('stage'),
        configuration_partition=configuration.get('partition'),configuration_contact_tolerance_m=configuration.get('contact_tolerance_m'),
        requires_complete_expanded_population=expanded,declared_target_count_not_array_verified=count,
        declared_full_coordinate_sha256=xy,exact_declared_full_coordinate_descriptor_links=full_links,
        all_declared_coordinate_links=coordinate_links,descriptor_file_links=links,
        expanded_full_coordinate_descriptor_link_resolved=bool(xy and full_links) if expanded else None,
        input_reconstruction_still_required=True,corrected_labels_accepted=False,
        corrected_scores_accepted=False,raw_online_predictions_reuse_proven=False,
        uncertainty_policy='preserve every unknown/conflict; no unknown treated as negative',
        status='lineage_and_frozen_files_verified_not_truth_or_score_revalidation')


def summarize(rows):
    if len({v['registry_index'] for v in rows})!=len(rows): raise ValueError('Registry rows duplicated')
    return dict(output_file_records_not_experiments=len(rows),
        packed_expanded_population_records=sum(v['requires_complete_expanded_population'] for v in rows),
        packed_full_coordinate_descriptor_links_resolved=sum(v['expanded_full_coordinate_descriptor_link_resolved'] is True for v in rows),
        packed_full_coordinate_descriptor_links_unresolved=sum(v['expanded_full_coordinate_descriptor_link_resolved'] is False for v in rows),
        corrected_labels_accepted=0,corrected_prediction_scores_accepted=0,raw_prediction_reuse_proven=0)


def source_bundle(blobs):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as target:
        for name,blob in sorted(blobs.items()):
            if name.startswith('/') or '..' in name.split('/') or ':' in name: raise ValueError('Relative immutable source name required')
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            target.writestr(info,blob)
    data=stream.getvalue()
    verify_bundle(data,{k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()})
    return data


def verify_bundle(blob,signature):
    with zipfile.ZipFile(io.BytesIO(blob)) as source:
        if len(source.namelist())!=len(signature) or set(source.namelist())!=set(signature): raise ValueError('Whole source snapshot required')
        for name,sha in signature.items():
            if hashlib.sha256(source.read(name)).hexdigest()!=sha: raise ValueError('Frozen source snapshot bytes differ')
