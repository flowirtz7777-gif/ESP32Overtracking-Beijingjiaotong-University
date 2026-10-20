"""Construct the administrative sequential lifecycle for the new candidate version."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
destination=HERE/'suffix_search_lifecycle_manager_v3.py'
if destination.exists(): raise RuntimeError('Manager version already exists')
text=(HERE/'probe_merge_lifecycle_manager_v1.py').read_text(encoding='utf-8')
text=text.replace('src_s4_unwitnessed_probe_merge_20261022_v1','src_s4_suffix_witness_search_20261022_v3')
text=text.replace('import probe_merge_driver as d','import suffix_driver as d')
text=text.replace('unwitnessed_probe_merge_lifecycle_v1','suffix_witness_search_lifecycle_v3')
text=text.replace('unwitnessed_probe_merge_closed_v1','suffix_witness_search_closed_v3')
text=text.replace('unwitnessed_probe_merge_first_close_v1','suffix_witness_search_first_close_v3')
text=text.replace('complete_pending_independent_unwitnessed_probe_merge_merge_close','complete_pending_independent_unwitnessed_probe_close')
text=text.replace("len(cp['completed'])==39","len(cp['completed'])==78")
old="""    r.require(a['accounting']['dataset_files']==57 and a['accounting']['geometry_groups']==39
        and a['accounting']['point_file_records']==3360000,'Complete census required')"""
if text.count(old)!=1: raise RuntimeError('Expected census guard differs')
text=text.replace(old,"    d.whole_counts(a['accounting'])")
text=text.replace('COMPLETE FULL PROBE MERGE SCIENTIFIC CLOSE AND REGISTRATION',
    'COMPLETE BOUNDED SUFFIX CANDIDATE SCIENTIFIC CLOSE AND REGISTRATION; NEW MERGE STILL REQUIRED')
text=text.replace('all_remaining_unknowns_full_coarse_fine_populations_controls_affected_scores_still_required=True',
    'full_current_scope_merge_all57projections_and_fresh_census_still_required=True,\n'
    '        all_remaining_unknowns_full_coarse_fine_populations_controls_affected_scores_still_required=True')
compile(text,str(destination),'exec')
destination.write_text(text,encoding='utf-8')
print(destination)
