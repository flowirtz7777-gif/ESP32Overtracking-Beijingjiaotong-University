"""Sufficient uniform edge code on a complete unchanged contact bracket.

Every accepted leaf uses the original spatial error, full local motion bound,
1 mm corner rule and numerical guard. Uncovered/budget/resolution cases stay
unknown. This is neither a contact search nor a physical identifiability claim.
"""
from decimal import Decimal
import math
import numpy as np
import local_motion_core as motion

BUDGET=64
RESOLUTION=1e-7
FLOATS=('a_s','b_s','mid_s','left_motion_m','right_motion_m','radius_m','envelope_m')
INTS=('parent','kind','code')
BOOLS=('selected_edge_uncertain','edge_newly_certified','cover_budget_exhausted',
       'cover_resolution_unresolved','cover_different_stable_code',
       'unwitnessed_contact_unknown_retained','known_noncontact_exact_reuse','already_certain_exact_reuse')


def same(a,b):
    return a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()


def selection(labels):
    return motion.selection(labels)


def empty(n,chosen,labels):
    t={k:np.full((n,BUDGET),np.nan) for k in FLOATS}
    t.update({k:np.zeros((n,BUDGET),np.int32) for k in INTS})
    t.update({k:np.zeros(n,bool) for k in BOOLS})
    t.update(query_count=np.zeros(n,np.int32),frontier_count=np.zeros(n,np.int32),
        faces_m=np.full((n,BUDGET,4),np.nan),margins_m=np.full((n,BUDGET,3),np.nan),
        frontier_a_s=np.full((n,BUDGET+1),np.nan),frontier_b_s=np.full((n,BUDGET+1),np.nan),
        frontier_parent=np.zeros((n,BUDGET+1),np.int32))
    t['selected_edge_uncertain']=chosen.copy()
    t['unwitnessed_contact_unknown_retained']=np.isfinite(labels['contact_lower_s'])&~np.isfinite(labels['contact_upper_s'])
    t['known_noncontact_exact_reuse']=labels['contact_status']==0
    t['already_certain_exact_reuse']=np.isfinite(labels['contact_upper_s'])&labels['edge_certain']
    return t


def pose(time,states,q):
    return np.array([np.interp(q,time,states[:,j]) for j in range(4)])


def scalar_rule(faces,envelope):
    order=sorted(range(4),key=lambda k:(float(faces[k]),k))
    near=float(faces[order[1]]-faces[order[0]])
    far=float(faces[order[2]]-faces[order[1]])
    pair=tuple(sorted(order[:2]))
    code=motion.ADJACENT[pair] if near<=.001 and pair in motion.ADJACENT else order[0]+1
    stable=near-2*envelope>.001 or (near+2*envelope<.001 and far>2*envelope and pair in motion.ADJACENT)
    return code,stable,(near-2*envelope-.001,.001-(near+2*envelope),far-2*envelope)


def candidate(xy,time,states,original,error,vehicle,geometry):
    chosen=selection(original)
    motion.validate_path(time,states,vehicle)
    if xy.shape!=(len(chosen),2) or not np.isfinite(xy).all() or not math.isfinite(error) or error<0:
        raise ValueError('Complete finite scope and original empirical error required')
    variation=motion.segment_variation(time,states,vehicle)
    out={k:v.copy() for k,v in original.items()}
    trace=empty(len(chosen),chosen,original)
    for i in np.flatnonzero(chosen):
        a,b=map(float,(original['contact_lower_s'][i],original['contact_upper_s'][i]))
        if not time[0]<=a<=b<=time[-1]:
            raise ValueError('Original complete contact bracket required')
        nominal=int(original['nominal_instantaneous_edge'][i])
        if not 1<=nominal<=8:
            raise ValueError('Original finite nominal edge code required')
        pending=[(a,b,-1)]
        count=0
        failed=False
        while pending and count<BUDGET:
            a,b,parent=pending.pop()
            mid,left,right,radius=motion.bracket_bound(time,variation,a,b)
            envelope=motion.up(math.fsum((float(error),radius,motion.GUARD)))
            _,faces=geometry(xy[i:i+1],pose(time,states,mid).reshape(1,4))
            faces=np.asarray(faces)[0]
            code,stable,margins=motion.face_rule(faces,envelope)
            for name,value in zip(FLOATS,(a,b,mid,left,right,radius,envelope)):
                trace[name][i,count]=value
            trace['parent'][i,count]=parent
            trace['code'][i,count]=code
            trace['faces_m'][i,count]=faces
            trace['margins_m'][i,count]=margins
            kind=1 if stable and code==nominal else 4 if stable else 3 if b-a<=RESOLUTION or not a<mid<b else 2
            trace['kind'][i,count]=kind
            node=count
            count+=1
            if kind==2:
                pending.extend(((mid,b,node),(a,mid,node)))
            elif kind in (3,4):
                trace['cover_resolution_unresolved' if kind==3 else 'cover_different_stable_code'][i]=True
                failed=True
                break
        trace['query_count'][i]=count
        trace['frontier_count'][i]=len(pending)
        for j,(a,b,parent) in enumerate(pending):
            trace['frontier_a_s'][i,j]=a
            trace['frontier_b_s'][i,j]=b
            trace['frontier_parent'][i,j]=parent
        trace['cover_budget_exhausted'][i]=bool(pending and count==BUDGET and not failed)
        certified=not pending and not failed
        trace['edge_newly_certified'][i]=certified
        if certified:
            out['edge_certain'][i]=True
            out['possible_edge_codes'][i]=1<<(nominal-1)
    return out,trace,variation


def independent_check(xy,time,states,original,proposed,error,vehicle,trace,variation,geos):
    chosen=selection(original)
    motion.validate_path(time,states,vehicle)
    n=len(chosen)
    expected=empty(n,chosen,original)
    if set(trace)!=set(expected) or set(proposed)!=set(original):
        raise ValueError('Complete fields and cover tree/frontier schema required')
    for key,value in expected.items():
        if trace[key].shape!=value.shape or trace[key].dtype!=value.dtype:
            raise ValueError('Exact cover trace shape and dtype required')
    for key,value in original.items():
        if proposed[key].shape!=value.shape or proposed[key].dtype!=value.dtype:
            raise ValueError('Exact candidate shape and dtype required')
        if key not in ('edge_certain','possible_edge_codes') and not same(proposed[key],value):
            raise ValueError('Scientific endpoints/contact evidence/provenance must be byte-exact')
    if variation.shape!=(len(time)-1,) or variation.dtype!=np.float64:
        raise ValueError('Every original segment variation required')
    travel=[motion.decimal_segment_variation(a,b,vehicle) for a,b in zip(states[:-1],states[1:])]
    for saved,exact in zip(variation,travel):
        if not math.isfinite(saved) or Decimal.from_float(float(saved))<exact or saved>float(exact)*(1+1e-13)+1e-12:
            raise ValueError('Full original interval variation not conservative/exact')
    queries=0
    certified_count=0
    for i in range(n):
        if not chosen[i]:
            if any(not same(proposed[k][i:i+1],v[i:i+1]) for k,v in original.items()):
                raise ValueError('Every unselected row must remain byte-exact')
            continue
        lower,upper=map(float,(original['contact_lower_s'][i],original['contact_upper_s'][i]))
        if not time[0]<=lower<=upper<=time[-1]:
            raise ValueError('Original full bracket required')
        nominal=int(original['nominal_instantaneous_edge'][i])
        pending=[(lower,upper,-1)]
        count=int(trace['query_count'][i])
        if not 1<=count<=BUDGET:
            raise ValueError('Exact positive bounded query count required')
        failed=False
        for j in range(count):
            if not pending or failed:
                raise ValueError('Cover query after termination or complete cover')
            a,b,parent=pending.pop()
            mid=(a+b)/2
            left=motion.independent_sum(time,variation,a,mid)
            right=motion.independent_sum(time,variation,mid,b)
            radius=max(left,right)
            envelope=motion.up(math.fsum((float(error),radius,motion.GUARD)))
            _,faces=geos(xy[i],pose(time,states,mid),vehicle)
            faces=np.asarray(faces)
            saved=trace['faces_m'][i,j]
            if faces.shape!=(4,) or not np.allclose(faces,saved,rtol=0,atol=1e-10):
                raise ValueError('Independent finite face geometry differs')
            for name,value in zip(FLOATS,(a,b,mid,left,right,radius,envelope)):
                if trace[name][i,j]!=value:
                    raise ValueError('Full node bracket, conservative envelope and branch order differ')
                expected[name][i,j]=value
            for actual,exact in zip((left,right,radius),motion.decimal_radius(time,states,vehicle,a,b,travel)):
                if Decimal.from_float(actual)<exact:
                    raise ValueError('Node motion underbounds Decimal70 full bracket')
            code,stable,margins=scalar_rule(saved,envelope)
            independent_code,independent_stable,_=scalar_rule(faces,envelope)
            if trace['parent'][i,j]!=parent or trace['code'][i,j]!=code or not np.array_equal(trace['margins_m'][i,j],np.asarray(margins)):
                raise ValueError('Every parent/code/signed margin must reproduce')
            if stable and (not independent_stable or code!=independent_code):
                raise ValueError('Strict independent sufficient edge proof differs')
            kind=1 if stable and code==nominal else 4 if stable else 3 if b-a<=RESOLUTION or not a<mid<b else 2
            if trace['kind'][i,j]!=kind:
                raise ValueError('Cover terminal/split outcome differs')
            expected['parent'][i,j]=parent
            expected['code'][i,j]=code
            expected['kind'][i,j]=kind
            expected['faces_m'][i,j]=saved
            expected['margins_m'][i,j]=margins
            if kind==2:
                pending.extend(((mid,b,j),(a,mid,j)))
            elif kind in (3,4):
                expected['cover_resolution_unresolved' if kind==3 else 'cover_different_stable_code'][i]=True
                failed=True
        if pending and not failed and count<BUDGET:
            raise ValueError('Unfinished cover silently truncated')
        expected['query_count'][i]=count
        expected['frontier_count'][i]=len(pending)
        for j,(a,b,parent) in enumerate(pending):
            expected['frontier_a_s'][i,j]=a
            expected['frontier_b_s'][i,j]=b
            expected['frontier_parent'][i,j]=parent
        expected['cover_budget_exhausted'][i]=bool(pending and count==BUDGET and not failed)
        certified=not pending and not failed
        expected['edge_newly_certified'][i]=certified
        for key,value in original.items():
            want=np.asarray([True],dtype=value.dtype) if key=='edge_certain' and certified else np.asarray([1<<(nominal-1)],dtype=value.dtype) if key=='possible_edge_codes' and certified else value[i:i+1]
            if not same(proposed[key][i:i+1],want):
                raise ValueError('All and only complete uniform-code cover candidates may change')
        queries+=count
        certified_count+=int(certified)
    for key,value in expected.items():
        if not same(trace[key],value):
            raise ValueError('Complete queried/padded/unknown trace or frontier differs: '+key)
    return dict(records=n,independent_cover_GE0S_queries=queries,newly_certified_edge_candidates=certified_count,
        complete_interval_cover_tree_frontier_budget_padding_checked=True,
        scientific_endpoints_and_original_prefixes_unchanged=True,
        no_global_physical_identifiability_or_noncontact_claim=True)
