"""Unadmitted correction primitives; not a replacement truth dataset or evaluator.

These isolate instantaneous finite-face geometry from swept-interval classification.
Entry refinement is valid only inside an independently isolated crossing bracket.
No global first-contact or physical validation claim follows from these functions.
"""
from __future__ import annotations
import numpy as np

def local_coordinates(xy, states, length, width, hitch_offset):
    xy = np.asarray(xy, dtype=float)
    states = np.broadcast_to(np.asarray(states, dtype=float), (len(xy), 4))
    if xy.shape != (len(xy), 2) or not np.isfinite(xy).all() or not np.isfinite(states).all():
        raise ValueError('Finite point coordinates and four-state poses required')
    if min(length, width) <= 0:
        raise ValueError('Positive rectangle dimensions required')
    theta, heading = states[:, 2], states[:, 2]-states[:, 3]
    hitch = states[:, :2] + hitch_offset*np.column_stack((np.cos(theta), np.sin(theta)))
    delta = xy-hitch
    longitudinal = delta[:, 0]*np.cos(heading)+delta[:, 1]*np.sin(heading)
    right = delta[:, 0]*np.sin(heading)-delta[:, 1]*np.cos(heading)
    return longitudinal, right

def finite_face_geometry(xy, states, *, length, width, hitch_offset):
    q, lateral = local_coordinates(xy, states, length, width, hitch_offset)
    outside_longitudinal = np.maximum.reduce((q, -length-q, np.zeros_like(q)))
    outside_lateral = np.maximum(np.abs(lateral)-width/2, 0)
    faces = np.column_stack((np.hypot(q, outside_lateral),
                             np.hypot(lateral-width/2, outside_longitudinal),
                             np.hypot(q+length, outside_lateral),
                             np.hypot(lateral+width/2, outside_longitudinal)))
    return np.hypot(outside_longitudinal, outside_lateral), faces

def edge_candidates(face_distances, uncertainty_m):
    distances = np.asarray(face_distances, dtype=float)
    if distances.ndim != 2 or distances.shape[1] != 4 or not np.isfinite(distances).all():
        raise ValueError('Four finite segment distances required')
    uncertainty = np.broadcast_to(np.asarray(uncertainty_m, dtype=float), (len(distances),))
    if not np.isfinite(uncertainty).all() or np.any(uncertainty < 0):
        raise ValueError('An explicit nonnegative spatial uncertainty bound is required')
    candidates = distances <= distances.min(axis=1, keepdims=True)+uncertainty[:, None]
    bits = (candidates.astype(np.uint8)*np.array([1, 2, 4, 8], dtype=np.uint8)).sum(axis=1).astype(np.uint8)
    return {'edge_candidate_bits': bits, 'multiple_edges': candidates.sum(axis=1) > 1,
            'right_possible': candidates[:, 1], 'front_possible': candidates[:, 0],
            'right_certain_single_face': candidates[:, 1] & (candidates.sum(axis=1) == 1)}

def refine_isolated_entry(xy, lower_state, upper_state, lower_time, upper_time, *,
                          length, width, hitch_offset, isolated_entry_proven=False,
                          contact_tolerance_m=.05, time_tolerance_s=1e-7):
    if not isolated_entry_proven:
        raise ValueError('First-entry isolation must be independently established, not assumed from endpoint signs')
    if not (time_tolerance_s > 0 and contact_tolerance_m >= 0 and upper_time > lower_time):
        raise ValueError('Valid time bracket and tolerances required')
    xy = np.asarray(xy, dtype=float)
    start = np.broadcast_to(np.asarray(lower_state, dtype=float), (len(xy), 4))
    end = np.broadcast_to(np.asarray(upper_state, dtype=float), (len(xy), 4))
    if np.any(np.abs(end[:, 2:]-start[:, 2:]) >= np.pi):
        raise ValueError('Unwrap reference angles before interpolation')
    params = dict(length=length, width=width, hitch_offset=hitch_offset)
    d0, _ = finite_face_geometry(xy, start, **params)
    d1, _ = finite_face_geometry(xy, end, **params)
    initial = d0 <= contact_tolerance_m
    bracketed = ~initial & (d1 <= contact_tolerance_m)
    unresolved = ~initial & ~bracketed
    low, high = np.zeros(len(xy)), np.ones(len(xy))
    high[initial] = 0
    iterations = int(np.ceil(np.log2(max(1., (upper_time-lower_time)/time_tolerance_s))))
    for _ in range(iterations):
        mid = (low+high)/2
        state = start + mid[:, None]*(end-start)
        distance, _ = finite_face_geometry(xy, state, **params)
        inside = distance <= contact_tolerance_m
        low = np.where(bracketed & ~inside, mid, low)
        high = np.where(bracketed & inside, mid, high)
    t_low = lower_time+low*(upper_time-lower_time)
    t_high = lower_time+high*(upper_time-lower_time)
    t_low[unresolved] = np.nan
    t_high[unresolved] = np.nan
    return {'contact_lower_s': t_low, 'contact_upper_s': t_high,
            'initial_overlap': initial, 'bracketed': bracketed, 'unresolved': unresolved,
            'model_scope': 'linear_pose_interpolant_with_externally_proven_entry_isolation',
            'is_admitted_global_truth_labeler': False}
