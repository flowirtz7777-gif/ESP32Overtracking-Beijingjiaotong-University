"""Development-only observer of the frozen prefix kernel; no real-data entrypoint."""
from __future__ import annotations
import ast
import functools
import inspect
from pathlib import Path
import sys
import textwrap
import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_interval_prefix_audit_20261019_v1'))
from prefix_audit import audit_prefixes, common


@functools.lru_cache(maxsize=1)
def observation_line():
    lines, first = inspect.getsourcelines(audit_prefixes)
    tree = ast.parse(textwrap.dedent(''.join(lines)))
    matches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                and target.value.id == 'uncertain' and isinstance(target.slice, ast.Subscript)
                and isinstance(target.slice.value, ast.Name) and target.slice.value.id == 'selected'
                and isinstance(target.slice.slice, ast.Name) and target.slice.slice.id == 'unknown'):
            matches.append(first + node.lineno - 1)
    if len(matches) != 1:
        raise RuntimeError('Frozen kernel leaf observation site is ambiguous')
    return matches[0]


def audit_with_leaf_evidence(xy, time, states, lower, **policy):
    """Observe uncertainty before assignment without modifying any kernel local."""
    if sys.gettrace() is not None:
        raise RuntimeError('An existing trace function must not be replaced')
    site = observation_line()
    evidence = []

    def observer(frame, event, argument):
        if frame.f_code is not audit_prefixes.__code__:
            return None
        if event == 'line' and frame.f_lineno == site:
            local = frame.f_locals
            mask = local['unknown']
            for j in np.flatnonzero(mask):
                index = int(local['selected'][j])
                a, b, middle = (float(local[name][j]) for name in ('a', 'b', 'middle'))
                k = int(local['k'])
                t = local['time']
                pose = local['states'][k] + middle * local['delta']
                point = local['xy'][index]
                corners = common.body_corners(pose[None, :], local['vehicle'])[0]
                distance = float(shapely.distance(shapely.Point(point), shapely.Polygon(corners)))
                motion = float(local['full_motion']) * (b - a) / 2
                error = float(local['spatial_error_m'])
                tolerance = float(local['tolerance_m'])
                evidence.append({'point_index': index, 'interval_index': k, 'fraction_a': a, 'fraction_b': b,
                    'time_a_s': float(t[k] + a * local['duration']),
                    'time_b_s': float(t[k] + b * local['duration']),
                    'time_mid_s': float(t[k] + middle * local['duration']),
                    'audited_until_s': float(local['limit'][index]),
                    'time_resolution_s': float(local['time_resolution_s']),
                    'leaf_width_s': float((b - a) * local['duration']),
                    'midpoint_distance_GE0S_m': distance, 'spatial_error_m': error,
                    'motion_half_enclosure_m': motion, 'tolerance_m': tolerance,
                    'exclusion_margin_m': distance - error - motion - 1e-12 - tolerance,
                    'contact_witness_margin_m': tolerance - distance - error,
                    'time_leaf': bool(local['leaf'][j]), 'evaluation_budget': bool(local['budget'][j]),
                    'GEOS_evaluations': int(local['counts'][index]), 'point_xy': point.tolist(), 'midpoint_pose': pose.tolist()})
        return observer

    sys.settrace(observer)
    try:
        arrays = audit_prefixes(xy, time, states, lower, **policy)
    finally:
        sys.settrace(None)
    indices = [row['point_index'] for row in evidence]
    expected = np.flatnonzero(arrays['prefix_undetermined']).tolist()
    if sorted(indices) != expected or len(set(indices)) != len(indices):
        raise RuntimeError('Every and only unresolved leaf must be observed exactly once')
    return arrays, evidence
