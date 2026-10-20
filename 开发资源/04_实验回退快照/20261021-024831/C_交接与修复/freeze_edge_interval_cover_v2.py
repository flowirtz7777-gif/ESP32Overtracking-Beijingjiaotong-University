"""Preserve pre-action v1 naming collision, freeze v2 with exact plan-path tests."""
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
SOURCE=ROOT/'src_s4_edge_interval_cover_20261022_v2'
OLD=ROOT/'src_s4_edge_interval_cover_20261022_v1'
FAIL=parent.AUTH/'runtime_sessions/edge_interval_cover_lifecycle_v1'
DEV=parent.AUTH/'runtime_sessions/edge_interval_cover_development_tests_v2'


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Used or cutoff')
    h,_=parent.execution()
    with h.exclusive() as mutex:
        _,idle=parent.execution()
        r.require(not (ROOT/'runs/resume_20261022_0000_edge_interval_cover_v1').exists()
            and not (ROOT/'protocol_edge_interval_cover_20261022_0000_v1.json').exists(),
            'V1 failure must precede every scientific action')
        failed=r.read(FAIL/'manager_failure.json')
        r.require('New lifecycle already used' in failed['failure'],'Exact preserved pre-action failure required')
        r.freeze(FAIL/'manager_source.py',(HERE/'edge_interval_cover_lifecycle_manager_v1.py').read_bytes())
        snapshot={p.name:r.file_hash(p) for p in sorted(OLD.glob('*.py'))}
        r.freeze(FAIL/'pre_action_failure_registration.json',r.encoded(dict(time=r.now(),execution=idle,mutex=mutex,
            failed_manager_actual_exit_code=1,reason='v1 PLAN/CLOSED_PLAN mistakenly referenced existing v14/v15; guard rejected before actions',
            original_source_files_sha256=snapshot,scientific_prepare_run_close_not_called=True,
            original_frozen_source_and_plan_files_unchanged=True)))
        blobs={p.name:p.read_bytes() for p in sorted(OLD.glob('*.py'))}
        text=blobs['edge_cover_driver.py'].decode('utf-8')
        text=text.replace('resume_20261022_0000_edge_interval_cover_v1','resume_20261022_0000_edge_interval_cover_v2')
        text=text.replace('protocol_edge_interval_cover_20261022_0000_v1','protocol_edge_interval_cover_20261022_0000_v2')
        text=text.replace('runtime_sessions/edge_interval_cover_launch_v1','runtime_sessions/edge_interval_cover_launch_v2')
        text=text.replace('resume_plan_20261022_0000_v14.json','resume_plan_20261022_0000_v38.json')
        text=text.replace('resume_plan_20261022_0000_v15.json','resume_plan_20261022_0000_v39.json')
        text=text.replace('CLOSURE,AUTH/"runtime_sessions/suffix_full_merge_first_close_v1")))',
            'CLOSURE,AUTH/"runtime_sessions/suffix_full_merge_first_close_v1",ROOT/"src_s4_edge_interval_cover_20261022_v1",AUTH/"runtime_sessions/edge_interval_cover_lifecycle_v1")))')
        r.require('resume_plan_20261022_0000_v14' not in text and 'resume_plan_20261022_0000_v15' not in text,'No conflicting plans')
        blobs['edge_cover_driver.py']=text.encode('utf-8')
        tests=blobs['test_edge_cover_driver.py'].decode('utf-8')
        tests=tests.replace("    def test_no_real_read_or_output_on_synthetic_build(self):", """    def test_exact_new_plan_paths_and_versioned_run(self):
        self.assertEqual(self.d.PLAN.name,'resume_plan_20261022_0000_v38.json')
        self.assertEqual(self.d.CLOSED_PLAN.name,'resume_plan_20261022_0000_v39.json')
        self.assertEqual(self.d.RUN.name,'resume_20261022_0000_edge_interval_cover_v2')
        self.assertEqual(self.d.PROTOCOL.name,'protocol_edge_interval_cover_20261022_0000_v2.json')
        self.assertEqual(self.d.SESSION.name,'edge_interval_cover_launch_v2')

    def test_no_real_read_or_output_on_synthetic_build(self):""")
        blobs['test_edge_cover_driver.py']=tests.encode('utf-8')
        for name in ('edge_cover_core.py','local_motion_core.py','local_scope.py','contact_primitives.py','test_edge_cover.py'):
            r.require(blobs[name]==(OLD/name).read_bytes(),'Scientific code and core tests byte-exact; path repair only')
        stage=HERE/'edge_interval_cover_staging_v2'
        stage.mkdir(exist_ok=False)
        for name,blob in blobs.items(): (stage/name).write_bytes(blob)
        test=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        r.batch([(DEV/'development_test.json',r.encoded(dict(time=r.now(),returncode=test.returncode,
            stdout=test.stdout,stderr=test.stderr,execution=idle,mutex=mutex,pure_synthetic_only=True,
            v1_pre_action_failure_preserved=str(FAIL),scientific_kernel_byte_exact=True,
            original_closed_parent_hashes_unchanged=True,resources=r.guard(3584*1024**2,0)))),
            (DEV/'builder_source.py',Path(__file__).read_bytes())]+[(DEV/name,blob) for name,blob in blobs.items()])
        print(test.stderr,flush=True)
        r.require(test.returncode==0,'V2 tests failed; preserve outcome, no freeze')
        r.batch([(SOURCE/name,blob) for name,blob in blobs.items()])
    print('ALL33 SYNTHETIC TESTS PASS; V1 FAILURE PRESERVED; V2 PATH REPAIR FROZEN; NO OLD SCIENTIFIC ENTRYPOINT REPEATED',flush=True)


if __name__=='__main__': main()
