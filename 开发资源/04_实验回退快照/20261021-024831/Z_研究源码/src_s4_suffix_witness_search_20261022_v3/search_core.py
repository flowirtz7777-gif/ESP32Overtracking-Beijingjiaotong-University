"""Supplemental strict witnesses for every unwitnessed row; no exclusion proof."""
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src_s4_local_motion_20261022_v2"))
import local_motion_core as motion
import search_control as suffix

TOL = .050000001
GUARD = 1e-12
RESOLUTION = 1e-7
FORWARD_STEPS = 256
REFINE_STEPS = 64
MUTABLE = {"contact_status", "contact_upper_s", "nominal_instantaneous_edge",
           "edge_certain", "possible_edge_codes"}


def same(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def selection(labels):
    lower, upper = labels["contact_lower_s"], labels["contact_upper_s"]
    n = len(lower)
    if (any(v.shape != (n,) for v in labels.values()) or np.any(np.isinf(lower))
            or np.any(np.isinf(upper)) or labels["budget_exhausted"].any()
            or np.any(np.isfinite(upper) != (labels["contact_status"] == 1))
            or np.any(np.isfinite(upper) & (~np.isfinite(lower) | (lower > upper)))
            or np.any(~np.isfinite(upper) & labels["edge_certain"])):
        raise ValueError("All current nonbudget fields, endpoints and contact states required")
    chosen = np.isfinite(lower) & ~np.isfinite(upper)
    if np.any(chosen & (labels["contact_status"] != 2)):
        raise ValueError("All and only unresolved unwitnessed rows may be probed")
    return chosen


def validate(xy, time, states, labels, error, vehicle):
    chosen = selection(labels)
    motion.validate_path(time, states, vehicle)
    if (xy.shape != (len(chosen), 2) or not np.isfinite(xy).all()
            or not math.isfinite(error) or error < 0
            or np.any(labels["contact_lower_s"][chosen] < time[0])
            or np.any(labels["contact_lower_s"][chosen] > time[-1])):
        raise ValueError("Complete finite coordinates, original path and error required")
    return chosen


def poses(time, states, queries):
    return np.column_stack([np.interp(queries, time, states[:, k]) for k in range(4)])


def forward_time(lower, horizon, step):
    return float(lower) if step == 0 else min(float(horizon), float(lower) + math.ldexp(RESOLUTION, step - 1))


def legacy_empty_trace(n, chosen):
    trace = {"selected_unwitnessed": chosen.copy(), "found_strict_witness": np.zeros(n, bool),
             "forward_evaluations": np.zeros(n, np.int16), "refine_evaluations": np.zeros(n, np.int16),
             "forward_budget_exhausted": np.zeros(n, bool), "refine_budget_exhausted": np.zeros(n, bool),
             "search_reached_horizon_without_witness": np.zeros(n, bool)}
    for prefix, count in (("forward", FORWARD_STEPS), ("refine", REFINE_STEPS)):
        trace[prefix + "_time_s"] = np.full((n, count), np.nan)
        trace[prefix + "_body_distance_m"] = np.full((n, count), np.nan)
        trace[prefix + "_witness"] = np.zeros((n, count), bool)
    for name in ("last_forward_probe_s", "refine_internal_remaining_width_s", "candidate_midpoint_s",
                 "left_motion_m", "right_motion_m", "motion_radius_m", "total_envelope_m"):
        trace[name] = np.full(n, np.nan)
    trace["candidate_midpoint_faces_m"] = np.full((n, 4), np.nan)
    trace["confidence_margins_m"] = np.full((n, 3), np.nan)
    return trace



def empty_trace(n,chosen):
    trace=legacy_empty_trace(n,chosen)
    del trace['search_reached_horizon_without_witness']
    for key in suffix.FLOAT_FIELDS:
        trace['search__'+key]=np.full((n,FORWARD_STEPS),np.nan)
    for key in suffix.INT_FIELDS:
        trace['search__'+key]=np.zeros((n,FORWARD_STEPS),np.int32)
    trace['suffix_initial_witness_upper_s']=np.full(n,np.nan)
    trace['suffix_query_budget']=np.zeros(n,np.int32)
    for key in ('suffix_resolution_unresolved','suffix_strict_predicate_pruned','suffix_not_noncontact_or_earliest'):
        trace[key]=np.zeros(n,bool)
    return trace


def distances(xy, time, states, ids, q, geometry):
    body, _ = geometry(xy[ids], poses(time, states, q))
    if body.shape != (len(ids),) or not np.isfinite(body).all() or np.any(body < 0):
        raise ValueError("Every probe must have a finite nonnegative body distance")
    return body


def candidate(xy,time,states,original,error,vehicle,geometry):
    chosen=validate(xy,time,states,original,error,vehicle)
    n=len(chosen)
    out={k:v.copy() for k,v in original.items()}
    trace=empty_trace(n,chosen)
    variation=motion.segment_variation(time,states,vehicle)
    low=original['contact_lower_s'].copy()
    high=np.full(n,np.nan)
    def one(point,pose,v):
        body,faces=geometry(point.reshape(1,2),pose.reshape(1,4))
        return float(body[0]),faces[0]
    for i in np.flatnonzero(chosen):
        result=suffix.search(xy[i],time,states,float(low[i]),error,vehicle,one,
            variation=variation,budget=FORWARD_STEPS)
        count=len(result['query_s'])
        trace['forward_evaluations'][i]=count
        trace['forward_time_s'][i,:count]=result['query_s']
        trace['forward_body_distance_m'][i,:count]=result['body_distance_m']
        trace['forward_witness'][i,:count]=result['node_status']==suffix.WITNESS
        trace['last_forward_probe_s'][i]=result['query_s'][-1]
        trace['forward_budget_exhausted'][i]=result['independent_budget_exhausted'][0]
        trace['suffix_resolution_unresolved'][i]=result['resolution_unresolved'][0]
        trace['suffix_strict_predicate_pruned'][i]=result['strict_predicate_suffix_pruned'][0]
        trace['suffix_not_noncontact_or_earliest'][i]=result['not_a_noncontact_or_global_earliest_proof'][0]
        trace['suffix_query_budget'][i]=result['query_budget'][0]
        high[i]=result['candidate_upper_s'][0]
        trace['suffix_initial_witness_upper_s'][i]=high[i]
        for key in suffix.FLOAT_FIELDS+suffix.INT_FIELDS:
            trace['search__'+key][i,:count]=result[key]
    found=np.isfinite(high)
    trace['found_strict_witness']=found.copy()
    internal_low=low.copy()
    for j in range(REFINE_STEPS):
        ids = np.flatnonzero(found & (high - internal_low > RESOLUTION))
        if not len(ids):
            break
        q = (internal_low[ids] + high[ids]) / 2
        if np.any((q <= internal_low[ids]) | (q >= high[ids])):
            raise ValueError("Refinement probe stagnation")
        body = distances(xy, time, states, ids, q, geometry)
        hit = body + error + GUARD <= TOL
        trace["refine_time_s"][ids, j] = q
        trace["refine_body_distance_m"][ids, j] = body
        trace["refine_witness"][ids, j] = hit
        trace["refine_evaluations"][ids] += 1
        high[ids[hit]] = q[hit]
        # This search cursor is never an exclusion or scientific lower bound.
        internal_low[ids[~hit]] = q[~hit]
    trace["refine_internal_remaining_width_s"][found] = high[found] - internal_low[found]
    trace["refine_budget_exhausted"][found] = high[found] - internal_low[found] > RESOLUTION
    ids = np.flatnonzero(found)
    if len(ids):
        out["contact_status"][ids] = 1
        out["contact_upper_s"][ids] = high[ids]
        queries = []
        for i in ids:
            mid, left, right, radius = motion.bracket_bound(time, variation, low[i], high[i])
            queries.append(mid)
            trace["candidate_midpoint_s"][i] = mid
            trace["left_motion_m"][i], trace["right_motion_m"][i] = left, right
            trace["motion_radius_m"][i] = radius
        _, faces = geometry(xy[ids], poses(time, states, np.asarray(queries)))
        for j, i in enumerate(ids):
            envelope = motion.up(math.fsum((error, float(trace["motion_radius_m"][i]), GUARD)))
            code, certain, margins = motion.face_rule(faces[j], envelope)
            trace["candidate_midpoint_faces_m"][i] = faces[j]
            trace["confidence_margins_m"][i] = margins
            trace["total_envelope_m"][i] = envelope
            out["nominal_instantaneous_edge"][i] = code
            out["edge_certain"][i] = certain
            out["possible_edge_codes"][i] = 1 << (code - 1) if certain else 255
    return out, trace, variation



def independent_check(xy, time, states, original, proposed, error, vehicle, trace, variation, geos):
    chosen = validate(xy, time, states, original, error, vehicle)
    n = len(chosen)
    schema = empty_trace(n, chosen)
    if set(trace) != set(schema) or any(trace[k].shape != schema[k].shape or trace[k].dtype != schema[k].dtype for k in schema):
        raise ValueError("Complete trace schema, shape and dtype required")
    if (set(original) != set(proposed) or any(not same(original[k], proposed[k])
            for k in original.keys() - MUTABLE)
            or any(original[k].dtype != proposed[k].dtype or original[k].shape != proposed[k].shape for k in original)):
        raise ValueError("Original scientific lower, label schema or construction provenance changed")
    if variation.shape != (len(time) - 1,) or variation.dtype != np.float64:
        raise ValueError("Every original segment variation required")
    exact_travel = [motion.decimal_segment_variation(a, b, vehicle) for a, b in zip(states[:-1], states[1:])]
    from decimal import Decimal
    for saved, exact in zip(variation, exact_travel):
        if not math.isfinite(float(saved)) or Decimal.from_float(float(saved)) < exact:
            raise ValueError("Original interval motion bound is not conservative")
    queries, witnesses = 0, 0
    for i in range(n):
        if not chosen[i]:
            if any(not same(proposed[k][i:i+1], original[k][i:i+1]) for k in original):
                raise ValueError("Every unselected field must remain byte-exact")
            for k, empty in schema.items():
                if not same(trace[k][i:i+1], empty[i:i+1]):
                    raise ValueError("Unqueried trace must have exact empty padding")
            continue
        lower = float(original["contact_lower_s"][i])

        count=int(trace['forward_evaluations'][i])
        if not 1<=count<=FORWARD_STEPS or not trace['selected_unwitnessed'][i]:
            raise ValueError('Every still-unwitnessed row requires its full bounded suffix search')
        saved={key:trace['search__'+key][i,:count].copy() for key in suffix.FLOAT_FIELDS+suffix.INT_FIELDS}
        saved.update(candidate_upper_s=trace['suffix_initial_witness_upper_s'][i:i+1].copy(),
            scientific_lower_s=np.asarray([lower],np.float64),query_budget=trace['suffix_query_budget'][i:i+1].copy(),
            independent_budget_exhausted=trace['forward_budget_exhausted'][i:i+1].copy(),
            resolution_unresolved=trace['suffix_resolution_unresolved'][i:i+1].copy(),
            strict_predicate_suffix_pruned=trace['suffix_strict_predicate_pruned'][i:i+1].copy(),
            not_a_noncontact_or_global_earliest_proof=trace['suffix_not_noncontact_or_earliest'][i:i+1].copy())
        if saved['query_budget'][0]!=FORWARD_STEPS:
            raise ValueError('The frozen independent query budget must remain exact')
        suffix.independently_check(xy[i],time,states,lower,error,vehicle,saved,geos,variation=variation)
        for key in suffix.FLOAT_FIELDS+suffix.INT_FIELDS:
            if not same(trace['search__'+key][i,count:],schema['search__'+key][i,count:]):
                raise ValueError('Every unused two-dimensional suffix slot must keep exact padding')
        if (not same(trace['forward_time_s'][i,:count],saved['query_s'])
            or not same(trace['forward_body_distance_m'][i,:count],saved['body_distance_m'])
            or not np.array_equal(trace['forward_witness'][i,:count],saved['node_status']==suffix.WITNESS)
            or trace['last_forward_probe_s'][i]!=saved['query_s'][-1]):
            raise ValueError('Every query and exact alias trace must bind')
        high=float(saved['candidate_upper_s'][0])
        found=math.isfinite(high)
        if bool(trace['found_strict_witness'][i])!=found:
            raise ValueError('Only an actual accepted strict suffix witness may set found')
        queries+=count
        for prefix, total, used in (("forward", FORWARD_STEPS, count),
                                   ("refine", REFINE_STEPS, int(trace["refine_evaluations"][i]))):
            if not 0 <= used <= total:
                raise ValueError("Invalid probe count")
            if (not np.isnan(trace[prefix + "_time_s"][i, used:]).all()
                    or not np.isnan(trace[prefix + "_body_distance_m"][i, used:]).all()
                    or trace[prefix + "_witness"][i, used:].any()):
                raise ValueError("Every unused probe slot must retain exact padding")
        refinements = int(trace["refine_evaluations"][i])
        if not found:
            if refinements or any(not same(proposed[k][i:i+1], original[k][i:i+1]) for k in original):
                raise ValueError("No new witness requires exact original labels, not a negative")
            for name in ("refine_internal_remaining_width_s", "candidate_midpoint_s", "left_motion_m",
                         "right_motion_m", "motion_radius_m", "total_envelope_m",
                         "candidate_midpoint_faces_m", "confidence_margins_m"):
                if not np.isnan(trace[name][i]).all():
                    raise ValueError("No-witness bracket diagnostics must remain NaN")
            if trace["refine_budget_exhausted"][i]:
                raise ValueError("Unattempted refinement cannot exhaust")
            continue
        cursor = lower
        for j in range(refinements):
            q = (cursor + high) / 2
            if (high - cursor <= RESOLUTION or not cursor < q < high or trace["refine_time_s"][i, j] != q):
                raise ValueError("Refinement recurrence differs")
            body, _ = geos(xy[i], poses(time, states, np.array([q]))[0], vehicle)
            saved = float(trace["refine_body_distance_m"][i, j])
            hit = saved + error + GUARD <= TOL
            if (not math.isfinite(saved) or saved < 0 or abs(float(body) - saved) > 1e-10
                    or bool(trace["refine_witness"][i, j]) != hit
                    or (hit and float(body) + error + GUARD > TOL)):
                raise ValueError("Independent refinement geometry or strict witness differs")
            if hit:
                high = q
            else:
                cursor = q
            queries += 1
        width = high - cursor
        if (refinements < REFINE_STEPS and width > RESOLUTION
                or trace["refine_internal_remaining_width_s"][i] != width
                or bool(trace["refine_budget_exhausted"][i]) != (width > RESOLUTION)
                or proposed["contact_upper_s"][i] != high or proposed["contact_status"][i] != 1):
            raise ValueError("Candidate upper or internal cursor incorrectly promoted")
        body, _ = geos(xy[i], poses(time, states, np.array([high]))[0], vehicle)
        if float(body) + error + GUARD > TOL:
            raise ValueError("Final finite upper is not a strict independent contact witness")
        queries += 1
        mid = (lower + high) / 2
        _, face = geos(xy[i], poses(time, states, np.array([mid]))[0], vehicle)
        saved_face = trace["candidate_midpoint_faces_m"][i]
        if not np.allclose(face, saved_face, rtol=0, atol=1e-10) or trace["candidate_midpoint_s"][i] != mid:
            raise ValueError("Every full-bracket midpoint finite face must reproduce")
        left, right, radius = motion.decimal_radius(time, states, vehicle, lower, high, exact_travel)
        for name, exact in (("left_motion_m", left), ("right_motion_m", right), ("motion_radius_m", radius)):
            if Decimal.from_float(float(trace[name][i])) < exact:
                raise ValueError("Full-bracket motion envelope underbounds")
        sl = motion.independent_sum(time, variation, lower, mid)
        sr = motion.independent_sum(time, variation, mid, high)
        if trace["left_motion_m"][i] != sl or trace["right_motion_m"][i] != sr or trace["motion_radius_m"][i] != max(sl, sr):
            raise ValueError("Every original interval and bracket endpoint must reproduce")
        env = motion.up(math.fsum((error, max(sl, sr), GUARD)))
        code, stable, margins = motion.face_rule(saved_face, env)
        independent_code, independent_stable, _ = motion.face_rule(face, env)
        bits = 1 << (code - 1) if stable else 255
        if (trace["total_envelope_m"][i] != env or not np.array_equal(trace["confidence_margins_m"][i], np.asarray(margins))
                or proposed["nominal_instantaneous_edge"][i] != code or bool(proposed["edge_certain"][i]) != stable
                or proposed["possible_edge_codes"][i] != bits
                or (stable and (not independent_stable or independent_code != code))):
            raise ValueError("Original finite-face/corner sufficient rule differs")
        queries += 1
        witnesses += 1
    return {"scope_records": n, "selected_unwitnessed_records": int(chosen.sum()),
            "new_strict_contact_witnesses": witnesses, "independent_GE0S_queries": queries,
            "all_original_scientific_lower_bytes_unchanged": True,
            "failed_probes_never_noncontact_or_scientific_lower_proofs": True,
            "no_global_earliest_or_exhaustive_search_claim": True, "complete_suffix_control_budget_and_frontier_checked": True}

