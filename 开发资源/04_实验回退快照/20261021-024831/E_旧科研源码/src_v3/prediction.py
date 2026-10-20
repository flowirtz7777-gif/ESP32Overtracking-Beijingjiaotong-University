from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from common import Vehicle, prediction_step


@dataclass(frozen=True)
class Method:
    mode: str
    gain: float = 1.0
    decay_s: float = .5
    acceleration_duration_s: float = .25
    history_s: float = .2
    alpha_limit_deg: float = 30.0
    rate_limit_deg_s: float = 32.0
    acceleration_limit_deg_s2: float = 160.0
    dt: float = .02


def historical_rates(alpha, dt=.02, history=.2):
    n = max(3, round(history/dt)+1)
    t = (np.arange(n)-(n-1))*dt
    matrix = np.column_stack((np.ones(n), t, t*t))
    coefficients = np.linalg.pinv(matrix)
    padded = np.pad(alpha, (n-1, 0), mode="edge")
    dot = np.convolve(padded, coefficients[1, ::-1], mode="valid")
    ddot = np.convolve(padded, 2*coefficients[2, ::-1], mode="valid")
    dot[0] = ddot[0] = 0
    return dot, ddot


def future_alpha(alpha, dot, ddot, u, method):
    dot = np.clip(dot, -np.deg2rad(method.rate_limit_deg_s), np.deg2rad(method.rate_limit_deg_s))
    ddot = np.clip(ddot, -np.deg2rad(method.acceleration_limit_deg_s2), np.deg2rad(method.acceleration_limit_deg_s2))
    limit = np.deg2rad(method.rate_limit_deg_s)
    rate = np.clip(method.gain*dot, -limit, limit)
    if method.mode == "hold":
        value = alpha
    elif method.mode == "linear":
        value = alpha + rate*u
    elif method.mode == "damped_linear":
        decay = np.maximum(method.decay_s, np.abs(rate)/np.deg2rad(method.acceleration_limit_deg_s2))
        value = alpha + rate*decay*(-np.expm1(-u/decay))
    elif method.mode == "bounded_second_order":
        bound = np.where(ddot >= 0, limit, -limit)
        crossing = np.full_like(rate, np.inf)
        np.divide(bound-rate, ddot, out=crossing, where=np.abs(ddot)>1e-12)
        active = np.minimum(min(u, method.acceleration_duration_s), np.maximum(0, crossing))
        terminal_rate = np.clip(rate+ddot*active, -limit, limit)
        value = alpha + rate*active + .5*ddot*active*active + terminal_rate*(u-active)
    else:
        raise ValueError(method.mode)
    return np.clip(value, -np.deg2rad(method.alpha_limit_deg), np.deg2rad(method.alpha_limit_deg))


def rollout(observed, method, horizon=2.0, vehicle=Vehicle()):
    count = round(horizon/method.dt)
    if abs(count*method.dt-horizon) > 1e-8:
        raise ValueError("Horizon must be an integer number of steps")
    alpha = observed["alpha"]
    dot, ddot = historical_rates(alpha, history=method.history_s)
    n = len(alpha)
    sequence = np.empty((n, count+1, 4))
    sequence[:, 0] = observed["state"]
    v = observed["v_B"]
    for k in range(count):
        u = k*method.dt
        sequence[:, k+1] = prediction_step(sequence[:, k],
            future_alpha(alpha, dot, ddot, u, method),
            future_alpha(alpha, dot, ddot, u+.5*method.dt, method),
            future_alpha(alpha, dot, ddot, u+method.dt, method), v, vehicle, method.dt)
    return sequence


def observed_phase(observed, history=.2):
    dot, _ = historical_rates(observed["alpha"], history=history)
    phase = np.zeros(len(dot), dtype=np.int8)
    current = 0
    for k, (alpha, rate) in enumerate(zip(observed["alpha"], dot)):
        if abs(alpha) > np.deg2rad(.5):
            current = 3 if alpha*rate < -np.deg2rad(.5)*np.deg2rad(.2) else (1 if current in [0, 1] else 2)
            if current == 1 and abs(rate) < np.deg2rad(.2):
                current = 2
        elif current:
            current = 4
        phase[k] = current
    return phase
