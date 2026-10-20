from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Vehicle:
    l: float = 4.0
    l_h: float = 1.8
    L: float = 13.5
    width: float = 2.0

    def mapping(self):
        return asdict(self)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def file_hash(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


def array_hash(array):
    array = np.ascontiguousarray(array)
    sha = hashlib.sha256(str((array.dtype.str, array.shape)).encode("ascii"))
    sha.update(array.tobytes())
    return sha.hexdigest()


def storage_guard(reserve_bytes=3 * 1024**3, budget_bytes=950 * 1024**2):
    free = shutil.disk_usage(ROOT).free
    used = sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())
    if free < reserve_bytes or used > budget_bytes:
        raise RuntimeError(f"Storage guard: free={free}, experiment_bytes={used}")
    return {"free_bytes": free, "experiment_bytes": used}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def derivative(state, alpha, v_B, vehicle):
    state = np.asarray(state)
    theta, phi = state[..., 2], state[..., 3]
    omega_tractor = v_B * np.tan(alpha) / vehicle.l
    omega_trailer = (v_B * np.sin(phi) + vehicle.l_h * omega_tractor * np.cos(phi)) / vehicle.L
    return np.stack((v_B * np.cos(theta), v_B * np.sin(theta), omega_tractor, omega_tractor - omega_trailer), axis=-1)


def prediction_step(state, alpha0, alphamid, alpha1, v_B, vehicle, dt):
    k1 = derivative(state, alpha0, v_B, vehicle)
    k2 = derivative(state + .5 * dt * k1, alphamid, v_B, vehicle)
    k3 = derivative(state + .5 * dt * k2, alphamid, v_B, vehicle)
    k4 = derivative(state + dt * k3, alpha1, v_B, vehicle)
    return state + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


def right_edge(states, vehicle):
    states = np.asarray(states)
    theta, phi = states[..., 2], states[..., 3]
    heading = theta - phi
    hitch = states[..., :2] + vehicle.l_h * np.stack((np.cos(theta), np.sin(theta)), axis=-1)
    rear = hitch - vehicle.L * np.stack((np.cos(heading), np.sin(heading)), axis=-1)
    normal = np.stack((np.sin(heading), -np.cos(heading)), axis=-1)
    return np.stack((hitch + vehicle.width / 2 * normal, rear + vehicle.width / 2 * normal), axis=-2)


def body_corners(states, vehicle):
    edge = right_edge(states, vehicle)
    heading = np.asarray(states)[..., 2] - np.asarray(states)[..., 3]
    normal = np.stack((np.sin(heading), -np.cos(heading)), axis=-1)
    front, rear = edge[..., 0, :], edge[..., 1, :]
    return np.stack((front, rear, rear - vehicle.width * normal, front - vehicle.width * normal), axis=-2)
