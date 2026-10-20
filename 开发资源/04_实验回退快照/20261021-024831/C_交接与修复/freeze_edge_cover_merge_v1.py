"""Rehash accepted cover candidate, finalize tested full-population merge and freeze."""
import os
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[key]='1'
HERE=Path(__file__).resolve().parent
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_edge_interval_cover_20261022_v2'))
import edge_cover_driver as d
r=d.r
SOURCE=ROOT/'src_s4_edge_cover_merge_20261022_v1'
DEV=d.AUTH/'runtime_sessions/edge_cover_merge_development_tests_v1'
CLOSED=d.AUTH/'runtime_sessions/edge_interval_cover_closed_v2'


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Version used or cutoff')
    h,_=d.execution()
    with h.exclusive() as mutex:
        _,idle=d.execution()
        d.verify()
        reg=r.read(CLOSED/'registration.json')
        r.require(reg['scientific_close_succeeded']
            and reg['actual_first_close_wait']['actual_wait_exit_code']==0
            and reg['actual_worker_wait']['actual_wait_exit_code']==0,'Actual waits required')
        actual={p.relative_to(d.RUN).as_posix():r.file_hash(p) for p in sorted(d.RUN.rglob('*')) if p.is_file()}
        r.require(actual==r.read(CLOSED/'all_closed_run_files_sha256.json') and len(actual)==reg['all_closed_file_count']==912,
            'Complete current closed candidate file set required')
        hashes={k:actual[k] for k in ('checkpoint.json','acceptance.json','close_receipt.json','source_manifest.json')}
        receipt=r.read(d.RUN/'close_receipt.json')
        r.require(receipt['acceptance_sha256']==hashes['acceptance.json'] and receipt['checkpoint_sha256']==hashes['checkpoint.json'],
            'Receipt binding differs')
        d.whole_counts(r.read(d.RUN/'acceptance.json')['accounting'])
        stage=HERE/'edge_cover_merge_staging_v1'
        text=(stage/'edge_cover_merge_driver.template.py').read_text(encoding='utf-8')
        marker='HASHES = {}  # BIND_ACCEPTED_EDGE_COVER_HASHES_BEFORE_FREEZING'
        r.require(text.count(marker)==1,'Template hash marker differs')
        text=text.replace(marker,'HASHES = '+repr(hashes))
        text=text.replace('bounded-suffix','complete-edge-cover').replace('bounded suffix','complete edge cover')
        text=text.replace('accepted suffix hashes','accepted edge cover hashes').replace('Closed suffix dependency','Closed edge cover dependency')
        text=text.replace('closed suffix candidate','closed edge cover candidate')
        text=text.replace('for field in ("contact_lower_s",):','for field in ("contact_lower_s", "contact_upper_s"):')
        text=text.replace('"only_mutable_fields_for_independently_accepted_new_witnesses"','"only_mutable_fields_for_independently_accepted_edge_covers"')
        text=text.replace('"every_no_witness_existing_witness_and_noncontact_row_byte_exact":True',
            '"every_uncertified_unknown_or_witnessed_or_noncontact_row_byte_exact":True,\n            "every_original_scientific_lower_upper_status_nominal_and_provenance_byte_exact":True')
        text=text.replace('Only independently accepted complete uniform edge-cover fields may change.',
            'Only edge_certain/possible_edge_codes for independently accepted complete uniform-code covers may change.')
        text=text.replace('unwitnessed unknowns, existing witnesses, noncontacts and prior provenance are byte-exact.',
            'All contact evidence, lower/upper endpoints and prior provenance are byte-exact; uncertified rows retain every field.')
        text=text.replace('suffix_full_merge_full_merge_running','edge_cover_merge_full_merge_running')
        text=text.replace('full_scope_suffix_full_merge_merge_all57projections_and_census_closed_not_global_truth',
            'full_scope_edge_cover_merge_all57projections_and_census_closed_not_global_truth')
        text=text.replace('all-scope strict-witness merge','all-scope uniform-code edge-cover merge')
        text=text.replace('"all_original_scientific_lower_bytes_unchanged": True,',
            '"all_original_scientific_lower_bytes_unchanged": True,\n                "all_original_scientific_lower_and_upper_bytes_unchanged": True,')
        text=text.replace("all(v['complete_interval_cover_tree_frontier_budget_padding_checked'] for v in a['checks'].values())",
            "all(v['complete_interval_cover_tree_frontier_budget_padding_checked'] and v['scientific_endpoints_and_original_prefixes_unchanged'] for v in a['checks'].values())")
        compile(text,'edge_cover_merge_driver.py','exec')
        blobs={'edge_cover_merge_driver.py':text.encode('utf-8'),
            'edge_merge_core.py':(stage/'edge_merge_core.py').read_bytes(),
            'test_edge_merge.py':(stage/'test_edge_merge.py').read_bytes()}
        tests=(HERE/'suffix_full_merge_staging_v1/test_suffix_full_merge_driver.py').read_text(encoding='utf-8')
        tests=tests.replace('import suffix_merge_core as core','import edge_merge_core as core').replace('from test_suffix_merge import fixture','from test_edge_merge import fixture')
        tests=tests.replace("ModuleType('suffix_driver')","ModuleType('edge_cover_driver')")
        tests=tests.replace("{'suffix_driver':parent}","{'edge_cover_driver':parent}")
        tests=tests.replace('suffix_full_merge_driver.template.py','edge_cover_merge_driver.template.py').replace('suffix_full_merge_driver.py','edge_cover_merge_driver.py')
        tests=tests.replace("('merge','upper_merge','local_motion','probe_merge')","('merge','upper_merge','local_motion','probe_merge','suffix_merge')")
        tests=tests.replace("('merge_','upper_merge_','local_motion_','probe_merge_')","('merge_','upper_merge_','local_motion_','probe_merge_','suffix_merge_')")
        tests=tests.replace("a[2]['original_index'].tolist(),[0,2]","a[2]['original_index'].tolist(),[2]")
        tests=tests.replace("a[2]['union_index'].tolist(),[4,1]","a[2]['union_index'].tolist(),[1]")
        tests=tests.replace('    def test_import_uses_stub_only_no_parent_io(self):', '''    def test_exact_plan_paths_and_versioned_run(self):
        self.assertEqual(self.d.PLAN.name,'resume_plan_20261022_0000_v40.json')
        self.assertEqual(self.d.CLOSED_PLAN.name,'resume_plan_20261022_0000_v41.json')
        self.assertEqual(self.d.RUN.name,'resume_20261022_0000_edge_cover_merge_v1')

    def test_import_uses_stub_only_no_parent_io(self):''')
        blobs['test_edge_cover_merge_driver.py']=tests.encode('utf-8')
        final=HERE/'edge_cover_merge_final_staging_v1'
        final.mkdir(exist_ok=False)
        for name,blob in blobs.items(): (final/name).write_bytes(blob)
        test=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(final),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        evidence=dict(time=r.now(),execution=idle,mutex=mutex,returncode=test.returncode,
            stdout=test.stdout,stderr=test.stderr,pure_synthetic_contract_and_driver=True,
            all_closed_candidate_files_rehashed=912,accepted_candidate_hashes=hashes,
            all45714_scope_path_rows_all39groups_all57files_all3360000_point_file_records_required=True,
            scientific_lower_and_upper_status_nominal_and_old_provenance_unchanged=True,
            resources=r.guard(3584*1024**2,0),no_old_entrypoint_repeated=True)
        r.batch([(DEV/'development_test.json',r.encoded(evidence)),(DEV/'builder_source.py',Path(__file__).read_bytes())]
            +[(DEV/name,blob) for name,blob in blobs.items()])
        print(test.stderr,flush=True)
        r.require(test.returncode==0,'Development tests failed; preserve outcome, source not frozen')
        r.batch([(SOURCE/name,blob) for name,blob in blobs.items()])
    print('EDGE COVER MERGE SOURCE FROZEN; ALL25 SYNTHETIC TESTS PASSED; ALL912 CLOSED FILES REHASHED',flush=True)


if __name__=='__main__': main()
