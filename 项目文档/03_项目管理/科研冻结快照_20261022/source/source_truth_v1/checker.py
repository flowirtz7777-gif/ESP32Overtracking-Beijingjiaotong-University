"""Independent pure-C candidate checker for worker source geometry frontiers.

This module consumes frozen source-step records, a separately recomputed own
error chain, and one worker point cover. It never imports worker code or the
worker frontier reducer. Results are candidate comparisons only: no labels,
scientific admission, or face pruning.
"""
from fractions import Fraction as F
from . import independent_geometry as _GEOM
_STEP = _GEOM._STEP

MAX_OWN_CALLS_PER_POINT = 4096
MAX_DEPTH = 24


def _rat(x):
    if isinstance(x, bool) or not isinstance(x, (int, F)):
        raise TypeError("Exact int/Fraction required; bool/float forbidden")
    return F(x)


def _pair(x):
    if not isinstance(x, (tuple, list)) or len(x) != 2:
        raise TypeError("Expected exact two-endpoint interval")
    a, b = map(_rat, x)
    if a > b:
        raise ValueError("Reversed interval")
    return a, b


def _vec(x, size, name):
    if not isinstance(x, (tuple, list)) or len(x) != size:
        raise ValueError(f"{name} must have length {size}")
    return tuple(map(_rat, x))


def _state_errors(x, name):
    out = _vec(x, 4, name)
    if any(v < 0 for v in out):
        raise ValueError(f"{name} must be nonnegative")
    return out


def _source_chain(source_records, own_chain, check=lambda: None):
    check()
    if not isinstance(source_records, (list, tuple)) or not source_records:
        raise ValueError("Complete nonempty source partition required")
    if isinstance(own_chain, dict):
        own_chain = own_chain.get("steps")
    if not isinstance(own_chain, (list, tuple)) or len(own_chain) != len(source_records):
        raise ValueError("Own chain must cover every original source step")
    out = []
    clock = None
    for i, (src, own) in enumerate(zip(source_records, own_chain)):
        check()
        if not isinstance(src, dict) or not isinstance(own, dict):
            raise TypeError("Source and own-chain records must be mappings")
        start, end = _rat(src["start"]), _rat(src["end"])
        if i == 0 and start != 0:
            raise ValueError("Complete source horizon must begin at t=0")
        if end <= start or (clock is not None and start != clock):
            raise ValueError("Source intervals must be positive and contiguous")
        if _rat(own["start"]) != start or _rat(own["end"]) != end:
            raise ValueError("Own-chain step identity differs from source interval")
        center = _vec(src["center"], 4, "source center")
        n = src["n"]
        if isinstance(n, bool) or type(n) is not int or n < 4:
            raise ValueError("Source polynomial degree must be exact integer >= 4")
        rows = src["P"]
        if not isinstance(rows, (list, tuple)) or len(rows) != 4:
            raise ValueError("Four full source-state polynomials required")
        rows = tuple(tuple(map(_rat, row)) for row in rows)
        if any(len(row) != n+1 or row[0] != 0 for row in rows):
            raise ValueError("Every source polynomial must be full degree and zero-origin")
        h = end-start
        initial = _state_errors(own["initial_errors"], "own initial errors")
        errors = _state_errors(own["end_errors"], "own end errors")
        if i == 0 and any(initial):
            raise ValueError("First source step must retain the exact audited initial anchor")
        if i:
            prev = out[-1]
            nominal_end = tuple(c+_STEP.at(_GEOM._poly(p), prev["h"]) for c, p in zip(prev["center"], prev["P"]))
            required = tuple(e+abs(v-c) for e, v, c in zip(prev["end_errors"], nominal_end, center))
            if any(got < need for got, need in zip(initial, required)):
                raise ValueError("Own chain drops inherited endpoint/recenter error")
        out.append(dict(index=i, start=start, end=end, h=h, center=center,
                        P=rows, n=n, initial_errors=initial, end_errors=errors))
        clock = end
    return out


def _decision(bounds, tolerance):
    lo, hi = _pair(bounds)
    if lo < 0:
        raise ValueError("Squared-distance lower bound must be nonnegative")
    t2 = tolerance*tolerance
    if lo > t2:
        return "excluded"
    if hi <= t2:
        return "contact"
    return "unknown"


def _validate_interval_claim(value, name):
    lo, hi = _pair(value)
    if lo < 0:
        raise ValueError(f"{name} squared distance must be nonnegative")
    return lo, hi


def _check_point_identity(expected_point, worker_point):
    if not isinstance(expected_point, dict) or not isinstance(worker_point, dict):
        raise TypeError("Expected and worker point identities must be mappings")
    for key in ("original_index", "union_index"):
        if (type(expected_point.get(key)) is not int or
                type(worker_point.get(key)) is not int or
                worker_point.get(key) != expected_point[key]):
            raise ValueError("Worker point identity mismatch")
    xy = _vec(expected_point["xy"], 2, "expected point")
    if _vec(worker_point["xy"], 2, "worker point") != xy:
        raise ValueError("Worker point coordinates mismatch")
    return xy


def check_point(source_records, own_chain, expected_point, worker_cover,
                *, hitch_offset, trailer_length, width, tolerance, check=lambda: None):
    """Recompute every evaluated trace cell and reconcile a full worker frontier.

    Worker per-point schema:
      {point:{original_index,union_index,xy}, steps:[
        {step_index,start,end,evaluated_trace:[{local_time,depth,
          distance_squared,finite_edge_distance_squared,call_index}],
         frontier:[{local_time,depth,trace_index,distance_squared,evaluations}]}],
       geometry_evaluations,summary}

    Frontier leaves must partition each original step. Their intervals define a
    canonical binary midpoint tree. Every split parent and every evaluated leaf
    must occur in evaluated_trace in preorder; all tree branches are represented,
    including explicit uncomputed unknown leaves. Trace bounds are checked for
    shape but never trusted for the independent result.
    """
    check()
    chain = _source_chain(source_records, own_chain, check)
    xy = _check_point_identity(expected_point, worker_cover["point"])
    tol = _rat(tolerance)
    lh, length, body_width = map(_rat, (hitch_offset, trailer_length, width))
    if tol < 0 or lh < 0 or length <= 0 or body_width <= 0:
        raise ValueError("Invalid tolerance or finite-body dimensions")
    steps = worker_cover["steps"]
    if not isinstance(steps, (list, tuple)) or len(steps) != len(chain):
        raise ValueError("Worker cover must retain every original source step")
    if type(worker_cover["geometry_evaluations"]) is not int:
        raise ValueError("Exact worker geometry evaluation count required")
    # Preflight the complete worker trace budget before any expensive geometry.
    trace_total = 0
    for step in steps:
        check()
        trace = step.get("evaluated_trace") if isinstance(step, dict) else None
        if not isinstance(trace, (list, tuple)):
            raise ValueError("Every source step needs an evaluated trace list")
        trace_total += len(trace)
        if trace_total > MAX_OWN_CALLS_PER_POINT:
            raise ValueError("Worker trace exceeds fixed 4096 calls before geometry")
    if worker_cover["geometry_evaluations"] != trace_total:
        raise ValueError("Worker global count disagrees with trace count before geometry")
    if trace_total > MAX_OWN_CALLS_PER_POINT:
        raise ValueError("Independent checker fixed per-point budget exceeded before geometry")

    own_calls = 0
    global_call = 0
    all_joint_leaves = []
    all_worker_states = []
    all_own_states = []
    step_reports = []

    for si, (src, wstep) in enumerate(zip(chain, steps)):
        check()
        if not isinstance(wstep, dict) or type(wstep.get("step_index")) is not int or wstep["step_index"] != si:
            raise ValueError("Worker original-step indices must be complete and ordered")
        if _rat(wstep["start"]) != src["start"] or _rat(wstep["end"]) != src["end"]:
            raise ValueError("Worker step identity differs from source record")
        trace, frontier = wstep["evaluated_trace"], wstep["frontier"]
        if not isinstance(trace, (list, tuple)) or not isinstance(frontier, (list, tuple)) or not frontier:
            raise ValueError("Each original step needs trace and a complete frontier")

        leaves = []
        clock = F(0)
        for fi, leaf in enumerate(frontier):
            check()
            if not isinstance(leaf, dict):
                raise TypeError("Frontier leaf must be a mapping")
            a, b = _pair(leaf["local_time"])
            if a != clock or not (0 <= a < b <= src["h"]):
                raise ValueError("Frontier leaves must form a chronological full-step partition")
            depth = leaf["depth"]
            if type(depth) is not int or not 0 <= depth <= MAX_DEPTH:
                raise ValueError("Frontier depth exceeds fixed contract")
            evaluations = leaf["evaluations"]
            if type(evaluations) is not int or evaluations not in (0, 1):
                raise ValueError("Frontier evaluation marker must be 0 or 1")
            ref = leaf["trace_index"]
            if ref is None:
                if evaluations != 0 or leaf["distance_squared"] is not None:
                    raise ValueError("Uncomputed leaf must be explicitly unknown with no bounds")
            elif type(ref) is not int or evaluations != 1:
                raise ValueError("Evaluated frontier leaf must reference one trace record")
            if leaf["distance_squared"] is not None:
                _validate_interval_claim(leaf["distance_squared"], "worker frontier")
            leaves.append(dict(index=fi, a=a, b=b, depth=depth,
                               trace_index=ref, evaluations=evaluations,
                               worker_bounds=leaf["distance_squared"]))
            clock = b
        if clock != src["h"]:
            raise ValueError("Frontier omits the original step suffix")

        # Parse leaves as a complete midpoint tree and produce canonical preorder
        # trace references. A split without both represented children is rejected.
        expected_trace_intervals = []
        leaf_to_trace = {}

        def walk(a, b, depth, subset):
            check()
            if not subset or subset[0]["a"] != a or subset[-1]["b"] != b:
                raise ValueError("Frontier tree has an omitted or unvisited interval")
            if len(subset) == 1 and subset[0]["a"] == a and subset[0]["b"] == b:
                leaf = subset[0]
                if leaf["depth"] != depth:
                    raise ValueError("Leaf depth disagrees with reconstructed split tree")
                if leaf["trace_index"] is None:
                    return
                if leaf["trace_index"] != len(expected_trace_intervals):
                    raise ValueError("Leaf trace indices must match canonical preorder")
                expected_trace_intervals.append((a, b, depth, leaf["index"]))
                leaf_to_trace[leaf["index"]] = leaf["trace_index"]
                return
            if depth >= MAX_DEPTH:
                raise ValueError("Expanded node exceeds fixed maximum depth")
            mid = (a+b)/2
            left = [x for x in subset if x["b"] <= mid]
            right = [x for x in subset if x["a"] >= mid]
            if not left or not right or left[-1]["b"] != mid or right[0]["a"] != mid:
                raise ValueError("Expanded frontier node lacks exact midpoint children")
            expected_trace_intervals.append((a, b, depth, None))
            walk(a, mid, depth+1, left)
            walk(mid, b, depth+1, right)

        walk(F(0), src["h"], 0, leaves)
        if len(trace) != len(expected_trace_intervals):
            raise ValueError("Trace omitted an expanded parent or contains an unvisited node")

        own_trace = []
        for ti, (record, expected) in enumerate(zip(trace, expected_trace_intervals)):
            check()
            if not isinstance(record, dict):
                raise TypeError("Evaluated trace record must be a mapping")
            a, b, depth, leaf_index = expected
            if _pair(record["local_time"]) != (a, b) or record["depth"] != depth:
                raise ValueError("Trace ordering, interval, or depth disagrees with frontier tree")
            if type(record["depth"]) is not int or record["depth"] > MAX_DEPTH:
                raise ValueError("Trace depth exceeds fixed contract")
            if type(record["call_index"]) is not int or record["call_index"] != global_call:
                raise ValueError("Trace call indices must be contiguous globally and ordered")
            worker_d2 = _validate_interval_claim(record["distance_squared"], "worker trace")
            edge_claims = record["finite_edge_distance_squared"]
            if not isinstance(edge_claims, (tuple, list)) or len(edge_claims) != 4:
                raise ValueError("All four finite edge distance claims must be retained")
            for edge in edge_claims:
                _validate_interval_claim(edge, "worker edge trace")
            if own_calls >= MAX_OWN_CALLS_PER_POINT:
                raise ValueError("Independent checker fixed per-point budget reached before geometry")
            check()
            result = _GEOM.project(
                xy, src["center"], src["P"], (a, b), src["h"], src["n"],
                src["end_errors"], lh, length, body_width)
            check()
            own_d2 = result["distance_squared"]
            own_state = _decision(own_d2, tol)
            worker_state = _decision(worker_d2, tol)
            own_calls += 1
            global_call += 1
            own_trace.append(dict(local_time=(a,b),depth=depth,
                worker_state=worker_state,own_state=own_state,
                own_distance_squared=own_d2,
                own_finite_edge_distance_squared=result["finite_edge_distance_squared"],
                inherited_end_errors=src["end_errors"],tube_reset=False))
            if leaf_index is not None:
                leaf = leaves[leaf_index]
                if leaf["trace_index"] != ti:
                    raise ValueError("Frontier leaf references the wrong trace index")
                if leaf["worker_bounds"] != worker_d2:
                    raise ValueError("Frontier leaf bounds disagree with its trace reference")
                leaf["worker_state"] = worker_state
                leaf["own_state"] = own_state
                leaf["own_bounds"] = own_d2
                leaf["joint_state"] = worker_state if worker_state == own_state else "unknown"
                if worker_state == "excluded" and own_state != "excluded":
                    leaf["conflict"] = "worker_exclusion_not_reproduced_by_own_tube"
                else:
                    leaf["conflict"] = None

        # Every frontier leaf must become an independent state. An uncomputed
        # budget leaf stays unknown; a linked leaf gets recomputed own geometry.
        step_leaves = []
        for leaf in leaves:
            if leaf["trace_index"] is None:
                leaf.update(worker_state="unknown", own_state="unknown",
                            own_bounds=None, joint_state="unknown", conflict=None)
            step_leaves.append(leaf)
            all_joint_leaves.append((src["start"]+leaf["a"], src["start"]+leaf["b"], leaf["joint_state"]))
            all_worker_states.append(leaf["worker_state"])
            all_own_states.append(leaf["own_state"])
        step_reports.append(dict(step_index=si,own_trace=own_trace,
            frontier=[dict(start=src["start"]+x["a"],end=src["start"]+x["b"],
                worker_state=x["worker_state"],own_state=x["own_state"],
                joint_state=x["joint_state"],conflict=x["conflict"],
                own_distance_squared=x["own_bounds"],depth=x["depth"]) for x in step_leaves],
            full_step_frontier_covered=True))

    if own_calls != worker_cover["geometry_evaluations"]:
        raise ValueError("Worker global evaluation count disagrees with complete evaluated trace")
    if own_calls > MAX_OWN_CALLS_PER_POINT:
        raise ValueError("Fixed 4096 per-point geometry budget exceeded")

    possible = [a for a,b,state in all_joint_leaves if state != "excluded"]
    certain = [a for a,b,state in all_joint_leaves if state == "contact"]
    first_possible = min(possible) if possible else None
    first_certain = min(certain) if certain else None
    if first_certain is not None:
        status = "candidate_contact_exists_mutual"
        first_interval = (first_possible, first_certain)
    elif first_possible is None:
        status = "candidate_noncontact_mutual"
        first_interval = None
    else:
        status = "unknown_or_conflict"
        first_interval = None
    return dict(point=dict(expected_point),candidate_status=status,
        first_contact_interval=first_interval,
        earliest_unexcluded_s=first_possible,
        candidate_contact_upper_s=first_certain,
        source_steps=len(chain),own_geometry_evaluations=own_calls,
        within_fixed_call_budget=True,entire_original_horizon_covered=True,
        all_four_finite_faces_retained=True,face_candidate_mask=255,
        face_certification_complete=False,corrected_truth_certificates=0,
        scientific_admission_allowed=False,step_reports=step_reports)
