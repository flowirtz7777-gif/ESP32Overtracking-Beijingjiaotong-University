from __future__ import annotations

import numpy as np

from common import Vehicle, prediction_step


def observe(truth, condition):
    rng = np.random.default_rng(condition.get("seed", 202610142001))
    level = condition.get("noise_level", 0)
    alpha = truth["alpha"] + rng.normal(0, np.deg2rad(.15)*level, len(truth["time"]))
    state = truth["state"].copy()
    state[:, 3] += rng.normal(0, np.deg2rad(.25)*level, len(truth["time"]))
    v = np.maximum(0, truth["v_B"]+rng.normal(0, .04*level, len(truth["time"])))
    source = np.searchsorted(truth["time"], truth["time"]-condition.get("delay_s", 0)+1e-9, side="right")-1
    source = np.maximum(0, source)
    assert np.all(source <= np.arange(len(source)))
    return {**truth, "state": state[source], "alpha": alpha[source], "v_B": v[source],
            "measurement_time": truth["time"][source], "source_index": source}


def preprocess(observed, mode, vehicle=Vehicle()):
    output = {**observed, "state": observed["state"].copy(), "alpha": observed["alpha"].copy()}
    if "alpha_lp" in mode:
        tau = .05
        for k in range(1, len(output["alpha"])):
            dt = observed["time"][k]-observed["time"][k-1]
            output["alpha"][k] = output["alpha"][k-1]+dt/(tau+dt)*(observed["alpha"][k]-output["alpha"][k-1])
    if "age_hold" in mode:
        age = observed["time"]-observed["measurement_time"]
        if age.max() > .25+1e-8 or age.min() < -1e-8:
            raise ValueError("Measurement age outside declared compensation range")
        remaining = age.copy()
        while np.any(remaining > 1e-10):
            dt = np.minimum(.005, remaining)
            output["state"] = prediction_step(output["state"], output["alpha"], output["alpha"], output["alpha"],
                                               output["v_B"], vehicle, dt[:, None])
            remaining -= dt
    return output


def conditions():
    result = [{"id": "clean", "delay_s": 0, "noise_level": 0}]
    for level in [.5, 1., 2.]:
        for seed in range(3):
            result.append({"id": f"noise{round(level*100):03d}_s{seed+1}", "delay_s": 0,
                           "noise_level": level, "seed": 202610142001+seed})
    for delay in [.05, .1, .2]:
        result.append({"id": f"delay{round(delay*1000)}", "delay_s": delay, "noise_level": 0})
    for seed in range(3):
        result.append({"id": f"combined100_s{seed+1}", "delay_s": .1, "noise_level": 1., "seed": 202610142001+seed})
    return result
