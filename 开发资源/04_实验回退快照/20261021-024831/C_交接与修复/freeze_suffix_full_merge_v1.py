"""Bind independently closed suffix candidate, test and freeze a fresh full merge version."""
import os
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
HERE=Path(__file__).resolve().parent
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_suffix_witness_search_20261022_v3'))
import suffix_driver as d
r=d.r
SOURCE=ROOT/'src_s4_suffix_full_merge_20261022_v1'
DEV=d.AUTH/'runtime_sessions/suffix_full_merge_development_tests_v1'
CLOSED=d.AUTH/'runtime_sessions/suffix_witness_search_closed_v3'


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Version used or cutoff')
    h,_=d.execution()
    with h.exclusive() as mutex:
        _,idle=d.execution()
        d.verify()
        registration=r.read(CLOSED/'registration.json')
        r.require(registration['scientific_close_succeeded']
            and registration['actual_first_close_wait']['actual_wait_exit_code']==0
            and registration['actual_worker_wait']['actual_wait_exit_code']==0,'Actual first worker/close wait required')
        inventory=r.read(CLOSED/'all_closed_run_files_sha256.json')
        actual={p.relative_to(d.RUN).as_posix():r.file_hash(p) for p in sorted(d.RUN.rglob('*')) if p.is_file()}
        r.require(inventory==actual and len(actual)==registration['all_closed_file_count']==852,'Complete closed file inventory differs')
        hashes={name:actual[name] for name in ('checkpoint.json','acceptance.json','close_receipt.json','source_manifest.json')}
        receipt=r.read(d.RUN/'close_receipt.json')
        r.require(receipt['acceptance_sha256']==hashes['acceptance.json']
            and receipt['checkpoint_sha256']==hashes['checkpoint.json'],'Receipt binding differs')
        r.require(r.read(d.RUN/'runner_lock.json')['status']=='stopped'
            and r.read(d.RUN/'analysis_runner_lock.json')['status']=='stopped','Stopped locks required')
        d.whole_counts(r.read(d.RUN/'acceptance.json')['accounting'])
        template=HERE/'suffix_full_merge_staging_v1'
        text=(template/'suffix_full_merge_driver.template.py').read_text(encoding='utf-8')
        marker='HASHES = {}  # BIND_ACCEPTED_SUFFIX_HASHES_BEFORE_FREEZING'
        r.require(text.count(marker)==1,'Template hash marker differs')
        text=text.replace(marker,'HASHES = '+repr(hashes))
        text=text.replace('unwitnessed_probe_merge','suffix_full_merge')
        text=text.replace('local-motion','bounded-suffix').replace('local_motion merge','bounded suffix merge')
        text=text.replace('Whole-scope local-motion edge merge','Whole-scope bounded suffix witness merge')
        text=text.replace('v36-unwitnessed-probe-full-merge','v36-bounded-suffix-full-merge')
        compile(text,'suffix_full_merge_driver.py','exec')
        blobs={'suffix_full_merge_driver.py':text.encode('utf-8')}
        for name in ('suffix_merge_core.py','test_suffix_merge.py','test_suffix_full_merge_driver.py'):
            blobs[name]=(template/name).read_bytes()
        stage=HERE/'suffix_full_merge_final_staging_v1'
        stage.mkdir(exist_ok=False)
        for name,blob in blobs.items():
            (stage/name).write_bytes(blob)
        test=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        evidence=dict(time=r.now(),execution=idle,mutex=mutex,returncode=test.returncode,
            stdout=test.stdout,stderr=test.stderr,pure_synthetic_adapter_and_core=True,
            all_closed_candidate_files_rehashed=len(actual),accepted_candidate_hashes=hashes,
            full_scope_path_rows=45714,original_order_point_file_records=3360000,
            no_old_entrypoint_repeated=True,resources=r.guard(3584*1024**2,0))
        r.batch([(DEV/'development_test.json',r.encoded(evidence)),(DEV/'builder_source.py',Path(__file__).read_bytes())]
            +[(DEV/name,blob) for name,blob in blobs.items()])
        print(test.stderr,flush=True)
        r.require(test.returncode==0,'Synthetic development failed; preserve outcome, no source freeze')
        r.batch([(SOURCE/name,blob) for name,blob in blobs.items()])
        print('ALL30 SYNTHETIC TESTS PASSED; 852 CLOSED FILES REHASHED; NEW SUFFIX FULL MERGE SOURCE FROZEN',flush=True)
        print(r.encoded(hashes).decode('utf-8'),flush=True)


if __name__=='__main__':
    main()
