"""Merge all accepted supplemental-witness scope rows without changing scientific lowers."""
import numpy as np

TAGS = ('oldpath', 'independent')
MUTABLE = {'contact_status', 'contact_upper_s', 'nominal_instantaneous_edge',
           'edge_certain', 'possible_edge_codes'}
PREFIXES = ('merge_', 'upper_merge_', 'local_motion_', 'probe_merge_', 'suffix_merge_')


def same(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def take(a, index, *, scalar=False):
    if scalar:
        return np.asarray([a[int(i)] for i in index], dtype=a.dtype).reshape((len(index),) + a.shape[1:])
    return a[index]


def merge_path(original, index, candidate, full_scope, found, *, scalar=False):
    n = len(original['contact_status'])
    if (full_scope.dtype != np.bool_ or full_scope.shape != (n,)
            or index.ndim != 1 or index.dtype.kind != 'i' or index.dtype.itemsize not in (4, 8)
            or not np.array_equal(index, np.flatnonzero(full_scope))
            or set(candidate) != set(original) or found.dtype != np.bool_
            or found.shape != (len(index),)):
        raise ValueError('Every complete original scope row and signed index must bind')
    old = {k: take(v, index, scalar=scalar) for k, v in original.items()}
    eligible = np.isfinite(old['contact_lower_s']) & ~np.isfinite(old['contact_upper_s']) & (old['contact_status'] == 2)
    if np.any(found & ~eligible):
        raise ValueError('Only originally unwitnessed unknown rows may gain accepted witnesses')
    for name, values in original.items():
        new = candidate[name]
        if new.dtype != values.dtype or new.shape != (len(index),) + values.shape[1:]:
            raise ValueError('Every field dtype and full shape must remain exact')
        if name not in MUTABLE and not same(new, old[name]):
            raise ValueError('Scientific lower or original provenance changed')
        if not same(new[~found], old[name][~found]):
            raise ValueError('Every unchanged, unknown and already witnessed row must remain byte-exact')
    upper, lower = candidate['contact_upper_s'][found], candidate['contact_lower_s'][found]
    codes = candidate['nominal_instantaneous_edge'][found].astype(np.int64)
    bits = candidate['possible_edge_codes'][found].astype(np.int64)
    certain = candidate['edge_certain'][found]
    if (np.any(candidate['contact_status'][found] != 1) or not np.isfinite(upper).all()
            or np.any(upper < lower) or np.any((codes < 1) | (codes > 8))
            or np.any((bits < 1) | (bits > 255))):
        raise ValueError('Accepted finite contact endpoints and nominal finite-face codes required')
    singleton = np.left_shift(1, codes - 1)
    if np.any((bits & singleton) == 0) or np.any(certain & (bits != singleton)):
        raise ValueError('Every nominal edge must be possible; certainty requires its singleton')
    output = {}
    for name, values in original.items():
        new = values.copy()
        if scalar:
            for j, i in enumerate(index):
                new[int(i)] = candidate[name][j]
        else:
            new[index] = candidate[name]
        if not same(new[~full_scope], values[~full_scope]) or not same(new[index], candidate[name]):
            raise RuntimeError('Selected or unselected replacement bytes differ')
        output[name] = new
    if not same(output['contact_lower_s'], original['contact_lower_s']):
        raise RuntimeError('All original scientific lowers and prefix coverage must remain exact')
    return output


def changed(old, new):
    n = len(old['contact_status'])
    result = np.zeros(n, bool)
    for name, a in old.items():
        b = new[name]
        row_bytes = a.dtype.itemsize * int(np.prod(a.shape[1:]))
        result |= np.any(np.ascontiguousarray(a).view(np.uint8).reshape(n, row_bytes)
            != np.ascontiguousarray(b).view(np.uint8).reshape(n, row_bytes), axis=1)
    return result


def unpack(mask, n):
    if mask.dtype != np.uint8 or mask.shape != ((n + 7) // 8,):
        raise ValueError('Exact packbits dtype and shape required')
    bits = np.unpackbits(mask, bitorder='little')
    if bits[n:].any():
        raise ValueError('Nonzero packbits padding')
    return bits[:n].astype(bool)


def group_payload(original, paths, combined, flags, scope, selected, found):
    out = {k: v for k, v in original.items()
        if not any(k.startswith(tag + '__') for tag in (*TAGS, 'combined'))}
    for tag, arrays in (*paths.items(), ('combined', combined)):
        out.update({tag + '__' + k: v for k, v in arrays.items()})
    out.update(all_reason_flags=flags, all_scope_packbits=np.packbits(scope, bitorder='little'))
    for tag in TAGS:
        selected_mask, witness_mask = np.zeros(len(flags), bool), np.zeros(len(flags), bool)
        selected_mask[selected[tag]], witness_mask[selected[tag]] = True, found[tag]
        old = {k.split('__', 1)[1]: v for k, v in original.items() if k.startswith(tag + '__')}
        differences = changed(old, paths[tag])
        if not np.array_equal(differences, witness_mask):
            raise ValueError('All and only independently accepted new-witness rows may change')
        for kind, mask in (('scope', selected_mask), ('new_witness', witness_mask), ('changed', differences)):
            out['suffix_merge_' + kind + '_' + tag + '__packbits'] = np.packbits(mask, bitorder='little')
    return out


def project(index, xy, target_xy, paths, combined, flags, scope, group, *, scalar=False):
    n = len(xy)
    if (index.ndim != 1 or index.dtype.kind != 'i' or index.dtype.itemsize not in (4, 8)
            or np.any(index < 0) or np.any(index >= n)
            or not same(take(xy, index, scalar=scalar), target_xy)):
        raise ValueError('Every original signed index, duplicate, order and coordinate byte must bind')
    out = {'union_index': index.copy(), 'xy': target_xy.copy(),
        'all_reason_flags': take(flags, index, scalar=scalar),
        'all_scope_packbits': np.packbits(take(scope, index, scalar=scalar), bitorder='little')}
    for tag, arrays in (*paths.items(), ('combined', combined)):
        out.update({tag + '__' + k: take(v, index, scalar=scalar) for k, v in arrays.items()})
    for name, mask in group.items():
        if name.startswith(PREFIXES) and name.endswith('__packbits'):
            out[name] = np.packbits(take(unpack(mask, n), index, scalar=scalar), bitorder='little')
    return out
