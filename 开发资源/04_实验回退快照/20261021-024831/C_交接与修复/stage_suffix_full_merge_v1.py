"""Code/synthetic preparation only while suffix candidate close runs; no research file reads."""
import json
import subprocess
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
STAGE=HERE/'suffix_full_merge_staging_v1'


def replace_function(text,name,replacement):
    start=text.index('\ndef '+name+'(')+1
    end=text.find('\ndef ',start+1)
    if end<0: end=len(text)
    return text[:start]+replacement.strip()+'\n\n'+text[end:]


def core_source():
    text=(HERE/'probe_merge_core_v1.py').read_text(encoding='utf-8')
    text=text.replace("'probe_merge_')","'probe_merge_', 'suffix_merge_')")
    text=text.replace("out['probe_merge_' + kind", "out['suffix_merge_' + kind")
    compile(text,'suffix_merge_core.py','exec')
    return text.encode('utf-8')


def driver_template():
    text=(HERE/'probe_merge_staging_tests_v2/probe_merge_driver.py').read_text(encoding='utf-8')
    text=text.replace('src_s4_unwitnessed_probe_20261022_v1','src_s4_suffix_witness_search_20261022_v3')
    text=text.replace('import probe_driver as local','import suffix_driver as local')
    text=text.replace('unwitnessed_probe_merge_core_v1','suffix_full_merge_core_v1').replace('probe_merge_core.py','suffix_merge_core.py')
    text=text.replace('resume_20261022_0000_unwitnessed_probe_merge_v1','resume_20261022_0000_suffix_full_merge_v1')
    text=text.replace('protocol_unwitnessed_probe_merge_20261022_0000_v1.json','protocol_suffix_full_merge_20261022_0000_v1.json')
    text=text.replace('resume_plan_20261022_0000_v32.json','resume_plan_20261022_0000_v36.json').replace('resume_plan_20261022_0000_v33.json','resume_plan_20261022_0000_v37.json')
    text=text.replace('runtime_sessions/unwitnessed_probe_merge_launch_v1','runtime_sessions/suffix_full_merge_launch_v1')
    text=text.replace('runtime_sessions/unwitnessed_probe_closed_v1','runtime_sessions/suffix_witness_search_closed_v3')
    text=text.replace('runtime_sessions/unwitnessed_probe_first_close_v1','runtime_sessions/suffix_witness_search_first_close_v3')
    text=text.replace('RESERVATION = 896 * 1024**2','RESERVATION = 3584 * 1024**2')
    text=text.replace('r.RUN, r.RUN_CAP = RUN, 1024**3','r.RUN, r.RUN_CAP = RUN, 4 * 1024**3')
    start=text.index('HASHES = {'); end=text.index('\n\n\ndef configure',start)
    text=text[:start]+'HASHES = {}  # BIND_ACCEPTED_SUFFIX_HASHES_BEFORE_FREEZING\n'+text[end:]
    gate=r'''
def gate():
    try:
        local.verify()
        r.require(set(HASHES)=={'checkpoint.json','acceptance.json','close_receipt.json','source_manifest.json'},
            'Actual accepted suffix hashes must be frozen before any real work')
        for name,digest in HASHES.items():
            r.require(r.file_hash(local.RUN/name)==digest,'Closed suffix dependency changed')
        a=r.read(local.RUN/'acceptance.json')
        local.whole_counts(a['accounting'])
        r.require(a['all_original_scientific_lowers_and_complete_prefix_proofs_byte_exact']
            and a['all57_original_order_double_path_full_fields_indices_probe_traces_and_padding_checked']
            and a['strict_new_witnesses_only_no_failed_probe_exclusions_or_scientific_lower_promotions']
            and a['all_no_witness_rows_exactly_unknown_not_negative']
            and all(v['complete_suffix_control_budget_and_frontier_checked'] for v in a['checks'].values())
            and a['truth_asset_promotion_allowed'] is False,'Complete independent bounded suffix candidate close required')
        receipt=r.read(local.RUN/'close_receipt.json')
        r.require(receipt['acceptance_sha256']==HASHES['acceptance.json']
            and receipt['checkpoint_sha256']==HASHES['checkpoint.json'],'Candidate close receipt differs')
        inventory=r.read(CLOSURE/'all_closed_run_files_sha256.json')
        actual={p.relative_to(local.RUN).as_posix():r.file_hash(p) for p in sorted(local.RUN.rglob('*')) if p.is_file()}
        registration=r.read(CLOSURE/'registration.json')
        r.require(actual==inventory and len(actual)==registration['all_closed_file_count'],
            'Every closed suffix candidate file required')
        r.require(r.read(AUTH/'runtime_sessions/suffix_witness_search_first_close_v3/exit.json')['actual_wait_exit_code']==0
            and registration['scientific_close_succeeded'],'Actual first-close wait and stopped signature registration required')
        r.require(r.read(PARENT/'acceptance.json')['strict_merged_all_point_prefix_coverage_passed'],
            'Complete current accepted lower-prefix coverage required')
    finally:
        configure()
'''
    text=replace_function(text,'gate',gate)
    text=text.replace('unwitnessed_probe_merge_development_tests_v*','suffix_full_merge_development_tests_v*')
    text=text.replace("and sum(int(v[2].sum()) for v in candidates.values())==2,",
        "and sum(int(v[2].sum()) for v in candidates.values())==acceptance['accounting']['group_path_totals']['strict_new_witnesses'],")
    text=text.replace('("merge_", "upper_merge_", "local_motion_")','("merge_", "upper_merge_", "local_motion_", "probe_merge_")')
    text=text.replace('all2_independently_accepted_strict_witness_candidates_exactly_merged',
        'all_independently_accepted_suffix_strict_witness_candidates_exactly_merged')
    text=text.replace('unwitnessed_probe_merge_full_merge_updated_census_20261022_0000_v1.md',
        'suffix_full_merge_updated_census_20261022_0000_v1.md')
    text=text.replace('20261022-0000-v32','20261022-0000-v36').replace('20261022-0000-v33','20261022-0000-v37')
    text=text.replace('Supplemental Probe Full Merge','Bounded Suffix Candidate Full Merge')
    text=text.replace('supplemental_probe_dependencies','bounded_suffix_dependencies')
    text=text.replace('SUPPLEMENTAL PROBE MERGE','BOUNDED SUFFIX FULL MERGE')
    text=text.replace('whole-full-scope-accepted-unwitnessed-probe-merge-v1','whole-full-scope-accepted-bounded-suffix-merge-v1')
    text=text.replace('not only2 new witnesses','not only changed or successful rows')
    text=text.replace('all_old_provenance_masks_exact_new_probe_merge_masks_separate',
        'all_old_provenance_masks_exact_new_suffix_merge_masks_separate')
    compile(text,'suffix_full_merge_driver.py','exec')
    return text.encode('utf-8')


def main():
    if STAGE.exists(): raise RuntimeError('Staging version already exists')
    STAGE.mkdir()
    tests=(HERE/'probe_merge_staging_tests_v2/test_probe_merge.py').read_text(encoding='utf-8')
    tests=tests.replace('import probe_merge_core as c','import suffix_merge_core as c')
    tests=tests.replace("out['probe_merge_changed_oldpath__packbits']","out['suffix_merge_changed_oldpath__packbits']")
    tests=tests.replace("'local_motion_changed_oldpath__packbits':np.array([4],np.uint8)}",
        "'local_motion_changed_oldpath__packbits':np.array([4],np.uint8),\n"
        "                  'probe_merge_changed_oldpath__packbits':np.array([4],np.uint8)}")
    tests=tests.replace("self.assertEqual(c.unpack(out['suffix_merge_changed_oldpath__packbits'],5).tolist(),[1,0,0,0,0])",
        "self.assertEqual(c.unpack(out['suffix_merge_changed_oldpath__packbits'],5).tolist(),[1,0,0,0,0])\n"
        "        self.assertTrue(c.same(out['probe_merge_changed_oldpath__packbits'],original['probe_merge_changed_oldpath__packbits']))")
    for name,blob in (('suffix_merge_core.py',core_source()),('suffix_full_merge_driver.template.py',driver_template()),
                      ('test_suffix_merge.py',tests.encode('utf-8'))):
        (STAGE/name).write_bytes(blob)
    result=subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s',str(STAGE),'-p','test_*.py','-v'],
        cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
    (STAGE/'synthetic_result.json').write_text(json.dumps(dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,
        code_and_synthetic_only=True,no_research_data_read=True,no_hashes_bound_or_real_prepare_run=True),ensure_ascii=False,indent=2),encoding='utf-8')
    print(result.stderr,flush=True)
    if result.returncode: raise RuntimeError('Staged synthetic tests failed; no real entrypoints')
    print('NEXT FULL MERGE CODE STAGED; ACCEPTED HASHES/INTEGRATION/FREEZING STILL REQUIRED AFTER CURRENT CLOSE',flush=True)


if __name__=='__main__': main()
