"""Local full-bracket motion bounds; no contact search or prefix changes."""
from decimal import Decimal, localcontext
import bisect
import math

import numpy as np

GUARD = 1e-12
CORNER = .001
ADJACENT = {(0, 1): 5, (1, 2): 6, (0, 3): 7, (2, 3): 8}


def up(x):
    if not math.isfinite(x) or x < 0:
        raise ValueError("A finite nonnegative bound is required")
    return math.nextafter(x, math.inf) if x else 0.


def delta_upper(a, b):
    return up(abs(float(b) - float(a)))


def validate_path(time, states, vehicle):
    if (time.ndim != 1 or len(time) < 2 or states.shape != (len(time), 4)
            or not np.isfinite(time).all() or not np.isfinite(states).all()
            or not np.all(np.diff(time) > 0)
            or not all(math.isfinite(float(x)) for x in (vehicle.L, vehicle.width, vehicle.l_h))
            or vehicle.L <= 0 or vehicle.width <= 0):
        raise ValueError("Invalid original piecewise-linear path or vehicle")


def segment_variation(time, states, vehicle):
    """Bound each corner's total travel on each complete original interval."""
    validate_path(time, states, vehicle)
    radius = up(math.hypot(float(vehicle.L), float(vehicle.width) / 2))
    values = []
    for a, b in zip(states[:-1], states[1:]):
        translation = up(math.hypot(delta_upper(a[0], b[0]), delta_upper(a[1], b[1])))
        tractor = up(abs(float(vehicle.l_h)) * delta_upper(a[2], b[2]))
        heading = up(abs(math.fsum((float(b[2]), -float(a[2]), -float(b[3]), float(a[3])))))
        trailer = up(radius * heading)
        values.append(up(math.fsum((translation, tractor, trailer))))
    return np.asarray(values, dtype=np.float64)


def integrated_bound(time, variation, start, end):
    if (not math.isfinite(start) or not math.isfinite(end)
            or not time[0] <= start <= end <= time[-1]
            or variation.shape != (len(time) - 1,)
            or not np.isfinite(variation).all() or np.any(variation < 0)):
        raise ValueError("The complete requested bracket must remain on the original path")
    if start == end:
        return 0.
    first = max(0, int(np.searchsorted(time, start, side="right")) - 1)
    last = min(len(time) - 2, int(np.searchsorted(time, end, side="left")) - 1)
    parts = []
    for k in range(first, last + 1):
        a, b = max(start, float(time[k])), min(end, float(time[k + 1]))
        if b <= a:
            continue
        numerator = up(b - a)
        denominator = math.nextafter(float(time[k + 1]) - float(time[k]), -math.inf)
        if denominator <= 0:
            raise ValueError("Original time interval cannot be conservatively divided")
        fraction = min(1., up(numerator / denominator))
        parts.append(up(float(variation[k]) * fraction))
    return up(math.fsum(parts))


def bracket_bound(time, variation, lower, upper):
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise ValueError("A witnessed original bracket with finite endpoints is required")
    midpoint = (lower + upper) / 2
    if not lower <= midpoint <= upper:
        raise ValueError("Midpoint overflow or invalid bracket")
    left = integrated_bound(time, variation, lower, midpoint)
    right = integrated_bound(time, variation, midpoint, upper)
    return midpoint, left, right, max(left, right)


def face_rule(faces, envelope):
    if (np.shape(faces) != (4,) or not np.isfinite(faces).all()
            or np.any(faces < 0) or not math.isfinite(envelope) or envelope < 0):
        raise ValueError("Invalid finite face distances or error envelope")
    order = sorted(range(4), key=lambda k: (float(faces[k]), k))
    near = float(faces[order[1]] - faces[order[0]])
    far = float(faces[order[2]] - faces[order[1]])
    pair = tuple(sorted(order[:2]))
    code = ADJACENT[pair] if near <= CORNER and pair in ADJACENT else order[0] + 1
    single = near - 2 * envelope - CORNER
    corner_near = CORNER - (near + 2 * envelope)
    corner_far = far - 2 * envelope
    stable = single > 0 or (corner_near > 0 and corner_far > 0 and pair in ADJACENT)
    return code, stable, (single, corner_near, corner_far)


def selection(labels):
    lower, upper = labels["contact_lower_s"], labels["contact_upper_s"]
    n = len(lower)
    if (lower.shape != (n,) or upper.shape != (n,)
            or any(v.shape != (n,) for v in labels.values())
            or np.any(labels["budget_exhausted"])
            or np.any(np.isfinite(upper) & (~np.isfinite(lower) | (lower > upper)))
            or np.any(np.isinf(lower)) or np.any(np.isinf(upper))):
        raise ValueError("Complete nonbudget labels and original endpoints required")
    finite = np.isfinite(upper)
    if np.any(finite != (labels["contact_status"] == 1)):
        raise ValueError("Finite uppers must already be accepted contact witnesses")
    if np.any(~finite & labels["edge_certain"]):
        raise ValueError("An unwitnessed or noncontact row cannot have a certain contact edge")
    return finite & ~labels["edge_certain"]


def candidate(xy, time, states, original, error, vehicle, geometry):
    """Keep all unknowns; only strengthen witnessed edge confidence."""
    if not math.isfinite(error) or error < 0:
        raise ValueError("Original spatial error must be finite and nonnegative")
    selected = selection(original)
    n = len(selected)
    if xy.shape != (n, 2) or not np.isfinite(xy).all():
        raise ValueError("Every selected scope coordinate is required")
    variation = segment_variation(time, states, vehicle)
    out = {k: v.copy() for k, v in original.items()}
    trace = {
        "selected_edge_uncertain": selected,
        "unwitnessed_contact_unknown_retained": np.isfinite(original["contact_lower_s"])
            & ~np.isfinite(original["contact_upper_s"]),
        "known_noncontact_exact_reuse": original["contact_status"] == 0,
        "already_certain_exact_reuse": np.isfinite(original["contact_upper_s"]) & original["edge_certain"],
        "new_midpoint_geometry_query": selected.copy(),
        "edge_newly_certified": np.zeros(n, bool),
        "midpoint_faces_m": np.full((n, 4), np.nan),
        "confidence_margins_m": np.full((n, 3), np.nan),
    }
    for name in ("midpoint_s", "left_motion_m", "right_motion_m", "motion_radius_m", "total_envelope_m"):
        trace[name] = np.full(n, np.nan)
    ids = np.flatnonzero(selected)
    if len(ids):
        queries = []
        for i in ids:
            low, high = map(float, (original["contact_lower_s"][i], original["contact_upper_s"][i]))
            mid, left, right, radius = bracket_bound(time, variation, low, high)
            for name, value in zip(("midpoint_s", "left_motion_m", "right_motion_m", "motion_radius_m"),
                                  (mid, left, right, radius)):
                trace[name][i] = value
            queries.append(mid)
        poses = np.column_stack([np.interp(queries, time, states[:, j]) for j in range(4)])
        _, faces = geometry(xy[ids], poses)
        if faces.shape != (len(ids), 4):
            raise ValueError("All four instantaneous finite faces must be present")
        for j, i in enumerate(ids):
            envelope = up(math.fsum((error, float(trace["motion_radius_m"][i]), GUARD)))
            code, stable, margins = face_rule(faces[j], envelope)
            if code != int(original["nominal_instantaneous_edge"][i]):
                raise ValueError("Original midpoint nominal code must reproduce exactly")
            trace["midpoint_faces_m"][i] = faces[j]
            trace["confidence_margins_m"][i] = margins
            trace["total_envelope_m"][i] = envelope
            if stable:
                out["edge_certain"][i] = True
                out["possible_edge_codes"][i] = 1 << (code - 1)
                trace["edge_newly_certified"][i] = True
    return out, trace, variation


def decimal_segment_variation(a, b, vehicle):
    with localcontext() as context:
        context.prec = 70
        D = Decimal.from_float
        s0, s1 = [D(float(x)) for x in a], [D(float(x)) for x in b]
        dx, dy, dt, dp = [y - x for x, y in zip(s0, s1)]
        radius = (D(float(vehicle.L))**2 + (D(float(vehicle.width)) / 2)**2).sqrt()
        return ((dx * dx + dy * dy).sqrt()
                + abs(D(float(vehicle.l_h))) * abs(dt) + radius * abs(dt - dp))


def decimal_radius(time, states, vehicle, lower, upper, travel=None):
    """Independent high-precision full-bracket integral, not a point estimate."""
    with localcontext() as context:
        context.prec = 70
        D = Decimal.from_float
        lo, hi = D(float(lower)), D(float(upper))
        mid = D(float((lower + upper) / 2))
        pieces = []
        for begin, finish in ((lo, mid), (mid, hi)):
            total = Decimal(0)
            first = max(0, bisect.bisect_right(time, float(begin)) - 1)
            last = min(len(time) - 2, bisect.bisect_left(time, float(finish)) - 1)
            for k in range(first, last + 1):
                t0, t1 = D(float(time[k])), D(float(time[k + 1]))
                a, b = max(begin, t0), min(finish, t1)
                if b <= a:
                    continue
                displacement = travel[k] if travel is not None else decimal_segment_variation(states[k], states[k+1], vehicle)
                total += displacement * (b - a) / (t1 - t0)
            pieces.append(total)
        return pieces[0], pieces[1], max(pieces)


def independent_sum(time, variation, a, b):
    """Reconstruct saved outward-rounded sums by a separate scalar traversal."""
    terms = []
    k = max(0, bisect.bisect_right(time, a) - 1)
    while k < len(time) - 1 and float(time[k]) < b:
        width = min(b, float(time[k + 1])) - max(a, float(time[k]))
        if width > 0:
            num = math.nextafter(width, math.inf)
            den = math.nextafter(float(time[k + 1]) - float(time[k]), -math.inf)
            fraction = min(1., math.nextafter(num / den, math.inf))
            product = float(variation[k]) * fraction
            terms.append(math.nextafter(product, math.inf) if product else 0.)
        k += 1
    total = math.fsum(terms)
    return math.nextafter(total, math.inf) if total else 0.


def independent_check(xy, time, states, original, proposed, error, vehicle, trace, variation, geos):
    """Every queried row and every unchanged row is checked, never sampled."""
    chosen = selection(original)
    if set(proposed) != set(original):
        raise ValueError("Candidate label schema changed")
    for name in original:
        if proposed[name].shape != original[name].shape or proposed[name].dtype != original[name].dtype:
            raise ValueError("Candidate field dtype or shape changed")
        if name not in ("edge_certain", "possible_edge_codes") and proposed[name].tobytes() != original[name].tobytes():
            raise ValueError("Scientific endpoints, contact evidence or provenance changed")
    if variation.shape != (len(time) - 1,) or variation.dtype != np.float64:
        raise ValueError("Every original interval motion bound required")
    expected_trace = {
        "selected_edge_uncertain", "unwitnessed_contact_unknown_retained",
        "known_noncontact_exact_reuse", "already_certain_exact_reuse",
        "new_midpoint_geometry_query", "edge_newly_certified", "midpoint_faces_m",
        "confidence_margins_m", "midpoint_s", "left_motion_m", "right_motion_m",
        "motion_radius_m", "total_envelope_m",
    }
    if set(trace) != expected_trace:
        raise ValueError("Complete diagnostic trace schema required")
    n = len(chosen)
    for name, arr in trace.items():
        shape = (n, 4) if name == "midpoint_faces_m" else (n, 3) if name == "confidence_margins_m" else (n,)
        dtype = np.dtype("bool") if name in expected_trace - {
            "midpoint_faces_m", "confidence_margins_m", "midpoint_s", "left_motion_m",
            "right_motion_m", "motion_radius_m", "total_envelope_m"} else np.dtype("float64")
        if arr.shape != shape or arr.dtype != dtype:
            raise ValueError("Diagnostic trace dtype or shape changed")
    travel = [decimal_segment_variation(a, b, vehicle) for a, b in zip(states[:-1], states[1:])]
    for k, exact in enumerate(travel):
        saved = float(variation[k])
        if (not math.isfinite(saved) or Decimal.from_float(saved) < exact
                or saved > float(exact) * (1 + 1e-13) + 1e-12):
            raise ValueError("Complete interval variation differs from independent high-precision bound")
    queries, certified = 0, 0
    for i in range(n):
        upper = float(original["contact_upper_s"][i])
        lower = float(original["contact_lower_s"][i])
        flags = {
            "selected_edge_uncertain": bool(chosen[i]), "new_midpoint_geometry_query": bool(chosen[i]),
            "unwitnessed_contact_unknown_retained": math.isfinite(lower) and not math.isfinite(upper),
            "known_noncontact_exact_reuse": int(original["contact_status"][i]) == 0,
            "already_certain_exact_reuse": math.isfinite(upper) and bool(original["edge_certain"][i]),
        }
        if any(bool(trace[k][i]) != value for k, value in flags.items()):
            raise ValueError("Complete unknown, contact or exact reuse classification differs")
        if not chosen[i]:
            if any(proposed[k][i:i+1].tobytes() != original[k][i:i+1].tobytes() for k in original):
                raise ValueError("Every unselected field must remain byte-exact, including NaNs")
            if trace["edge_newly_certified"][i]:
                raise ValueError("Unselected row marked newly certain")
            if any(not np.isnan(trace[k][i]).all() for k in
                   ("midpoint_faces_m", "confidence_margins_m", "midpoint_s", "left_motion_m",
                    "right_motion_m", "motion_radius_m", "total_envelope_m")):
                raise ValueError("Unqueried row must have exact NaN trace padding")
            continue
        mid = (lower + upper) / 2
        if trace["midpoint_s"][i] != mid:
            raise ValueError("Original full bracket midpoint changed")
        pose = np.asarray([np.interp(mid, time, states[:, k]) for k in range(4)])
        _, faces = geos(xy[i], pose, vehicle)
        saved = trace["midpoint_faces_m"][i]
        if not np.allclose(faces, saved, rtol=0, atol=1e-10):
            raise ValueError("Independent instantaneous finite face geometry differs")
        left, right, bound = decimal_radius(time, states, vehicle, lower, upper, travel)
        for name, exact in (("left_motion_m", left), ("right_motion_m", right), ("motion_radius_m", bound)):
            if Decimal.from_float(float(trace[name][i])) < exact:
                raise ValueError("Local envelope underbounds the full original interval")
        saved_left = independent_sum(time, variation, lower, mid)
        saved_right = independent_sum(time, variation, mid, upper)
        if (trace["left_motion_m"][i] != saved_left or trace["right_motion_m"][i] != saved_right
                or trace["motion_radius_m"][i] != max(saved_left, saved_right)):
            raise ValueError("Every full-bracket motion sum and endpoint must reproduce exactly")
        radius = float(trace["motion_radius_m"][i])
        envelope = float(trace["total_envelope_m"][i])
        if envelope < math.fsum((error, radius, GUARD)):
            raise ValueError("Original empirical spatial error or guard reduced")
        order = sorted(range(4), key=lambda k: (float(faces[k]), k))
        gap = float(faces[order[1]] - faces[order[0]])
        far = float(faces[order[2]] - faces[order[1]])
        pair = tuple(sorted(order[:2]))
        code = ADJACENT[pair] if gap <= .001 and pair in ADJACENT else order[0] + 1
        certain = gap - 2 * envelope > .001 or (
            gap + 2 * envelope < .001 and far > 2 * envelope and pair in ADJACENT)
        worker_order = sorted(range(4), key=lambda k: (float(saved[k]), k))
        wg, wf = float(saved[worker_order[1]] - saved[worker_order[0]]), float(saved[worker_order[2]] - saved[worker_order[1]])
        margins = (wg - 2 * envelope - .001, .001 - (wg + 2 * envelope), wf - 2 * envelope)
        if not np.array_equal(trace["confidence_margins_m"][i], np.asarray(margins)):
            raise ValueError("Every signed margin must be retained without clipping")
        worker_stable = margins[0] > 0 or (
            margins[1] > 0 and margins[2] > 0 and tuple(sorted(worker_order[:2])) in ADJACENT)
        if (bool(proposed["edge_certain"][i]) != worker_stable
                or bool(trace["edge_newly_certified"][i]) != worker_stable):
            raise ValueError("Candidate confidence does not match saved sufficient rule")
        if worker_stable and (not certain or code != int(original["nominal_instantaneous_edge"][i])):
            raise ValueError("New code must independently satisfy strict finite-face confidence")
        bits = 1 << (int(original["nominal_instantaneous_edge"][i]) - 1) if worker_stable else int(original["possible_edge_codes"][i])
        if int(proposed["possible_edge_codes"][i]) != bits:
            raise ValueError("Uncertain edge set changed or certified singleton differs")
        queries += 1
        certified += int(worker_stable)
    return {"records": n, "independent_midpoint_GE0S_queries": queries,
            "newly_certified_edge_candidates": certified, "scientific_endpoints_unchanged": True,
            "unwitnessed_contact_rows_exactly_retained_not_repaired": True}

