"""Exact whole-scope earlier-upper replacement; no scientific lower changes."""
import numpy as np

TAGS = ('oldpath', 'independent')
MUTABLE = {'contact_upper_s', 'nominal_instantaneous_edge', 'edge_certain', 'possible_edge_codes'}


def selected_mask(original):
    return np.isfinite(original['contact_upper_s']) & ~original['edge_certain']


def merge_path(original, indices, candidate, *, scalar=False):
    n = len(original['contact_status'])
    indices = np.asarray(indices)
    if (indices.ndim != 1 or indices.dtype.kind not in 'iu' or np.any(indices < 0)
            or np.any(indices >= n) or np.any(indices[1:] <= indices[:-1])
            or not np.array_equal(indices, np.flatnonzero(selected_mask(original)))
            or set(candidate) != set(original)):
        raise ValueError('Every finite-upper uncertain-edge row, sorted and unique, is required')
    if np.any(original['contact_status'][indices] != 1) or np.any(original['budget_exhausted'][indices]):
        raise ValueError('All selected rows must already have a nonbudget witness')
    for k, old in original.items():
        new = candidate[k]
        if new.dtype != old.dtype or new.shape != (len(indices), *old.shape[1:]):
            raise ValueError('Every full field and its exact dtype/shape is required')
        if k not in MUTABLE and old[indices].tobytes() != new.tobytes():
            raise ValueError('Original science lower or other immutable field changed')
    upper = candidate['contact_upper_s']
    if (not np.isfinite(upper).all() or np.any(upper > original['contact_upper_s'][indices])
            or np.any(upper < original['contact_lower_s'][indices])):
        raise ValueError('Candidate witness upper must not rise or precede original science lower')
    same_upper = upper == original['contact_upper_s'][indices]
    if any(candidate[k][same_upper].tobytes() != original[k][indices][same_upper].tobytes() for k in original):
        raise ValueError('No earlier witness requires exact reuse of all original fields')
    keep = np.ones(n, bool)
    keep[indices] = False
    out = {}
    for k, old in original.items():
        value = old.copy()
        if scalar:
            for j, i in enumerate(indices):
                value[i] = candidate[k][j]
        else:
            value[indices] = candidate[k]
        if value[keep].tobytes() != old[keep].tobytes() or value[indices].tobytes() != candidate[k].tobytes():
            raise RuntimeError('Selected or unselected replacement bytes differ')
        out[k] = value
    if out['contact_lower_s'].tobytes() != original['contact_lower_s'].tobytes():
        raise RuntimeError('All science lower bytes must remain unchanged')
    return out


def row_changed(old, new):
    n = len(old['contact_status'])
    changed = np.zeros(n, bool)
    for k, value in old.items():
        a = np.ascontiguousarray(value).view(np.uint8).reshape(n, value.dtype.itemsize)
        b = np.ascontiguousarray(new[k]).view(np.uint8).reshape(n, value.dtype.itemsize)
        changed |= np.any(a != b, axis=1)
    return changed


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
        out['upper_merge_selected_' + tag + '__packbits'] = np.packbits(mask, bitorder='little')
        out['upper_merge_changed_' + tag + '__packbits'] = np.packbits(row_changed(old, paths[tag]), bitorder='little')
    return out


def add_projection_masks(out, index, group_arrays, n):
    for tag in TAGS:
        for kind in ('selected', 'changed'):
            name = 'upper_merge_' + kind + '_' + tag + '__packbits'
            full = np.unpackbits(group_arrays[name], bitorder='little', count=n).astype(bool)
            out[name] = np.packbits(full[index], bitorder='little')
    return out

