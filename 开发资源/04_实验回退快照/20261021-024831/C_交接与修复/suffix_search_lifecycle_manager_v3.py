"""First-use prepare/run/close lifecycle with real sequential Popen/wait and preserved outcomes."""
import os
import subprocess
import sys
import traceback
from pathlib import Path
sys.dont_write_bytecode=True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[key]='1'
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_suffix_witness_search_20261022_v3'))
import suffix_driver as d
r=d.r
LIFECYCLE=d.AUTH/'runtime_sessions/suffix_witness_search_lifecycle_v3'
CLOSED=d.AUTH/'runtime_sessions/suffix_witness_search_closed_v3'


def action(name,session):
    d.configure()
    r.require(r.before_deadline() and not session.exists(),'Action session used or cutoff: '+name)
    argv=[str(r.PYTHON),'-X','utf8','-B','-u',str(Path(d.__file__)),name]
    h,idle=d.execution()
    with h.exclusive() as mutex:
        _,idle=d.execution()
        r.freeze(session/'policy.json',r.encoded(dict(time=r.now(),argv=argv,cwd=r'C:\Users\Admin',
            execution=idle,mutex=mutex,resources=r.guard(8*1024**2,4*1024**2),no_retry=True)))
    for filename in ('stdout.log','stderr.log'): r.freeze(session/filename,b'')
    with (session/'stdout.log').open('ab') as out,(session/'stderr.log').open('ab') as err:
        child=subprocess.Popen(argv,cwd=r'C:\Users\Admin',stdin=subprocess.DEVNULL,stdout=out,stderr=err,
            env=dict(os.environ),creationflags=subprocess.CREATE_NO_WINDOW)
        r.freeze(session/'launched.json',r.encoded(dict(time=r.now(),pid_historical_identity_only=child.pid,
            ancestor_manager_pid=os.getpid(),argv=argv,not_admission_proof=True)))
        print('FIRST '+name.upper()+' SUBMITTED PID '+str(child.pid),flush=True)
        last=''
        while True:
            try:
                actual_exit=child.wait(timeout=20)
                break
            except subprocess.TimeoutExpired:
                # Read child logs inside its ancestor manager, never a second ROOT-bearing monitor shell.
                lines=(session/'stdout.log').read_text(encoding='utf-8',errors='replace').splitlines()
                current=lines[-1] if lines else 'no progress marker yet; child still active'
                if current!=last:
                    print(name.upper()+' PROGRESS: '+current[-320:],flush=True)
                    last=current
    d.configure()
    r.freeze(session/'exit.json',r.encoded(dict(time=r.now(),actual_wait_exit_code=actual_exit,
        pid=child.pid,ancestor_manager_pid=os.getpid(),argv=argv)))
    print('FIRST '+name.upper()+' ACTUAL WAIT EXIT '+str(actual_exit),flush=True)
    if actual_exit:
        print((session/'stderr.log').read_text(encoding='utf-8',errors='replace')[-8000:],flush=True)
    return actual_exit


def main():
    r.require(Path(sys.executable)==r.PYTHON and r.before_deadline(),'Runtime or cutoff')
    r.require(not LIFECYCLE.exists() and not d.RUN.exists() and not d.PROTOCOL.exists()
        and not d.PLAN.exists() and not d.CLOSED_PLAN.exists(),'New lifecycle already used')
    h,idle=d.execution()
    with h.exclusive() as mutex:
        _,idle=d.execution()
        r.freeze(LIFECYCLE/'manager_source.py',Path(__file__).read_bytes())
        r.freeze(LIFECYCLE/'policy.json',r.encoded(dict(time=r.now(),execution=idle,mutex=mutex,
            prepare_run_close_each_first_use=True,never_retries=True,workers=1,inflight=1,
            full_scope_group_unique_points=22857,full_both_path_scope_records=45714,
            full_population_original_order_point_file_records=3360000,original_dataset_files=57,
            full_coarse_fine_populations_controls_scores_still_required=True,
            truth_asset_promotion_allowed=False,resources=r.guard(1024**2,0))))
    prepare=LIFECYCLE/'prepare'
    if action('prepare',prepare): return 1
    if action('run',d.SESSION): return 1
    h,stopped=d.execution()
    with h.exclusive() as released:
        _,stopped=d.execution()
    cp=r.read(d.RUN/'checkpoint.json')
    r.require(cp['status']=='complete_pending_independent_unwitnessed_probe_close'
        and len(cp['completed'])==78,'Full merge incomplete; cannot close')
    r.freeze(LIFECYCLE/'worker_stopped.json',r.encoded(dict(time=r.now(),execution=stopped,
        mutex_acquired_released=released,checkpoint_sha256=r.file_hash(d.RUN/'checkpoint.json'),
        actual_worker_wait=r.read(d.SESSION/'exit.json'),independent_close_still_pending=True)))
    close_session=d.AUTH/'runtime_sessions/suffix_witness_search_first_close_v3'
    exitcode=action('close',close_session)
    h,after=d.execution()
    with h.exclusive() as released:
        _,after=d.execution()
    r.require(exitcode==0,'First scientific merge close failed; do not retry')
    a=r.read(d.RUN/'acceptance.json'); receipt=r.read(d.RUN/'close_receipt.json')
    r.require(receipt['acceptance_sha256']==r.file_hash(d.RUN/'acceptance.json')
        and receipt['checkpoint_sha256']==r.file_hash(d.RUN/'checkpoint.json'),'Receipt binding differs')
    d.whole_counts(a['accounting'])
    inventory={p.relative_to(d.RUN).as_posix():r.file_hash(p) for p in sorted(d.RUN.rglob('*')) if p.is_file()}
    r.freeze(CLOSED/'all_closed_run_files_sha256.json',r.encoded(inventory))
    r.freeze(CLOSED/'registration.json',r.encoded(dict(time=r.now(),execution_after=after,
        actual_first_close_wait=r.read(close_session/'exit.json'),actual_worker_wait=r.read(d.SESSION/'exit.json'),
        mutex_acquired_released=released,scientific_close_succeeded=True,
        analysis_runner_lock=r.read(d.RUN/'analysis_runner_lock.json'),all_closed_file_count=len(inventory),
        checkpoint_sha256=inventory['checkpoint.json'],acceptance_sha256=inventory['acceptance.json'],
        close_receipt_sha256=inventory['close_receipt.json'],source_manifest_sha256=inventory['source_manifest.json'],
        protocol_sha256=r.file_hash(d.PROTOCOL),accounting=a['accounting'],
        truth_asset_promotion_allowed=False,corrected_truth_revalidated_prediction_jobs=0,
        full_current_scope_merge_all57projections_and_fresh_census_still_required=True,
        all_remaining_unknowns_full_coarse_fine_populations_controls_affected_scores_still_required=True)))
    print('COMPLETE BOUNDED SUFFIX CANDIDATE SCIENTIFIC CLOSE AND REGISTRATION; NEW MERGE STILL REQUIRED',flush=True)
    print(r.encoded(a['accounting']).decode('utf-8'),flush=True)
    return 0


if __name__=='__main__':
    try: sys.exit(main())
    except Exception:
        traceback.print_exc()
        # Preserve manager failure independently without modifying any frozen outcome.
        d.configure()
        dest=LIFECYCLE/'manager_failure.json'
        if not dest.exists():
            r.freeze(dest,r.encoded(dict(time=r.now(),failure=traceback.format_exc(),old_entrypoints_not_retried=True)))
        raise
