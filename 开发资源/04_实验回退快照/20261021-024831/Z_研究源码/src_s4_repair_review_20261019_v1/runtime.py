"""Versioned, bounded research I/O. No historical entrypoint is called."""
from __future__ import annotations
import datetime as dt
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
RUN = ROOT / "runs/resume_20261019_geometry_delay_v1"
AUTH = ROOT / "runs/resume_20261019_0800_authorization_v1"
PROTOCOL = ROOT / "protocol_geometry_delay_20261019_v1.json"
PLAN = ROOT / "resume_plan_20261019_v1.json"
PYTHON = Path(r"C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe")
DEADLINE = dt.datetime(2026, 10, 19, 0, tzinfo=dt.timezone.utc)
CAP, RESERVE, RUN_CAP = 16 * 1024**3, 3 * 1024**3, 256 * 1024**2
BATCH_RESERVATION = 160 * 1024**2
HELPER_SHA = "441e5bccfe47605b70ba2413c3b6cbccd6631abea9c22732b490f7ac8349e722"
OLD_RUNS = (
    "resume_20261017_fine_RIGHT_census_v1", "resume_20261017_fine_RIGHT_acceptance_v1",
    "resume_20261017_fine_counterexamples_v1", "resume_20261017_fine_temporal_trace_v1",
    "night_20261016_fine_inventory_v1", "night_20261016_fine_inventory_acceptance_v1",
    "resume_S4_RIGHT_census_v1", "resume_20261017_fine_factorial_1900_v1",
    "resume_20261017_matched_factorial_2400_v1", "resume_20261018_full_fine_cross_v1",
)

def require(value, message):
    if not value:
        raise RuntimeError(message)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def before_deadline():
    return dt.datetime.now(dt.timezone.utc) < DEADLINE

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def sha(blob):
    return hashlib.sha256(blob).hexdigest()

def retry(call):
    end = time.monotonic() + 30
    while True:
        try:
            return call()
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or time.monotonic() >= end:
                raise
            time.sleep(min(.25, max(0, end - time.monotonic())))

def file_hash(path):
    def perform():
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    return retry(perform)

def helper():
    require(Path(sys.executable) == PYTHON, "Exact Python required")
    path = ROOT / "\u7ba1\u7406\u811a\u672c/close_authorization_20261017_1400_v3.py"
    require(file_hash(path) == HELPER_SHA, "Frozen execution helper changed")
    spec = importlib.util.spec_from_file_location("execution_evidence_only", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NAMES = OLD_RUNS
    return module

def tree_bytes(root):
    return sum((Path(parent) / name).stat().st_size
               for parent, _, names in os.walk(root) for name in names)

def resources():
    e = helper().ORIGINAL_PLAN.parent
    zbytes, ebytes = tree_bytes(ROOT), tree_bytes(e)
    return {"time": now(), "combined_research_bytes": zbytes + ebytes,
            "preserved_E_bytes": ebytes, "execution_Z_bytes": zbytes,
            "research_cap_bytes": CAP, "research_remaining_bytes": CAP-zbytes-ebytes,
            "physical_free_Z_bytes": shutil.disk_usage(ROOT).free,
            "physical_reserve_bytes": RESERVE, "run_bytes": tree_bytes(RUN),
            "run_cap_bytes": RUN_CAP, "E_is_read_only": True}

def fits(state, extra, run_extra):
    return (state["combined_research_bytes"] + extra <= CAP
            and state["physical_free_Z_bytes"] - extra >= RESERVE
            and state["run_bytes"] + run_extra <= RUN_CAP)

def guard(extra, run_extra=None):
    state = resources()
    require(fits(state, extra, extra if run_extra is None else run_extra),
            "Resource admission failed; never remove or move history")
    return state

def freeze(path, blob):
    path = Path(path).resolve()
    require(path.is_relative_to(ROOT), "Writes only to Z research root")
    require(not path.exists(), "Frozen file already exists: " + str(path))
    guard(len(blob), len(blob) if path.is_relative_to(RUN) else 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    def perform():
        with path.open("xb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
    retry(perform)
    require(path.read_bytes() == blob, "Full write readback differs")

def batch(items):
    require(len({str(p) for p, _ in items}) == len(items), "Duplicate payload paths")
    total = sum(len(b) for _, b in items)
    run_total = sum(len(b) for p, b in items if p.is_relative_to(RUN))
    guard(total + 1024**2, run_total + 1024**2)
    for p, blob in items:
        freeze(p, blob)
    return total

def mutable(path, value):
    blob = encoded(value)
    old_size = path.stat().st_size if path.exists() else 0
    guard(len(blob), max(0, len(blob)-old_size) if path.is_relative_to(RUN) else 0)
    temporary = AUTH / "runtime" / (path.name + "." + str(time.time_ns()) + ".tmp")
    freeze(temporary, blob)
    retry(lambda: os.replace(temporary, path))
    require(path.read_bytes() == blob, "Mutable record readback differs")

def checkpoint(value):
    blob = encoded(value)
    packed = gzip.compress(blob, mtime=0)
    require(gzip.decompress(packed) == blob, "Checkpoint gzip mismatch")
    freeze(RUN / "checkpoint_history" / (sha(blob) + ".json.gz"), packed)
    mutable(RUN / "checkpoint.json", value)

def source_signature():
    paths = [*SOURCE.glob("*.py"), SOURCE / "review.md",
             *sorted((ROOT / "src_v3").glob("*.py")),
             *sorted((ROOT / "src_s4_v1").glob("*.py")),
             PROTOCOL, AUTH / "authorization.json"]
    return {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(paths)}

def verify_sources():
    expected = read(RUN / "source_manifest.json")
    require(source_signature() == expected, "Frozen source or protocol changed")
    for rel, digest in expected.items():
        require(file_hash(RUN / "source" / rel) == digest, "Source snapshot changed")
    return expected

def execution(h, include_new=False):
    result = h.execution_evidence()
    names = list(OLD_RUNS) + ([RUN.name] if include_new else [])
    locks = {}
    for name in names:
        for path in (ROOT / "runs" / name).glob("*runner_lock.json"):
            value = read(path)
            require(value.get("status") == "stopped", "Runner/analysis lock busy: " + str(path))
            locks[str(path)] = {"value": value, "sha256": file_hash(path)}
    result["all_runner_and_analysis_locks"] = locks
    return result
