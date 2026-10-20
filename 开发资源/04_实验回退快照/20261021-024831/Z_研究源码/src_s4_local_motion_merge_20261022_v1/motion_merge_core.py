"""Full combined-scope edge-only replacement and byte-exact projections."""
import numpy as np

TAGS = ("oldpath", "independent")
MUTABLE = {"edge_certain", "possible_edge_codes"}


def same(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def take(a, index, *, scalar=False):
    if scalar:
        return np.asarray([a[int(i)] for i in index], dtype=a.dtype).reshape((len(index),) + a.shape[1:])
    return a[index]


def merge_path(original, index, candidate, full_scope, certified, *, scalar=False):
    n = len(original["contact_status"])
    if (full_scope.dtype != np.bool_ or full_scope.shape != (n,) or index.ndim != 1
            or index.dtype.kind != "i" or index.dtype.itemsize not in (4, 8)
            or not np.array_equal(index, np.flatnonzero(full_scope))
            or set(candidate) != set(original) or certified.dtype != np.bool_
            or certified.shape != (len(index),)):
        raise ValueError("Every full combined-scope row on both paths is required")
    old = {k: take(v, index, scalar=scalar) for k, v in original.items()}
    eligible = np.isfinite(old["contact_upper_s"]) & ~old["edge_certain"]
    if np.any(certified & (~eligible | (old["contact_status"] != 1))):
        raise ValueError("Only previously witnessed uncertain edges may gain confidence")
    for name, values in original.items():
        new = candidate[name]
        if new.dtype != values.dtype or new.shape != (len(index),) + values.shape[1:]:
            raise ValueError("Every original field dtype and shape must remain exact")
        if name not in MUTABLE and not same(new, old[name]):
            raise ValueError("Immutable scientific endpoints, nominal code or provenance changed")
        if not same(new[~certified], old[name][~certified]):
            raise ValueError("Every noncertified row, including unknowns, must remain byte-exact")
    if np.any(~candidate["edge_certain"][certified]):
        raise ValueError("Every independently certified row must be marked certain")
    codes = old["nominal_instantaneous_edge"][certified].astype(np.int64)
    if np.any((codes < 1) | (codes > 8)):
        raise ValueError("Original nominal edge/corner code required")
    if not np.array_equal(candidate["possible_edge_codes"][certified], np.left_shift(1, codes - 1)):
        raise ValueError("Only the original nominal singleton code may replace the edge set")
    output = {}
    keep = ~full_scope
    for name, values in original.items():
        new = values.copy()
        if scalar:
            for j, i in enumerate(index):
                new[i] = candidate[name][j]
        else:
            new[index] = candidate[name]
        if not same(new[keep], values[keep]) or not same(new[index], candidate[name]):
            raise RuntimeError("Selected or unselected replacement bytes differ")
        output[name] = new
    return output


def changed(old, new):
    n = len(old["contact_status"])
    result = np.zeros(n, bool)
    for name, a in old.items():
        b = new[name]
        row_bytes = a.dtype.itemsize * int(np.prod(a.shape[1:]))
        left = np.ascontiguousarray(a).view(np.uint8).reshape(n, row_bytes)
        right = np.ascontiguousarray(b).view(np.uint8).reshape(n, row_bytes)
        result |= np.any(left != right, axis=1)
    return result


def unpack(mask, n):
    if mask.dtype != np.uint8 or mask.shape != ((n + 7) // 8,):
        raise ValueError("Exact packbits shape and dtype required")
    bits = np.unpackbits(mask, bitorder="little")
    if bits[n:].any():
        raise ValueError("Nonzero packbits padding")
    return bits[:n].astype(bool)


def group_payload(original, paths, combined, flags, scope, selected, certified):
    out = {k: v for k, v in original.items()
           if not any(k.startswith(tag + "__") for tag in (*TAGS, "combined"))}
    for tag, arrays in (*paths.items(), ("combined", combined)):
        out.update({tag + "__" + k: v for k, v in arrays.items()})
    out.update(all_reason_flags=flags, all_scope_packbits=np.packbits(scope, bitorder="little"))
    for tag in TAGS:
        n = len(flags)
        chosen = np.zeros(n, bool)
        chosen[selected[tag]] = True
        proof = np.zeros(n, bool)
        proof[selected[tag]] = certified[tag]
        old = {k.split("__", 1)[1]: v for k, v in original.items() if k.startswith(tag + "__")}
        masks = {"selected": chosen, "certified": proof, "changed": changed(old, paths[tag])}
        if not np.array_equal(masks["changed"], proof):
            raise ValueError("All and only certified rows may change")
        for kind, mask in masks.items():
            out["local_motion_" + kind + "_" + tag + "__packbits"] = np.packbits(mask, bitorder="little")
    return out


def project(index, xy, target_xy, paths, combined, flags, scope, group, *, scalar=False):
    n = len(xy)
    if (index.ndim != 1 or index.dtype.kind != "i" or index.dtype.itemsize not in (4, 8)
            or np.any(index < 0) or np.any(index >= n)
            or not same(take(xy, index, scalar=scalar), target_xy)):
        raise ValueError("Every original signed index dtype, order and coordinate must bind exactly")
    out = {"union_index": index.copy(), "xy": target_xy.copy(),
           "all_reason_flags": take(flags, index, scalar=scalar),
           "all_scope_packbits": np.packbits(take(scope, index, scalar=scalar), bitorder="little")}
    for tag, arrays in (*paths.items(), ("combined", combined)):
        out.update({tag + "__" + k: take(v, index, scalar=scalar) for k, v in arrays.items()})
    for name, mask in group.items():
        if name.startswith(("merge_", "upper_merge_", "local_motion_")) and name.endswith("__packbits"):
            out[name] = np.packbits(take(unpack(mask, n), index, scalar=scalar), bitorder="little")
    return out

