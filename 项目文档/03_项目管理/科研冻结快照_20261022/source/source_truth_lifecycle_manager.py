"""No-retry manager for a future frozen-Z source-truth lifecycle only."""
import os, sys, subprocess, traceback
from pathlib import Path

for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"

ROOT = Path(r"Z:\大创内轮差项目_实验结果\科研实验_2026-10-14")
sys.path.insert(0, str(ROOT / "src_s4_conditional_method_limit_20261024_v2"))
import conditional_method_driver as parent
sys.path.insert(0,str(ROOT / "src_s4_source_model_truth_20261024_v1"))
import source_truth_driver as d

r = d.r


def _freeze(path, blob):
    d._guard_write(len(blob) + 8 * 1024**2)
    r.freeze(path, blob)


def _json(path, value):
    _freeze(path, r.encoded(value))


def _inventory(folder):
    return {p.relative_to(folder).as_posix(): r.file_hash(p)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def _action(name, session):
    d.configure()
    r.require(r.before_deadline() and not session.exists(), "First-use/cutoff gate: "+name)
    argv=[str(r.PYTHON),"-X","utf8","-B","-u",str(Path(d.__file__)),name]
    handle,_=d.execution()
    with handle.exclusive() as mutex:
        _,idle=d.execution()
        _json(session/"policy.json",dict(time=r.now(),argv=argv,cwd=r"C:\Users\Admin",
            execution=idle,mutex=mutex,resources=r.guard(8*1024**2,8*1024**2),
            measured_ram_guard_before_each_write=True,no_retry=True,
            live_child_logs_follow_original_manager_append_policy=True))
    for filename in ("stdout.log","stderr.log"):_freeze(session/filename,b"")
    with (session/"stdout.log").open("ab") as out,(session/"stderr.log").open("ab") as err:
        child=subprocess.Popen(argv,cwd=r"C:\Users\Admin",stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,env=dict(os.environ),creationflags=subprocess.CREATE_NO_WINDOW)
        _json(session/"launched.json",dict(time=r.now(),pid_historical_identity_only=child.pid,
            ancestor_manager_pid=os.getpid(),argv=argv,not_admission_proof=True))
        last=""
        while True:
            try:code=child.wait(timeout=20);break
            except subprocess.TimeoutExpired:
                lines=(session/"stdout.log").read_text(encoding="utf8",errors="replace").splitlines()
                line=lines[-1] if lines else "child active"
                if line!=last:print(name.upper()+" PROGRESS "+line[-320:],flush=True);last=line
    _json(session/"exit.json",dict(time=r.now(),actual_wait_exit_code=code,
        pid=child.pid,ancestor_manager_pid=os.getpid(),argv=argv))
    print("FIRST "+name.upper()+" ACTUAL WAIT "+str(code),flush=True)
    if code:print((session/"stderr.log").read_text(encoding="utf8",errors="replace")[-8000:],flush=True)
    return code

def main():
    r.require(r.file_hash(Path(__file__)) == r.file_hash(Path(d.__file__).parent / "source_truth_lifecycle_manager.py"),
              "Exact frozen manager bytes; C control copy only")
    r.require(Path(sys.executable) == r.PYTHON and Path.cwd() == Path(r"C:\Users\Admin"),
              "Exact approved Python runtime/workdir")
    r.require(Path(d.__file__).resolve() == (ROOT / "src_s4_source_model_truth_20261024_v1" /
        "source_truth_driver.py").resolve(), "Frozen-Z driver exact path required")
    r.require(r.before_deadline(), "Authorized cutoff")
    d._parent_gate()
    r.require(not any(p.exists() for p in (d.LIFECYCLE, d.CLOSED, d.RUN, d.PROTOCOL,
        d.PLAN, d.CLOSED_PLAN, d.SESSION, d.CLOSE_SESSION)), "Lifecycle has never been used")
    handle, _ = d.execution()
    with handle.exclusive() as mutex:
        _, idle = d.execution()
        source = Path(__file__).read_bytes()
        _freeze(d.LIFECYCLE / "manager_source.py", source)
        _json(d.LIFECYCLE / "manager_policy.json", dict(time=r.now(), execution=idle,
            mutex=mutex, sequence=("prepare", "run", "stop-and-observe-worker", "first-close"),
            no_retry=True, max_workers=1, max_inflight=1,
            all_parents_verified=True, full_source_truth_close=True,
            corrected_truth_score_training_admission=False,
            measured_ram_guard_before_each_write=True))
    r.require(r.file_hash(d.LIFECYCLE / "manager_source.py") == r.file_hash(Path(__file__)),
              "Persisted exact manager bytes")
    if _action("prepare", d.LIFECYCLE / "prepare"):
        return 1
    if _action("run", d.SESSION):
        return 1
    worker_wait = r.read(d.SESSION / "exit.json")
    r.require(worker_wait.get("actual_wait_exit_code") == 0,
              "First close prohibited unless actual worker wait is zero")
    handle, _ = d.execution()
    with handle.exclusive() as mutex:
        _, stopped = d.execution()
        cp = r.read(d.RUN / "checkpoint.json")
        r.require(cp.get("status") == "complete_pending_FIRST_independent_source_truth_close",
                  "Complete stopped first worker required")
        _json(d.LIFECYCLE / "worker_stopped.json", dict(time=r.now(), execution=stopped,
            mutex=mutex, actual_worker_wait=worker_wait,
            checkpoint_sha256=r.file_hash(d.RUN / "checkpoint.json")))
    if _action("close", d.CLOSE_SESSION):
        return 1
    close_wait = r.read(d.CLOSE_SESSION / "exit.json")
    r.require(close_wait.get("actual_wait_exit_code") == 0, "First independent close actual wait zero")
    handle, _ = d.execution()
    with handle.exclusive() as mutex:
        _, after = d.execution()
        acceptance = r.read(d.RUN / "acceptance.json")
        receipt = r.read(d.RUN / "close_receipt.json")
        for key, name in (("acceptance_sha256", "acceptance.json"),
                          ("checkpoint_sha256", "checkpoint.json"),
                          ("diagnostic_sha256", "source_model_truth_diagnostic.json"),
                          ("worker_proof_sha256", "source_model_truth_worker_proof.json.gz"),
                          ("independent_proof_sha256", "source_model_truth_independent_proof.json.gz")):
            r.require(receipt.get(key) == r.file_hash(d.RUN / name),
                      "Exact independent source truth receipt: " + name)
        inv = _inventory(d.RUN)
        _json(d.CLOSED / "all_closed_run_files_sha256.json", inv)
        _json(d.CLOSED / "registration.json", dict(time=r.now(), execution_after=after,
            mutex=mutex, actual_worker_wait=worker_wait, actual_first_close_wait=close_wait,
            scientific_close_succeeded=True, all_closed_run_file_count=len(inv),
            accounting=acceptance["accounting"], full_mother=70000,
            corrected_truth_certificates=0, corrected_score_certificates=0,
            scientific_admission_allowed=False, training_allowed=False))
    print("SOURCE MODEL TRUTH FIRST CLOSE REGISTERED; ADMISSION FALSE", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        d.configure()
        failure = d.LIFECYCLE / "manager_failure.json"
        if not failure.exists():
            _json(failure, dict(time=r.now(), failure=traceback.format_exc(),
                old_entries_not_retried=True, admission_false=True))
        raise
