"""Prepare a new complete-bracket edge driver from closed generic orchestration."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
STAGE=HERE/'edge_interval_cover_staging_v1'


def function(text,name,replacement):
    a=text.index('\ndef '+name+'(')+1
    b=text.find('\ndef ',a+1)
    return text[:a]+replacement.strip()+'\n\n'+text[b:]


def main():
    text=(HERE/'suffix_search_staging_v3/suffix_driver.py').read_text(encoding='utf-8')
    text=text.replace('src_s4_unwitnessed_probe_merge_20261022_v1','src_s4_suffix_full_merge_20261022_v1')
    text=text.replace('import probe_merge_driver as parent','import suffix_full_merge_driver as parent')
    text=text.replace('import search_core as core','import edge_cover_core as core')
    text=text.replace('suffix_witness_search','edge_interval_cover').replace('_v3','_v1')
    text=text.replace('resume_plan_20261022_0000_v34','resume_plan_20261022_0000_v38').replace('resume_plan_20261022_0000_v35','resume_plan_20261022_0000_v39')
    text=text.replace('unwitnessed_probe_merge_closed_v1','suffix_full_merge_closed_v1').replace('unwitnessed_probe_merge_first_close_v1','suffix_full_merge_first_close_v1')
    a=text.index('HASHES = {'); b=text.index('\n\n\ndef configure',a)
    hashes={'checkpoint.json':'47a120b10059e406fdd9e29a7d6fb9ef6a46b4c38d61129ce93f78262e0c253d',
        'acceptance.json':'f1f494e65e974e1bad8faf5cbeab44a497f0d8a05e241e67b3e4965891202067',
        'close_receipt.json':'7888837f4b558f1a51c302840d6c151a1ac755aaa1e10edfbd7ec5542f70926d',
        'source_manifest.json':'d80b03d11eca7738a5484c307f4a24d8bfc718c2872706a3f2ec25f70fc29887'}
    text=text[:a]+'HASHES = '+repr(hashes)+text[b:]
    text=function(text,'gate','''
def gate():
    try:
        parent.verify()
        for name,digest in HASHES.items():
            r.require(r.file_hash(PARENT/name)==digest,'Closed v37 dependency changed')
        a=r.read(PARENT/'acceptance.json')
        r.require(a['strict_merged_all_point_prefix_coverage_passed']
            and a['all45714_scope_records_exactly_merged_including_unchanged']
            and a['all_original_scientific_lower_bytes_unchanged']
            and a['accounting']['complete_census_point_file_records']==26878
            and a['accounting']['complete_census_group_unique_points']==22857
            and a['accounting']['combined_status_unknown_point_file_records']==13949
            and a['truth_asset_promotion_allowed'] is False,'Complete accepted v37 population required')
        inventory=r.read(CLOSURE/'all_closed_run_files_sha256.json')
        actual={p.relative_to(PARENT).as_posix():r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.require(actual==inventory and len(actual)==1059,'All1059 stopped closed-parent files required')
        r.require(r.read(AUTH/'runtime_sessions/suffix_full_merge_first_close_v1/exit.json')['actual_wait_exit_code']==0,
            'Actual first-close wait required')
        r.require((SOURCE/'local_motion_core.py').read_bytes()==(ROOT/'src_s4_local_motion_20261022_v2/local_motion_core.py').read_bytes(),
            'Original outward-rounded and independent Decimal70 motion code byte-exact')
    finally:
        configure()
''')
    text=text.replace('AUTH / "runtime_sessions/edge_interval_cover_development_tests_v1/design.json"','CLOSURE / "registration.json"')
    text=text.replace('("merge_", "upper_merge_", "local_motion_", "probe_merge_")','("merge_", "upper_merge_", "local_motion_", "probe_merge_", "suffix_merge_")')
    text=function(text,'summary','''
def summary(original,candidate,trace,retained):
    chosen,found=trace['selected_edge_uncertain'],trace['edge_newly_certified']
    lower=original['contact_lower_s']; upper=original['contact_upper_s']
    return dict(scope_records=len(chosen),selected_uncertain_witnessed_edges=int(chosen.sum()),
        new_edge_certified_candidates=int(found.sum()),remaining_selected_edge_uncertain=int((chosen&~found).sum()),
        unwitnessed_contact_unknown_exactly_retained=int((np.isfinite(lower)&~np.isfinite(upper)).sum()),
        initial_unknown_exactly_retained=int(retained['retained_unknown_metric__initial_origin'].sum()),
        noninitial_time_leaf_unknown_exactly_retained=int(retained['retained_unknown_metric__time_leaf_origin'].sum()),
        known_noncontact_exact_reuse=int((original['contact_status']==0).sum()),
        already_certain_exact_reuse=int((np.isfinite(upper)&original['edge_certain']).sum()),
        interval_geometry_queries=int(trace['query_count'].sum()),cover_budget_exhausted=int(trace['cover_budget_exhausted'].sum()),
        cover_resolution_unresolved=int(trace['cover_resolution_unresolved'].sum()),
        cover_different_stable_code=int(trace['cover_different_stable_code'].sum()),
        scientific_lower_changes=int(np.sum(lower.view(np.uint64)!=candidate['contact_lower_s'].view(np.uint64))),
        scientific_upper_changes=int(np.sum(upper.view(np.uint64)!=candidate['contact_upper_s'].view(np.uint64))))
''')
    text=function(text,'whole_counts','''
def whole_counts(value):
    totals=value['group_path_totals']
    r.require(value['path_blocks']==78 and value['projected_path_files']==114
        and value['scope_group_unique_points']==22857 and value['scope_point_file_records']==26878
        and value['group_point_path_records_not_independent_samples']==45714
        and totals['selected_uncertain_witnessed_edges']==22464
        and totals['unwitnessed_contact_unknown_exactly_retained']==22830
        and totals['scientific_lower_changes']==totals['scientific_upper_changes']==0,'Complete current both-path scope required')
    for tag,unknown,edge in (('oldpath',13949,12929),('independent',13707,12645)):
        row=value['weighted_path_diagnostics'][tag]
        r.require(row['unwitnessed_contact_unknown_exactly_retained']==unknown
            and row['initial_unknown_exactly_retained']+row['noninitial_time_leaf_unknown_exactly_retained']==unknown
            and row['selected_uncertain_witnessed_edges']==edge,'All current unknowns and edge uncertainty required')
''')
    text=text.replace('values["scientific_lower_changes"] == 0','values["scientific_lower_changes"] == values["scientific_upper_changes"] == 0')
    a=text.index('        protocol = {'); b=text.index('\n        plan = {',a)
    protocol='''        protocol = dict(version='full-current-scope-complete-bracket-edge-cover-v1',
            deadline=r.read(AUTH/'authorization.json')['deadline'],parent_merged_assets=str(PARENT),parent_hashes=HASHES,
            scope='all22857 current group-scope points, both45714 path records, all57/114 original-order projections',
            selection='all finite witnessed upper, edge uncertain; retain all unwitnessed/initial/leaf diagnostics',
            tree='original full lower/upper; deterministic chronological midpoint subdivision, at most64 node queries per point',
            leaf_proof='same original nominal code on every covering leaf, full local motion plus original empirical error and1e-12, original1mm corner rule',
            resolution_s=1e-7,maximum_queries=64,scientific_lower_and_upper_and_all_contact_evidence_byte_exact=True,
            budget_resolution_different_code_open_frontier='keep original uncertainty and every field; never a negative or impossibility proof',
            mutable_fields=['edge_certain','possible_edge_codes'],new_budgets_separate_original_budget_masks_exact=True,
            independent_close='all scalar GEOS probes; independent exact tree/frontier/budget/padding replay, full original-segment Decimal70 and all114 projections',
            no_global_physical_identifiability_or_noncontact_or_real_vehicle_certificate=True,
            no_proven_excluded_points_recomputed=True,truth_asset_promotion_allowed=False,corrected_truth_revalidated_prediction_jobs=0,
            all_remaining_unknowns_expanded_populations_controls_scores_still_required=True,
            workers=1,inflight=1,run_cap_bytes=r.RUN_CAP,reservation_bytes=RESERVATION,total_E_Z_cap_bytes=r.CAP,Z_reserve_bytes=r.RESERVE,
            submitted_block='one complete scope path and every original-order projection, drain at cutoff')'''
    text=text[:a]+protocol+text[b:]
    text=text.replace('v34','v38').replace('v35','v39').replace('suffix-witness','edge-interval-cover')
    text=text.replace('bounded suffix strict witness candidates','complete bracket uniform-code edge candidates')
    text=text.replace('full_scope_unwitnessed_probe_candidates_running','full_scope_edge_interval_cover_candidates_running')
    text=text.replace('complete_pending_independent_unwitnessed_probe_close','complete_pending_independent_edge_interval_cover_close')
    text=text.replace('full_scope_supplemental_unwitnessed_witness_candidates_checked_not_merged','full_scope_complete_bracket_edge_cover_candidates_checked_not_merged')
    text=text.replace('strict_new_witnesses_only_no_failed_probe_exclusions_or_scientific_lower_promotions','only_complete_uniform_edge_cover_candidates_no_contact_endpoint_changes')
    text=text.replace('full_scope_unwitnessed_probe_independently_closed_candidates_not_merged','full_scope_edge_interval_cover_independently_closed_candidates_not_merged')
    text=text.replace('fixed_probes_not_exhaustive_or_global_earliest_or_noncontact_proof','complete_original_bracket_cover_only_not_physical_identifiability_or_noncontact_proof')
    text=text.replace('SUFFIX WITNESS SEARCH','EDGE INTERVAL COVER').replace('UNWITNESSED SCALAR GEOS DECIMAL FULL SCOPE','EDGE COVER SCALAR GEOS DECIMAL FULL SCOPE')
    text=text.replace('strict new-witness','uniform bracket edge-certification').replace('strict witnesses','uniform bracket edge certificates')
    text=text.replace('supplemental unwitnessed probes','complete bracket edge cover')
    text=text.replace('every successful/failed 2D probe','every complete tree/frontier')
    compile(text,'edge_cover_driver.py','exec')
    target=STAGE/'edge_cover_driver.py'
    if target.exists(): raise RuntimeError('Preserve staged source version')
    target.write_bytes(text.encode('utf-8'))
    print('EDGE COVER DRIVER CODE STAGED; NOT FROZEN/ADMITTED')


if __name__=='__main__': main()
