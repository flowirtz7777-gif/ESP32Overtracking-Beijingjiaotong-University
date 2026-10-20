"""Exact conditional-asset replacement and independent scalar combination."""
import numpy as np

TAGS = ('oldpath', 'independent')


def merge_path(original, indices, refined, *, scalar=False):
    n = len(original['contact_status'])
    indices = np.asarray(indices)
    if (indices.ndim != 1 or indices.dtype.kind not in 'iu'
            or np.any(indices < 0) or np.any(indices >= n)
            or np.any(indices[1:] <= indices[:-1])
            or not np.array_equal(indices, np.flatnonzero(original['budget_exhausted']))
            or set(original) != set(refined)):
        raise ValueError('Every and only original exhausted index, sorted and unique, is required')
    output = {}
    keep = np.ones(n, bool)
    keep[indices] = False
    for name, values in original.items():
        new = refined[name]
        if values.dtype != new.dtype or new.shape != (len(indices), *values.shape[1:]):
            raise ValueError('Complete replacement shape and dtype must remain exact')
        out = values.copy()
        if scalar:
            for j, i in enumerate(indices):
                out[i] = new[j]
        else:
            out[indices] = new
        if out[keep].tobytes() != values[keep].tobytes() or out[indices].tobytes() != new.tobytes():
            raise RuntimeError('Any selected or unselected quantity changed during exact merge')
        output[name] = out
    return output


def scalar_combine(a, b):
    n = len(a['contact_status'])
    out = {'contact_status': np.empty(n, np.int8),
           'contact_lower_s': np.empty(n, a['contact_lower_s'].dtype),
           'contact_upper_s': np.empty(n, a['contact_upper_s'].dtype),
           'possible_edge_codes': np.empty(n, a['possible_edge_codes'].dtype),
           **{k: np.empty(n, bool) for k in
              ('model_conflict', 'time_interval_conflict', 'edge_set_conflict')}}
    for i in range(n):
        sa, sb = int(a['contact_status'][i]), int(b['contact_status'][i])
        both, neither = sa == 1 and sb == 1, sa == 0 and sb == 0
        out['contact_status'][i] = 3 if 3 in (sa, sb) else (1 if both else (0 if neither else 2))
        out['contact_lower_s'][i] = np.fmin(a['contact_lower_s'][i], b['contact_lower_s'][i])
        out['contact_upper_s'][i] = np.fmax(a['contact_upper_s'][i], b['contact_upper_s'][i])
        x, y = int(a['possible_edge_codes'][i]), int(b['possible_edge_codes'][i])
        out['possible_edge_codes'][i] = (x | y) if both or neither else 255
        time_conflict = both and (a['contact_lower_s'][i] > b['contact_upper_s'][i]
                                  or b['contact_lower_s'][i] > a['contact_upper_s'][i])
        edge_conflict = both and (x & y) == 0
        out['time_interval_conflict'][i] = time_conflict
        out['edge_set_conflict'][i] = edge_conflict
        out['model_conflict'][i] = ((sa == 0 and sb == 1) or (sa == 1 and sb == 0)
                                    or time_conflict or edge_conflict)
    return out


def changed(a, b):
    result = np.zeros(len(a['contact_status']), bool)
    for name in a:
        left, right = a[name], b[name]
        equal = left == right
        if left.dtype.kind == 'f':
            equal |= np.isnan(left) & np.isnan(right)
        if equal.ndim > 1:
            equal = equal.all(axis=tuple(range(1, equal.ndim)))
        result |= ~equal
    return result


def group_payload(original, paths, combined, flags, scope, selected):
    out = {k: v for k, v in original.items()
           if not any(k.startswith(tag + '__') for tag in (*TAGS, 'combined'))}
    for tag, arrays in (*paths.items(), ('combined', combined)):
        out.update({tag + '__' + k: v for k, v in arrays.items()})
    out.update(all_reason_flags=flags, all_scope_packbits=np.packbits(scope, bitorder='little'))
    for tag in TAGS:
        mask = np.zeros(len(flags), bool)
        mask[selected[tag]] = True
        old = {k.split('__', 1)[1]: v for k, v in original.items() if k.startswith(tag + '__')}
        out['merge_selected_' + tag + '__packbits'] = np.packbits(mask, bitorder='little')
        out['merge_changed_' + tag + '__packbits'] = np.packbits(changed(old, paths[tag]), bitorder='little')
    return out


def project(index, xy, original_xy, paths, combined, flags, scope, group_masks):
    if (index.ndim != 1 or index.dtype.kind not in 'iu' or np.any(index < 0)
            or np.any(index >= len(xy)) or not np.array_equal(xy[index], original_xy)):
        raise ValueError('Every original point/coordinate/index must project exactly')
    out = {'union_index': index, 'xy': original_xy, 'all_reason_flags': flags[index],
           'all_scope_packbits': np.packbits(scope[index], bitorder='little')}
    for tag, arrays in (*paths.items(), ('combined', combined)):
        out.update({tag + '__' + k: v[index] for k, v in arrays.items()})
    for tag in TAGS:
        for kind in ('selected', 'changed'):
            key = 'merge_' + kind + '_' + tag + '__packbits'
            full = np.unpackbits(group_masks[key], bitorder='little', count=len(xy)).astype(bool)
            out[key] = np.packbits(full[index], bitorder='little')
    return out


def scalar_discrepancies(target, combined):
    n = len(combined['contact_status'])
    out = {k: np.zeros(n, bool) for k in ('old_existence_incompatible', 'old_edge_incompatible',
        'old_time_outside_new_interval', 'all_undetermined', 'all_model_conflicts')}
    for i in range(n):
        old = bool(np.isfinite(target['contact_time'][i]))
        status = int(combined['contact_status'][i])
        edge = 1 << max(int(target['edge'][i]) - 1, 0)
        out['old_existence_incompatible'][i] = status < 2 and old != (status == 1)
        out['old_edge_incompatible'][i] = status < 2 and old and not (int(combined['possible_edge_codes'][i]) & edge)
        out['old_time_outside_new_interval'][i] = status == 1 and old and (
            target['contact_time'][i] < combined['contact_lower_s'][i] - 1e-10
            or target['contact_time'][i] > combined['contact_upper_s'][i] + 1e-10)
        out['all_undetermined'][i] = status >= 2
        out['all_model_conflicts'][i] = bool(combined['model_conflict'][i])
    return out
