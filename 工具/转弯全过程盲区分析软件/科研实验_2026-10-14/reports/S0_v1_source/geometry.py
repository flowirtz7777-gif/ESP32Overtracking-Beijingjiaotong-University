from __future__ import annotations

import numpy as np
import shapely
from shapely import STRtree

from common import Vehicle, body_corners, right_edge

TOLERANCE = .05
GEOMETRY_EPS = 1e-9
EDGE_NAMES = {0: "NONCONTACT", 1: "FRONT", 2: "RIGHT", 3: "REAR", 4: "LEFT",
              5: "FRONT_RIGHT_CORNER", 6: "REAR_RIGHT_CORNER", 7: "FRONT_LEFT_CORNER", 8: "REAR_LEFT_CORNER"}


def swept_segments(corners):
    vertices = np.concatenate((corners[:-1], corners[1:]), axis=1)
    return shapely.convex_hull(shapely.multipoints(vertices))


def edge_segments(edges):
    return swept_segments(edges)


def edge_union(edges):
    # Co-linear overlaps are reduced before GEOS noding; curved segments remain separate.
    direction = edges[:-1, 0]-edges[:-1, 1]
    direction /= np.linalg.norm(direction, axis=1)[:, None]
    delta = edges[1:]-edges[:-1, :1]
    cross = direction[:, None, 0]*delta[:, :, 1]-direction[:, None, 1]*delta[:, :, 0]
    linear = np.max(np.abs(cross), axis=1) < 1e-10
    shapes = list(edge_segments(edges)[~linear]) if np.any(~linear) else []
    k = 0
    while k < len(linear):
        if not linear[k]:
            k += 1
            continue
        last = k+1
        origin, unit = edges[k, 0], direction[k]
        while last < len(linear) and linear[last]:
            d = edges[last+1]-origin
            if np.max(np.abs(unit[0]*d[:, 1]-unit[1]*d[:, 0])) >= 1e-9:
                break
            last += 1
        shapes.append(shapely.convex_hull(shapely.multipoints(edges[k:last+1].reshape(-1, 2))))
        k = last
    return shapely.union_all(shapes)


def complete_geometry(states, vehicle=Vehicle()):
    body = swept_segments(body_corners(states, vehicle))
    return body, shapely.union_all(body), edge_union(right_edge(states, vehicle))


def classify_edges(xy, state, vehicle=Vehicle()):
    theta, phi = state[2], state[3]
    heading = theta - phi
    hitch = state[:2] + vehicle.l_h * np.array([np.cos(theta), np.sin(theta)])
    delta = xy - hitch
    longitudinal = delta @ np.array([np.cos(heading), np.sin(heading)])
    lateral_right = delta @ np.array([np.sin(heading), -np.cos(heading)])
    distances = np.stack((np.abs(longitudinal), np.abs(lateral_right-vehicle.width/2),
                          np.abs(longitudinal+vehicle.L), np.abs(lateral_right+vehicle.width/2)), axis=1)
    order = np.argsort(distances, axis=1)
    edges = (order[:, 0] + 1).astype(np.int8)
    tied = np.take_along_axis(distances, order[:, :2], axis=1)
    corner = tied[:, 1]-tied[:, 0] <= .001
    for pair, code in [((0, 1), 5), ((1, 2), 6), ((0, 3), 7), ((2, 3), 8)]:
        selected = corner & (np.sort(order[:, :2], axis=1) == pair).all(axis=1)
        edges[selected] = code
    return edges


def label_contacts(xy, reference, segments, vehicle=Vehicle(), tolerance=TOLERANCE):
    points = shapely.points(xy)
    tree = STRtree(points)
    first = np.full(len(xy), -1, dtype=np.int32)
    edge = np.zeros(len(xy), dtype=np.int8)
    initial = shapely.polygons(body_corners(reference["state"][:1], vehicle))[0]
    ids = tree.query(initial, predicate="dwithin", distance=tolerance+GEOMETRY_EPS)
    first[ids] = 0
    edge[ids] = classify_edges(xy[ids], reference["state"][0], vehicle)
    for k, segment in enumerate(segments):
        ids = tree.query(segment, predicate="dwithin", distance=tolerance+GEOMETRY_EPS)
        ids = ids[first[ids] < 0]
        if not len(ids):
            continue
        first[ids] = k+1
        edge[ids] = classify_edges(xy[ids], reference["state"][k+1], vehicle)
    contact = np.full(len(xy), np.nan)
    valid = first >= 0
    contact[valid] = reference["time"][first[valid]]
    return {"contact_time": contact, "contact_index": first, "edge": edge,
            "front_ignored": np.isin(edge, [1, 5, 7])}


def deterministic_order(ix, iy, seed=2026101401):
    with np.errstate(over="ignore"):
        value = ix.astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
        value ^= iy.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
        value ^= np.uint64(seed)
        value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        value ^= value >> np.uint64(31)
    return np.argsort(value, kind="stable")


def generate_target_pool(body_union, right_union, maximum=35000, spacing=.025):
    minx, miny, maxx, maxy = shapely.bounds(body_union)
    ix = np.arange(np.floor((minx-.5)/spacing), np.ceil((maxx+.5)/spacing)+1, dtype=np.int32)
    iy = np.arange(np.floor((miny-.5)/spacing), np.ceil((maxy+.5)/spacing)+1, dtype=np.int32)
    pool = [[], [], []]
    # Prepared containment screens the large raster; exact distances handle the contact shell.
    body_near = shapely.buffer(body_union, TOLERANCE+.0001, quad_segs=32)
    negative_outer = shapely.buffer(body_union, .5, quad_segs=32)
    right_near_shape = shapely.buffer(right_union, .20, quad_segs=32)
    for shape in [body_union, body_near, negative_outer, right_near_shape]:
        shapely.prepare(shape)
    rows_per_chunk = max(1, 60000 // len(ix))
    for start in range(0, len(iy), rows_per_chunk):
        gx, gy = np.meshgrid(ix, iy[start:start+rows_per_chunk])
        grid = np.column_stack((gx.ravel(), gy.ravel()))
        pts = shapely.points(grid.astype(float)*spacing)
        inside = shapely.covers(body_union, pts)
        positive = inside.copy()
        shell = ~inside & shapely.covers(body_near, pts)
        positive[shell] = shapely.dwithin(pts[shell], body_union, TOLERANCE+GEOMETRY_EPS)
        right_near = shapely.covers(right_near_shape, pts) & positive
        masks = [right_near, positive & ~right_near,
                 ~positive & shapely.covers(negative_outer, pts)]
        for group, mask in enumerate(masks):
            if np.any(mask):
                pool[group].append(grid[mask])
    required = [maximum//3+(i<maximum%3) for i in range(3)]
    rows, groups, capacity = [], [], []
    for group, chunks in enumerate(pool):
        cells = np.concatenate(chunks)
        capacity.append(len(cells))
        if len(cells) < required[group]:
            raise ValueError(f"Insufficient unique near-field target pool: group={group} capacity={len(cells)} needed={required[group]}")
        order = deterministic_order(cells[:, 0], cells[:, 1])[:required[group]]
        rows.append(cells[order].astype(float)*spacing)
        groups.append(np.full(required[group], group, dtype=np.int8))
    xy = np.concatenate(rows)
    if len(np.unique(xy, axis=0)) != maximum:
        raise AssertionError("Duplicate target coordinates")
    return xy, np.concatenate(groups), {"spacing_m": spacing, "capacity": capacity,
        "stratum_counts": required, "seed": 2026101401,
        "strata": ["right_boundary_neighborhood", "swept_interior", "near_noncontact"],
        "negative_max_distance_m": .5, "negative_min_distance_m": TOLERANCE}


def subset_indices(group, count):
    ids = []
    for i in range(3):
        wanted = count//3 + (i<count%3)
        existing = np.flatnonzero(group == i)
        if len(existing) < wanted:
            raise ValueError("Subset exceeds frozen pool")
        ids.extend(existing[:wanted])
    return np.asarray(ids, dtype=np.int32)
