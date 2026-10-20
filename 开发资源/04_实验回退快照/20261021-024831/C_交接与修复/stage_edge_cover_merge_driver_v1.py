"""Code-only full merge template; accepted candidate hashes intentionally unbound."""
from pathlib import Path
import stage_suffix_full_merge_v1 as helper
HERE=Path(__file__).resolve().parent
STAGE=HERE/'edge_cover_merge_staging_v1'


def main():
    text=(HERE/'suffix_full_merge_final_staging_v1/suffix_full_merge_driver.py').read_text(encoding='utf-8')
    text=text.replace('src_s4_suffix_witness_search_20261022_v3','src_s4_edge_interval_cover_20261022_v2')
    text=text.replace('import suffix_driver as local','import edge_cover_driver as local')
    text=text.replace('suffix_full_merge_core_v1','edge_cover_merge_core_v1').replace('suffix_merge_core.py','edge_merge_core.py')
    text=text.replace('resume_20261022_0000_suffix_full_merge_v1','resume_20261022_0000_edge_cover_merge_v1')
    text=text.replace('protocol_suffix_full_merge_20261022_0000_v1','protocol_edge_cover_merge_20261022_0000_v1')
    text=text.replace('resume_plan_20261022_0000_v36','resume_plan_20261022_0000_v40').replace('resume_plan_20261022_0000_v37','resume_plan_20261022_0000_v41')
    text=text.replace('runtime_sessions/suffix_full_merge_launch_v1','runtime_sessions/edge_cover_merge_launch_v1')
    text=text.replace('runtime_sessions/suffix_witness_search_closed_v3','runtime_sessions/edge_interval_cover_closed_v2')
    text=text.replace('runtime_sessions/suffix_witness_search_first_close_v3','runtime_sessions/edge_interval_cover_first_close_v2')
    a=text.index('HASHES = '); b=text.index('\n\n\ndef configure',a)
    text=text[:a]+'HASHES = {}  # BIND_ACCEPTED_EDGE_COVER_HASHES_BEFORE_FREEZING'+text[b:]
    text=text.replace('suffix_full_merge_development_tests_v*','edge_cover_merge_development_tests_v*')
    text=text.replace('complete_suffix_control_budget_and_frontier_checked','complete_interval_cover_tree_frontier_budget_padding_checked')
    text=text.replace('strict_new_witnesses_only_no_failed_probe_exclusions_or_scientific_lower_promotions',
        'only_complete_uniform_edge_cover_candidates_no_contact_endpoint_changes')
    text=text.replace('trace__found_strict_witness','trace__edge_newly_certified').replace('trace__selected_unwitnessed','trace__selected_edge_uncertain')
    text=text.replace("check['new_strict_contact_witnesses']","check['newly_certified_edge_candidates']")
    text=text.replace("check['selected_unwitnessed_records']==int(arrays['trace__selected_edge_uncertain'].sum())", "check['records']==len(expected_index)")
    text=text.replace("['group_path_totals']['strict_new_witnesses']","['group_path_totals']['new_edge_certified_candidates']")
    text=text.replace('("merge_", "upper_merge_", "local_motion_", "probe_merge_")','("merge_", "upper_merge_", "local_motion_", "probe_merge_", "suffix_merge_")')
    text=text.replace('new_strict_witnesses','new_edge_certificates').replace('strict new-witness','complete uniform edge-cover')
    text=text.replace('new_suffix_merge_masks','new_edge_cover_merge_masks').replace('suffix_full_merge_updated_census','edge_cover_merge_updated_census')
    text=text.replace('all_independently_accepted_suffix_strict_witness_candidates_exactly_merged','all_independently_accepted_complete_bracket_edge_candidates_exactly_merged')
    text=text.replace('bounded_suffix_dependencies','complete_edge_cover_dependencies')
    text=text.replace('whole-full-scope-accepted-bounded-suffix-merge-v1','whole-full-scope-accepted-complete-bracket-edge-merge-v1')
    text=text.replace('20261022-0000-v36','20261022-0000-v40').replace('20261022-0000-v37','20261022-0000-v41')
    text=text.replace('BOUNDED SUFFIX FULL MERGE','EDGE COVER MERGE')
    text=text.replace('complete_pending_independent_suffix_full_merge_merge_close','complete_pending_independent_edge_cover_merge_close')
    text=text.replace('suffix_full_merge_full_scope_merge','edge_cover_merge_full_scope_merge')
    text=text.replace('Bounded Suffix Candidate Full Merge','Complete Bracket Edge Candidate Full Merge')
    text=text.replace('all2D_probe','all3D_cover').replace('all_successful_failed_2D_probes','complete_cover_tree_frontier')
    text=text.replace('All114 full 2D probe trace/diagnostic projections','All114 full 3D face and complete tree/frontier diagnostic projections')
    text=text.replace('scientific lowers','scientific lower and upper endpoints')
    compile(text,'edge_cover_merge_driver.py','exec')
    target=STAGE/'edge_cover_merge_driver.template.py'
    if target.exists(): raise RuntimeError('Preserve prepared version')
    target.write_bytes(text.encode('utf-8'))
    print('EDGE COVER FULL MERGE DRIVER TEMPLATE STAGED; NO ACCEPTED HASHES/DATA/SCIENCE ENTRYPOINTS')


if __name__=='__main__': main()
