from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED, as_completed
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np

from common import ROOT, file_hash, array_hash, read_json, write_json, storage_guard, utc_now
from evaluation import evaluate, summarize, Variant
from foundation import build_dataset, elementary_checks
from observations import observe, preprocess, conditions
from prediction import Method, rollout
from reporting import core_report, csv_rows, statistics, rank_key
from audit import numerical_and_contact_audit

RUN = ROOT/"runs"/"overnight_20261014_v2"
DEADLINE = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc).timestamp()


class DeadlineReached(Exception):
    pass


def signature():
    return {p.name: file_hash(p) for p in sorted((ROOT/"src").glob("*.py"))}


def method_id(m):
    if m.mode == "hold": return "hold"
    if m.mode == "linear": return f"linear_g{round(m.gain*100):03d}"
    if m.mode == "damped_linear": return f"damped_d{round(m.decay_s*1000):04d}"
    return f"second_a{round(m.acceleration_duration_s*1000):04d}"


def methods():
    nominal = [Method(m) for m in ["hold", "linear", "damped_linear", "bounded_second_order"]]
    search = [Method("hold")]
    search += [Method("linear", gain=g) for g in [.5, .75, 1, 1.25, 1.5, 2]]
    search += [Method("damped_linear", decay_s=t) for t in [.125, .25, .5, 1, 2, 4]]
    search += [Method("bounded_second_order", acceleration_duration_s=t) for t in [.05, .1, .2, .25, .5, 1]]
    return nominal, search


def load_case(partition, case_id):
    directory = ROOT/"datasets"/partition/case_id
    manifest = read_json(directory/"manifest.json")
    for name, sha in manifest["files"].items():
        if file_hash(directory/name) != sha:
            raise AssertionError("Input hash mismatch "+case_id+"/"+name)
    return dict(np.load(directory/"trajectory.npz")), dict(np.load(directory/"targets.npz")), manifest


def execute_job(job):
    storage_guard()
    start = time.perf_counter()
    directory = RUN/"jobs"/job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    data, targets, manifest = load_case(job["partition"], job["case_id"])
    observed = preprocess(observe(data, job["condition"]), job["preprocessing"])
    method = Method(**job["method"])
    variants = [Variant(**v) for v in job["variants"]]
    result = evaluate(observed, targets, method, variants)
    summaries = []
    for state, summary in zip(result["states"], result["summaries"]):
        for count in job.get("density_counts", [len(targets["xy"])]):
            s = dict(summary) if count == len(targets["xy"]) else {**summary, **summarize(observed, targets, state, count)}
            s.update({"case_id": job["case_id"], "partition": job["partition"], "config_id": method_id(method),
                "condition": job["condition"]["id"], "preprocessing": job["preprocessing"],
                "stage": job["stage"], "job_id": job["id"]})
            summaries.append(s)
    np.savez_compressed(directory/"target_results.npz", **result["point_output"])
    np.savez_compressed(directory/"frame_results.npz", counts=result["frame_counts"],
                        time=observed["time"], phase=result["observed_phase"])
    write_json(directory/"summary.json", summaries)
    write_json(directory/"configuration.json", job)
    write_json(directory/"timing.json", {**result["timing"], "benchmark_target_count": len(targets["xy"]),
                                        "scoring_workload_not_real_sensor_target_count": True})
    output_names = ["target_results.npz", "frame_results.npz", "summary.json", "configuration.json", "timing.json"]
    report = {"id": job["id"], "source_signature": job["source_signature"], "input_hashes": manifest["files"],
        "target_coordinates_sha256": manifest["target_coordinates_sha256"],
        "contact_label_sha256": manifest["contact_label_sha256"],
        "observed_state_sha256": array_hash(observed["state"]), "observed_alpha_sha256": array_hash(observed["alpha"]),
        "output_sha256": {name: file_hash(directory/name) for name in output_names},
        "target_count": len(targets["xy"]), "wall_s": time.perf_counter()-start}
    write_json(directory/"report.json", report)
    return {"id": job["id"], "report_sha256": file_hash(directory/"report.json"), "summaries": summaries, "wall_s": report["wall_s"]}


def verify_job(job, record):
    directory = RUN/"jobs"/job["id"]
    assert file_hash(directory/"report.json") == record["report_sha256"]
    report = read_json(directory/"report.json")
    assert report["source_signature"] == job["source_signature"]
    assert read_json(directory/"configuration.json") == job
    for name, sha in report["output_sha256"].items():
        assert file_hash(directory/name) == sha


def run_jobs(stage, jobs, cp, workers=4):
    pending = []
    for job in jobs:
        if job["id"] in cp["completed"]:
            verify_job(job, cp["completed"][job["id"]])
        else:
            pending.append(job)
    print(f"STAGE {stage} {len(pending)}/{len(jobs)} remaining", flush=True)
    if not pending:
        return
    iterator = iter(pending)
    finished = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        active = {}
        def send():
            if time.time() >= DEADLINE:
                return False
            job = next(iterator, None)
            if job is None:
                return False
            storage_guard()
            active[pool.submit(execute_job, job)] = job
            return True
        for _ in range(workers): send()
        while active:
            completed, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
            for future in completed:
                job = active.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    write_json(RUN/"last_failure.json", {"job": job, "error": repr(error), "time": utc_now()})
                    for f in active: f.cancel()
                    raise
                cp["completed"][result["id"]] = {"report_sha256": result["report_sha256"]}
                cp["summaries"].extend(result["summaries"])
                write_json(RUN/"checkpoint.json", cp)
                finished += 1
                print(f"DONE {stage} {finished}/{len(pending)} {result['id']} {result['wall_s']:.1f}s", flush=True)
                send()
        if finished != len(pending):
            raise DeadlineReached("Night deadline reached with saved completed jobs")


def job(stage, partition, case, method, source, condition=None, preprocessing="raw", variants=None, density=None):
    condition = condition or {"id": "clean", "noise_level": 0, "delay_s": 0}
    identifier = "__".join([stage, case, method_id(method), condition["id"], preprocessing])
    j = {"id": identifier, "stage": stage, "partition": partition, "case_id": case,
         "method": asdict(method), "source_signature": source, "condition": condition,
         "preprocessing": preprocessing, "variants": [asdict(v) for v in (variants or [Variant()])]}
    if density: j["density_counts"] = density
    return j


def density_gate(rows, count):
    low = 21000 if count == 35000 else count//2
    cases = sorted({r["case_id"] for r in rows})
    methods_present = sorted({r["config_id"] for r in rows})
    differences, paired = [], []
    for case in cases:
        base = {n: next(r for r in rows if r["case_id"]==case and r["config_id"]=="hold" and r["target_count"]==n) for n in [low, count]}
        for m in methods_present:
            a = next(r for r in rows if r["case_id"]==case and r["config_id"]==m and r["target_count"]==low)
            b = next(r for r in rows if r["case_id"]==case and r["config_id"]==m and r["target_count"]==count)
            differences.append({"case": case, "method": m, "right_delta_pp": abs(a["right_pct"]-b["right_pct"]),
                "fp_delta_pp": abs(a["negative_fp_pct"]-b["negative_fp_pct"]),
                "lead_p10_delta_s": abs(a["right_lead_p10_s"]-b["right_lead_p10_s"])})
            paired.append(abs((a["right_pct"]-base[low]["right_pct"])-(b["right_pct"]-base[count]["right_pct"])))
    return {"target_count": count, "lower_count": low, "case_count": len(cases),
        "max_right_absolute_delta_pp": max(x["right_delta_pp"] for x in differences),
        "max_point_fp_delta_pp": max(x["fp_delta_pp"] for x in differences),
        "max_lead_p10_delta_s": max(x["lead_p10_delta_s"] for x in differences),
        "max_paired_method_delta_pp": max(paired), "rows": differences,
        "passed": all(x["right_delta_pp"]<=.2 and x["fp_delta_pp"]<=.5 and x["lead_p10_delta_s"]<=.05+1e-8 for x in differences)
                  and max(paired)<=.2}


def build_all(specs, count, partition, workers=4):
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(build_dataset, s, count, partition): s["id"] for s in specs}
        for i, f in enumerate(as_completed(pending), 1):
            r = f.result()
            print(f"FROZEN {partition} {i}/{len(specs)} {r['id']} n={r['target_count']}", flush=True)


def acquire_lock():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, "Local\\InnerWheelResearch20261014")
    if kernel.WaitForSingleObject(handle, 0) not in [0, 128]:
        kernel.CloseHandle(handle)
        raise RuntimeError("A new experiment runner is already active")
    return kernel, handle


def main(workers=4):
    global RUN
    kernel, mutex = acquire_lock()
    RUN.mkdir(parents=True, exist_ok=True)
    source = signature()
    write_json(RUN/"runner_lock.json", {"pid": os.getpid(), "status": "running", "time": utc_now()})
    cp_file = RUN/"checkpoint.json"
    cp = read_json(cp_file) if cp_file.exists() else {"source_signature": source, "completed": {}, "summaries": [], "stages": {}}
    if cp["source_signature"] != source:
        raise RuntimeError("Runner source changed; preserve previous run and create a versioned output directory")
    snapshot = RUN/"source"
    snapshot.mkdir(exist_ok=True)
    for name, sha in source.items():
        target = snapshot/name
        if target.exists(): assert file_hash(target)==sha
        else: target.write_bytes((ROOT/"src"/name).read_bytes())
    write_json(RUN/"plan_snapshot.json", read_json(ROOT/"plan.json"))
    write_json(cp_file, cp)
    try:
        nominal, candidates = methods()
        designs = read_json(ROOT/"scenario_matrix.json")
        selected_cases = ["v2_r2_symmetric", "v3_r4_fast_return", "v4_r8_fast_entry"]
        count, partition = 35000, "development_v2"
        elementary_checks()
        if not cp["stages"].get("S0"):
            numerical_and_contact_audit(partition)
            accepted = None
            for count in [35000, 70000, 105000]:
                partition = "development_v2" if count==35000 else f"development_v2_n{count}"
                subset = [s for s in designs if s["id"] in selected_cases]
                build_all(subset, count, partition, workers)
                low = 21000 if count==35000 else count//2
                stage = "S0_density_n"+str(count)
                jobs = [job(stage, partition, s["id"], m, source, density=[low, count]) for s in subset for m in nominal]
                run_jobs(stage, jobs, cp, workers)
                check = density_gate([r for r in cp["summaries"] if r["stage"]==stage], count)
                write_json(ROOT/"reports"/(stage+".json"), check)
                print("DENSITY "+json.dumps({k:v for k,v in check.items() if k!='rows'}), flush=True)
                if check["passed"]:
                    accepted = check
                    break
            if accepted is None:
                raise RuntimeError("S0 density did not stabilize; formal algorithm search stopped")
            build_all(designs, count, partition, workers)
            cp["stages"]["S0"] = {"done": True, "target_count": count, "partition": partition, "density": accepted}
            write_json(ROOT/"reports"/"S0_acceptance.json", {"status": "passed", "target_count": count,
                "reference_sampling_and_frame_point_counts_checked": True, "density": accepted,
                "source_signature": source, "physical_validation": False})
            write_json(cp_file, cp)
        count = cp["stages"]["S0"]["target_count"]
        partition = cp["stages"]["S0"]["partition"]
        if not cp["stages"].get("S1_nominal"):
            jobs = [job("S1_nominal", partition, s["id"], m, source) for s in designs for m in nominal]
            run_jobs("S1_nominal", jobs, cp, workers)
            cp["stages"]["S1_nominal"] = {"done": True, "prediction_jobs": len(jobs)}
            write_json(cp_file, cp)
        if not cp["stages"].get("S1_search"):
            existing = {method_id(m) for m in nominal}
            extra = [m for m in candidates if method_id(m) not in existing]
            jobs = [job("S1_search", partition, s["id"], m, source) for s in designs for m in extra]
            run_jobs("S1_search", jobs, cp, workers)
            cp["stages"]["S1_search"] = {"done": True, "prediction_jobs": len(jobs)}
            write_json(cp_file, cp)
        rows = [r for r in cp["summaries"] if r["stage"] in ["S1_nominal", "S1_search"]]
        core = core_report(rows, {method_id(m): asdict(m) for m in candidates})
        finalists = [Method(**r["method"]) for r in core["finalists"]]
        robustness_methods = finalists + ([Method("hold")] if not any(m.mode=="hold" for m in finalists) else [])
        representatives = ["v2_r2_symmetric", "v2_r8_fast_return", "v3_r4_symmetric",
                           "v3_r4_fast_entry", "v4_r2_fast_return", "v4_r8_fast_entry"]
        processing = ["raw", "alpha_lp", "age_hold"]
        if not cp["stages"].get("S2"):
            jobs = [job("S2", partition, case, m, source, c, pp) for case in representatives
                    for m in robustness_methods for c in conditions() for pp in processing]
            run_jobs("S2", jobs, cp, workers)
            cp["stages"]["S2"] = {"done": True, "prediction_jobs": len(jobs)}
            write_json(cp_file, cp)
        rows2 = [r for r in cp["summaries"] if r["stage"]=="S2"]
        processing_rank = [{"preprocessing": p, **statistics([r for r in rows2 if r["preprocessing"]==p])} for p in processing]
        processing_rank.sort(key=rank_key)
        chosen_processing = processing_rank[0]["preprocessing"]
        write_json(ROOT/"reports"/"S2_analysis.json", {"status": "completed", "ranked": processing_rank,
            "chosen_preprocessing": chosen_processing, "shared_across_finalists": True, "physical_validation": False})
        csv_rows(ROOT/"reports"/"S2_all_scores.csv", rows2)
        selection = []
        for speed in [2.5, 3.5]:
            for rate in [3, 6]:
                for t in read_json(ROOT/"plan.json")["driving_factors"]["templates"]:
                    selection.append({"id": f"sel_v{speed}_r{rate}_{t['id']}", "v_B_mps": speed,
                        "entry_rate_abs_deg_s": rate*t["entry_rate_multiplier"], "return_rate_abs_deg_s": rate*t["return_rate_multiplier"],
                        "alpha_peak_abs_deg": 10, "turn_heading_change_deg": 90})
        build_all(selection, count, "selection_v2", workers)
        variants = [Variant(w, margin, gate) for w in [2, 3] for margin in [0, .02, .05] for gate in [0, .1]]
        stress = [c for c in conditions() if c["id"] in ["clean", "delay100"]
                  or c["id"].startswith("noise100_s") or c["id"].startswith("combined100_s")]
        cases = [(partition, s["id"]) for s in designs]+[("selection_v2", s["id"]) for s in selection]
        if not cp["stages"].get("S3"):
            jobs = [job("S3", part, case, m, source, c, chosen_processing, variants) for part, case in cases for m in finalists for c in stress]
            run_jobs("S3", jobs, cp, workers)
            cp["stages"]["S3"] = {"done": True, "prediction_jobs": len(jobs), "variant_scores": len(jobs)*len(variants)}
            write_json(cp_file, cp)
        if not any(m.mode=="hold" for m in finalists) and not cp["stages"].get("S3_baseline"):
            jobs = [job("S3_baseline", part, case, Method("hold"), source, c, chosen_processing)
                    for part, case in cases for c in stress]
            run_jobs("S3_baseline", jobs, cp, workers)
            cp["stages"]["S3_baseline"] = {"done": True, "prediction_jobs": len(jobs)}
            write_json(cp_file, cp)
        rows3 = [r for r in cp["summaries"] if r["stage"]=="S3"]
        comparison = []
        for m in finalists:
            for v in variants:
                a = [r for r in rows3 if r["config_id"]==method_id(m) and r["EXIT_W_s"]==v.exit_W
                     and r["margin_m"]==v.margin and r["confirmation_s"]==v.confirmation]
                comparison.append({"config_id": method_id(m), **asdict(v), **statistics(a)})
        comparison.sort(key=rank_key)
        write_json(ROOT/"reports"/"S3_analysis.json", {"status": "completed", "ranked": comparison,
            "feasible_configurations": sum(r["passes_research_budget"] for r in comparison),
            "finalists": [asdict(m) for m in finalists], "preprocessing": chosen_processing,
            "final_independent_test_started": False, "physical_validation": False})
        csv_rows(ROOT/"reports"/"S3_all_scores.csv", rows3)
        csv_rows(ROOT/"reports"/"S3_baseline_scores.csv", [r for r in cp["summaries"] if r["stage"]=="S3_baseline"])
        csv_rows(ROOT/"reports"/"S3_joint_comparison.csv", comparison)
        cp["status"] = "S3_complete_S4_next"
        write_json(cp_file, cp)
        print("S0 THROUGH S3 COMPLETE; S4 AND FINAL TEST REQUIRE NEXT IMPLEMENTED BATCH", flush=True)
    except DeadlineReached as error:
        cp["status"] = "deadline_saved"
        write_json(cp_file, cp)
        print(str(error), flush=True)
    except Exception as error:
        cp["status"] = "needs_repair"
        cp["error"] = repr(error)
        write_json(cp_file, cp)
        raise
    finally:
        write_json(RUN/"runner_lock.json", {"pid": os.getpid(), "status": "stopped", "time": utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    main(parser.parse_args().workers)
