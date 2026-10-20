"""Restart-isolated recovery: preserve interrupted run and reuse verified outputs."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src_s4_repair_review_20261019_v1"))
import runtime as r
import run_repair as dep
import numpy as np

ORIGINAL = r.RUN
RUN = ROOT / "runs/resume_20261019_geometry_delay_recovery_v1"
PLAN = ROOT / "resume_plan_20261019_recovery_v1.json"
SESSION = r.AUTH / "runtime_sessions/repair_recovery_launch_v1"
EXPECTED_CP = "38a5416021d81faa240d0a8acfc53e4c2d19fdefd26dc971610fcf80ec5e3132"
base_verify = r.verify_sources
r.RUN = RUN
r.PLAN = PLAN

def scan_size(root):
    total, stack = 0, [Path(root)]
    while stack:
        path = stack.pop()
        if not path.exists():
            continue
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                else:
                    raise RuntimeError("Nonregular research asset: " + entry.path)
    return total

r.tree_bytes = scan_size

def system_state():
    cmd = "Get-CimInstance Win32_OperatingSystem | Select-Object @{n='boot_utc';e={$_.LastBootUpTime.ToUniversalTime().ToString('o')}} | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                            check=True, capture_output=True, encoding="utf-8-sig", timeout=30)
    return json.loads(result.stdout)

def interrupted_idle(h):
    idle = r.execution(h, include_new=(RUN / "runner_lock.json").exists())
    lock = r.read(ORIGINAL / "runner_lock.json")
    boot = system_state()
    r.require(dt.datetime.fromisoformat(lock["time"]) < dt.datetime.fromisoformat(boot["boot_utc"]),
              "Interrupted lock must predate current OS boot")
    r.require(r.file_hash(ORIGINAL / "checkpoint.json") == EXPECTED_CP, "Interrupted checkpoint changed")
    return {"execution": idle, "system": boot, "original_stale_lock": lock,
            "original_lock_is_not_rewritten": True, "original_checkpoint_sha256": EXPECTED_CP}

def recovery_signature():
    paths = [*Path(__file__).parent.glob("*.py"), PLAN]
    return {str(p.relative_to(ROOT)): r.file_hash(p) for p in paths}

def verify():
    result = base_verify()
    expected = r.read(RUN / "recovery_source_manifest.json")
    r.require(recovery_signature() == expected, "Recovery source/plan changed")
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / "recovery_source" / rel) == digest, "Recovery snapshot changed")
    evidence = r.read(RUN / "interruption_receipt.json")
    for rel, digest in evidence["original_files_sha256"].items():
        r.require(r.file_hash(ORIGINAL / rel) == digest, "Interrupted history changed: " + rel)
    return result

r.verify_sources = verify

def prepare():
    r.require(r.before_deadline() and not RUN.exists() and not PLAN.exists(), "Recovery already prepared or cutoff")
    h = r.helper()
    with h.exclusive() as mutex:
        evidence = interrupted_idle(h)
        original_cp = r.read(ORIGINAL / "checkpoint.json")
        r.require(len(original_cp["geometry"]) == 12 and len(original_cp["completed"]) == 4,
                  "Unexpected interruption boundary")
        manifest = r.read(ORIGINAL / "source_manifest.json")
        r.require(r.source_signature() == manifest, "Frozen scientific source changed")
        tests = subprocess.run([str(r.PYTHON), "-X", "utf8", "-B", "-m", "unittest", "discover",
                                "-s", str(Path(__file__).parent), "-p", "test_recovery.py", "-v"],
                               cwd=r"C:\Users\Admin", capture_output=True, encoding="utf-8", timeout=180)
        r.require(tests.returncode == 0, "Recovery tests failed: " + tests.stderr)
        inventory = {p.relative_to(ORIGINAL).as_posix(): r.file_hash(p)
                     for p in ORIGINAL.rglob("*") if p.is_file()}
        items = []
        for rel, digest in manifest.items():
            path = ORIGINAL / "source" / rel
            r.require(r.file_hash(path) == digest, "Original source snapshot changed")
            items.append((RUN / "source" / rel, path.read_bytes()))
        items.append((RUN / "source_manifest.json", r.encoded(manifest)))
        for key, record in original_cp["geometry"].items():
            folder = ORIGINAL / "geometry" / key
            r.require(r.read(folder / "result.json") == record, "Geometry CP differs")
            r.require(r.file_hash(folder / "reference.npz") == record["reference_npz_sha256"], "Reference changed")
            for path in folder.iterdir():
                items.append((RUN / path.relative_to(ORIGINAL), path.read_bytes()))
        for key, record in original_cp["completed"].items():
            folder = ORIGINAL / "jobs" / key
            r.require(r.file_hash(folder / "report.json") == record["report_sha256"], "Completed report differs")
            report = r.read(folder / "report.json")
            for name, digest in report["output_sha256"].items():
                r.require(r.file_hash(folder / name) == digest, "Completed output differs")
            for path in folder.iterdir():
                items.append((RUN / path.relative_to(ORIGINAL), path.read_bytes()))
        seed = {**original_cp, "status": "recovery_prepared", "reused_completed_predictions": 4,
                "remaining_predictions_maximum": 5, "new_accepted_diagnostics": 0}
        plan = r.read(ROOT / "resume_plan_20261019_v1.json")
        plan.update(version="20261019-recovery-v1", run_directory=str(RUN), entrypoint=str(Path(__file__)),
                    interrupted_run=str(ORIGINAL), original_checkpoint_sha256=EXPECTED_CP,
                    reuse_geometry=12, reuse_predictions=4, remaining_predictions=5,
                    no_old_source_or_output_modified=True,
                    next_action="new worker admission; reuse four complete outputs; compute only five incomplete jobs")
        evidence.update(time=r.now(), mutex=mutex, original_files_sha256=inventory,
                        test_stdout=tests.stdout, test_stderr=tests.stderr,
                        incomplete_partial_outputs_preserved_not_reused=[
                            key for key in inventory if "hold__delay200__alpha_lp/" in key])
        r.batch(items + [(RUN / "interruption_receipt.json", r.encoded(evidence)),
                         (RUN / "seed.json", r.encoded(seed)), (PLAN, r.encoded(plan))])
        signature = recovery_signature()
        r.batch([(RUN / "recovery_source_manifest.json", r.encoded(signature))] +
                [(RUN / "recovery_source" / rel, (ROOT / rel).read_bytes()) for rel in signature])
        active = r.read(ROOT / "active_research_run.json")
        active.update(status="recovery_registered_not_running", pid=None, running_predictions=False,
                      running_analysis=False, running_preflight=False, run_directory=str(RUN),
                      plan=str(PLAN), entrypoint=str(Path(__file__)), next_action=plan["next_action"])
        r.mutable(ROOT / "active_research_run.json", active)
    print("RECOVERY PREPARED: 12 geometries and 4 complete predictions reused; 5 pending", flush=True)

def run():
    r.require(r.before_deadline() and not (RUN / "checkpoint.json").exists(), "Recovery already started or cutoff")
    h = r.helper()
    cp = r.read(RUN / "seed.json")
    with h.exclusive() as mutex:
        idle = interrupted_idle(h)
        verify()
        r.mutable(RUN / "runner_lock.json", {"status": "running", "pid": os.getpid(), "time": r.now()})
        try:
            data, targets, raw, manifest = dep.load_inputs()
            for job in dep.old_matrix():
                if job["id"] in cp["completed"]:
                    dep.independently_check_job(job, cp["completed"][job["id"]], targets, data)
            preflight = {"time": r.now(), "python": sys.executable, "root": str(ROOT), "mutex": mutex,
                         "execution": idle, "source_signature": verify(), "input_manifest": manifest,
                         "recovery_source_signature": recovery_signature(),
                         "all_nine_processed_inputs_exact": True, "reused_predictions_verified": 4,
                         "loaded_modules": {m.__name__: str(Path(m.__file__).resolve()) for m in
                                            (dep.common, dep.geometry, dep.observations, dep.prediction, dep.evaluator)},
                         "resources": r.guard(r.BATCH_RESERVATION, r.BATCH_RESERVATION)}
            r.batch([(RUN / "preflight.json", r.encoded(preflight)),
                     (RUN / "raw_observations.npz", dep.npz_blob({k: raw[k] for k in dep.SENSOR_KEYS}))])
            print("RECOVERY PREFLIGHT PASSED: all original inputs exact; four outputs independently checked", flush=True)
            active = r.read(ROOT / "active_research_run.json")
            active.update(status="recovery_delay_predictions_running", pid=os.getpid(),
                          running_predictions=True, running_preflight=False, input_worker_admitted=True)
            r.mutable(ROOT / "active_research_run.json", active)
            cp["status"] = "recovery_delay_predictions_running"
            r.checkpoint(cp)
            for job in dep.old_matrix():
                if job["id"] in cp["completed"]:
                    continue
                r.require(r.before_deadline(), "08:00 cutoff")
                verify()
                r.guard(16 * 1024**2)
                print("SUBMIT RECOVERY DELAY " + job["id"], flush=True)
                cp["completed"][job["id"]] = dep.delay_job(job, data, targets, raw)
                r.checkpoint(cp)
                print("DONE RECOVERY DELAY " + job["id"], flush=True)
            cp["status"] = "complete_pending_independent_acceptance"
            r.checkpoint(cp)
        except Exception:
            cp.update(status="stopped_failure_or_deadline", recovery_failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / "runner_lock.json", {"status": "stopped", "pid": os.getpid(), "time": r.now()})
    print("RECOVERY EXITING; real exit and independent close still required", flush=True)

def launch():
    r.require(not SESSION.exists() and not (RUN / "checkpoint.json").exists(), "Launch already attempted")
    h = r.helper()
    with h.exclusive() as mutex:
        idle = interrupted_idle(h)
        verify()
        r.freeze(SESSION / "execution_policy.json", r.encoded({"time": r.now(), "mutex": mutex,
                 "execution": idle, "source_signature": recovery_signature(),
                 "release_parent_mutex_before_child": True, "resources": r.guard(r.BATCH_RESERVATION)}))
    with (SESSION / "stdout.log").open("xb") as out, (SESSION / "stderr.log").open("xb") as err:
        process = subprocess.Popen([str(r.PYTHON), "-X", "utf8", "-B", "-u", str(Path(__file__)), "run"],
                                   cwd=r"C:\Users\Admin", stdout=out, stderr=err,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / "launched.json", r.encoded({"time": r.now(), "pid": process.pid,
              "pid_is_not_liveness_evidence": True, "source_signature": recovery_signature()}))
    print(json.dumps({"launched_pid": process.pid, "session": str(SESSION)}), flush=True)

def close():
    h = r.helper()
    with h.exclusive():
        interrupted_idle(h)
        verify()
    dep.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "run", "close"))
    globals()[parser.parse_args().action]()
