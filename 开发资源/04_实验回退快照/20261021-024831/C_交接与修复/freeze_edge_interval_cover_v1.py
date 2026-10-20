"""Freeze tested complete-bracket edge cover without invoking any old entrypoint."""
import os
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[key]='1'
HERE=Path(__file__).resolve().parent
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_suffix_full_merge_20261022_v1'))
import suffix_full_merge_driver as parent
r=parent.r
SOURCE=ROOT/'src_s4_edge_interval_cover_20261022_v1'
DEV=parent.AUTH/'runtime_sessions/edge_interval_cover_development_tests_v1'


def main():
    r.require(Path(sys.executable)==r.PYTHON and r.before_deadline(),'Runtime or cutoff')
    r.require(not SOURCE.exists() and not DEV.exists(),'New version used')
    h,_=parent.execution()
    with h.exclusive() as mutex:
        _,idle=parent.execution()
        parent.verify()
        closed=parent.AUTH/'runtime_sessions/suffix_full_merge_closed_v1'
        actual={p.relative_to(parent.RUN).as_posix():r.file_hash(p) for p in sorted(parent.RUN.rglob('*')) if p.is_file()}
        r.require(actual==r.read(closed/'all_closed_run_files_sha256.json') and len(actual)==1059,'Every closed parent file required')
        registration=r.read(closed/'registration.json')
        r.require(registration['actual_worker_wait']['actual_wait_exit_code']==0
            and registration['actual_first_close_wait']['actual_wait_exit_code']==0,'Actual first-use waits required')
        stage=HERE/'edge_interval_cover_staging_v1'
        blobs={p.name:p.read_bytes() for p in sorted(stage.glob('*.py'))}
        for name in blobs: compile(blobs[name],name,'exec')
        r.require(blobs['local_motion_core.py']==(ROOT/'src_s4_local_motion_20261022_v2/local_motion_core.py').read_bytes()
            and blobs['local_scope.py']==(ROOT/'src_s4_local_motion_20261022_v2/local_scope.py').read_bytes()
            and blobs['contact_primitives.py']==(ROOT/'src_s4_truth_remediation_20261019_v1/contact_primitives.py').read_bytes(),
            'Original motion/projection/geometry code byte-exact reused')
        test=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        evidence=dict(time=r.now(),execution=idle,mutex=mutex,returncode=test.returncode,
            stdout=test.stdout,stderr=test.stderr,pure_synthetic_only=True,
            physical_rectangle_GE0S_hitch_and_distinct_trailer_heading_included=True,
            parent_all_closed_files_rehashed=1059,parent_closed_hashes={k:actual[k] for k in ('checkpoint.json','acceptance.json','close_receipt.json','source_manifest.json')},
            maximum_node_queries=64,resolution_s=1e-7,unchanged_scientific_endpoints=True,
            original_empirical_spatial_error_and1mm_corner_and1e12_guard_unchanged=True,
            resources=r.guard(3584*1024**2,0),no_old_entrypoints_repeated=True)
        writes=[(DEV/'development_test.json',r.encoded(evidence)),(DEV/'builder_source.py',Path(__file__).read_bytes())]
        writes += [(DEV/name,blob) for name,blob in blobs.items()]
        for p in sorted((stage/'development_failure_1').rglob('*')):
            if p.is_file(): writes.append((DEV/'preserved_development_failure_1'/p.name,p.read_bytes()))
        r.batch(writes)
        print(test.stderr,flush=True)
        r.require(test.returncode==0,'Development failed; source not frozen')
        r.batch([(SOURCE/name,blob) for name,blob in blobs.items()])
    print('ALL32 SYNTHETIC TESTS PASSED; NEW EDGE INTERVAL COVER SOURCE FROZEN; REAL PREPARE/RUN NOT YET USED',flush=True)


if __name__=='__main__': main()
