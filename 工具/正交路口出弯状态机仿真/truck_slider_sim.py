"""
Interactive Phase-1 truck/trailer replay with a time slider.

The default path replays the current PID scenario CSV exported by
pid工况仿真导出器.html. If that CSV is absent, the script falls back to a
Python port of the exporter's default PID simulation parameters.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
from matplotlib.widgets import Slider
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR / "scenarios" / "pid_scenario_20260530_020804.csv"
rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False
MATLAB_DEMO_TARGETS_20260530_020804 = np.array(
    [
        [1.034546627, 9.064921825],
        [5.165832032, 24.046315542],
        [15.162112188, 34.264469347],
        [25.335459623, 36.779763982],
        [41.480453564, 38.856137380],
    ],
    dtype=float,
)


@dataclass
class Config:
    l: float = 4.0
    l_h: float = 1.8
    L: float = 13.5
    width: float = 2.0
    speed: float = 3.0
    total_time: float = 35.0
    dt: float = 0.02
    smoothing: float = 0.95
    theta_start_deg: float = 90.0
    theta_end_deg: float = 0.0
    t1: float = 3.0
    t2: float = 15.0
    kp_theta: float = 0.8
    ki_theta: float = 0.02
    kd_theta: float = 0.02
    integral_theta_limit: float = 0.4
    kp_phi: float = 0.3
    ki_phi: float = 0.01
    kd_phi: float = 0.01
    integral_phi_limit: float = 0.2
    alpha_limit_deg: float = 30.0
    phi_limit_deg: float = 15.0


def clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def wrap_pi(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def deg2rad(value: float) -> float:
    return value * math.pi / 180.0


def rad2deg(value: float) -> float:
    return value * 180.0 / math.pi


def build_reference_heading(time_s: float, cfg: Config) -> float:
    theta_start = deg2rad(cfg.theta_start_deg)
    theta_end = deg2rad(cfg.theta_end_deg)
    if time_s <= cfg.t1:
        return theta_start
    if time_s <= cfg.t2:
        ratio = (time_s - cfg.t1) / (cfg.t2 - cfg.t1)
        return theta_start + (theta_end - theta_start) * ratio
    return theta_end


def simulate_default_exporter(cfg: Config) -> dict[str, np.ndarray]:
    """Port of the current HTML exporter's default simulation logic."""
    t = np.arange(0.0, cfg.total_time + 0.5 * cfg.dt, cfg.dt)
    n = len(t)

    x_a = np.zeros(n)
    y_a = np.zeros(n)
    x_b = np.zeros(n)
    y_b = np.zeros(n)
    x_h = np.zeros(n)
    y_h = np.zeros(n)
    x_t = np.zeros(n)
    y_t = np.zeros(n)
    theta = np.zeros(n)
    theta_t = np.zeros(n)
    theta_ref = np.zeros(n)
    alpha = np.zeros(n)
    phi = np.zeros(n)

    x_a[0] = 0.0
    y_a[0] = cfg.l
    theta[0] = deg2rad(cfg.theta_start_deg)
    x_h[0] = x_b[0] + cfg.l_h * math.cos(theta[0])
    y_h[0] = y_b[0] + cfg.l_h * math.sin(theta[0])
    theta_t[0] = theta[0] - phi[0]
    x_t[0] = x_h[0] - cfg.L * math.cos(theta_t[0])
    y_t[0] = y_h[0] - cfg.L * math.sin(theta_t[0])

    integral_theta = 0.0
    integral_phi = 0.0
    prev_e_theta = 0.0
    prev_e_phi = 0.0
    alpha_limit = deg2rad(cfg.alpha_limit_deg)
    phi_limit = deg2rad(cfg.phi_limit_deg)

    for i, time_s in enumerate(t):
        theta_ref[i] = build_reference_heading(time_s, cfg)

    for k in range(n - 1):
        theta_k = math.atan2(y_a[k] - y_b[k], x_a[k] - x_b[k])
        theta[k] = theta_k
        theta_t[k] = theta_k - phi[k]

        e_theta = wrap_pi(theta_ref[k] - theta_k)
        integral_theta = clamp(
            integral_theta + e_theta * cfg.dt,
            -cfg.integral_theta_limit,
            cfg.integral_theta_limit,
        )
        derivative_theta = (e_theta - prev_e_theta) / cfg.dt
        alpha_1 = (
            cfg.kp_theta * e_theta
            + cfg.ki_theta * integral_theta
            + cfg.kd_theta * derivative_theta
        )

        e_phi = -phi[k]
        integral_phi = clamp(
            integral_phi + e_phi * cfg.dt,
            -cfg.integral_phi_limit,
            cfg.integral_phi_limit,
        )
        derivative_phi = (e_phi - prev_e_phi) / cfg.dt
        delta_alpha = (
            cfg.kp_phi * e_phi
            + cfg.ki_phi * integral_phi
            + cfg.kd_phi * derivative_phi
        )

        alpha_k = alpha_1 + delta_alpha
        if k > 0:
            alpha_k = cfg.smoothing * alpha[k - 1] + (1.0 - cfg.smoothing) * alpha_k
        alpha_k = clamp(alpha_k, -alpha_limit, alpha_limit)
        alpha[k] = alpha_k

        v_b = cfg.speed * math.cos(alpha_k)
        v_bx = v_b * math.cos(theta_k)
        v_by = v_b * math.sin(theta_k)
        v_ax = cfg.speed * math.cos(theta_k + alpha_k)
        v_ay = cfg.speed * math.sin(theta_k + alpha_k)

        x_a[k + 1] = x_a[k] + v_ax * cfg.dt
        y_a[k + 1] = y_a[k] + v_ay * cfg.dt
        x_b[k + 1] = x_b[k] + v_bx * cfg.dt
        y_b[k + 1] = y_b[k] + v_by * cfg.dt

        current_l = math.hypot(x_a[k + 1] - x_b[k + 1], y_a[k + 1] - y_b[k + 1])
        delta_l = current_l - cfg.l
        if abs(delta_l) > 1e-5 and current_l > 1e-9:
            adjust_x = ((x_a[k + 1] - x_b[k + 1]) / current_l) * delta_l
            adjust_y = ((y_a[k + 1] - y_b[k + 1]) / current_l) * delta_l
            x_b[k + 1] += adjust_x
            y_b[k + 1] += adjust_y

        theta_next = math.atan2(y_a[k + 1] - y_b[k + 1], x_a[k + 1] - x_b[k + 1])
        theta[k + 1] = theta_next

        omega_1 = cfg.speed * math.sin(alpha_k) / cfg.l
        omega_2 = (v_b * math.sin(phi[k]) + cfg.l_h * omega_1 * math.cos(phi[k])) / cfg.L
        phi[k + 1] = clamp(phi[k] + (omega_1 - omega_2) * cfg.dt, -phi_limit, phi_limit)

        x_h[k + 1] = x_b[k + 1] + cfg.l_h * math.cos(theta_next)
        y_h[k + 1] = y_b[k + 1] + cfg.l_h * math.sin(theta_next)
        theta_t[k + 1] = theta_next - phi[k + 1]
        x_t[k + 1] = x_h[k + 1] - cfg.L * math.cos(theta_t[k + 1])
        y_t[k + 1] = y_h[k + 1] - cfg.L * math.sin(theta_t[k + 1])

        prev_e_theta = e_theta
        prev_e_phi = e_phi

    if n > 1:
        alpha[-1] = alpha[-2]

    return {
        "time_s": t,
        "xA_m": x_a,
        "yA_m": y_a,
        "xB_m": x_b,
        "yB_m": y_b,
        "xH_m": x_h,
        "yH_m": y_h,
        "xT_m": x_t,
        "yT_m": y_t,
        "theta_rad": theta,
        "theta_t_rad": theta_t,
        "alpha_rad": alpha,
        "phi_rad": phi,
        "v_input_mps": np.full(n, cfg.speed),
        "width_m": np.full(n, cfg.width),
        "l_m": np.full(n, cfg.l),
        "l_h_m": np.full(n, cfg.l_h),
        "L_m": np.full(n, cfg.L),
    }


def load_csv(path: Path) -> dict[str, np.ndarray]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    cols = {name: np.array([float(row[name]) for row in rows]) for name in reader.fieldnames or []}
    return cols


def config_from_data(data: dict[str, np.ndarray], fallback: Config | None = None) -> Config:
    cfg = fallback or Config()
    field_map = {
        "l": "l_m",
        "l_h": "l_h_m",
        "L": "L_m",
        "width": "width_m",
        "speed": "v_input_mps",
    }
    for attr, col in field_map.items():
        if col in data:
            setattr(cfg, attr, float(data[col][0]))
    if "time_s" in data and len(data["time_s"]) > 1:
        cfg.dt = float(data["time_s"][1] - data["time_s"][0])
    if "phi_max_rad" in data:
        cfg.phi_limit_deg = rad2deg(float(data["phi_max_rad"][0]))
    return cfg


def load_targets_csv(path: Path) -> np.ndarray:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        names = reader.fieldnames or []

    candidates = [("x", "y"), ("x_m", "y_m"), ("target_x_m", "target_y_m")]
    for x_col, y_col in candidates:
        if x_col in names and y_col in names:
            return np.array([[float(row[x_col]), float(row[y_col])] for row in rows], dtype=float)
    raise ValueError("Target CSV must contain x/y, x_m/y_m, or target_x_m/target_y_m columns.")


def parse_targets_text(text: str) -> np.ndarray:
    pairs = []
    for item in text.replace(";", "\n").splitlines():
        item = item.strip()
        if not item:
            continue
        parts = item.replace(",", " ").split()
        if len(parts) != 2:
            raise ValueError(f"Bad target pair: {item!r}")
        pairs.append([float(parts[0]), float(parts[1])])
    if not pairs:
        raise ValueError("No target points were provided.")
    return np.array(pairs, dtype=float)


def prompt_path(prompt: str) -> Path | None:
    raw = input(prompt).strip().strip('"')
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = SCRIPT_DIR / path
    return path


def choose_scenario() -> tuple[dict[str, np.ndarray], Config, str, Path | None]:
    print("\n=== Truck Slider Replay ===")
    print("1) Use default scenario CSV and MATLAB demo targets")
    print("2) Import another scenario CSV")
    print("3) Use built-in exporter default simulation")
    choice = input("Choose [1/2/3, default 1]: ").strip() or "1"

    cfg = Config()
    csv_path: Path | None = None
    if choice == "2":
        csv_path = prompt_path("Scenario CSV path: ")
        if csv_path is None or not csv_path.exists():
            raise FileNotFoundError(f"Scenario CSV not found: {csv_path}")
        data = load_csv(csv_path)
        cfg = config_from_data(data, cfg)
        source_label = f"CSV: {csv_path.name}"
    elif choice == "3":
        data = simulate_default_exporter(cfg)
        source_label = "Python fallback: exporter default parameters"
    else:
        if DEFAULT_CSV.exists():
            csv_path = DEFAULT_CSV
            data = load_csv(DEFAULT_CSV)
            cfg = config_from_data(data, cfg)
            source_label = f"CSV: {DEFAULT_CSV.name}"
        else:
            data = simulate_default_exporter(cfg)
            source_label = "Python fallback: exporter default parameters"

    print("\nVehicle parameters loaded:")
    print(f"  l={cfg.l:.3f} m, l_h={cfg.l_h:.3f} m, L={cfg.L:.3f} m, width={cfg.width:.3f} m")
    print(f"  speed={cfg.speed:.3f} m/s, dt={cfg.dt:.4f} s, phi_limit={cfg.phi_limit_deg:.2f} deg")
    return data, cfg, source_label, csv_path


def choose_targets(data: dict[str, np.ndarray], cfg: Config, csv_path: Path | None) -> np.ndarray:
    print("\nTarget source:")
    print("1) Use default/demo targets for this scenario")
    print("2) Import target CSV (columns: x,y or x_m,y_m)")
    print("3) Type target centers manually")
    choice = input("Choose [1/2/3, default 1]: ").strip() or "1"

    if choice == "2":
        target_path = prompt_path("Target CSV path: ")
        if target_path is None or not target_path.exists():
            raise FileNotFoundError(f"Target CSV not found: {target_path}")
        targets = load_targets_csv(target_path)
    elif choice == "3":
        print("Enter target centers as 'x,y; x,y; ...' or one 'x y' pair per line.")
        text = input("Targets: ")
        targets = parse_targets_text(text)
    else:
        targets = make_demo_targets(data, cfg)

    print("\nTargets loaded:")
    for i, xy in enumerate(targets, start=1):
        print(f"  R{i}: ({xy[0]:.6f}, {xy[1]:.6f})")
    return targets


def kinematics_step(state: np.ndarray, alpha: float, v: float, cfg: Config, dt: float) -> np.ndarray:
    x_b, y_b, theta, phi = state
    omega_1 = v * math.sin(alpha) / cfg.l
    v_b = v * math.cos(alpha)
    omega_2 = (v_b * math.sin(phi) + cfg.l_h * omega_1 * math.cos(phi)) / cfg.L
    phi_limit = deg2rad(cfg.phi_limit_deg)
    return np.array(
        [
            x_b + v_b * math.cos(theta) * dt,
            y_b + v_b * math.sin(theta) * dt,
            theta + omega_1 * dt,
            clamp(phi + (omega_1 - omega_2) * dt, -phi_limit, phi_limit),
        ],
        dtype=float,
    )


def derive_points_from_state(state: np.ndarray, cfg: Config) -> dict[str, np.ndarray | float]:
    x_b, y_b, theta, phi = state
    h = np.array([x_b + cfg.l_h * math.cos(theta), y_b + cfg.l_h * math.sin(theta)])
    theta_t = theta - phi
    return {
        "A": np.array([x_b + cfg.l * math.cos(theta), y_b + cfg.l * math.sin(theta)]),
        "B": np.array([x_b, y_b]),
        "H": h,
        "T": h - cfg.L * np.array([math.cos(theta_t), math.sin(theta_t)]),
        "theta_t": theta_t,
    }


def current_trailer_body(state: np.ndarray, cfg: Config) -> np.ndarray:
    points = derive_points_from_state(state, cfg)
    right_normal = np.array([math.sin(points["theta_t"]), -math.cos(points["theta_t"])])
    half_w = 0.5 * cfg.width
    h = points["H"]
    t = points["T"]
    return np.vstack([h + half_w * right_normal, t + half_w * right_normal,
                      t - half_w * right_normal, h - half_w * right_normal])


def predict_swept_raw(
    state: np.ndarray,
    alpha_now: float,
    v_now: float,
    cfg: Config,
    horizon_s: float,
    dt_pred: float = 0.02,
) -> np.ndarray:
    """Raw right-edge swept polygon for the live Python view."""
    steps = int(math.floor(horizon_s / dt_pred))
    state_i = np.array(state, dtype=float)
    h_right = []
    t_right = []
    half_w = 0.5 * cfg.width

    for i in range(steps + 1):
        points = derive_points_from_state(state_i, cfg)
        right_normal = np.array([math.sin(points["theta_t"]), -math.cos(points["theta_t"])])
        h_right.append(points["H"] + half_w * right_normal)
        t_right.append(points["T"] + half_w * right_normal)
        if i < steps:
            state_i = kinematics_step(state_i, alpha_now, v_now, cfg, dt_pred)

    return np.vstack([h_right, np.asarray(t_right)[::-1]])


def points_in_poly(points: np.ndarray, poly: np.ndarray) -> np.ndarray:
    x = points[:, 0]
    y = points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    xj = poly[-1, 0]
    yj = poly[-1, 1]
    for xi, yi in poly:
        cond = (yi > y) != (yj > y)
        x_intersect = xi + (y - yi) * (xj - xi) / ((yj - yi) + 1e-300)
        inside ^= cond & (x < x_intersect)
        xj, yj = xi, yi
    return inside


def target_risk_by_ttc(
    state: np.ndarray,
    alpha_now: float,
    v_now: float,
    targets: np.ndarray,
    cfg: Config,
    dt_pred: float = 0.02,
) -> tuple[np.ndarray, np.ndarray]:
    """Classify targets by first future trailer-body occupancy time.

    The plotted PolyW/A/I windows are useful geometry, but center-point risk
    should answer a temporal question: will the trailer rectangle cover this
    target center within 0.3/1.0/2.0 seconds?
    """
    ttc = np.full(len(targets), np.inf)
    state_i = np.array(state, dtype=float)
    steps = int(math.floor(2.0 / dt_pred))

    for step in range(steps + 1):
        tau = step * dt_pred
        body = current_trailer_body(state_i, cfg)
        hits = points_in_poly(targets, body)
        newly_hit = hits & np.isinf(ttc)
        ttc[newly_hit] = tau
        if step < steps:
            state_i = kinematics_step(state_i, alpha_now, v_now, cfg, dt_pred)

    risk = np.zeros(len(targets), dtype=int)
    risk[ttc < 2.0] = 1
    risk[ttc < 1.0] = 2
    risk[ttc < 0.3] = 3
    return risk, ttc


def make_demo_targets(data: dict[str, np.ndarray], cfg: Config) -> np.ndarray:
    """Match the MATLAB demo target placement strategy closely."""
    is_default_scenario = (
        len(data["time_s"]) == 1751
        and abs(float(data["time_s"][-1]) - 35.0) < 1e-9
        and abs(float(data["l_m"][0]) - 4.0) < 1e-9
        and abs(float(data["l_h_m"][0]) - 1.8) < 1e-9
        and abs(float(data["L_m"][0]) - 13.5) < 1e-9
        and abs(float(data["width_m"][0]) - 2.0) < 1e-9
    )
    if is_default_scenario:
        return MATLAB_DEMO_TARGETS_20260530_020804.copy()

    n = len(data["time_s"])
    keyframes = np.unique(np.rint(np.linspace(0, n - 1, 20)).astype(int))
    n_kf = len(keyframes)
    pick = np.unique(np.rint(np.linspace(2, max(2, round(n_kf * 0.7) - 1), 5)).astype(int))
    if len(pick) < 5:
        pick = np.rint(np.linspace(2, max(2, round(n_kf * 0.8) - 1), 5)).astype(int)
    sample_idx = keyframes[pick[:5]]

    rng = np.random.default_rng(42)
    targets = []
    half_w = 0.5 * cfg.width

    for k_now in sample_idx:
        future_k = min(n - 1, int(k_now) + 50)
        theta_t_f = data["theta_rad"][future_k] - data["phi_rad"][future_k]

        h = np.array([data["xH_m"][future_k], data["yH_m"][future_k]])
        t = np.array([data["xT_m"][future_k], data["yT_m"][future_k]])
        right_normal = np.array([math.sin(theta_t_f), -math.cos(theta_t_f)])
        body_mid = (h + half_w * right_normal + t + half_w * right_normal) / 2.0

        if future_k < n - 1:
            theta_t_next = data["theta_rad"][future_k + 1] - data["phi_rad"][future_k + 1]
            d_theta_t = wrap_pi(theta_t_next - theta_t_f)
        elif future_k > 0:
            theta_t_prev = data["theta_rad"][future_k - 1] - data["phi_rad"][future_k - 1]
            d_theta_t = wrap_pi(theta_t_f - theta_t_prev)
        else:
            d_theta_t = 0.0

        inward_dir = -right_normal if d_theta_t > 1e-4 else right_normal
        side_offset = -0.3 + 0.6 * rng.random()
        targets.append(body_mid + side_offset * inward_dir)

    return np.asarray(targets)


def vehicle_patch(center_a: np.ndarray, center_b: np.ndarray, width: float, color: str, alpha: float):
    heading = center_a - center_b
    heading = heading / max(np.linalg.norm(heading), 1e-12)
    right_normal = np.array([heading[1], -heading[0]])
    pts = np.vstack(
        [
            center_a + 0.5 * width * right_normal,
            center_a - 0.5 * width * right_normal,
            center_b - 0.5 * width * right_normal,
            center_b + 0.5 * width * right_normal,
        ]
    )
    return Polygon(pts, closed=True, facecolor=color, edgecolor=color, alpha=alpha, linewidth=1.4)


def patch_from_poly(poly: np.ndarray, color: str, alpha: float, label: str) -> Polygon:
    return Polygon(poly, closed=True, facecolor=color, edgecolor=color, alpha=alpha, linewidth=1.2, label=label)


def build_plot(data: dict[str, np.ndarray], targets: np.ndarray, cfg: Config, source_label: str) -> None:
    t = data["time_s"]
    fig, ax = plt.subplots(figsize=(12, 7))
    plt.subplots_adjust(bottom=0.18)

    ax.plot(data["xH_m"], data["yH_m"], color="#3568d4", linewidth=1.5, label="H path")
    ax.plot(data["xT_m"], data["yT_m"], color="#2f9d52", linewidth=1.5, label="T path")
    ax.plot(data["xB_m"], data["yB_m"], color="#555555", linewidth=1.0, linestyle="--", label="B path")

    risk_colors = {
        0: "#59a14f",  # safe
        1: "#edc948",  # PolyW
        2: "#f28e2b",  # PolyA
        3: "#e15759",  # PolyI or current body
    }
    target_scatter = ax.scatter(
        targets[:, 0],
        targets[:, 1],
        s=130,
        c=[risk_colors[0]] * len(targets),
        edgecolors="black",
        alpha=0.45,
        linewidths=1.0,
        zorder=7,
    )
    center_scatter = ax.scatter(
        targets[:, 0],
        targets[:, 1],
        s=32,
        c="black",
        marker="+",
        alpha=0.75,
        linewidths=1.1,
        zorder=8,
    )
    for i, xy in enumerate(targets, start=1):
        ax.text(xy[0] + 0.35, xy[1], f"R{i}", fontsize=11, weight="bold", va="center")

    initial_state = np.array([data["xB_m"][0], data["yB_m"][0], data["theta_rad"][0], data["phi_rad"][0]])
    poly_w = patch_from_poly(predict_swept_raw(initial_state, data["alpha_rad"][0], data["v_input_mps"][0], cfg, 2.0),
                             risk_colors[1], 0.12, "PolyW 2.0s")
    poly_a = patch_from_poly(predict_swept_raw(initial_state, data["alpha_rad"][0], data["v_input_mps"][0], cfg, 1.0),
                             risk_colors[2], 0.18, "PolyA 1.0s")
    poly_i = patch_from_poly(predict_swept_raw(initial_state, data["alpha_rad"][0], data["v_input_mps"][0], cfg, 0.3),
                             risk_colors[3], 0.24, "PolyI 0.3s")
    body_now_patch = patch_from_poly(current_trailer_body(initial_state, cfg), "#7f7f7f", 0.16, "BodyNow")
    for patch in (poly_w, poly_a, poly_i, body_now_patch):
        patch.set_zorder(2)
        ax.add_patch(patch)

    tractor = vehicle_patch(
        np.array([data["xA_m"][0], data["yA_m"][0]]),
        np.array([data["xB_m"][0], data["yB_m"][0]]),
        cfg.width,
        "#4c78a8",
        0.45,
    )
    trailer = vehicle_patch(
        np.array([data["xH_m"][0], data["yH_m"][0]]),
        np.array([data["xT_m"][0], data["yT_m"][0]]),
        cfg.width,
        "#f58518",
        0.42,
    )
    ax.add_patch(tractor)
    ax.add_patch(trailer)

    point_plot, = ax.plot([], [], "ko", markersize=4)
    time_text = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top", fontsize=11)

    x_all = np.concatenate([data["xA_m"], data["xB_m"], data["xH_m"], data["xT_m"], targets[:, 0]])
    y_all = np.concatenate([data["yA_m"], data["yB_m"], data["yH_m"], data["yT_m"], targets[:, 1]])
    pad = 4.0
    ax.set_xlim(float(x_all.min() - pad), float(x_all.max() + pad))
    ax.set_ylim(float(y_all.min() - pad), float(y_all.max() + pad))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.28)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title("Prediction Simulation Demo")
    legend_handles = [
        Line2D([0], [0], color="#3568d4", lw=1.5, label="H path"),
        Line2D([0], [0], color="#2f9d52", lw=1.5, label="T path"),
        Line2D([0], [0], color="#555555", lw=1.0, linestyle="--", label="B path"),
        poly_w,
        poly_a,
        poly_i,
        body_now_patch,
        Line2D([0], [0], marker="o", color="w", markerfacecolor=risk_colors[0], markeredgecolor="black", alpha=0.45, markersize=9, label="Target: safe"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=risk_colors[1], markeredgecolor="black", alpha=0.45, markersize=9, label="Target: PolyW"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=risk_colors[2], markeredgecolor="black", alpha=0.45, markersize=9, label="Target: PolyA"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=risk_colors[3], markeredgecolor="black", alpha=0.45, markersize=9, label="Target: PolyI/BodyNow"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=8)

    slider_ax = fig.add_axes([0.12, 0.07, 0.76, 0.035])
    slider = Slider(slider_ax, "time / s", float(t[0]), float(t[-1]), valinit=float(t[0]), valstep=float(cfg.dt))

    def update(time_s: float) -> None:
        k = int(np.clip(np.searchsorted(t, time_s), 0, len(t) - 1))
        state = np.array([data["xB_m"][k], data["yB_m"][k], data["theta_rad"][k], data["phi_rad"][k]])
        alpha_now = float(data["alpha_rad"][k])
        v_now = float(data["v_input_mps"][k])
        swept_w = predict_swept_raw(state, alpha_now, v_now, cfg, 2.0)
        swept_a = predict_swept_raw(state, alpha_now, v_now, cfg, 1.0)
        swept_i = predict_swept_raw(state, alpha_now, v_now, cfg, 0.3)
        body_now = current_trailer_body(state, cfg)

        poly_w.set_xy(swept_w)
        poly_a.set_xy(swept_a)
        poly_i.set_xy(swept_i)
        body_now_patch.set_xy(body_now)

        risk, ttc = target_risk_by_ttc(state, alpha_now, v_now, targets, cfg)
        target_scatter.set_facecolors([risk_colors[int(level)] for level in risk])
        center_scatter.set_offsets(targets)

        tractor.set_xy(
            vehicle_patch(
                np.array([data["xA_m"][k], data["yA_m"][k]]),
                np.array([data["xB_m"][k], data["yB_m"][k]]),
                cfg.width,
                "#4c78a8",
                0.45,
            ).get_xy()
        )
        trailer.set_xy(
            vehicle_patch(
                np.array([data["xH_m"][k], data["yH_m"][k]]),
                np.array([data["xT_m"][k], data["yT_m"][k]]),
                cfg.width,
                "#f58518",
                0.42,
            ).get_xy()
        )
        point_plot.set_data(
            [data["xA_m"][k], data["xB_m"][k], data["xH_m"][k], data["xT_m"][k]],
            [data["yA_m"][k], data["yB_m"][k], data["yH_m"][k], data["yT_m"][k]],
        )
        time_text.set_text(
            f"{source_label}\n"
            f"t = {t[k]:.2f} s / {t[-1]:.2f} s\n"
            f"alpha = {rad2deg(data['alpha_rad'][k]):.2f} deg, "
            f"phi = {rad2deg(data['phi_rad'][k]):.2f} deg\n"
            f"target risk = {', '.join(f'R{i + 1}:{level}' for i, level in enumerate(risk))}\n"
            f"TTC = {', '.join(f'R{i + 1}:{ttc_i:.2f}s' if np.isfinite(ttc_i) else f'R{i + 1}:--' for i, ttc_i in enumerate(ttc))}"
        )
        fig.canvas.draw_idle()

    slider.on_changed(update)
    update(float(t[0]))
    plt.show()


def main() -> None:
    data, cfg, source_label, csv_path = choose_scenario()
    targets = choose_targets(data, cfg, csv_path)
    build_plot(data, targets, cfg, source_label)


if __name__ == "__main__":
    main()
