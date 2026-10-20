"""Earlier witness candidates only; internal probe lows are not science bounds."""
import numpy as np

TOL = .050000001
GUARD = 1e-12
RESOLUTION = 1e-7
STEPS = 64


def selection(labels):
    mask = np.isfinite(labels['contact_upper_s']) & ~labels['edge_certain']
    if np.any(mask & ((labels['contact_status'] != 1) | labels['budget_exhausted'])):
        raise ValueError('Every selected record must already have a nonbudget witness')
    return mask


def poses(time, states, query):
    return np.column_stack([np.interp(query, time, states[:, j]) for j in range(4)])


def validate_inputs(xy, time, states, labels, error):
    n = len(xy)
    if (xy.shape != (n, 2) or states.shape != (len(time), 4) or len(time) < 2
            or not np.all(np.diff(time) > 0) or not np.isfinite(states).all()
            or not np.isfinite(xy).all() or not np.isfinite(error) or error < 0
            or any(v.shape != (n,) for v in labels.values())):
        raise ValueError('Invalid complete selected path data')
    low, high = labels['contact_lower_s'], labels['contact_upper_s']
    if (not selection(labels).all() or not np.isfinite(low).all() or np.any(low > high)
            or np.any(low < time[0]) or np.any(high > time[-1])):
        raise ValueError('Only witnessed uncertain-edge rows on the original path are allowed')


def candidate(xy, time, states, original, error, geometry, speed, nominal, confidence):
    validate_inputs(xy, time, states, original, error)
    n = len(xy)
    low = original['contact_lower_s'].copy()
    high = original['contact_upper_s'].copy()
    trace = {'time_s': np.full((n, STEPS), np.nan), 'body_distance_m': np.full((n, STEPS), np.nan),
             'witness': np.zeros((n, STEPS), bool), 'evaluations': np.zeros(n, np.int16)}
    for j in range(STEPS):
        ids = np.flatnonzero(high - low > RESOLUTION)
        if not len(ids):
            break
        q = (low[ids] + high[ids]) / 2
        if np.any((q <= low[ids]) | (q >= high[ids])):
            raise ValueError('Unresolved floating-point probe stagnation')
        distance, _ = geometry(xy[ids], poses(time, states, q))
        if not np.isfinite(distance).all() or np.any(distance < 0):
            raise ValueError('Invalid probe geometry')
        hit = distance + error + GUARD <= TOL
        trace['time_s'][ids, j], trace['body_distance_m'][ids, j] = q, distance
        trace['witness'][ids, j] = hit
        trace['evaluations'][ids] += 1
        high[ids[hit]] = q[hit]
        # A failed witness test is not a noncontact or first-contact lower proof.
        low[ids[~hit]] = q[~hit]
    trace['internal_remaining_width_s'] = high - low
    trace['probe_budget_exhausted'] = high - low > RESOLUTION
    out = {k: v.copy() for k, v in original.items()}
    changed = high < original['contact_upper_s']
    ids = np.flatnonzero(changed)
    out['contact_upper_s'][ids] = high[ids]
    if len(ids):
        middle = (original['contact_lower_s'][ids] + high[ids]) / 2
        _, faces = geometry(xy[ids], poses(time, states, middle))
        code = nominal(faces)
        env = error + float(np.max(speed)) * (high[ids] - original['contact_lower_s'][ids]) / 2
        certain, _, _ = confidence(faces, env)
        out['nominal_instantaneous_edge'][ids] = code
        out['edge_certain'][ids] = certain
        out['possible_edge_codes'][ids] = 255
        out['possible_edge_codes'][ids[certain]] = np.left_shift(np.uint16(1), code[certain].astype(np.uint16) - 1)
    return out, trace


def identical(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def independently_check(xy, time, states, original, proposed, error, vehicle, trace, geos, max_speed):
    """Scalar replay of every probe and every candidate face/confidence decision."""
    validate_inputs(xy, time, states, original, error)
    n = len(xy)
    if (set(proposed) != set(original) or any(proposed[k].dtype != original[k].dtype
            or proposed[k].shape != original[k].shape for k in original)):
        raise ValueError('Candidate schema differs')
    shapes = {'time_s': ((n, STEPS), np.dtype('float64')), 'body_distance_m': ((n, STEPS), np.dtype('float64')),
              'witness': ((n, STEPS), np.dtype('bool')), 'evaluations': ((n,), np.dtype('int16')),
              'internal_remaining_width_s': ((n,), np.dtype('float64')),
              'probe_budget_exhausted': ((n,), np.dtype('bool'))}
    if set(trace) != set(shapes) or any(trace[k].shape != s or trace[k].dtype != d for k, (s, d) in shapes.items()):
        raise ValueError('Full trace schema differs')
    mutable = {'contact_upper_s', 'nominal_instantaneous_edge', 'edge_certain', 'possible_edge_codes'}
    if any(not identical(proposed[k], original[k]) for k in original.keys() - mutable):
        raise ValueError('Original lower or immutable label evidence changed')
    checked = 0
    for i in range(n):
        lo, hi = float(original['contact_lower_s'][i]), float(original['contact_upper_s'][i])
        count = int(trace['evaluations'][i])
        if not 0 <= count <= STEPS:
            raise ValueError('Invalid trace evaluation count')
        for j in range(count):
            if hi - lo <= RESOLUTION:
                raise ValueError('Extra probe after fixed stopping condition')
            q = (lo + hi) / 2
            if not lo < q < hi or trace['time_s'][i, j] != q:
                raise ValueError('Internal probe recurrence differs')
            pose = np.asarray([np.interp(q, time, states[:, k]) for k in range(4)])
            body, _ = geos(xy[i], pose, vehicle)
            saved = float(trace['body_distance_m'][i, j])
            if not np.isfinite(saved) or saved < 0 or abs(body - saved) > 1e-10:
                raise ValueError('Independent probe body geometry differs')
            hit = bool(saved + error + GUARD <= TOL)
            if hit != bool(trace['witness'][i, j]) or (hit and body + error > TOL):
                raise ValueError('Probe decision or strict independent witness differs')
            if hit:
                hi = q
            else:
                lo = q
            checked += 1
        if count < STEPS and hi - lo > RESOLUTION:
            raise ValueError('Prematurely truncated trace')
        if (not np.isnan(trace['time_s'][i, count:]).all()
                or not np.isnan(trace['body_distance_m'][i, count:]).all()
                or trace['witness'][i, count:].any()
                or trace['internal_remaining_width_s'][i] != hi - lo
                or bool(trace['probe_budget_exhausted'][i]) != (hi - lo > RESOLUTION)
                or proposed['contact_upper_s'][i] != hi):
            raise ValueError('Trace padding, final probe width or candidate upper differs')
        changed = hi < original['contact_upper_s'][i]
        if not changed:
            if any(not identical(proposed[k][i:i+1], original[k][i:i+1]) for k in original):
                raise ValueError('No earlier witness must reuse every original byte')
            continue
        pose = np.asarray([np.interp(hi, time, states[:, k]) for k in range(4)])
        body, _ = geos(xy[i], pose, vehicle)
        if body + error > TOL:
            raise ValueError('New upper is not a strict independent witness')
        mid = (float(original['contact_lower_s'][i]) + hi) / 2
        _, face = geos(xy[i], np.asarray([np.interp(mid, time, states[:, k]) for k in range(4)]), vehicle)
        order = np.argsort(face)
        a, b = sorted(map(int, order[:2]))
        adjacent = (a, b) in ((0, 1), (1, 2), (0, 3), (2, 3))
        near = face[order[1]] - face[order[0]]
        far = face[order[2]] - face[order[1]]
        corner_codes = {(0, 1): 5, (1, 2): 6, (0, 3): 7, (2, 3): 8}
        code = corner_codes[(a, b)] if near <= .001 and adjacent else int(order[0]) + 1
        env = error + max_speed * (hi - float(original['contact_lower_s'][i])) / 2
        stable = (near - 2 * env > .001) or (near + 2 * env < .001 and far > 2 * env and adjacent)
        bits = (1 << (code - 1)) if stable else 255
        if (proposed['nominal_instantaneous_edge'][i] != code or bool(proposed['edge_certain'][i]) != stable
                or proposed['possible_edge_codes'][i] != bits):
            raise ValueError('Independent nominal finite face or confidence differs')
    return {'all_selected_records': n, 'all_probe_GE0S_queries': checked,
            'strict_new_upper_witnesses': int(np.sum(proposed['contact_upper_s'] < original['contact_upper_s'])),
            'all_original_scientific_lower_bytes_unchanged': True,
            'internal_probe_low_never_promoted_to_scientific_lower': True}


def summary(original, proposed, trace):
    changed = proposed['contact_upper_s'] < original['contact_upper_s']
    return {'selected_point_path_records': len(changed), 'earlier_witnesses': int(changed.sum()),
        'all_fields_exact_reused_no_earlier_witness': int((~changed).sum()),
        'initial_zero_width_exact_reuse': int(np.sum(original['contact_upper_s'] == original['contact_lower_s'])),
        'candidate_edge_certain': int(proposed['edge_certain'].sum()),
        'candidate_edge_still_uncertain': int((~proposed['edge_certain']).sum()),
        'probe_evaluations': int(trace['evaluations'].sum()),
        'probe_budget_exhausted': int(trace['probe_budget_exhausted'].sum())}
