"""Additional exact schema/control replay over the preserved v1 scalar independent checker."""
import math
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src_s4_suffix_witness_search_20261022_v1'))
import suffix_search_core as prior
TOL,GUARD,RESOLUTION,MAX_QUERIES=prior.TOL,prior.GUARD,prior.RESOLUTION,prior.MAX_QUERIES
OPEN,WITNESS,PRUNED,RESOLUTION_STOP,EXPANDED=prior.OPEN,prior.WITNESS,prior.PRUNED,prior.RESOLUTION_STOP,prior.EXPANDED
motion=prior.motion
FLOAT_FIELDS=('start_s','end_s','query_s','body_distance_m','left_motion_m','right_motion_m','lower_body_bound_m')
INT_FIELDS=('parent_index','node_kind','node_status')
BOOL_FIELDS=('independent_budget_exhausted','resolution_unresolved','strict_predicate_suffix_pruned','not_a_noncontact_or_global_earliest_proof')


def search(*args,**kwargs):
    out=prior.search(*args,**kwargs)
    out['query_budget']=np.asarray([kwargs.get('budget',MAX_QUERIES)],np.int32)
    return out


def independently_check(point,time,states,lower,error,vehicle,saved,geos,*,variation=None):
    expected=set(FLOAT_FIELDS+INT_FIELDS+BOOL_FIELDS+('candidate_upper_s','scientific_lower_s','query_budget'))
    if set(saved)!=expected: raise ValueError('Complete independent search schema required')
    n=len(saved['query_s'])
    for key in FLOAT_FIELDS+INT_FIELDS:
        dtype=np.float64 if key in FLOAT_FIELDS else np.int32
        if saved[key].shape!=(n,) or saved[key].dtype!=dtype: raise ValueError('Exact vector shape/dtype required: '+key)
    for key in ('candidate_upper_s','scientific_lower_s')+BOOL_FIELDS+('query_budget',):
        dtype=np.bool_ if key in BOOL_FIELDS else np.int32 if key=='query_budget' else np.float64
        if saved[key].shape!=(1,) or saved[key].dtype!=dtype: raise ValueError('Exact scalar shape/dtype required: '+key)
    if any(not np.isfinite(saved[key]).all() for key in FLOAT_FIELDS): raise ValueError('Every actual search query field must be finite')
    budget=int(saved['query_budget'][0])
    if not 2<=budget<=MAX_QUERIES or n>budget: raise ValueError('Independent search budget differs')
    base={k:v for k,v in saved.items() if k!='query_budget'}
    checked=prior.independently_check(point,time,states,lower,error,vehicle,base,geos,variation=variation)
    cursor=0
    def recorded_geometry(p,pose,v):
        nonlocal cursor
        if cursor>=n: raise ValueError('Saved control flow truncated a required geometry query')
        q=float(saved['query_s'][cursor])
        expected_pose=np.asarray([np.interp(q,time,states[:,k]) for k in range(4)])
        if not np.array_equal(np.asarray(p),np.asarray(point)) or pose.tobytes()!=expected_pose.tobytes():
            raise ValueError('Saved priority/split/control query differs')
        distance=float(saved['body_distance_m'][cursor]); cursor+=1
        return distance,np.zeros(4)
    rebuilt=search(point,time,states,lower,error,vehicle,recorded_geometry,variation=variation,budget=budget)
    if cursor!=n or set(rebuilt)!=set(saved): raise ValueError('Complete deterministic search trace required')
    for name in rebuilt:
        if rebuilt[name].dtype!=saved[name].dtype or rebuilt[name].shape!=saved[name].shape or rebuilt[name].tobytes()!=saved[name].tobytes():
            raise ValueError('Exact control replay/budget/frontier/padding differs: '+name)
    checked.update(exact_priority_split_control_and_frontier_replay=True,query_budget=budget)
    return checked
