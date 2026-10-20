"""Administrative first-close manager: preserves actual wait; no scientific kernel changes."""
import os
import subprocess
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0, str(ROOT / 'src_s4_unwitnessed_probe_20261022_v1'))
import probe_driver as driver

r = driver.r
SESSION = driver.AUTH / 'runtime_sessions/unwitnessed_probe_first_close_v1'
REGISTRATION = driver.AUTH / 'runtime_sessions/unwitnessed_probe_closed_v1'


def main():
    r.require(Path(sys.executable) == r.PYTHON and r.before_deadline(), 'Runtime or authorization cutoff')
    r.require(not SESSION.exists() and not REGISTRATION.exists(), 'First-close session already used')
    for name in ('acceptance.json', 'analysis_runner_lock.json', 'close_receipt.json'):
        r.require(not (driver.RUN / name).exists(), 'Prior close evidence exists: ' + name)
    r.require(not driver.CLOSED_PLAN.exists(), 'Closed plan already exists')
    prior_close_sessions = [str(p) for p in (driver.AUTH / 'runtime_sessions').iterdir()
        if 'unwitnessed_probe' in p.name and 'close' in p.name]
    r.require(not prior_close_sessions, 'Possible prior close attempt: ' + str(prior_close_sessions))
    h, initial = driver.execution()
    with h.exclusive() as mutex:
        _, idle = driver.execution()
        r.require(r.read(driver.RUN / 'runner_lock.json')['status'] == 'stopped', 'Worker still active')
        cp = r.read(driver.RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_unwitnessed_probe_close'
            and len(cp['completed']) == 78, 'Candidate computation incomplete')
        driver.whole_counts(cp['accounting'])
        r.require(sum(len(v['datasets']) for v in cp['completed'].values()) == 114,
            'Missing original-order projection')
        print('FIRST CLOSE: verifying every frozen source and stopped-parent dependency', flush=True)
        driver.verify()
        resources = r.guard(32 * 1024**2, 8 * 1024**2)
        r.freeze(SESSION / 'manager_source.py', Path(__file__).read_bytes())
        r.freeze(SESSION / 'precheck.json', r.encoded(dict(time=r.now(), execution=idle,
            mutex_acquired_released_after_context=mutex, resources=resources,
            stopped_checkpoint_sha256=r.file_hash(driver.RUN / 'checkpoint.json'),
            source_manifest_sha256=r.file_hash(driver.RUN / 'source_manifest.json'),
            all_frozen_sources_snapshots_and_stopped_parent_dependencies_verified=True,
            complete_path_blocks=78, complete_original_order_path_projections=114,
            no_prior_scientific_close_evidence=True, candidate_numbers_not_scientific_acceptance=True)))
    argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(driver.__file__)), 'close']
    r.require(r.before_deadline(), 'No first close submission after cutoff')
    for name in ('stdout.log', 'stderr.log'):
        r.freeze(SESSION / name, b'')
    r.freeze(SESSION / 'policy.json', r.encoded(dict(time=r.now(), argv=argv,
        cwd=r'C:\Users\Admin', no_retry=True, scientific_workers=1, inflight=1,
        blas_threads=1, standalone_external_root_monitoring_forbidden_while_child_active=True)))
    with (SESSION / 'stdout.log').open('ab') as out, (SESSION / 'stderr.log').open('ab') as err:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
        r.freeze(SESSION / 'launched.json', r.encoded(dict(time=r.now(), pid=child.pid,
            ancestor_manager_pid=os.getpid(), argv=argv, pid_historical_identity_only=True)))
        print('FIRST SCIENTIFIC CLOSE SUBMITTED PID ' + str(child.pid), flush=True)
        actual_exit = child.wait()
    r.freeze(SESSION / 'exit.json', r.encoded(dict(time=r.now(), actual_wait_exit_code=actual_exit,
        pid=child.pid, ancestor_manager_pid=os.getpid(), argv=argv)))
    print('FIRST SCIENTIFIC CLOSE ACTUAL WAIT EXIT ' + str(actual_exit), flush=True)
    h, stopped = driver.execution()
    with h.exclusive() as released:
        _, final = driver.execution()
    success = actual_exit == 0 and (driver.RUN / 'acceptance.json').exists() and (driver.RUN / 'close_receipt.json').exists()
    if success:
        receipt = r.read(driver.RUN / 'close_receipt.json')
        r.require(receipt['checkpoint_sha256'] == r.file_hash(driver.RUN / 'checkpoint.json')
            and receipt['acceptance_sha256'] == r.file_hash(driver.RUN / 'acceptance.json'), 'Receipt binding differs')
    inventory = {p.relative_to(driver.RUN).as_posix(): r.file_hash(p)
        for p in sorted(driver.RUN.rglob('*')) if p.is_file()}
    r.freeze(REGISTRATION / 'all_closed_run_files_sha256.json', r.encoded(inventory))
    accepted = r.read(driver.RUN / 'acceptance.json') if success else None
    r.freeze(REGISTRATION / 'registration.json', r.encoded(dict(time=r.now(),
        actual_first_close_wait=r.read(SESSION / 'exit.json'), execution_after=final,
        mutex_acquired_released=released, scientific_close_succeeded=success,
        analysis_lock=r.read(driver.RUN / 'analysis_runner_lock.json') if (driver.RUN / 'analysis_runner_lock.json').exists() else None,
        all_run_files=len(inventory), checkpoint_sha256=inventory['checkpoint.json'],
        acceptance_sha256=inventory.get('acceptance.json'), close_receipt_sha256=inventory.get('close_receipt.json'),
        source_manifest_sha256=inventory['source_manifest.json'],
        protocol_sha256=r.file_hash(driver.PROTOCOL), accounting=accepted['accounting'] if accepted else None,
        truth_asset_promotion_allowed=False, all57_full_merge_and_fresh_census_still_required=True,
        original_sources_protocols_candidates_failures_preserved=True)))
    print('CLOSE REGISTRATION SAVED; SUCCESS=' + str(success), flush=True)
    if accepted:
        print(r.encoded(accepted['accounting']).decode('utf-8'), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        raise
