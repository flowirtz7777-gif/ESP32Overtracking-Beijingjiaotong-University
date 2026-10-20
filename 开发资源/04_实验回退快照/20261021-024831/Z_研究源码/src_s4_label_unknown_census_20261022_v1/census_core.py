"""Complete conditional-label accounting; no labels, times or scores are changed."""
import numpy as np

REASONS = {
    1: 'combined_status_unknown', 2: 'both_witnessed_combined_edge_not_singleton',
    4: 'contact_existence_not_decided_by_both_paths',
    8: 'oldpath_possible_without_witness', 16: 'independent_possible_without_witness',
    32: 'oldpath_budget', 64: 'independent_budget', 128: 'model_conflict',
    256: 'time_interval_conflict', 512: 'edge_set_conflict',
    1024: 'oldpath_witnessed_edge_uncertain', 2048: 'independent_witnessed_edge_uncertain'}


def validate(a, b, combined):
    n = len(combined['contact_status'])
    for value in (a, b, combined):
        if (any(len(v) != n for v in value.values()) or not np.isin(value['contact_status'], [0, 1, 2, 3]).all()
                or not np.isin(value['possible_edge_codes'], np.arange(256)).all()
                or np.isinf(value['contact_lower_s']).any() or np.isinf(value['contact_upper_s']).any()):
            raise ValueError('Invalid full label population')
    for value in (a, b):
        upper, lower = value['contact_upper_s'], value['contact_lower_s']
        if (np.any(np.isfinite(upper) & (~np.isfinite(lower) | (upper < lower)))
                or np.any((value['contact_status'] == 0) & (np.isfinite(lower) | np.isfinite(upper)))
                or np.any((value['contact_status'] == 1) & ~np.isfinite(upper))):
            raise ValueError('Invalid path witness or interval')
    return n


def classify(a, b, combined):
    n = validate(a, b, combined)
    wa, wb = np.isfinite(a['contact_upper_s']), np.isfinite(b['contact_upper_s'])
    both = wa & wb
    none = (a['contact_status'] == 0) & (b['contact_status'] == 0)
    bits = combined['possible_edge_codes'].astype(np.uint16)
    singleton = (bits != 0) & ((bits & (bits - np.uint16(1))) == 0)
    conditions = [combined['contact_status'] >= 2, both & ~singleton, ~(both | none),
        np.isfinite(a['contact_lower_s']) & ~wa, np.isfinite(b['contact_lower_s']) & ~wb,
        a['budget_exhausted'], b['budget_exhausted'], combined['model_conflict'],
        combined['time_interval_conflict'], combined['edge_set_conflict'],
        wa & ~a['edge_certain'], wb & ~b['edge_certain']]
    flags = np.zeros(n, np.uint16)
    for bit, condition in zip(REASONS, conditions):
        flags[condition] |= bit
    scope = (combined['contact_status'] >= 2) | (both & ~singleton) | combined['model_conflict']
    if not np.array_equal(scope, flags != 0):
        raise ValueError('A label uncertainty exists outside the complete census scope')
    return flags, scope


def independent_classify(a, b, combined):
    n = validate(a, b, combined)
    output = np.zeros(n, np.uint16)
    scope = np.zeros(n, bool)
    for i in range(n):
        wa, wb = np.isfinite(a['contact_upper_s'][i]), np.isfinite(b['contact_upper_s'][i])
        edge_count = int(combined['possible_edge_codes'][i]).bit_count()
        unknown = int(combined['contact_status'][i]) in (2, 3)
        edge_unknown = wa and wb and edge_count != 1
        conflict = bool(combined['model_conflict'][i])
        conditions = (unknown, edge_unknown,
            not ((wa and wb) or (int(a['contact_status'][i]) == 0 and int(b['contact_status'][i]) == 0)),
            np.isfinite(a['contact_lower_s'][i]) and not wa,
            np.isfinite(b['contact_lower_s'][i]) and not wb,
            bool(a['budget_exhausted'][i]), bool(b['budget_exhausted'][i]), conflict,
            bool(combined['time_interval_conflict'][i]), bool(combined['edge_set_conflict'][i]),
            wa and not bool(a['edge_certain'][i]), wb and not bool(b['edge_certain'][i]))
        output[i] = sum(bit for bit, condition in zip(REASONS, conditions) if condition)
        scope[i] = unknown or edge_unknown or conflict
    if not np.array_equal(scope, output != 0):
        raise ValueError('Independent census selection is incomplete')
    return output, scope


def summarize(a, b, combined, flags, scope):
    values, counts = np.unique(flags[scope], return_counts=True)
    return {'points': len(flags), 'census_points': int(scope.sum()),
        'combined_status_unknown': int((combined['contact_status'] >= 2).sum()),
        'reason_counts_nonexclusive': {name: int(((flags & bit) != 0).sum()) for bit, name in REASONS.items()},
        'exclusive_reason_combinations': {str(int(v)): int(n) for v, n in zip(values, counts)},
        'status_counts': {tag: {str(k): int((value['contact_status'] == k).sum()) for k in range(4)}
                          for tag, value in (('oldpath', a), ('independent', b), ('combined', combined))},
        'both_path_contact_witnesses': int((np.isfinite(a['contact_upper_s']) & np.isfinite(b['contact_upper_s'])).sum())}


def group_payload(xy, paths, combined, flags, scope):
    ids = np.flatnonzero(scope)
    result = {'union_index': ids, 'xy': xy[ids], 'all_reason_flags': flags,
              'all_scope_packbits': np.packbits(scope, bitorder='little')}
    for tag, values in (*paths.items(), ('combined', combined)):
        result.update({tag + '__' + name: value[ids] for name, value in values.items()})
    return result


def projection_payload(index, xy, original_xy, flags, scope):
    if (index.dtype.kind not in 'iu' or np.any(index < 0) or np.any(index >= len(xy))
            or not np.array_equal(xy[index], original_xy)):
        raise ValueError('Full original coordinate projection must be exact')
    selected = scope[index]
    ids = np.flatnonzero(selected)
    return {'original_index': ids, 'union_index': index[ids], 'xy': original_xy[ids],
            'reason_flags': flags[index[ids]], 'all_scope_packbits': np.packbits(selected, bitorder='little')}
