"""Exact original-order scope and retained unwitnessed diagnostic projection."""
import numpy as np


def same(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def rows(source, requested, *, scalar=False):
    if (source.ndim != 1 or requested.ndim != 1 or source.dtype.kind != "i" or source.dtype.itemsize not in (4, 8)
            or requested.dtype.kind != "i" or requested.dtype.itemsize not in (4, 8) or len(np.unique(source)) != len(source)
            or np.any(source < 0) or np.any(requested < 0)):
        raise ValueError("Unique nonnegative original union-index source required")
    if scalar:
        lookup = {int(v): i for i, v in enumerate(source)}
        try:
            return np.asarray([lookup[int(v)] for v in requested], np.int64)
        except KeyError as error:
            raise ValueError("A requested original point is absent") from error
    order = np.argsort(source)
    ordered = source[order]
    at = np.searchsorted(ordered, requested)
    if np.any(at >= len(source)) or not np.array_equal(ordered[at], requested):
        raise ValueError("A requested original point is absent")
    return order[at]


def take(values, index, *, scalar=False):
    return np.asarray([values[int(i)] for i in index], dtype=values.dtype).reshape(
        (len(index),) + values.shape[1:]) if scalar else values[index]


def retained_unknown(scope_index, xy, labels, old, tag, *, scalar=False):
    mask = np.isfinite(labels["contact_lower_s"]) & ~np.isfinite(labels["contact_upper_s"])
    selected = np.flatnonzero(mask).astype(np.int64)
    index = scope_index[selected]
    prior_rows = rows(old["union_index"], index, scalar=scalar)
    if not same(xy[selected], take(old["xy"], prior_rows, scalar=scalar)):
        raise ValueError("Every retained unwitnessed coordinate must be byte-exact")
    result = {"retained_unknown_union_index": index, "retained_unknown_xy": xy[selected],
              "retained_unknown_parent_row": prior_rows}
    for name, values in labels.items():
        before = old[tag + "__label__" + name]
        projected = take(before, prior_rows, scalar=scalar)
        if not same(values[selected], projected):
            raise ValueError("Unwitnessed label evidence differs from accepted diagnostic")
        result["retained_unknown_label__" + name] = projected
    metrics = {k[len(tag + "__metric__"):]: v for k, v in old.items() if k.startswith(tag + "__metric__")}
    if not metrics:
        raise ValueError("All accepted initial/leaf/errorband diagnostics are required")
    result.update({"retained_unknown_metric__" + k: take(v, prior_rows, scalar=scalar)
                   for k, v in metrics.items()})
    return result


def project(full_xy, union_index, target_xy, group, *, scalar=False):
    if (union_index.ndim != 1 or union_index.dtype.kind != "i" or union_index.dtype.itemsize not in (4, 8)
            or np.any(union_index < 0) or np.any(union_index >= len(full_xy))
            or not same(full_xy[union_index], target_xy)):
        raise ValueError("Every original-order coordinate and union index must bind exactly")
    full_scope = np.zeros(len(full_xy), bool)
    full_scope[group["union_index"]] = True
    selected = np.flatnonzero(full_scope[union_index]).astype(np.int64)
    projected_union = union_index[selected]
    rr = rows(group["union_index"], projected_union, scalar=scalar)
    out = {"source_union_index": union_index.copy(), "original_index": selected,
           "union_index": projected_union, "xy": target_xy[selected],
           "full_scope_packbits": np.packbits(full_scope[union_index], bitorder="little")}
    for name, value in group.items():
        if name.startswith(("original__", "candidate__", "trace__")) and not name.endswith("__packbits"):
            out[name] = take(value, rr, scalar=scalar)
            if value.dtype == np.bool_:
                out[name + "__packbits"] = np.packbits(out[name], bitorder="little")
    unknown = np.zeros(len(full_xy), bool)
    unknown[group["retained_unknown_union_index"]] = True
    original_unknown = np.flatnonzero(unknown[union_index]).astype(np.int64)
    unknown_union = union_index[original_unknown]
    uu = rows(group["retained_unknown_union_index"], unknown_union, scalar=scalar)
    out.update(original_unknown_index=original_unknown, retained_unknown_union_index=unknown_union,
               retained_unknown_xy=target_xy[original_unknown],
               full_unknown_packbits=np.packbits(unknown[union_index], bitorder="little"))
    for name, value in group.items():
        if name.startswith(("retained_unknown_label__", "retained_unknown_metric__")) or name == "retained_unknown_parent_row":
            out[name] = take(value, uu, scalar=scalar)
    for name, value in group.items():
        if name.startswith("parent_provenance__"):
            unpacked = np.unpackbits(value, bitorder="little")
            if len(value) != (len(full_xy) + 7) // 8 or unpacked[len(full_xy):].any():
                raise ValueError("Parent full mask length/padding differs")
            out[name] = np.packbits(unpacked[:len(full_xy)][union_index], bitorder="little")
    return out


