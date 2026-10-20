"""Post-prefix diagnostic queries only; no relabeling or new exclusion proof."""
import bisect
import math
import numpy as np
import shapely

TOLERANCE = .050000001
RESOLUTION = 1e-7
CORNER = .001


def leaf(time, lower):
    k = int(np.searchsorted(time, lower, side='right')) - 1
    if k < 0 or k >= len(time) - 1:
        raise ValueError('Noninitial retained lower has no original interval')
    h = float(time[k + 1] - time[k])
    depth, width = 0, h
    while width > RESOLUTION:
        width /= 2
        depth += 1
    q = round(float((lower - time[k]) / h) * 2**depth)
    a = q / 2**depth
    if q < 0 or q >= 2**depth:
        raise ValueError('Retained lower cannot be placed on the original dyadic grid')
    return k, depth, a, width, float(time[k] + a * h), float(time[k] + (a + 2.**-depth) * h)


def confidence(face, envelope):
    order = np.argsort(face, axis=1)
    ordered = np.take_along_axis(face, order, axis=1)
    gap, far = ordered[:, 1] - ordered[:, 0], ordered[:, 2] - ordered[:, 1]
    pair = np.sort(order[:, :2], axis=1)
    adjacent = np.any(np.stack([(pair == p).all(axis=1) for p in ((0, 1), (1, 2), (0, 3), (2, 3))]), axis=0)
    margins = {'single_margin_m': gap - 2 * envelope - CORNER,
        'corner_near_margin_m': CORNER - (gap + 2 * envelope),
        'corner_far_margin_m': far - 2 * envelope}
    stable = (gap - 2 * envelope > CORNER) | ((gap + 2 * envelope < CORNER) & (far > 2 * envelope) & adjacent)
    return stable, adjacent, margins


def diagnose(xy, time, states, labels, error, vehicle, geometry, speed, nominal):
    n = len(xy)
    lower, upper = labels['contact_lower_s'], labels['contact_upper_s']
    finite, witness = np.isfinite(lower), np.isfinite(upper)
    initial = finite & (lower == time[0])
    retained = finite & ~initial
    out = {'has_lower': finite, 'has_witness': witness, 'initial_origin': initial,
           'time_leaf_origin': retained, 'known_noncontact_exact_proof_reuse': labels['contact_status'] == 0,
           'leaf_interval': np.full(n, -1, np.int32), 'leaf_depth': np.zeros(n, np.int16),
           'leaf_lower_reconstructed_exact': np.ones(n, bool), 'source_edge_rule_exact': np.ones(n, bool),
           'source_initial_rule_exact': np.ones(n, bool), 'leaf_potential_predicate_exact': np.ones(n, bool),
           'spatial_only_midpoint_rule_passes': np.zeros(n, bool), 'midpoint_adjacent': np.zeros(n, bool)}
    floats = ('leaf_a', 'leaf_start_s', 'leaf_end_s', 'leaf_width_s', 'initial_body_distance_m',
        'initial_exclusion_margin_m', 'initial_witness_margin_m', 'leaf_mid_body_distance_m',
        'leaf_motion_half_m', 'leaf_exclusion_margin_m', 'leaf_witness_margin_m',
        'bracket_width_s', 'temporal_envelope_m', 'total_envelope_m', 'witness_body_distance_m',
        'witness_margin_m', 'single_margin_m', 'corner_near_margin_m', 'corner_far_margin_m',
        'spatial_single_margin_m', 'spatial_corner_near_margin_m', 'spatial_corner_far_margin_m')
    out.update({k: np.full(n, np.nan) for k in floats})
    out['midpoint_faces_m'] = np.full((n, 4), np.nan)
    ii = np.flatnonzero(initial)
    if len(ii):
        distance, _ = geometry(xy[ii], np.broadcast_to(states[0], (len(ii), 4)))
        out['initial_body_distance_m'][ii] = distance
        out['initial_exclusion_margin_m'][ii] = distance - error - TOLERANCE
        out['initial_witness_margin_m'][ii] = TOLERANCE - (distance + error)
        out['source_initial_rule_exact'][ii] = (
            (labels['initial_tolerance_contact_possible'][ii] == (distance - error <= TOLERANCE))
            & (labels['initial_tolerance_contact_certain'][ii] == (distance + error <= TOLERANCE)))
    jj = np.flatnonzero(retained)
    poses = []
    for i in jj:
        k, depth, a, width, start, end = leaf(time, lower[i])
        out['leaf_interval'][i], out['leaf_depth'][i] = k, depth
        out['leaf_a'][i], out['leaf_width_s'][i] = a, width
        out['leaf_start_s'][i], out['leaf_end_s'][i] = start, end
        out['leaf_lower_reconstructed_exact'][i] = start == lower[i]
        out['leaf_motion_half_m'][i] = speed[k] * width / 2
        poses.append(states[k] + (a + 2.**(-depth - 1)) * (states[k + 1] - states[k]))
    if len(jj):
        distance, _ = geometry(xy[jj], np.asarray(poses))
        out['leaf_mid_body_distance_m'][jj] = distance
        margin = distance - error - out['leaf_motion_half_m'][jj] - 1e-12 - TOLERANCE
        out['leaf_exclusion_margin_m'][jj] = margin
        out['leaf_witness_margin_m'][jj] = TOLERANCE - (distance + error)
        out['leaf_potential_predicate_exact'][jj] = margin <= 0
    wi = np.flatnonzero(witness)
    if len(wi):
        middle = (lower[wi] + upper[wi]) / 2
        pose = np.column_stack([np.interp(middle, time, states[:, j]) for j in range(4)])
        _, faces = geometry(xy[wi], pose)
        upper_pose = np.column_stack([np.interp(upper[wi], time, states[:, j]) for j in range(4)])
        distance, _ = geometry(xy[wi], upper_pose)
        width = upper[wi] - lower[wi]
        temporal = float(speed.max()) * width / 2
        envelope = error + temporal
        stable, adjacent, margins = confidence(faces, envelope)
        spatial, _, spatial_margins = confidence(faces, np.full(len(wi), error))
        out['midpoint_faces_m'][wi] = faces
        out['bracket_width_s'][wi], out['temporal_envelope_m'][wi], out['total_envelope_m'][wi] = width, temporal, envelope
        out['witness_body_distance_m'][wi], out['witness_margin_m'][wi] = distance, TOLERANCE - (distance + error)
        out['source_edge_rule_exact'][wi] = (stable == labels['edge_certain'][wi]) & (nominal(faces) == labels['nominal_instantaneous_edge'][wi])
        out['spatial_only_midpoint_rule_passes'][wi], out['midpoint_adjacent'][wi] = spatial, adjacent
        for name, values in margins.items():
            out[name][wi] = values
        for name, values in spatial_margins.items():
            out['spatial_' + name][wi] = values
    out['source_initial_origin_exact'] = initial == labels['initial_tolerance_contact_possible']
    return out


def summary(labels, metrics):
    unknown = metrics['has_lower'] & ~metrics['has_witness']
    edge = metrics['has_witness'] & ~labels['edge_certain']
    spatial = metrics['spatial_only_midpoint_rule_passes']
    return {'records': len(unknown), 'known_noncontact_exact_proof_reuse': int(metrics['known_noncontact_exact_proof_reuse'].sum()),
        'possible_without_witness': int(unknown.sum()),
        'possible_without_witness_initial_origin': int((unknown & metrics['initial_origin']).sum()),
        'possible_without_witness_time_leaf_origin': int((unknown & metrics['time_leaf_origin']).sum()),
        'witnessed': int(metrics['has_witness'].sum()), 'witnessed_edge_uncertain': int(edge.sum()),
        'uncertain_edge_spatial_only_midpoint_rule_passes': int((edge & spatial).sum()),
        'uncertain_edge_spatial_only_midpoint_rule_fails': int((edge & ~spatial).sum()),
        'budget_flags': int(labels['budget_exhausted'].sum()),
        'all_saved_initial_and_edge_rules_exact': all(bool(metrics[k].all()) for k in
            ('source_initial_origin_exact', 'source_initial_rule_exact', 'source_edge_rule_exact')),
        'all_reconstructed_leaf_lowers_exact': bool(metrics['leaf_lower_reconstructed_exact'].all()),
        'all_retained_leaf_predicates_reproduced': bool(metrics['leaf_potential_predicate_exact'].all())}


def geos_geometry(point, pose, vehicle):
    x, y, theta, phi = map(float, pose)
    heading = theta - phi
    hx, hy = x + vehicle.l_h * math.cos(theta), y + vehicle.l_h * math.sin(theta)
    rx, ry = hx - vehicle.L * math.cos(heading), hy - vehicle.L * math.sin(heading)
    nx, ny = vehicle.width / 2 * math.sin(heading), -vehicle.width / 2 * math.cos(heading)
    corners = [(hx + nx, hy + ny), (rx + nx, ry + ny), (rx - nx, ry - ny), (hx - nx, hy - ny)]
    p = shapely.Point(*point)
    faces = [p.distance(shapely.LineString([corners[a], corners[b]])) for a, b in ((3, 0), (0, 1), (1, 2), (2, 3))]
    return p.distance(shapely.Polygon(corners)), np.asarray(faces)


def independently_check(xy, time, states, labels, error, vehicle, saved):
    speeds = []
    for k in range(len(time) - 1):
        delta = states[k + 1] - states[k]
        speeds.append((math.hypot(float(delta[0]), float(delta[1])) + abs(vehicle.l_h) * abs(float(delta[2]))
            + math.hypot(vehicle.L, vehicle.width / 2) * abs(float(delta[2] - delta[3]))) / float(time[k + 1] - time[k]))
    maximum = max(speeds)
    geometries = 0
    for i, point in enumerate(xy):
        lower, upper = float(labels['contact_lower_s'][i]), float(labels['contact_upper_s'][i])
        if labels['budget_exhausted'][i]:
            raise RuntimeError('This complete nonbudget diagnostic cannot omit a remaining budget')
        initial, retained = math.isfinite(lower) and lower == time[0], math.isfinite(lower) and lower != time[0]
        if initial != bool(saved['initial_origin'][i]) or retained != bool(saved['time_leaf_origin'][i]):
            raise RuntimeError('Original lower provenance differs')
        booleans = {'has_lower': math.isfinite(lower), 'has_witness': math.isfinite(upper),
            'known_noncontact_exact_proof_reuse': int(labels['contact_status'][i]) == 0,
            'source_initial_origin_exact': initial == bool(labels['initial_tolerance_contact_possible'][i]),
            'source_initial_rule_exact': True, 'source_edge_rule_exact': True,
            'leaf_lower_reconstructed_exact': True, 'leaf_potential_predicate_exact': True,
            'spatial_only_midpoint_rule_passes': False, 'midpoint_adjacent': False}
        expected = {}
        if initial:
            distance, _ = geos_geometry(point, states[0], vehicle)
            geometries += 1
            expected.update(initial_body_distance_m=distance, initial_exclusion_margin_m=distance - error - TOLERANCE,
                            initial_witness_margin_m=TOLERANCE - (distance + error))
            booleans['source_initial_rule_exact'] = (
                bool(labels['initial_tolerance_contact_possible'][i]) == (distance - error <= TOLERANCE)
                and bool(labels['initial_tolerance_contact_certain'][i]) == (distance + error <= TOLERANCE))
        if retained:
            k = bisect.bisect_right(time, lower) - 1
            duration = float(time[k + 1] - time[k])
            depth = 0
            while duration / 2**depth > RESOLUTION:
                depth += 1
            a = float(saved['leaf_a'][i])
            if (saved['leaf_interval'][i] != k or saved['leaf_depth'][i] != depth
                    or not (0 <= a < 1) or not (a * 2**depth).is_integer()
                    or float(time[k] + a * duration) != lower):
                raise RuntimeError('Every original dyadic retained leaf endpoint must reconstruct exactly')
            width = duration / 2**depth
            pose = states[k] + (a + .5 / 2**depth) * (states[k + 1] - states[k])
            distance, _ = geos_geometry(point, pose, vehicle)
            geometries += 1
            motion = speeds[k] * width / 2
            expected.update(leaf_start_s=lower, leaf_end_s=float(time[k] + (a + 1 / 2**depth) * duration),
                leaf_width_s=width, leaf_mid_body_distance_m=distance, leaf_motion_half_m=motion,
                leaf_exclusion_margin_m=distance - error - motion - 1e-12 - TOLERANCE,
                leaf_witness_margin_m=TOLERANCE - (distance + error))
        if math.isfinite(upper):
            midpoint = (lower + upper) / 2
            pose = np.asarray([np.interp(midpoint, time, states[:, j]) for j in range(4)])
            _, faces = geos_geometry(point, pose, vehicle)
            upper_pose = np.asarray([np.interp(upper, time, states[:, j]) for j in range(4)])
            distance, _ = geos_geometry(point, upper_pose, vehicle)
            geometries += 2
            order = sorted(range(4), key=lambda k: (faces[k], k))
            gap, far = faces[order[1]] - faces[order[0]], faces[order[2]] - faces[order[1]]
            adjacent = tuple(sorted(order[:2])) in ((0, 1), (1, 2), (0, 3), (2, 3))
            temporal = maximum * (upper - lower) / 2
            envelope = error + temporal
            expected.update(midpoint_faces_m=faces, bracket_width_s=upper - lower, temporal_envelope_m=temporal,
                total_envelope_m=envelope, witness_body_distance_m=distance, witness_margin_m=TOLERANCE - (distance + error),
                single_margin_m=gap - 2 * envelope - CORNER, corner_near_margin_m=CORNER - (gap + 2 * envelope),
                corner_far_margin_m=far - 2 * envelope, spatial_single_margin_m=gap - 2 * error - CORNER,
                spatial_corner_near_margin_m=CORNER - (gap + 2 * error), spatial_corner_far_margin_m=far - 2 * error)
            stable = gap - 2 * envelope > CORNER or (gap + 2 * envelope < CORNER and far > 2 * envelope and adjacent)
            spatial = gap - 2 * error > CORNER or (gap + 2 * error < CORNER and far > 2 * error and adjacent)
            nominal = order[0] + 1
            if gap <= CORNER:
                nominal = {(0, 1): 5, (1, 2): 6, (0, 3): 7, (2, 3): 8}.get(tuple(sorted(order[:2])), nominal)
            booleans.update(midpoint_adjacent=adjacent, spatial_only_midpoint_rule_passes=spatial,
                source_edge_rule_exact=(stable == bool(labels['edge_certain'][i])
                    and nominal == int(labels['nominal_instantaneous_edge'][i])))
        for name, value in booleans.items():
            if bool(saved[name][i]) != value:
                raise RuntimeError('Independent complete scalar diagnostic flag differs: ' + name)
        for name, value in expected.items():
            if not np.allclose(saved[name][i], value, rtol=1e-12, atol=1e-10, equal_nan=True):
                raise RuntimeError('Independent scalar/GEOS diagnostic geometry differs: ' + name)
    return {'all_records': len(xy), 'independent_GE0S_pose_queries': geometries,
            'comparison_tolerance_not_a_label_or_margin_relaxation': True}
