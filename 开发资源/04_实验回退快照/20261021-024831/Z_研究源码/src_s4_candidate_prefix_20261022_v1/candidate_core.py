"""Sparse full-prefix hull proofs; omitted intervals have strict AABB bounds."""
from pathlib import Path
import math
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_prefix_hull_completion_20261022_v1'))
import hull
import hull_driver

TOLERANCE = .050000001
RESOLUTION = 1e-8
INTERVAL_BUDGET = 131072
FIELDS = ('interval', 'status', 'evaluations', *hull.FLOAT_FIELDS)


def boxes(time, states, vehicle):
    time, states = np.asarray(time), np.asarray(states)
    if (len(time) < 2 or states.shape != (len(time), 4) or not np.isfinite(states).all()
            or not np.isfinite(time).all() or not np.all(np.diff(time) > 0)):
        raise ValueError('Invalid original path')
    corners = hull.common.body_corners(states, vehicle)
    delta = np.diff(states, axis=0)
    curve = (abs(vehicle.l_h) * delta[:, 2]**2
             + np.hypot(vehicle.L, vehicle.width / 2) * (delta[:, 2] - delta[:, 3])**2) / 8
    return {'lo': np.minimum(corners[:-1].min(axis=1), corners[1:].min(axis=1)),
            'hi': np.maximum(corners[:-1].max(axis=1), corners[1:].max(axis=1)), 'curve': curve}


def endpoint(time, lower):
    if np.isinf(lower) or (np.isfinite(lower) and not time[0] <= lower <= time[-1]):
        raise ValueError('Changed or invalid prefix lower endpoint')
    return float(time[-1] if np.isnan(lower) else lower)


def independent_boxes(states, vehicle, saved):
    corners = []
    for x, y, theta, phi in states:
        heading = theta - phi
        hx, hy = x + vehicle.l_h * math.cos(theta), y + vehicle.l_h * math.sin(theta)
        rx, ry = hx - vehicle.L * math.cos(heading), hy - vehicle.L * math.sin(heading)
        nx, ny = vehicle.width / 2 * math.sin(heading), -vehicle.width / 2 * math.cos(heading)
        corners.append(((hx+nx, hy+ny), (rx+nx, ry+ny), (rx-nx, ry-ny), (hx-nx, hy-ny)))
    corners = np.asarray(corners)
    lo, hi, curves = [], [], []
    for k in range(len(states) - 1):
        joined = corners[k:k+2].reshape(-1, 2)
        lo.append(joined.min(axis=0))
        hi.append(joined.max(axis=0))
        theta = float(states[k+1, 2] - states[k, 2])
        heading = theta - float(states[k+1, 3] - states[k, 3])
        curves.append((abs(vehicle.l_h) * theta**2 + math.hypot(vehicle.L, vehicle.width/2) * heading**2) / 8)
    independent = {'lo': np.asarray(lo), 'hi': np.asarray(hi), 'curve': np.asarray(curves)}
    if any(not np.allclose(independent[n], saved[n], rtol=1e-13, atol=1e-12) for n in independent):
        raise RuntimeError('Independent scalar corner/chord reconstruction differs')
    return {'lo': np.minimum(independent['lo'], saved['lo']),
            'hi': np.maximum(independent['hi'], saved['hi']),
            'curve': np.maximum(independent['curve'], saved['curve'])}


def selected(point, time, lower, broad, error):
    until = endpoint(time, lower)
    if not np.isfinite(point).all() or not np.isfinite(error) or error < 0:
        raise ValueError('Invalid original point/error')
    gap = np.maximum(np.maximum(broad['lo'] - point, point - broad['hi']), 0.)
    margin = np.hypot(gap[:, 0], gap[:, 1]) - broad['curve'] - error - 1e-12 - TOLERANCE
    return np.flatnonzero((np.asarray(time[:-1]) < until) & (margin <= 0)).astype(np.int32)


def independent_selected(point, time, lower, broad, error):
    until, found = endpoint(time, lower), []
    for k in range(len(time) - 1):
        if time[k] >= until:
            break
        dx = max(float(broad['lo'][k, 0] - point[0]), float(point[0] - broad['hi'][k, 0]), 0.)
        dy = max(float(broad['lo'][k, 1] - point[1]), float(point[1] - broad['hi'][k, 1]), 0.)
        margin = math.hypot(dx, dy) - float(broad['curve'][k]) - error - 1e-12 - TOLERANCE
        if margin <= 0:
            found.append(k)
    return np.asarray(found, np.int32)


def audit(point, time, states, lower, error, vehicle, broad):
    wanted = selected(point, time, lower, broad, error)
    until, records, counts = endpoint(time, lower), [], 0
    pieces = {name: [] for name in FIELDS}
    offset, terminal = 0, 'excluded'
    for k in wanted:
        stop = min(until, float(time[k + 1]))
        proof, summary = hull.audit_point(point, time[k:k+2], states[k:k+2], stop,
            vehicle=vehicle, spatial_error_m=error, tolerance_m=TOLERANCE,
            time_resolution_s=RESOLUTION, maximum_evaluations=INTERVAL_BUDGET)
        for name in FIELDS:
            pieces[name].append(proof[name])
        records.append({'original_interval': int(k), 'offset': offset, 'summary': summary})
        offset += summary['proof_rows']
        counts += summary['GEOS_evaluations']
        terminal = summary['status']
        if terminal != 'excluded':
            break
    dtype = {'interval': np.int32, 'status': np.uint8, 'evaluations': np.int8}
    arrays = {name: np.concatenate(parts) if parts else np.empty(0, dtype.get(name, np.float64))
              for name, parts in pieces.items()}
    arrays['selected_original_intervals'] = wanted
    return arrays, {'status': terminal, 'all_required_prefix_excluded': terminal == 'excluded',
        'audited_until_s': until, 'original_lower_is_nan': bool(np.isnan(lower)),
        'selected_intervals': len(wanted), 'GEOS_evaluations': counts, 'interval_records': records}


def validate(point, time, states, lower, error, vehicle, broad, arrays, summary):
    wanted = independent_selected(point, time, lower, broad, error)
    if (set(arrays) != {*FIELDS, 'selected_original_intervals'}
            or arrays['selected_original_intervals'].dtype != np.dtype('int32')
            or not np.array_equal(wanted, arrays['selected_original_intervals'])):
        raise RuntimeError('Omitted interval is not independently excluded')
    until = endpoint(time, lower)
    if summary['audited_until_s'] != until or summary['original_lower_is_nan'] != bool(np.isnan(lower)):
        raise RuntimeError('Original lower/full-path endpoint changed')
    records, offset, total, terminal = summary['interval_records'], 0, 0, 'excluded'
    for j, row in enumerate(records):
        if j >= len(wanted) or row['original_interval'] != wanted[j] or row['offset'] != offset:
            raise RuntimeError('Selected interval order/coverage differs')
        if terminal != 'excluded':
            raise RuntimeError('Evidence continues after unresolved/witness leaf')
        k, local = int(wanted[j]), row['summary']
        n = local['proof_rows']
        proof = {name: arrays[name][offset:offset+n] for name in FIELDS}
        hull_driver.independent_geometry(point, time[k:k+2], states[k:k+2], min(until, float(time[k+1])),
                                         error, vehicle, proof, local)
        offset += n
        total += local['GEOS_evaluations']
        terminal = local['status']
    complete = terminal == 'excluded'
    if ((complete and len(records) != len(wanted)) or offset != len(arrays['interval'])
            or any(len(arrays[n]) != offset for n in FIELDS)
            or summary['status'] != terminal or summary['all_required_prefix_excluded'] != complete
            or summary['selected_intervals'] != len(wanted) or summary['GEOS_evaluations'] != total):
        raise RuntimeError('Incomplete or surplus full-prefix proof')
    return {'complete': complete, 'selected_intervals': len(wanted), 'independent_GE0S_evaluations': total}
