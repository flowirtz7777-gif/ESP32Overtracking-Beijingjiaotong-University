"""First-use source-model simulated-truth candidate; frozen-Z actions only.

This is a candidate lifecycle, not a scientific label/score/training admission.
It deliberately accepts no empirical-E argument in its source geometry path.
"""
import os, sys, io, time, traceback, argparse, hashlib, subprocess, importlib
from pathlib import Path
from fractions import Fraction as F

for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"

ROOT = Path("Z:/大创内轮差项目_实验结果/科研实验_2026-10-14")
SOURCE = Path(__file__).resolve().parent
HERE = Path(r"C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1")
AUTH_CHOICE = HERE / "SOURCE_MODEL_TRUTH_AUTHORIZATION_20261022_v1.json"
CONTRACT = HERE / "SOURCE_MODEL_TRUTH_GEOMETRY_CONTRACT_20261022_v1.md"

sys.path.insert(0, str(ROOT / "src_s4_conditional_method_limit_20261024_v2"))
sys.path.insert(0, str(SOURCE))
import conditional_method_driver as parent
import source_truth_v1 as source_core
from source_truth_v1 import core as source_api
from source_truth_v1 import worker as source_worker
from source_truth_v1 import frontier as source_frontier
from source_truth_v1 import audit_core as independent_source_audit

np = parent.np
r = parent.r
extension = parent.extension
bundle_core = parent.bundle_core
PAIR = parent.PAIR
RUN = ROOT / "runs/resume_20261024_0000_source_model_truth_v1"
PROTOCOL = ROOT / "protocol_source_model_truth_20261024_0000_v1.json"
PLAN = ROOT / "resume_plan_20261024_0000_v114.json"
CLOSED_PLAN = ROOT / "resume_plan_20261024_0000_v115.json"
SESSION = parent.AUTH / "runtime_sessions/source_model_truth_launch_v1"
LIFECYCLE = parent.AUTH / "runtime_sessions/source_model_truth_lifecycle_v1"
CLOSE_SESSION = parent.AUTH / "runtime_sessions/source_model_truth_first_close_v1"
CLOSED = parent.AUTH / "runtime_sessions/source_model_truth_closed_v1"
PARENT_CLOSE = parent.CLOSE_SESSION
PARENT_CLOSED = parent.CLOSED
PARENT_RUN = parent.RUN
PARENT_SOURCE = parent.parent.CANDIDATE
IDS = (63731, 69993)
GEOMETRY_BUDGET = 4096
MAX_DEPTH = 24
SECONDS = 1800
TARGET = "source-model-continuous-simulated-truth-v1"
MAX_STEPS = 512
RUN_CAP = 512 * 1024**2


def configure():
    parent.configure()
    extension.configure_deadline(r)
    r.RUN, r.RUN_CAP = RUN, RUN_CAP


configure()


def execution():
    try:
        return parent.execution()
    finally:
        configure()


def boundary():
    r.require(SOURCE.resolve() == (ROOT / "src_s4_source_model_truth_20261024_v1").resolve(),
              "Scientific actions require the frozen-Z source truth driver")
    r.require(r.before_deadline(), "Authorized cutoff; no action after deadline")


def _guard_write(extra=8 * 1024**2):
    """Measured runtime guard immediately before every candidate artifact write."""
    configure()
    r.require(r.RUN == RUN and r.RUN_CAP == RUN_CAP, "Shared runtime restored to new RUN before write")
    return r.guard(extra, extra)


def _freeze(path, blob):
    _guard_write(len(blob) + 8 * 1024**2)
    r.freeze(path, blob)


def _mutable(path, value):
    blob = r.encoded(value)
    _guard_write(len(blob) + 8 * 1024**2)
    r.mutable(path, value)


def _json(path, value):
    _freeze(path, r.encoded(value))


def _batch(items):
    # Keep a measured RAM check immediately adjacent to every individual write.
    for path, blob in items:
        _freeze(path, blob)


def _inventory(folder):
    return {p.relative_to(folder).as_posix(): r.file_hash(p)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def _parent_gate():
    """Require the complete, actually waited v113 parent; never trust status alone."""
    try:
        parent.verify()
        worker_exit = r.read(parent.SESSION / "exit.json")
        close_exit = r.read(PARENT_CLOSE / "exit.json")
        registration = r.read(PARENT_CLOSED / "registration.json")
        inventory = r.read(PARENT_CLOSED / "all_closed_run_files_sha256.json")
        receipt = r.read(PARENT_RUN / "close_receipt.json")
        acceptance = r.read(PARENT_RUN / "acceptance.json")
        r.require(worker_exit.get("actual_wait_exit_code") == 0, "Parent v112 worker actual wait zero")
        r.require(close_exit.get("actual_wait_exit_code") == 0, "Parent v113 close actual wait zero")
        r.require(registration.get("actual_worker_wait", {}).get("actual_wait_exit_code") == 0,
              "Registered parent worker wait zero")
        r.require(registration.get("actual_first_close_wait", {}).get("actual_wait_exit_code") == 0,
              "Registered parent first-close wait zero")
        r.require(registration.get("scientific_close_succeeded") is True,
              "Parent v113 actual scientific close registration")
        r.require(len(inventory) >= 16 and _inventory(PARENT_RUN) == inventory,
              "Full parent v113 closed-run inventory (minimum 16 files)")
        r.require(len(inventory) == registration.get("all_closed_run_file_count"),
              "Parent v113 inventory count")
        for field, filename in (("checkpoint_sha256", "checkpoint.json"),
                            ("acceptance_sha256", "acceptance.json"),
                            ("diagnostic_sha256", "conditional_method_diagnostic.json"),
                            ("worker_proof_sha256", "worker_four_case_proof.json.gz"),
                            ("independent_proof_sha256", "independent_four_case_proof.json.gz")):
            r.require(receipt.get(field) == r.file_hash(PARENT_RUN / filename),
                  "Exact parent v113 receipt binding " + filename)
        r.require(acceptance.get("status") == "complete_four_case_conditional_method_limit_diagnostic",
              "Accepted v113 parent diagnostic")
        r.require(acceptance.get("training_allowed") is False and
              acceptance.get("corrected_labels_accepted") is False and
              acceptance.get("corrected_scores_accepted") is False,
              "Parent has no downstream promotion")
        return dict(worker_exit=worker_exit, close_exit=close_exit,
                inventory_count=len(inventory), receipt_sha256=r.file_hash(PARENT_RUN / "close_receipt.json"),
                acceptance_sha256=r.file_hash(PARENT_RUN / "acceptance.json"))
    finally:
        configure()


def _kernels():
    base = SOURCE / "source_truth_v1"
    expected = {"source_truth_v1": base / "__init__.py", **{
        "source_truth_v1." + name: base / (name + ".py")
        for name in ("core", "worker", "frontier", "audit_core", "independent_geometry")}}
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(base)
        if path.name.startswith("test_"):
            continue
        if path.name == "__init__.py":
            name = "source_truth_v1" + ("." + ".".join(rel.parent.parts) if rel.parent.parts else "")
        else:
            name = "source_truth_v1." + ".".join(rel.with_suffix("").parts)
        expected[name] = path
    for name, path in expected.items():
        module = importlib.import_module(name)
        r.require(Path(module.__file__).resolve() == path.resolve(),
                  "Exact staged candidate module " + name)
    r.require(callable(source_api.bind_source) and callable(source_api.worker_geometry) and
              callable(getattr(source_api, "independent_geometry", None)),
              "Complete source_truth_v1 bind/worker/independent-close API")
    r.require(callable(independent_source_audit.audit), "Independent source audit API")


def _signature():
    paths = set()
    parent_manifest = r.read(PARENT_RUN / "source_manifest.json")
    paths.update(ROOT / rel for rel in parent_manifest)
    paths.update(p for p in PARENT_RUN.rglob("*") if p.is_file())
    paths.update(p for p in PARENT_CLOSED.rglob("*") if p.is_file())
    paths.update(p for p in PARENT_CLOSE.rglob("*") if p.is_file())
    paths.update(p for p in parent.SESSION.rglob("*") if p.is_file())
    paths.update(SOURCE.rglob("*.py"))
    paths.update((PROTOCOL, PLAN, RUN / "selection.json", RUN / "environment.json",
                  RUN / "source_model_truth_authorization.json", SOURCE / "freeze_admission.json"))
    paths.add(extension.EXTENSION)
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p)
            for p in sorted(PAIR.nonarchive_source_paths(paths))}


def verify():
    _kernels()
    signed = r.read(RUN / "source_manifest.json")
    r.require(_signature() == signed, "Frozen source truth candidate and dependency hashes")
    bundle_core.verify_bundle((RUN / "source_bundle.zip").read_bytes(), signed)
    selection = r.read(RUN / "selection.json")
    admission = _read_freeze_admission(selection["authorization_sha256"])
    r.require(admission.get("human_choice_sha256") == r.file_hash(RUN / "source_model_truth_authorization.json") and
              admission.get("geometry_contract_sha256") == selection["geometry_contract_sha256"] and
              admission.get("source_artifact_sha256") == selection["source_artifact_sha256"],
              "Frozen admission binds exact human choice and geometry contract")
    r.require(parent.parent.parent.environment() == r.read(RUN / "environment.json"), "Pinned parent runtime")
    _parent_gate()


def _inputs():
    # Frozen-Z-only call. parent.parent is accepted v111 source_chain_audit_driver.
    try:
        args, refs, mother, sourceartifact = parent.parent.inputs()
    finally:
        configure()
    return args, refs, mother, sourceartifact


def _bind(args, refs, mother, sourceartifact):
    identity, old_requests, by_reference = parent._bind(args, refs, mother)
    r.require(tuple(int(x["original_index"]) for x in args["points"]) == IDS,
              "Exact original source-truth point IDs")
    r.require(len(mother["original_index"]) == 70000 and
              np.array_equal(mother["original_index"], np.arange(70000)),
              "Complete 70000-point original-order mother")
    r.require(set(sourceartifact) >= {"control", "vehicle", "speed", "end", "initial", "points", "limits", "steps"},
              "Complete accepted source artifact schema")
    r.require(len(sourceartifact["steps"]) <= MAX_STEPS, "Frozen source step cap")
    source_api.bind_source(sourceartifact, args)
    source_identity = dict(target=TARGET, parent_identity=identity,
        source_artifact_sha256=r.file_hash(PARENT_SOURCE / "source_chain_proof.json.gz"),
        complete_mother_identity=identity["mother_sha256"],
        old_reference_sha256=identity["reference_sha256"],
        old_reference_errors_retained_only_as_source_identity=True,
        original_indices=IDS, full_mother_count=70000,
        control=sourceartifact["control"], vehicle=sourceartifact["vehicle"],
        speed=sourceartifact["speed"], end=sourceartifact["end"],
        initial=sourceartifact["initial"], limits=sourceartifact["limits"],
        points=sourceartifact["points"])
    points = {int(p["original_index"]): p for p in args["points"]}
    r.require(set(points) == set(IDS), "Both source points retained")
    for i in IDS:
        row = np.asarray(mother["xy"])[i].tolist()
        r.require(points[i]["xy"] == row, "Source point coordinate equals full mother")
    return source_identity, points, by_reference, old_requests


def _authorization_copy():
    raw = AUTH_CHOICE.read_bytes()
    import json
    choice = json.loads(raw.decode("utf-8"))
    r.require(choice.get("version") == "source-model-truth-human-choice-20261022-v1" and
              choice.get("approved_option") == 1 and
              choice.get("old_truth_domain_mutation_authorized") is False and
              choice.get("real_vehicle_accuracy_claim_authorized") is False and
              choice.get("training_before_all_original_gates_authorized") is False and
              choice.get("deployment_authorized") is False,
              "Exact human choice scope is separately authorized")
    r.require(choice.get("first_bounded_trial_original_indices") == list(IDS) and
              choice.get("mother_population") == 70000 and
              choice.get("no_automatic_budget_order_or_step_increase") is True and
              choice.get("no_uniform_1nm_gate") is True,
              "Authorization matches frozen two-point trial")
    proposal = Path(choice["proposal_file"])
    r.require(proposal.is_file() and r.file_hash(proposal) == choice.get("proposal_sha256"),
              "Human-choice proposal exact hash")
    return raw, hashlib.sha256(raw).hexdigest(), choice


def _read_freeze_admission(choice_sha):
    path = SOURCE / "freeze_admission.json"
    r.require(path.is_file(), "Immutable source freeze_admission.json must pre-exist prepare")
    admission = r.read(path)
    package_hashes = {p.relative_to(SOURCE).as_posix(): r.file_hash(p)
        for p in sorted((SOURCE / "source_truth_v1").rglob("*.py"))}
    all_source_hashes = {p.relative_to(SOURCE).as_posix(): r.file_hash(p)
        for p in sorted(SOURCE.rglob("*.py"))}
    r.require(admission.get("human_choice_sha256") == choice_sha,
              "Pre-frozen admission pins exact human choice bytes")
    r.require(admission.get("geometry_contract_sha256") == r.file_hash(CONTRACT),
              "Pre-frozen admission pins geometry contract")
    r.require(admission.get("authorization_extension_sha256") == r.file_hash(extension.EXTENSION),
              "Pre-frozen admission pins deadline extension")
    r.require(admission.get("source_artifact_sha256") == r.file_hash(PARENT_SOURCE / "source_chain_proof.json.gz"),
              "Pre-frozen admission pins accepted source artifact bytes")
    r.require(admission.get("source_package_files") == package_hashes,
              "Pre-frozen admission pins every vendored source truth module")
    r.require(admission.get("all_source_files_sha256") == all_source_hashes,
              "Pre-frozen admission pins driver, manager, and all source modules")
    r.require(admission.get("synthetic_tests",{}).get("success") is True, "Pre-frozen pure tests passed")
    return admission


def _save_mother(mother):
    stream = io.BytesIO()
    np.savez_compressed(stream, **{k: np.asarray(v) for k, v in mother.items()})
    blob = stream.getvalue()
    with np.load(io.BytesIO(blob), allow_pickle=False) as z:
        r.require(set(z.files) == set(mother) and
                  all(np.array_equal(z[k], np.asarray(mother[k])) for k in mother),
                  "Complete mother lossless NPZ roundtrip")
    _freeze(RUN / "full70000_mother.npz", blob)


def _source_control_check(args, artifact, check):
    count = 0
    total = len(artifact["steps"])
    def phase_check():
        nonlocal count
        check()
        count += 1
        print("SOURCE CONTROL PHASE " + str(count) + "/" + str(total), flush=True)
    return source_api.bind_source(artifact, args, check=phase_check)


def prepare():
    boundary()
    r.require(not any(p.exists() for p in (RUN, PROTOCOL, PLAN, CLOSED_PLAN, SESSION, CLOSE_SESSION, CLOSED)),
              "First-use lifecycle only; no retry")
    r.require((SOURCE / "freeze_admission.json").is_file(),
              "Freeze admission must be frozen before prepare")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        lineage = _parent_gate()
        _kernels()
        extension_status = extension.configure_deadline(r)
        raw_choice, choice_sha, choice = _authorization_copy()
        admission = _read_freeze_admission(choice_sha)
        source_artifact_sha = r.file_hash(PARENT_SOURCE / "source_chain_proof.json.gz")
        r.require(r.DEADLINE.isoformat() == choice["deadline_utc"], "Authorized exact deadline")
        protocol = dict(time=r.now(), deadline=r.DEADLINE.isoformat(), target=TARGET,
            human_choice_sha256=choice_sha, human_choice_exact_bytes=True,
            authorization_extension_sha256=r.file_hash(extension.EXTENSION),
            authorization_extension=extension_status, parent_lineage=lineage,
            scope="First bounded source-model simulated-truth existence trial for original indices 63731 and 69993; both complete original references/E retained as provenance only; source model is a separate target.",
            first_use_only=True, failed_prepare_run_close_terminal=True,
            worker_seconds=SECONDS, close_seconds=SECONDS, workers=1, inflight=1,
            blas_threads=1, run_cap_bytes=RUN_CAP, maximum_source_steps=MAX_STEPS,
            source_degree=6, maximum_source_step_s="0.2", geometry_calls_per_point=GEOMETRY_BUDGET,
            checker_calls_per_point=GEOMETRY_BUDGET, maximum_geometry_depth=MAX_DEPTH,
            full_original_horizon=True, full_original_mother=70000, original_indices=list(IDS),
            old_reference_and_empirical_E="identity/provenance only; excluded from source distance bounds",
            tolerance="exact inherited source tolerance, bound at worker/close",
            no_step_order_budget_increase=True,
            no_uniform_1nm_gate=True, face_candidate_mask=255, face_certification_complete=False,
            unknown_frontier_retained=True, original_time_lower_bound_retained=True,
            empirical_E_in_source判界=False, label_gain_expected=[0,2],
            scientific_admission_allowed=False, corrected_labels_accepted=False,
            corrected_scores_accepted=False, training_allowed=False, deployment_allowed=False)
        plan = dict(version="20261024-v114-source-model-truth", run_directory=str(RUN),
            protocol=str(PROTOCOL), entrypoint=str(Path(__file__)), deadline=protocol["deadline"],
            stage_status="prepared_not_admitted", target=TARGET, original_indices=list(IDS),
            full_mother=70000, scientific_admission_allowed=False,
            corrected_labels_accepted=False, corrected_scores_accepted=False, training_allowed=False)
        selection = dict(parent_run=str(PARENT_RUN), parent_close=str(PARENT_CLOSE),
            parent_closed=str(PARENT_CLOSED), source_candidate=str(PARENT_SOURCE),
            parent_lineage=lineage, source_artifact_sha256=source_artifact_sha,
            original_indices=list(IDS), full_mother=70000,
            retained_reference_names=list(parent.REFS),
            retained_reference_and_E_role="provenance only; excluded from source distance bounds",
            geometry_contract_sha256=r.file_hash(CONTRACT),
            authorization_sha256=choice_sha, geometry_budget=GEOMETRY_BUDGET,
            max_depth=MAX_DEPTH, worker_close_seconds=SECONDS, target=TARGET,
            admission_false=True)
        environment = parent.parent.parent.environment()
        _batch([(RUN / "selection.json", r.encoded(selection)),
                (RUN / "environment.json", r.encoded(environment)),
                (PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
                (RUN / "source_model_truth_authorization.json", raw_choice),
                (RUN / "prelaunch.json", r.encoded(dict(time=r.now(), execution=idle,
                    mutex=mutex, resources=r.guard(64*1024**2, 64*1024**2),
                    full_source_identity_only=True, no_real_proof_decoded=True)))])
        signed = _signature()
        _freeze(RUN / "source_manifest.json", r.encoded(signed))
        _freeze(RUN / "source_bundle.zip", bundle_core.source_bundle({k: (ROOT/k).read_bytes() for k in signed}))
    print("SOURCE MODEL TRUTH PREPARED; NOT SCIENTIFIC CLOSE", flush=True)


def run():
    boundary()
    r.require(not (RUN / "checkpoint.json").exists(), "Worker is first-use only")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        _mutable(RUN / "runner_lock.json", dict(status="running", pid=os.getpid(), time=r.now()))
        try:
            begun = time.monotonic()
            def check(*_):
                boundary()
                r.require(time.monotonic()-begun < SECONDS, "Fixed 1800-second worker limit")
            active=r.read(ROOT / "active_research_run.json")
            active.update(version="20261024-v114-source-model-truth-running",run_directory=str(RUN),
                protocol=str(PROTOCOL),plan=str(PLAN),entrypoint=str(Path(__file__)),pid=os.getpid(),
                running_analysis=True,running_predictions=False,scientific_acceptance=None,
                scientific_close_receipt=None,scientific_close_actual_wait_exit_code=None,
                stdout=str(SESSION / "stdout.log"),stderr=str(SESSION / "stderr.log"),target=TARGET)
            _mutable(ROOT / "active_research_run.json",active)
            args, refs, mother, artifact = _inputs()
            identity, points, by_reference, old_requests = _bind(args, refs, mother, artifact)
            raw_choice, choice_sha, _ = _authorization_copy()
            r.require(raw_choice == (RUN / "source_model_truth_authorization.json").read_bytes() and
                      choice_sha == r.read(RUN / "selection.json")["authorization_sha256"],
                      "Exact approved source-model choice bytes")
            _save_mother(mother)
            codec = parent.parent.codec
            source_proof_path = PARENT_SOURCE / "source_chain_proof.json.gz"
            source_proof_bytes = source_proof_path.read_bytes()
            r.require(hashlib.sha256(source_proof_bytes).hexdigest() ==
                      identity["source_artifact_sha256"] and
                      codec.decode(source_proof_bytes) == artifact,
                      "Exact accepted source artifact bytes bound before geometry")
            _freeze(RUN / "source_model_truth_source_artifact.json.gz", source_proof_bytes)
            _source_control_check(args, artifact, check)
            worker_result = source_api.worker_geometry(artifact, args, check=check,
                progress=lambda s: print(s, flush=True))
            r.require(worker_result.get("target") == TARGET and
                      worker_result.get("corrected_truth_certificates") == 0 and
                      worker_result.get("training_allowed") is False and
                      len(worker_result.get("point_covers", [])) == len(IDS),
                      "Complete bounded worker result without admission")
            for cover in worker_result["point_covers"]:
                r.require(cover["geometry_evaluations"] <= GEOMETRY_BUDGET and
                          len(cover["steps"]) == len(artifact["steps"]),
                          "Fixed per-point geometry budget and full source-step coverage")
            proof = dict(target=TARGET, identity=identity,
                source_artifact_sha256=r.file_hash(RUN / "source_model_truth_source_artifact.json.gz"),
                worker_result=worker_result,
                geometry_budget=GEOMETRY_BUDGET, max_depth=MAX_DEPTH,
                empirical_E_used_in_source_geometry=False, old_references_retained=True,
                face_candidate_mask=255, scientific_admission_allowed=False)
            blob = codec.encode(proof)
            r.require(codec.decode(blob) == proof, "RAM lossless proof roundtrip")
            _freeze(RUN / "source_model_truth_worker_proof.json.gz", blob)
            summary = dict(time=r.now(), status="complete_pending_FIRST_independent_source_truth_close",
                proof_sha256=r.file_hash(RUN / "source_model_truth_worker_proof.json.gz"),
                points=[dict(original_index=x["point"]["original_index"],
                    geometry_evaluations=x["geometry_evaluations"],
                    candidate_status=x["summary"]["candidate_status"],
                    scientific_admission_allowed=False) for x in worker_result["point_covers"]],
                full_mother=70000, full_source_steps=len(artifact["steps"]),
                corrected_truth_certificates=0, labels_scores_training=0)
            _json(RUN / "source_model_truth_worker_summary.json", summary)
            _mutable(RUN / "checkpoint.json", dict(status=summary["status"],
                proof_sha256=summary["proof_sha256"], target=TARGET))
        except Exception:
            _mutable(RUN / "checkpoint.json", dict(status="source_model_truth_worker_failed",
                failure=traceback.format_exc(), target=TARGET))
            raise
        finally:
            _mutable(RUN / "runner_lock.json", dict(status="stopped", pid=os.getpid(), time=r.now()))
    print("SOURCE TRUTH WORKER COMPLETE; INDEPENDENT FIRST CLOSE PENDING", flush=True)


def close():
    boundary()
    r.require(not (RUN / "analysis_runner_lock.json").exists() and not (RUN / "acceptance.json").exists(),
              "First independent close only")
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / "checkpoint.json")
        proof_path = RUN / "source_model_truth_worker_proof.json.gz"
        r.require(cp.get("status") == "complete_pending_FIRST_independent_source_truth_close" and
                  cp.get("proof_sha256") == r.file_hash(proof_path), "Stopped complete worker required")
        _mutable(RUN / "analysis_runner_lock.json", dict(status="running", pid=os.getpid(), time=r.now()))
        try:
            begun = time.monotonic()
            def check(*_):
                boundary()
                r.require(time.monotonic()-begun < SECONDS, "Fixed 1800-second independent close limit")
            args, refs, mother, artifact = _inputs()
            identity, points, by_reference, old_requests = _bind(args, refs, mother, artifact)
            raw_choice, choice_sha, _ = _authorization_copy()
            r.require(raw_choice == (RUN / "source_model_truth_authorization.json").read_bytes() and
                      choice_sha == r.read(RUN / "selection.json")["authorization_sha256"],
                      "Exact approved choice retained through close")
            with np.load(RUN / "full70000_mother.npz", allow_pickle=False) as z:
                r.require(set(z.files) == set(mother) and
                          all(np.array_equal(z[k], np.asarray(mother[k])) for k in mother),
                          "Independent close full-mother identity")
            codec = parent.parent.codec
            source_artifact_path = RUN / "source_model_truth_source_artifact.json.gz"
            source_artifact_bytes = source_artifact_path.read_bytes()
            r.require(hashlib.sha256(source_artifact_bytes).hexdigest() ==
                      identity["source_artifact_sha256"] and codec.decode(source_artifact_bytes) == artifact,
                      "Close independently rebinds exact saved source artifact")
            proof = codec.decode(proof_path.read_bytes())
            r.require(proof.get("target") == TARGET and proof.get("identity") == identity and
                      proof.get("source_artifact_sha256") == r.file_hash(source_artifact_path) and
                      len(proof.get("worker_result", {}).get("point_covers", [])) == 2 and
                      proof.get("empirical_E_used_in_source_geometry") is False,
                      "Exact source target/two-point proof identity")
            close_proof = source_api.independent_geometry(artifact, args,
                proof["worker_result"], check=check,
                progress=lambda s: print("INDEPENDENT CLOSE " + s, flush=True))
            r.require(close_proof.get("target") == TARGET and
                      close_proof.get("corrected_truth_or_score_certificates") == 0 and
                      close_proof.get("training_allowed") is False and
                      len(close_proof.get("point_results", [])) == 2 and
                      close_proof.get("existence_candidates") in (0, 1, 2),
                      "Complete independent source/two-point close, admission remains false")
            close_proof.update(identity=identity, source_steps=len(artifact["steps"]),
                full_original_horizon=True, old_references_and_E_retained_as_provenance=True,
                source_geometry_did_not_use_empirical_E=True, face_candidate_mask=255,
                face_certification_complete=False, corrected_truth_certificates=0,
                corrected_score_certificates=0, scientific_admission_allowed=False)
            close_blob = codec.encode(close_proof)
            r.require(codec.decode(close_blob) == close_proof, "Independent proof lossless roundtrip")
            _freeze(RUN / "source_model_truth_independent_proof.json.gz", close_blob)
            point_summary = []
            for result in close_proof["point_results"]:
                interval = result.get("first_contact_interval")
                compact_interval = None if interval is None else [
                    parent.parent.down(interval[0]), parent.parent.up(interval[1])]
                point_summary.append(dict(original_index=result["point"]["original_index"],
                    candidate_status=result["candidate_status"],
                    first_contact_interval_s_outward=compact_interval,
                    earliest_unexcluded_s_outward=None if result.get("earliest_unexcluded_s") is None
                        else parent.parent.down(result["earliest_unexcluded_s"]),
                    candidate_contact_upper_s_outward=None if result.get("candidate_contact_upper_s") is None
                        else parent.parent.up(result["candidate_contact_upper_s"]),
                    source_steps=result["source_steps"],
                    independent_geometry_calls=result["own_geometry_evaluations"],
                    unknown_frontier_cells=sum(
                        leaf["joint_state"] == "unknown"
                        for step in result["step_reports"] for leaf in step["frontier"]),
                    face_candidate_mask=255, face_certification_complete=False,
                    corrected_truth_certificates=0, scientific_admission_allowed=False))
            diagnostic = dict(time=r.now(), target=TARGET,
                points=point_summary,
                existence_candidates=close_proof["existence_candidates"],
                unknown_retained=True, no_full57_truth_or_score=True,
                corrected_truth_certificates=0, corrected_score_certificates=0,
                training_allowed=False, physical_accuracy_claim_allowed=False)
            _json(RUN / "source_model_truth_diagnostic.json", diagnostic)
            acceptance = dict(time=r.now(),
                status="complete_two_point_source_model_truth_existence_diagnostic_not_admission",
                target=TARGET, accounting=dict(points=2, full_mother=70000,
                    full_source_steps=len(artifact["steps"]),
                    existence_candidates=close_proof["existence_candidates"],
                    geometry_evaluations=sum(x["geometry_evaluations"]
                        for x in proof["worker_result"]["point_covers"]),
                    corrected_truth_certificates=0, corrected_score_certificates=0),
                worker_proof_sha256=r.file_hash(proof_path),
                independent_proof_sha256=r.file_hash(RUN / "source_model_truth_independent_proof.json.gz"),
                diagnostic_sha256=r.file_hash(RUN / "source_model_truth_diagnostic.json"),
                both_points_independently_replayed=True, face_candidate_mask=255,
                face_certification_complete=False, scientific_admission_allowed=False,
                corrected_labels_accepted=False, corrected_scores_accepted=False,
                training_allowed=False, deployment_allowed=False,
                    real_vehicle_accuracy_claim_allowed=False, full57_truth_admitted=False,
                execution=idle, mutex=mutex)
            _json(RUN / "acceptance.json", acceptance)
        finally:
            _mutable(RUN / "analysis_runner_lock.json", dict(status="stopped", pid=os.getpid(), time=r.now()))
    with h.exclusive() as released:
        _, after = execution()
    closed_plan = {**r.read(PLAN), "version": "20261024-v115-source-model-truth-closed",
        "stage_status": acceptance["status"], "accounting": acceptance["accounting"]}
    _json(RUN / "close_receipt.json", dict(time=r.now(),
        checkpoint_sha256=r.file_hash(RUN / "checkpoint.json"),
        acceptance_sha256=r.file_hash(RUN / "acceptance.json"),
        diagnostic_sha256=r.file_hash(RUN / "source_model_truth_diagnostic.json"),
        worker_proof_sha256=r.file_hash(proof_path),
        independent_proof_sha256=r.file_hash(RUN / "source_model_truth_independent_proof.json.gz"),
        execution_after=after, mutex_acquired_released=released))
    _json(CLOSED_PLAN, closed_plan)
    active = r.read(ROOT / "active_research_run.json")
    active.update(version=closed_plan["version"], status=closed_plan["stage_status"],
        plan=str(CLOSED_PLAN), pid=None, running_analysis=False, running_predictions=False,
        scientific_acceptance=str(RUN / "acceptance.json"),
        scientific_close_receipt=str(RUN / "close_receipt.json"),
        next_action="Review two-point source-model simulated-truth existence diagnostic; no full57 truth/score/training admission")
    _mutable(ROOT / "active_research_run.json", active)
    print("SOURCE MODEL TRUTH FIRST CLOSE COMPLETE; ADMISSION FALSE", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "close"))
    globals()[parser.parse_args().action]()
