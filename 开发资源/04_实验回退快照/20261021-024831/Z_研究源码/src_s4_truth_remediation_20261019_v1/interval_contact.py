"""Conservative first-contact intervals for a piecewise-linear pose model.

The bound covers translation, hitch rotation and trailer rotation. It is conditional
on the supplied pose path and spatial error bound, not a real-vehicle certificate.
Unresolved leaves and exhaustion are exposed, never relabeled as noncontact.
"""
import numpy as np
from contact_primitives import finite_face_geometry

def motion_bound(states, time, length, width, hitch_offset):
    change = np.diff(states, axis=0)
    duration = np.diff(time)
    center = np.linalg.norm(change[:, :2], axis=1)
    theta = np.abs(change[:, 2])
    heading = np.abs(change[:, 2]-change[:, 3])
    return (center+abs(hitch_offset)*theta+np.hypot(length, width/2)*heading)/duration

def point_contact_interval(xy, time, states, *, length, width, hitch_offset,
                           tolerance_m=.05, spatial_error_m=0., time_resolution_s=1e-7,
                           numerical_guard_m=1e-12, maximum_evaluations=20000):
    time, states, xy = np.asarray(time, float), np.asarray(states, float), np.asarray(xy, float)
    if (time.ndim != 1 or len(time) < 2 or states.shape != (len(time), 4)
            or xy.shape != (2,) or not np.isfinite(time).all() or not np.isfinite(states).all()
            or not np.isfinite(xy).all() or not np.all(np.diff(time) > 0)):
        raise ValueError('Finite strictly ordered reference and one point required')
    if (spatial_error_m < 0 or time_resolution_s <= 0 or numerical_guard_m < 0
            or maximum_evaluations < 3 or tolerance_m < 0):
        raise ValueError('Invalid interval policy')
    params = dict(length=length, width=width, hitch_offset=hitch_offset)
    speeds = motion_bound(states, time, **params)
    # An additive guard avoids treating floating equality as a proof of exclusion.
    points = np.broadcast_to(xy, (len(time), 2))
    endpoint_d, _ = finite_face_geometry(points, states, **params)
    middle_states = (states[:-1]+states[1:])/2
    middle_d, _ = finite_face_geometry(np.broadcast_to(xy, (len(middle_states), 2)), middle_states, **params)
    lower_bounds = middle_d-speeds*np.diff(time)/2-spatial_error_m-numerical_guard_m
    candidates = np.flatnonzero(lower_bounds <= tolerance_m)
    lower, upper = None, None
    witness = None
    evaluations, exhausted = 0, False
    if endpoint_d[0]+spatial_error_m <= tolerance_m:
        return {'status': 'contact', 'lower_s': float(time[0]), 'upper_s': float(time[0]),
                'witness_s': float(time[0]), 'initial_overlap': True, 'exhausted': False,
                'evaluations': 0, 'candidate_intervals': len(candidates)}
    for index in candidates:
        start, end = float(time[index]), float(time[index+1])
        origin, delta = states[index], states[index+1]-states[index]
        speed = float(speeds[index])
        stack = [(start, end)]
        while stack:
            a, b = stack.pop()
            if upper is not None and a >= upper:
                continue
            middle = (a+b)/2
            pose = origin+((middle-start)/(end-start))*delta
            distance = float(finite_face_geometry(xy[None, :], pose, **params)[0][0])
            evaluations += 1
            if distance-spatial_error_m-speed*(b-a)/2-numerical_guard_m > tolerance_m:
                continue
            if distance+spatial_error_m <= tolerance_m:
                if upper is None or middle < upper:
                    upper, witness = middle, middle
            if b-a <= time_resolution_s or evaluations >= maximum_evaluations:
                lower = a if lower is None else min(lower, a)
                exhausted |= evaluations >= maximum_evaluations
                if exhausted:
                    # The current interval is visited before remaining intervals.
                    break
                continue
            # LIFO right then left ensures chronological inspection without monotonicity.
            stack.append((middle, b))
            stack.append((a, middle))
        if exhausted or upper is not None:
            break
    if exhausted:
        status = 'unresolved_budget'
    elif upper is not None:
        status = 'contact'
    elif lower is not None:
        status = 'possible_contact_unresolved'
    else:
        status = 'noncontact'
    if upper is not None and lower is None:
        raise AssertionError('Verified contact without a covering possible interval')
    return {'status': status, 'lower_s': lower, 'upper_s': upper, 'witness_s': witness,
            'initial_overlap': False, 'exhausted': exhausted, 'evaluations': evaluations,
            'candidate_intervals': len(candidates)}

def original_corner_rule(face_distances):
    distances = np.asarray(face_distances, float)
    if distances.ndim != 2 or distances.shape[1] != 4 or not np.isfinite(distances).all():
        raise ValueError('Four finite face distances required')
    order = np.argsort(distances, axis=1)
    codes = (order[:, 0]+1).astype(np.int8)
    tied = np.take_along_axis(distances, order[:, :2], axis=1)
    corner = tied[:, 1]-tied[:, 0] <= .001
    for pair, code in (((0,1),5), ((1,2),6), ((0,3),7), ((2,3),8)):
        codes[corner & (np.sort(order[:, :2], axis=1) == pair).all(axis=1)] = code
    return codes
