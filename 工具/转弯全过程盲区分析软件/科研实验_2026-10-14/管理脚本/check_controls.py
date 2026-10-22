import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from common import read_json, write_json
from prediction import Method, historical_rates, future_alpha

methods = [Method(m) for m in ["hold", "linear", "damped_linear", "bounded_second_order"]]
methods += [Method("linear", gain=2), Method("bounded_second_order", acceleration_duration_s=1)]
rows = []
for case in ["v2_r2_symmetric", "v3_r4_fast_return", "v4_r8_fast_entry"]:
    data = np.load(ROOT/"datasets/development_v2_n70000"/case/"trajectory.npz")
    dot, ddot = historical_rates(data["alpha"])
    for method in methods:
        controls = np.column_stack([future_alpha(data["alpha"], dot, ddot, t, method) for t in np.arange(401)*.005])
        rate = np.rad2deg(np.max(np.abs(np.diff(controls, axis=1))/.005))
        rows.append({"case": case, "mode": method.mode, "gain": method.gain,
                     "acceleration_duration_s": method.acceleration_duration_s,
                     "future_max_rate_deg_s": float(rate), "estimator_rate_limit_deg_s": method.rate_limit_deg_s})
write_json(ROOT/"reports"/"S0_control_envelope_diagnostic.json", {"status": "diagnostic", "rows": rows,
    "input_derivative_limit_is_not_automatically_output_control_rate_limit": True})
print([(r["case"], r["mode"], r["gain"], round(r["future_max_rate_deg_s"], 3)) for r in rows])
