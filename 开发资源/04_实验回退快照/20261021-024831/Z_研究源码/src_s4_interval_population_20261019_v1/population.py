"""All-point interval labels with conservative broad phase and explicit unknowns.

Bounds are conditional on the input piecewise-linear pose and spatial envelope.
They must not be described as formal interval-ODE or real-vehicle guarantees.
"""
from pathlib import Path
import sys
import numpy as np
import shapely

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src_v3'))
sys.path.insert(0,str(ROOT/'src_s4_truth_remediation_20261019_v1'))
import common
from contact_primitives import finite_face_geometry
from interval_contact import motion_bound, original_corner_rule

def interval_candidates(states, vehicle):
    corners=common.body_corners(states,vehicle)
    hulls=shapely.convex_hull(shapely.multipoints(np.concatenate((corners[:-1],corners[1:]),axis=1)))
    delta=np.diff(states,axis=0)
    radius=np.hypot(vehicle.L,vehicle.width/2)
    curvature=(abs(vehicle.l_h)*delta[:,2]**2+radius*(delta[:,2]-delta[:,3])**2)/8
    return hulls,curvature

def search_first_possible(points, start, end, duration, speed, tolerance, space_error,
                          time_resolution, max_evaluations, params):
    n=len(points)
    lower=np.full(n,np.nan)
    upper=np.full(n,np.nan)
    count=np.zeros(n,np.int32)
    budget=np.zeros(n,bool)
    d_end,_=finite_face_geometry(points,end,**params)
    upper[d_end+space_error<=tolerance]=1.
    unresolved=np.ones(n,bool)
    stack=[(np.arange(n),np.zeros(n),np.ones(n))]
    delta=end-start
    while stack:
        ids,a,b=stack.pop()
        use=unresolved[ids]
        ids,a,b=ids[use],a[use],b[use]
        if not len(ids):
            continue
        middle=(a+b)/2
        pose=start+middle[:,None]*delta
        distance,_=finite_face_geometry(points[ids],pose,**params)
        count[ids]+=1
        potential=distance-space_error-speed*(b-a)*duration/2-1e-12<=tolerance
        ids,a,b,middle,distance=ids[potential],a[potential],b[potential],middle[potential],distance[potential]
        if not len(ids):
            continue
        witness=distance+space_error<=tolerance
        wi=ids[witness]
        upper[wi]=np.fmin(upper[wi],middle[witness])
        exhausted=count[ids]>=max_evaluations
        leaf=((b-a)*duration<=time_resolution)|exhausted
        lower[ids[leaf]]=a[leaf]
        budget[ids[leaf]]=exhausted[leaf]
        unresolved[ids[leaf]]=False
        ids,a,b,middle=ids[~leaf],a[~leaf],b[~leaf],middle[~leaf]
        if len(ids):
            stack.append((ids,middle,b))
            stack.append((ids,a,middle))
    if np.any(np.isfinite(upper)&~np.isfinite(lower)):
        raise AssertionError('Contact witness without possible-time cover')
    return lower,upper,count,budget

def label_population(xy,time,states,*,vehicle=None,spatial_error_m=0.,tolerance_m=.050000001,
                     time_resolution_s=1e-7,max_evaluations_per_interval=2048,progress=None):
    vehicle=common.Vehicle() if vehicle is None else vehicle
    xy,time,states=np.asarray(xy,float),np.asarray(time,float),np.asarray(states,float)
    if (xy.ndim!=2 or xy.shape[1]!=2 or states.shape!=(len(time),4) or len(time)<2
            or not np.isfinite(xy).all() or not np.isfinite(time).all() or not np.isfinite(states).all()
            or not np.all(np.diff(time)>0)
            or not np.isfinite([spatial_error_m,time_resolution_s,tolerance_m]).all()
            or spatial_error_m<0 or time_resolution_s<=0
            or tolerance_m<0 or max_evaluations_per_interval<3):
        raise ValueError('Invalid complete population or interval policy')
    params=dict(length=vehicle.L,width=vehicle.width,hitch_offset=vehicle.l_h)
    n=len(xy)
    lower=np.full(n,np.nan)
    upper=np.full(n,np.nan)
    budget=np.zeros(n,bool)
    seen=np.zeros(n,bool)
    evaluated=np.zeros(n,np.int32)
    initial_distance,_=finite_face_geometry(xy,states[0],**params)
    initial_certain=initial_distance+spatial_error_m<=tolerance_m
    initial_possible=initial_distance-spatial_error_m<=tolerance_m
    lower[initial_possible]=time[0]
    upper[initial_certain]=time[0]
    hulls,curve=interval_candidates(states,vehicle)
    speed=motion_bound(states,time,**params)
    tree=shapely.STRtree(shapely.points(xy))
    for k,hull in enumerate(hulls):
        if progress is not None and k%1000==0:
            progress(k,len(hulls),int(np.isfinite(upper).sum()))
        ids=tree.query(hull,predicate='dwithin',distance=tolerance_m+spatial_error_m+curve[k]+1e-12)
        ids=ids[~np.isfinite(upper[ids])]
        if not len(ids):
            continue
        seen[ids]=True
        fresh=ids[~np.isfinite(lower[ids])]
        if len(fresh):
            a,b,counts,exhausted=search_first_possible(xy[fresh],states[k],states[k+1],time[k+1]-time[k],
                speed[k],tolerance_m,spatial_error_m,time_resolution_s,max_evaluations_per_interval,params)
            possible=np.isfinite(a)
            lower[fresh[possible]]=time[k]+a[possible]*(time[k+1]-time[k])
            good=np.isfinite(b)
            upper[fresh[good]]=time[k]+b[good]*(time[k+1]-time[k])
            evaluated[fresh]+=counts
            budget[fresh]|=exhausted
        pending=ids[np.isfinite(lower[ids])&~np.isfinite(upper[ids])]
        if len(pending):
            # An unresolved earlier interval is retained; later evidence may prove contact.
            for alpha in (0.,.5,1.):
                pose=states[k]+alpha*(states[k+1]-states[k])
                distance,_=finite_face_geometry(xy[pending],pose,**params)
                good=(distance+spatial_error_m<=tolerance_m)&~np.isfinite(upper[pending])
                upper[pending[good]]=time[k]+alpha*(time[k+1]-time[k])
    status=np.zeros(n,np.int8)
    status[np.isfinite(lower)]=2
    status[np.isfinite(upper)]=1
    status[budget]=3
    codes=np.zeros(n,np.int8)
    bits=np.zeros(n,np.uint16)
    bits[status>=2]=255
    witness_pose=np.full((n,4),np.nan)
    confidence=np.zeros(n,bool)
    witnessed=np.isfinite(upper)
    if np.any(witnessed):
        ids=np.flatnonzero(witnessed)
        middle=(lower[ids]+upper[ids])/2
        pose=np.column_stack([np.interp(middle,time,states[:,j]) for j in range(4)])
        _,face=finite_face_geometry(xy[ids],pose,**params)
        nominal=original_corner_rule(face)
        ordered=np.sort(face,axis=1)
        order=np.argsort(face,axis=1)
        envelope=spatial_error_m+float(speed.max())*(upper[ids]-lower[ids])/2
        single=ordered[:,1]-ordered[:,0]-2*envelope>.001
        pair=np.sort(order[:,:2],axis=1)
        adjacent=np.any(np.stack([(pair==p).all(axis=1) for p in ((0,1),(1,2),(0,3),(2,3))]),axis=0)
        corner=(ordered[:,1]-ordered[:,0]+2*envelope<.001)&(ordered[:,2]-ordered[:,1]>2*envelope)&adjacent
        stable=(single|corner)&~budget[ids]
        codes[ids]=nominal
        bits[ids]=255
        bits[ids[stable]]=np.left_shift(np.uint16(1),nominal[stable].astype(np.uint16)-1)
        confidence[ids]=stable
        witness_pose[ids]=np.column_stack([np.interp(upper[ids],time,states[:,j]) for j in range(4)])
    return {'contact_status':status,'contact_lower_s':lower,'contact_upper_s':upper,
        'nominal_instantaneous_edge':codes,'possible_edge_codes':bits,'edge_certain':confidence,
        'initial_tolerance_contact_certain':initial_certain,'initial_tolerance_contact_possible':initial_possible,
        'initial_nominal_body_overlap':initial_distance==0,
        'candidate_interval_seen':seen,'interval_evaluations':evaluated,'budget_exhausted':budget,
        'witness_pose':witness_pose}
