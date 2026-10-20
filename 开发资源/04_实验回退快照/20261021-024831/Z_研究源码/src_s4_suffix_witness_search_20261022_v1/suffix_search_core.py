"""Bounded deterministic strict-witness search; no noncontact or scientific-lower promotion."""
import heapq
import math
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src_s4_local_motion_20261022_v2'))
import local_motion_core as motion

TOL=.050000001
GUARD=1e-12
RESOLUTION=1e-7
MAX_QUERIES=256
OPEN,WITNESS,PRUNED,RESOLUTION_STOP,EXPANDED=range(5)


def lower_bound(distance,radius):
    # This lower bound only prunes searches for the strict sufficient predicate.
    # It never proves physical noncontact or raises a scientific lower endpoint.
    value=math.fsum((float(distance),-float(radius),-2*GUARD))
    return max(0.,math.nextafter(value,-math.inf))


def strict_possible(bound,error):
    optimistic=math.nextafter(math.fsum((float(bound),float(error),GUARD)),-math.inf)
    return optimistic<=TOL


def search(point,time,states,lower,error,vehicle,geometry,*,variation=None,budget=MAX_QUERIES):
    motion.validate_path(time,states,vehicle)
    point=np.asarray(point,dtype=np.float64)
    if (point.shape!=(2,) or not np.isfinite(point).all() or not math.isfinite(lower)
            or not time[0]<=lower<=time[-1] or not math.isfinite(error) or error<0
            or not isinstance(budget,int) or budget<2 or budget>MAX_QUERIES):
        raise ValueError('Finite original lower/path/point/error and independent fixed budget required')
    if variation is None: variation=motion.segment_variation(time,states,vehicle)
    if variation.dtype!=np.float64 or variation.shape!=(len(time)-1,) or not np.isfinite(variation).all() or np.any(variation<0):
        raise ValueError('Every original path interval variation must bind')
    rows=[]
    heap=[]
    witness=math.nan

    def evaluate(a,b,parent,kind):
        nonlocal witness
        q=float(a) if kind==0 else float(a+(b-a)/2)
        pose=np.asarray([np.interp(q,time,states[:,k]) for k in range(4)])
        body,_=geometry(point,pose,vehicle)
        distance=float(body)
        if not math.isfinite(distance) or distance<0: raise ValueError('Finite nonnegative body distance required')
        left=motion.integrated_bound(time,variation,float(a),q)
        right=motion.integrated_bound(time,variation,q,float(b))
        radius=max(left,right)
        bound=lower_bound(distance,radius)
        hit=distance+error+GUARD<=TOL
        status=WITNESS if hit else PRUNED if not strict_possible(bound,error) or kind==0 else (
            RESOLUTION_STOP if b-a<=RESOLUTION or q in (a,b) else OPEN)
        index=len(rows)
        rows.append((float(a),float(b),q,distance,left,right,bound,int(parent),int(kind),int(status)))
        if hit: witness=q
        elif status==OPEN: heapq.heappush(heap,(bound,float(a),float(b),index))
        return index

    evaluate(lower,lower,-1,0)
    if not math.isfinite(witness) and lower<time[-1]:
        evaluate(lower,float(time[-1]),-1,1)
    while heap and not math.isfinite(witness):
        # A full split requires both children. Never silently drop an unsubmitted child.
        if len(rows)+2>budget: break
        _,a,b,parent=heapq.heappop(heap)
        midpoint=rows[parent][2]
        rows[parent]=(*rows[parent][:-1],EXPANDED)
        left=evaluate(a,midpoint,parent,1)
        if math.isfinite(witness):
            # Preserve the other half explicitly, even when witness search stops early.
            rows[parent]=(*rows[parent][:-1],OPEN)
            break
        evaluate(midpoint,b,parent,1)
    names=('start_s','end_s','query_s','body_distance_m','left_motion_m','right_motion_m',
           'lower_body_bound_m','parent_index','node_kind','node_status')
    out={name:np.asarray([row[k] for row in rows],dtype=np.int32 if k>=7 else np.float64)
         for k,name in enumerate(names)}
    # open parent on an early one-child witness is explicitly not a completed partition proof.
    out['candidate_upper_s']=np.asarray([witness],np.float64)
    out['scientific_lower_s']=np.asarray([lower],np.float64)
    out['independent_budget_exhausted']=np.asarray([bool(heap and not math.isfinite(witness) and len(rows)+2>budget)],bool)
    out['resolution_unresolved']=np.asarray([any(row[-1]==RESOLUTION_STOP for row in rows)],bool)
    out['strict_predicate_suffix_pruned']=np.asarray([not math.isfinite(witness) and not heap
        and not any(row[-1]==RESOLUTION_STOP for row in rows)],bool)
    out['not_a_noncontact_or_global_earliest_proof']=np.asarray([True],bool)
    return out


def independently_check(point,time,states,lower,error,vehicle,saved,geos,*,variation=None):
    if variation is None: variation=motion.segment_variation(time,states,vehicle)
    required={'start_s','end_s','query_s','body_distance_m','left_motion_m','right_motion_m',
        'lower_body_bound_m','parent_index','node_kind','node_status','candidate_upper_s','scientific_lower_s',
        'independent_budget_exhausted','resolution_unresolved','strict_predicate_suffix_pruned',
        'not_a_noncontact_or_global_earliest_proof'}
    if set(saved)!=required: raise ValueError('Every search trace field required')
    n=len(saved['query_s'])
    vector_names=required-{'candidate_upper_s','scientific_lower_s','independent_budget_exhausted',
        'resolution_unresolved','strict_predicate_suffix_pruned','not_a_noncontact_or_global_earliest_proof'}
    if not 1<=n<=MAX_QUERIES or any(saved[k].shape!=(n,) for k in vector_names):
        raise ValueError('Complete query trace shape required')
    if saved['scientific_lower_s'].dtype!=np.float64 or saved['scientific_lower_s'].shape!=(1,) or saved['scientific_lower_s'].tobytes()!=np.asarray([lower],np.float64).tobytes():
        raise ValueError('Original scientific lower bytes changed')
    witnesses=[]
    for j in range(n):
        a,b,q=map(float,(saved['start_s'][j],saved['end_s'][j],saved['query_s'][j]))
        kind,parent,status=map(int,(saved['node_kind'][j],saved['parent_index'][j],saved['node_status'][j]))
        if not lower<=a<=q<=b<=time[-1] or kind not in (0,1) or status not in range(5):
            raise ValueError('No query before lower or beyond original suffix')
        if j==0 and (kind!=0 or parent!=-1 or a!=lower or b!=lower or q!=lower):
            raise ValueError('Original lower must be queried explicitly first')
        if kind==1 and q!=a+(b-a)/2: raise ValueError('Deterministic midpoint query differs')
        if kind==1 and parent<0 and (j!=1 or a!=lower or b!=time[-1]):
            raise ValueError('Full suffix root must bind')
        if parent>=0:
            if parent>=j: raise ValueError('Parent must precede child')
            pa,pb,pq=map(float,(saved['start_s'][parent],saved['end_s'][parent],saved['query_s'][parent]))
            if (a,b) not in ((pa,pq),(pq,pb)): raise ValueError('Child interval is not an exact half of parent')
        pose=np.asarray([np.interp(q,time,states[:,k]) for k in range(4)])
        distance,_=geos(np.asarray(point),pose,vehicle)
        distance=float(distance)
        if not math.isclose(distance,float(saved['body_distance_m'][j]),rel_tol=0,abs_tol=1e-10):
            raise ValueError('Every success and failed probe must reproduce with scalar GEOS')
        left=motion.independent_sum(time,variation,a,q)
        right=motion.independent_sum(time,variation,q,b)
        if saved['left_motion_m'][j]!=left or saved['right_motion_m'][j]!=right:
            raise ValueError('Every full original-interval motion integral must reproduce')
        bound=float(saved['lower_body_bound_m'][j])
        if bound<0 or bound>max(0.,distance-max(left,right)-GUARD):
            raise ValueError('Saved body-distance lower bound is not conservative in independent geometry')
        strict=distance+error+GUARD<=TOL
        if status==WITNESS:
            if not strict: raise ValueError('Saved upper is not a strict independent GEOS witness')
            witnesses.append(q)
        elif strict: raise ValueError('A strict successful probe was silently dropped')
        if status==PRUNED and kind==1 and strict_possible(bound,error):
            raise ValueError('Interval pruning cannot exclude the strict predicate')
        if status==RESOLUTION_STOP and b-a>RESOLUTION and q not in (a,b):
            raise ValueError('Resolution stop before fixed resolution')
        if status==EXPANDED:
            children=np.flatnonzero(saved['parent_index']==j)
            intervals=sorted((float(saved['start_s'][i]),float(saved['end_s'][i])) for i in children)
            if intervals!=[(a,q),(q,b)]: raise ValueError('Expanded parent must retain both children without gap')
    upper=float(saved['candidate_upper_s'][0])
    if math.isfinite(upper):
        if not witnesses or upper!=witnesses[-1]: raise ValueError('Candidate upper must be an actually checked strict witness')
    elif witnesses: raise ValueError('A saved witness cannot be omitted')
    if bool(saved['strict_predicate_suffix_pruned'][0]):
        if math.isfinite(upper) or np.any(np.isin(saved['node_status'],[OPEN,WITNESS,RESOLUTION_STOP])):
            raise ValueError('A partially searched suffix cannot be called predicate-pruned')
        if lower<time[-1] and (n<2 or saved['node_kind'][1]!=1):
            raise ValueError('Complete suffix root required even for strict-predicate-only pruning')
    if not bool(saved['not_a_noncontact_or_global_earliest_proof'][0]):
        raise ValueError('Do not promote finite/strict-sufficiency search to noncontact or earliest proof')
    return {'query_records':n,'all_scalar_geos_probes_checked':True,
        'strict_witness_found':math.isfinite(upper),'scientific_lower_unchanged':True,
        'no_noncontact_or_global_earliest_or_physical_identifiability_claim':True}
