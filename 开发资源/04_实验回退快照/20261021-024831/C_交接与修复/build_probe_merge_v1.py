"""Construct a new full merge version; never edits frozen ancestors or invokes old entrypoints."""
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[key]='1'
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src_s4_unwitnessed_probe_20261022_v1'))
import probe_driver as probe
r=probe.r
SOURCE=ROOT/'src_s4_unwitnessed_probe_merge_20261022_v1'
DEV=probe.AUTH/'runtime_sessions/unwitnessed_probe_merge_development_tests_v1'


def replace_def(text,name,replacement):
    start=text.index('\ndef '+name+'(')+1
    end=text.find('\ndef ',start+1)
    if end<0: raise RuntimeError('Expected another function after '+name)
    return text[:start]+replacement.strip()+'\n\n'+text[end:]


def build_driver():
    text=(ROOT/'src_s4_local_motion_merge_20261022_v1/motion_merge_driver.py').read_text(encoding='utf-8')
    text=text.replace('src_s4_local_motion_20261022_v2','src_s4_unwitnessed_probe_20261022_v1')
    text=text.replace('import local_motion_driver as local','import probe_driver as local')
    text=text.replace('local_motion_merge_core_v1','unwitnessed_probe_merge_core_v1').replace('motion_merge_core.py','probe_merge_core.py')
    text=text.replace('resume_20261022_0000_local_motion_merge_v1','resume_20261022_0000_unwitnessed_probe_merge_v1')
    text=text.replace('protocol_local_motion_merge_20261022_0000_v1.json','protocol_unwitnessed_probe_merge_20261022_0000_v1.json')
    text=text.replace('resume_plan_20261022_0000_v28.json','resume_plan_20261022_0000_v32.json').replace('resume_plan_20261022_0000_v29.json','resume_plan_20261022_0000_v33.json')
    text=text.replace('runtime_sessions/local_motion_merge_launch_v1','runtime_sessions/unwitnessed_probe_merge_launch_v1')
    text=text.replace('runtime_sessions/local_motion_v2_closed_v1','runtime_sessions/unwitnessed_probe_closed_v1')
    start=text.index('DEPENDENCIES = '); end=text.index('\nRESERVATION',start)
    text=text[:start]+'''DEPENDENCIES = tuple(dict.fromkeys((local.RUN, PARENT, *local.DEPENDENCIES,
    CLOSURE, AUTH / "runtime_sessions/unwitnessed_probe_first_close_v1")))'''+text[end:]
    start=text.index('HASHES = {'); end=text.index('\n\n\ndef configure',start)
    text=text[:start]+'''HASHES = {
    "checkpoint.json": "4f8a4328819f7960c6ae1dce70d50f1528084022c03b261b207a36aaa11b1dea",
    "acceptance.json": "1a85013fab54e961b711d3835cb20917503bf8385eb39392a1eba36eb2a37e86",
    "close_receipt.json": "fc16b94d2ddd59bcdcee096b998f01752fb42258cd70548db0e6c6e0ae6ac820",
    "source_manifest.json": "8ce32131db3f97bef01158efebf85f91568e289fd158b2797b5105fe771f9d30"}'''+text[end:]
    text=replace_def(text,'gate',r'''
def gate():
    try:
        local.verify()
        for name,digest in HASHES.items():
            r.require(r.file_hash(local.RUN/name)==digest,'Closed probe dependency changed')
        a=r.read(local.RUN/'acceptance.json')
        local.whole_counts(a['accounting'])
        r.require(a['all_original_scientific_lowers_and_complete_prefix_proofs_byte_exact']
            and a['all57_original_order_double_path_full_fields_indices_probe_traces_and_padding_checked']
            and a['strict_new_witnesses_only_no_failed_probe_exclusions_or_scientific_lower_promotions']
            and a['all_no_witness_rows_exactly_unknown_not_negative']
            and a['truth_asset_promotion_allowed'] is False
            and a['accounting']['group_path_totals']['strict_new_witnesses']==2,
            'All accepted supplemental probes and original prefix proofs required')
        receipt=r.read(local.RUN/'close_receipt.json')
        r.require(receipt['acceptance_sha256']==HASHES['acceptance.json']
            and receipt['checkpoint_sha256']==HASHES['checkpoint.json'],'Candidate close receipt differs')
        inventory=r.read(CLOSURE/'all_closed_run_files_sha256.json')
        actual={p.relative_to(local.RUN).as_posix():r.file_hash(p)
            for p in sorted(local.RUN.rglob('*')) if p.is_file()}
        r.require(actual==inventory and len(actual)==789,'Complete independently closed probe files required')
        exit_record=r.read(AUTH/'runtime_sessions/unwitnessed_probe_first_close_v1/exit.json')
        registration=r.read(CLOSURE/'registration.json')
        r.require(exit_record['actual_wait_exit_code']==0 and registration['scientific_close_succeeded']
            and registration['actual_first_close_wait']['actual_wait_exit_code']==0,'Actual first-close wait required')
        r.require(r.read(PARENT/'acceptance.json')['strict_merged_all_point_prefix_coverage_passed'],
            'Complete original lower-prefix coverage required')
    finally:
        configure()
''')
    # The signature retains the full immutable ancestor source list and all new closure evidence.
    text=text.replace('local_motion_merge_development_tests_v*','unwitnessed_probe_merge_development_tests_v*')
    text=replace_def(text,'admit',r'''
def admit():
    try:
        gate()
        loaded,groups,assets,diagnostics=local.admit()
        cp=r.read(local.RUN/'checkpoint.json')
        acceptance=r.read(local.RUN/'acceptance.json')
        candidates,bindings={},{}
        for key,ids in groups.items():
            asset=assets[key]
            scope=asset[0]['all_reason_flags']!=0
            r.require(np.array_equal(core.unpack(asset[0]['all_scope_packbits'],len(scope)),scope),'Parent scope mask differs')
            for tag,time,states,error,vehicle,labels in local.path_iter(key,loaded,groups,asset):
                name=key+'/'+tag
                arrays,meta=base.read_arrays(local.RUN/'paths'/name)
                entry=cp['completed'][name]
                expected_index=np.flatnonzero(scope).astype(np.int64)
                r.require(r.file_hash(local.RUN/'paths'/name/'result.json')==entry['path']['result_sha256']
                    and meta['summary']==entry['path']['summary'],'Accepted path metadata binding differs')
                r.require(core.same(arrays['union_index'],expected_index)
                    and core.same(arrays['xy'],asset[0]['xy'][expected_index]),'All22857 full-scope coordinates required')
                original,candidate=strip(arrays,'original__'),strip(arrays,'candidate__')
                found=arrays['trace__found_strict_witness']
                r.require(set(original)==set(labels),'Every original field required')
                for field,value in labels.items():
                    r.require(core.same(original[field],value[expected_index]),'Original field bytes changed')
                core.merge_path(labels,expected_index,candidate,scope,found)
                check=acceptance['checks'][name]
                r.require(check['new_strict_contact_witnesses']==int(found.sum())
                    and check['selected_unwitnessed_records']==int(arrays['trace__selected_unwitnessed'].sum()),
                    'Full per-path independent probe acceptance must bind')
                for dataset_id in ids:
                    out,rec=local.projection(dataset_id,asset[0],arrays,scalar=True)
                    rec.update(group=key,path=tag)
                    merged.checked_output(local.RUN/'datasets'/tag/dataset_id,out,rec,entry['datasets'][dataset_id])
                candidates[name]=expected_index,candidate,found
                bindings[name]={'scope_records':len(expected_index),'new_strict_witnesses':int(found.sum()),
                    'path_result_sha256':entry['path']['result_sha256'],'accepted_candidate_hashes':HASHES,
                    'original_lower_sha256':base.common.array_hash(original['contact_lower_s']),
                    'complete_original_prefix_exact_reuse_no_geometry':True,
                    'all_successful_failed_2D_probes_original_diagnostics_and114_projections_bound':True}
        r.require(set(candidates)==set(cp['completed'])==set(acceptance['checks'])
            and len(candidates)==78 and len(groups)==39 and len(loaded)==57
            and sum(len(v[0]) for v in candidates.values())==45714
            and sum(int(v[2].sum()) for v in candidates.values())==2,
            'All scope rows, paths and accepted witnesses required')
        return loaded,groups,assets,candidates,bindings
    finally:
        configure()
''')
    # Build/close reuse independent scalar combination, classification and discrepancy implementations.
    text=text.replace('for field in ("contact_lower_s", "contact_upper_s"):', 'for field in ("contact_lower_s",):')
    text=text.replace('("merge_", "upper_merge_")','("merge_", "upper_merge_", "local_motion_")')
    text=text.replace('both_original_scientific_endpoints_all_bytes_exact','all_original_scientific_lowers_and_prefixes_byte_exact')
    text=text.replace('both_original_endpoints_and_original_prefixes_exact','all_original_lowers_and_original_prefixes_exact')
    text=text.replace('local_motion_dependencies','supplemental_probe_dependencies')
    text=text.replace('old_budget_and_upper_provenance_masks_exact_new_local_masks_separate','all_old_provenance_masks_exact_new_probe_merge_masks_separate')
    text=text.replace('both_scientific_endpoints_all_bytes_unchanged','all_original_scientific_lower_bytes_unchanged')
    text=text.replace('all45970_scope_records_exactly_merged_including_unchanged','all45714_scope_records_exactly_merged_including_unchanged')
    text=text.replace('all147_independently_certified_edge_candidates_exactly_merged','all2_independently_accepted_strict_witness_candidates_exactly_merged')
    text=text.replace('both_original_scientific_endpoints_all_bytes_exact','all_original_scientific_lowers_and_prefixes_byte_exact')
    text=text.replace('local_motion','unwitnessed_probe_merge')
    # The blanket presentation rename must not alter the retained provenance prefix.
    text=text.replace('("merge_", "upper_merge_", "unwitnessed_probe_merge_")','("merge_", "upper_merge_", "local_motion_")')
    text=text.replace('20261022-0000-v28','20261022-0000-v32').replace('20261022-0000-v29','20261022-0000-v33')
    text=text.replace('LOCAL MOTION','SUPPLEMENTAL PROBE MERGE').replace('ALL45970','ALL45714')
    text=text.replace('UNCHANGED ENDPOINTS','UNCHANGED SCIENTIFIC LOWERS')
    # Replace protocol/plan construction entirely: the adopted contract permits strict-witness fields only.
    start=text.index('        protocol = {',text.index('def prepare(')); end=text.index('        inventory = ',start)
    text=text[:start]+'''        protocol = {"version":"whole-full-scope-accepted-unwitnessed-probe-merge-v1",
            "deadline":r.read(AUTH/"authorization.json")["deadline"],
            "parent_merged_assets":str(PARENT),"accepted_probes":str(local.RUN),"candidate_hashes":HASHES,
            "selection":"all22857 current scope points, both45714 path rows, not only2 new witnesses",
            "only_mutable_fields_for_independently_accepted_new_witnesses":sorted(core.MUTABLE),
            "all_scientific_lowers_original_prefix_proofs_and_other_provenance_byte_exact":True,
            "every_no_witness_existing_witness_and_noncontact_row_byte_exact":True,
            "full_population":"all39groups/57original-order projections/3360000point-file records",
            "all114_original_order_full_2D_probe_traces_and_unknown_diagnostics_retained_byte_exact":True,
            "independent_close":"scalar full replacement/combine/conflicts/classify/discrepancies/projection/all fields/padding",
            "full_census_recomputed_no_readding_old_valid_or_unknown_counts":True,
            "no_new_geometry_ODE_prediction_or_score_computation":True,
            "truth_asset_promotion_allowed":False,"corrected_truth_revalidated_prediction_jobs":0,
            "not_global_earliest_identifiability_formal_ODE_or_real_vehicle_certificate":True,
            "workers":1,"inflight":1,"run_cap_bytes":r.RUN_CAP,"reservation_bytes":RESERVATION,
            "total_E_Z_cap_bytes":r.CAP,"Z_reserve_bytes":r.RESERVE,
            "submitted_block":"one complete group and all original-order projections/census; drain at cutoff"}
        plan={"version":"20261022-0000-v32-unwitnessed-probe-full-merge",
            "deadline":protocol["deadline"],"authorization":str(AUTH/"authorization.json"),
            "run_directory":str(RUN),"entrypoint":str(Path(__file__)),"protocol":str(PROTOCOL),
            "parent_merged_assets":str(PARENT),"accepted_probes":str(local.RUN),
            "parent_complete_census":r.read(PARENT/"acceptance.json")["accounting"],
            "stage_status":"prepared_not_admitted","scientific_acceptance_exists":False,
            "truth_asset_promotion_allowed":False,"corrected_truth_revalidated_prediction_jobs":0,
            "all_label_dependent_claims_withheld":True,"S4_overall_complete":False,"M2_allowed":False,"S5_allowed":False,
            "ordered_remaining":["full merge all57projections fresh census independent close",
                "all remaining contact/time/edge identifiability and full coarse/fine populations/controls",
                "every affected score/report repair or exact unaffected proof"],
            "next_action":"full input/closed probe admission, all-scope strict-witness merge"}
'''+text[end:]
    # Correct the report: no claims about unchanged upper endpoints or edge-only changes.
    start=text.index('    report = (',text.index('def close(')); end=text.index('    r.batch(',start)
    text=text[:start]+'''    report=("# Supplemental Probe Full Merge and Updated Census\\n\\n"
        "All45714 scope path records, all39 groups, all57 original-order double-path projections and all3360000 point-file records. "
        "Only independently accepted strict new-witness fields may change. Scientific lowers and original prefix proofs, "
        "unwitnessed unknowns, existing witnesses, noncontacts and prior provenance are byte-exact. "
        "All114 full 2D probe trace/diagnostic projections retained byte-exact. "
        "Independent scalar replacement, combination/conflicts/classification/discrepancies/projection/padding checked. "
        "Reasons overlap; this is neither global truth promotion nor complete identifiability, score repair, formal ODE or real-vehicle certification.\\n\\n"
        +str(counts)+"\\n").encode("utf-8")
'''+text[end:]
    # Avoid inheriting obsolete next-stage and proof statements from the edge-only merge.
    text=text.replace('all remaining unwitnessed contact/time/edge identifiability','all remaining contact/time/edge identifiability')
    text=text.replace('Only independently certified edge confidence/set fields change.', 'Only accepted strict-witness fields change.')
    text=text.replace('all57inputs_39groups_all45970_scope_candidates_and114_unknown_diagnostics_bound',
                      'all57inputs_39groups_all45714_scope_candidates_and114_probe_diagnostics_bound')
    compile(text,'probe_merge_driver.py','exec')
    return text


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Version already used or cutoff')
    h,_=probe.execution()
    with h.exclusive() as mutex:
        _,idle=probe.execution()
        stage=HERE/'probe_merge_staging_v1'
        stage.mkdir(exist_ok=False)
        core=(HERE/'probe_merge_core_v1.py').read_bytes()
        tests=(HERE/'test_probe_merge_v1.py').read_bytes()
        driver=build_driver().encode('utf-8')
        for name,blob in (('probe_merge_core.py',core),('test_probe_merge.py',tests),('probe_merge_driver.py',driver)):
            (stage/name).write_bytes(blob)
        result=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        # Preserve every development outcome, including failures, before deciding admission.
        evidence=dict(time=r.now(),execution=idle,mutex=mutex,returncode=result.returncode,
            stdout=result.stdout,stderr=result.stderr,pure_synthetic_only=True,scientific_inputs_not_read_by_tests=True)
        r.batch([(DEV/'development_test.json',r.encoded(evidence)),(DEV/'builder_source.py',Path(__file__).read_bytes())]
            +[(DEV/name,blob) for name,blob in (('probe_merge_core.py',core),('test_probe_merge.py',tests),('probe_merge_driver.py',driver))])
        print(result.stderr,flush=True)
        r.require(result.returncode==0,'Synthetic contract failure; preserve version and do not launch')
        r.batch([(SOURCE/name,blob) for name,blob in (('probe_merge_core.py',core),('test_probe_merge.py',tests),('probe_merge_driver.py',driver))])
    print('NEW FULL PROBE MERGE SOURCE AND SYNTHETIC TESTS FROZEN; prepare/run not yet used',flush=True)


if __name__=='__main__': main()
