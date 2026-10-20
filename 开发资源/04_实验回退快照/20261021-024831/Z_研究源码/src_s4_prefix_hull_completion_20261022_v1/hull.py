"""Conditional prefix exclusion using endpoint hulls and corner chord error.

For affine pose parameter u, each corner is a translation plus two rotations.
Its second derivative norm is bounded by |l_h|*dtheta**2 + radius*dheading**2.
The chord error on [a,b] is at most that bound*(b-a)**2/8. Every intermediate
rectangle lies in the convex hull of the eight endpoint corners plus that ball.
The supplied empirical spatial error and the existing 1e-12 guard are added,
never reduced. This is not an interval-ODE or floating-point formal certificate.
"""
from pathlib import Path
import sys
import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_v3'))
import common

EXCLUDED, UNKNOWN, WITNESS, BUDGET = 1, 2, 3, 4
FLOAT_FIELDS = ('a', 'b', 'hull_distance_m', 'curvature_m', 'exclusion_margin_m', 'midpoint_distance_m')


def enclosure(start, delta, a, b, vehicle):
    poses = start + np.array([a, b])[:, None] * delta
    corners = common.body_corners(poses, vehicle)
    polygon = shapely.convex_hull(shapely.MultiPoint(corners.reshape(-1, 2)))
    curvature = (abs(vehicle.l_h) * delta[2] ** 2
                 + np.hypot(vehicle.L, vehicle.width / 2) * (delta[2] - delta[3]) ** 2) * (b - a) ** 2 / 8
    return polygon, float(curvature)


def audit_point(xy, time, states, lower, *, vehicle, spatial_error_m,
                tolerance_m=.050000001, time_resolution_s=1e-8, maximum_evaluations=131072):
    xy, time, states = np.asarray(xy, float), np.asarray(time, float), np.asarray(states, float)
    if (xy.shape != (2,) or time.ndim != 1 or len(time) < 2 or states.shape != (len(time), 4)
            or not np.isfinite(xy).all() or not np.isfinite(time).all() or not np.isfinite(states).all()
            or not np.all(np.diff(time) > 0) or np.isinf(lower)
            or (np.isfinite(lower) and not time[0] <= lower <= time[-1])
            or not np.isfinite([spatial_error_m, tolerance_m, time_resolution_s]).all()
            or spatial_error_m < 0 or tolerance_m < 0 or time_resolution_s <= 0 or maximum_evaluations < 1):
        raise ValueError('Invalid unchanged conditional-prefix contract')
    until = float(time[-1] if np.isnan(lower) else lower)
    point, rows, count, status = shapely.Point(xy), [], 0, EXCLUDED
    for k in range(len(time) - 1):
        duration = time[k + 1] - time[k]
        end = min(1., (until - time[k]) / duration)
        if end <= 0:
            break
        delta = states[k + 1] - states[k]
        stack = [(0., end)]
        while stack:
            a, b = stack.pop()
            if count >= maximum_evaluations:
                rows.append((k, BUDGET, 0, a, b, np.nan, np.nan, np.nan, np.nan))
                status = BUDGET
                break
            polygon, curvature = enclosure(states[k], delta, a, b, vehicle)
            distance = float(shapely.distance(point, polygon))
            count += 1
            margin = distance - curvature - spatial_error_m - 1e-12 - tolerance_m
            if margin > 0:
                rows.append((k, EXCLUDED, 1, a, b, distance, curvature, margin, np.nan))
                continue
            if count >= maximum_evaluations:
                rows.append((k, BUDGET, 1, a, b, distance, curvature, margin, np.nan))
                status = BUDGET
                break
            middle = (a + b) / 2
            corners = common.body_corners((states[k] + middle * delta)[None], vehicle)[0]
            midpoint = float(shapely.distance(point, shapely.Polygon(corners)))
            count += 1
            if midpoint + spatial_error_m <= tolerance_m:
                rows.append((k, WITNESS, 2, a, b, distance, curvature, margin, midpoint))
                status = WITNESS
                break
            if (b - a) * duration <= time_resolution_s:
                rows.append((k, UNKNOWN, 2, a, b, distance, curvature, margin, midpoint))
                status = UNKNOWN
                break
            # Parent evaluations are retained, including nodes that were subdivided.
            rows.append((k, 0, 2, a, b, distance, curvature, margin, midpoint))
            stack.extend(((middle, b), (a, middle)))
        if status != EXCLUDED:
            break
    matrix = np.asarray(rows, float).reshape(-1, 9)
    proof = {'interval': matrix[:, 0].astype(np.int32), 'status': matrix[:, 1].astype(np.uint8),
             'evaluations': matrix[:, 2].astype(np.int8)}
    proof.update({name: matrix[:, j + 3] for j, name in enumerate(FLOAT_FIELDS)})
    summary = {'status': {EXCLUDED: 'excluded', UNKNOWN: 'unknown_time_leaf', WITNESS: 'early_contact_witness',
                          BUDGET: 'unknown_budget'}[status],
               'all_required_prefix_excluded': status == EXCLUDED, 'GEOS_evaluations': count,
               'proof_rows': len(rows), 'audited_until_s': until, 'original_lower_is_nan': bool(np.isnan(lower))}
    return proof, summary


def validate_tree(proof, time, until, complete):
    """Check every recorded split and the full original prefix, without geometry."""
    time = np.asarray(time)
    intervals = [k for k in range(len(time) - 1) if time[k] < until]
    position = 0
    stopped = False
    for k in intervals:
        end = min(1., (until - time[k]) / (time[k + 1] - time[k]))
        stack = [(0., end)]
        while stack:
            a, b = stack.pop()
            if position >= len(proof['interval']):
                raise RuntimeError('Missing required prefix node')
            i = position
            if (int(proof['interval'][i]) != k or proof['a'][i] != a or proof['b'][i] != b):
                raise RuntimeError('Prefix tree has a gap, overlap, wrong index or changed endpoint')
            status = int(proof['status'][i])
            position += 1
            if status == 0:
                middle = (a + b) / 2
                stack.extend(((middle, b), (a, middle)))
            elif status not in (EXCLUDED, UNKNOWN, WITNESS, BUDGET):
                raise RuntimeError('Invalid node status')
            elif status != EXCLUDED:
                stopped = True
                break
        if stopped:
            break
    if position != len(proof['interval']) or complete == stopped:
        raise RuntimeError('Incomplete or surplus prefix proof cannot certify exclusion')
    return True
