from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
import time

import numpy as np
import shapely

from common import ROOT, Vehicle, array_hash, file_hash, right_edge, storage_guard, utc_now, write_json, read_json
from geometry import complete_geometry, generate_target_pool, label_contacts, subset_indices, EDGE_NAMES, GEOMETRY_EPS
from prediction import Method, historical_rates, rollout
from scenarios import Maneuver, SinusoidalManeuver, integrate_reference

DATA = ROOT / "datasets" / "development_v2"


def source_signature():
    files = [ROOT / "src" / name for name in ["common.py", "scenarios.py", "geometry.py", "prediction.py", "foundation.py"]]
    return {p.name: file_hash(p) for p in files}


def build_dataset(spec, count=35000, partition="development_v2"):
    storage_guard()
    directory = ROOT / "datasets" / partition / spec["id"]
    start = time.perf_counter()
    signatures = source_signature()
    if (directory / "manifest.json").exists():
        manifest = read_json(directory / "manifest.json")
        if manifest["source_sha256"] != signatures or manifest["target_count"] != count:
            raise RuntimeError("Frozen dataset source/count changed; use a new dataset version")
        if read_json(directory / "profile.json")["design"] != spec:
            raise RuntimeError("Frozen input design changed")
        for name, sha in manifest["files"].items():
            if file_hash(directory / name) != sha:
                raise RuntimeError(f"Dataset hash mismatch {spec['id']}/{name}")
        return {**manifest["summary"], "resumed": True}
    vehicle = Vehicle()
    control = SinusoidalManeuver if spec.get("control_shape") == "sinusoidal" else Maneuver
    maneuver = control.from_spec(spec, vehicle)
    fine = integrate_reference(maneuver, .005, vehicle)
    denser = integrate_reference(maneuver, .0025, vehicle)
    print(f"REFERENCE {spec['id']} {time.perf_counter()-start:.1f}s", flush=True)
    edge = right_edge(fine["state"], vehicle)
    dense_edge = right_edge(denser["state"][::2], vehicle)
    error = float(np.linalg.norm(edge-dense_edge, axis=-1).max())
    if error > .005:
        raise AssertionError(f"Reference did not converge: {error}")
    segments, body_union, right_union = complete_geometry(fine["state"], vehicle)
    print(f"GEOMETRY {spec['id']} {time.perf_counter()-start:.1f}s", flush=True)
    if not shapely.is_valid(body_union) or not shapely.is_valid(right_union):
        raise AssertionError("Invalid truth geometry")
    xy, groups, sampling = generate_target_pool(body_union, right_union, count)
    print(f"TARGET POOL {spec['id']} {time.perf_counter()-start:.1f}s", flush=True)
    labels = label_contacts(xy, fine, segments, vehicle)
    # Geometry union and segment labelers must agree for every frozen target.
    expected = shapely.dwithin(shapely.points(xy), body_union, .05+GEOMETRY_EPS)
    if not np.array_equal(expected, np.isfinite(labels["contact_time"])):
        mismatch = np.flatnonzero(expected != np.isfinite(labels["contact_time"]))
        write_json(ROOT / "reports" / ("S0_label_mismatch_"+spec["id"]+".json"),
                   {"indices": mismatch.tolist(), "xy": xy[mismatch].tolist()})
        raise AssertionError(f"Continuous sweep/target-label mismatch: {len(mismatch)}")
    if np.any(np.isfinite(labels["contact_time"][groups == 2])):
        raise AssertionError("Near-negative pool contains a contact")
    stride = 4
    observed = {key: fine[key][::stride] for key in ["time", "state", "alpha", "v_B", "true_phase"]}
    check = {"frame_count": len(observed["time"]), "duration_s": maneuver.end,
             "theta_end_rad": float(fine["state"][-1, 2]),
             "phi_max_deg": float(np.rad2deg(np.abs(fine["state"][:, 3])).max()),
             "reference_edge_error_005_vs_0025_m": error,
             "right_contacts": int(np.sum(labels["edge"] == 2)),
             "right_by_stratum": {str(g): int(np.sum((labels["edge"]==2)&(groups==g))) for g in range(3)},
             "front_ignored": int(labels["front_ignored"].sum()),
             "negative_count": int(np.sum(~np.isfinite(labels["contact_time"]))),
             "edge_counts": {name: int(np.sum(labels["edge"] == code)) for code, name in EDGE_NAMES.items()},
             "pool": sampling, "target_count": count,
             "id": spec["id"], "wall_s": time.perf_counter()-start}
    if check["right_contacts"] < 1000:
        raise AssertionError(f"Too few RIGHT contacts in frozen pool: {check['right_contacts']}")
    if check["right_by_stratum"]["0"] < 100 or check["right_by_stratum"]["1"] < 100:
        raise AssertionError("RIGHT boundary and interior strata both require valid coverage")
    directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(directory / "trajectory.npz", **observed, fine_time=fine["time"], fine_state=fine["state"])
    np.savez_compressed(directory / "targets.npz", xy=xy, group=groups, **labels)
    write_json(directory / "profile.json", {"design": spec, "control": asdict(maneuver), "vehicle": vehicle.mapping(),
                                            "phase_is_offline_stratification_only": True, "summary": check})
    write_json(directory / "manifest.json", {"status": "frozen", "target_count": count,
        "partition": partition, "geometry_epsilon_m": GEOMETRY_EPS,
        "source_sha256": signatures, "files": {name: file_hash(directory/name) for name in ["trajectory.npz", "targets.npz", "profile.json"]},
        "target_coordinates_sha256": array_hash(xy), "contact_label_sha256": array_hash(labels["contact_time"]),
        "summary": check})
    return check


def elementary_checks():
    vehicle = Vehicle()
    t = np.arange(60)*.02
    a = .03+.02*t
    dot, ddot = historical_rates(a)
    assert np.max(np.abs(dot[12:]-.02)) < 1e-11
    assert np.max(np.abs(ddot[12:])) < 1e-10
    state = np.tile([0, 0, 0, 0], (len(t), 1)).astype(float)
    observed = {"time": t, "alpha": a, "v_B": np.full(len(t), 3.), "state": state}
    checked = 0
    for mode in ["hold", "linear", "damped_linear", "bounded_second_order"]:
        method = Method(mode)
        x = rollout(observed, method, 2)
        y = rollout(observed, method, 3)
        assert np.array_equal(x, y[:, :x.shape[1]])
        poison = {k: v.copy() for k, v in observed.items()}
        poison["alpha"][30:] += .1
        poison["state"][30:] += 10
        z = rollout(poison, method, 2)
        assert np.array_equal(x[:30], z[:30])
        checked += 2
    straight = {"time": t, "alpha": np.zeros(len(t)), "v_B": np.full(len(t), 3.), "state": state}
    result = rollout(straight, Method("hold"), 2)
    assert np.max(np.abs(result[:, -1, 0]-6)) < 1e-12
    assert np.max(np.abs(result[:, :, 1:])) < 1e-12
    write_json(ROOT / "reports" / "S0_elementary.json", {"status": "passed", "past_only_and_prefix_checks": checked,
        "straight_analytic_check": True, "historical_linear_derivative_check": True,
        "source_signature": source_signature(), "created_at": utc_now()})
    return checked


def run(count=35000, workers=4, pilot=True):
    elementary_checks()
    specs = read_json(ROOT / "scenario_matrix.json")
    if pilot:
        pick = ["v2_r2_symmetric", "v2_r4_fast_entry", "v2_r8_fast_return",
                "v3_r2_fast_entry", "v3_r4_fast_return", "v3_r8_symmetric",
                "v4_r2_fast_return", "v4_r4_symmetric", "v4_r8_fast_entry"]
        specs = [s for s in specs if s["id"] in pick]
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(build_dataset, s, count): s["id"] for s in specs}
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(f"DATASET {len(rows)}/{len(specs)} {row['id']} n={row['target_count']} RIGHT={row['right_contacts']} {row['wall_s']:.1f}s", flush=True)
            write_json(ROOT / "reports" / ("S0_pilot_progress.json" if pilot else "S0_all_progress.json"),
                       {"status": "running", "completed": len(rows), "total": len(specs), "rows": rows})
    report = {"status": "reference_sampling_passed_density_pending", "pilot": pilot,
              "datasets": len(rows), "target_count": count, "rows": sorted(rows, key=lambda r: r["id"]),
              "physical_validation": False, "source_signature": source_signature()}
    write_json(ROOT / "reports" / ("S0_pilot_reference_sampling.json" if pilot else "S0_all_reference_sampling.json"), report)
    print("FOUNDATION REFERENCE AND SAMPLING COMPLETE; DENSITY GATE STILL PENDING", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--count", type=int, default=35000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.count < 20000:
        raise ValueError("User-authorized formal minimum is 20000 unique points")
    run(args.count, args.workers, not args.all)
