"""Unfrozen independent prefix exclusion audit; no real-data entrypoint.

The pose model and spatial envelope remain conditional. GEOS distances plus
motion bounds audit all time before a supplied first-possible lower bound.
Unknowns, evaluation limits and actual early witnesses are distinct results.
"""
from pathlib import Path
import sys
import numpy as np
import shapely

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src_v3'))
import common


def audit_prefixes(xy,time,states,lower,*,vehicle=None,spatial_error_m=0.,tolerance_m=.050000001,
                   time_resolution_s=1e-8,max_evaluations_per_point=8192):
    vehicle=common.Vehicle() if vehicle is None else vehicle
    xy,time,states,lower=map(lambda a:np.asarray(a,float),(xy,time,states,lower))
    if (xy.ndim!=2 or xy.shape[1]!=2 or lower.shape!=(len(xy),)
        or len(time)<2 or states.shape!=(len(time),4)
        or not np.isfinite(xy).all() or not np.isfinite(time).all() or not np.isfinite(states).all()
        or not np.all(np.diff(time)>0) or np.isinf(lower).any()
        or np.any(np.isfinite(lower)&((lower<time[0])|(lower>time[-1])))
        or not np.isfinite([spatial_error_m,tolerance_m,time_resolution_s]).all()
        or spatial_error_m<0 or tolerance_m<0 or time_resolution_s<=0
        or max_evaluations_per_point<1):
        raise ValueError('Invalid full prefix audit contract')
    n=len(xy)
    limit=np.where(np.isnan(lower),time[-1],lower)
    uncertain=np.zeros(n,bool)
    witness=np.zeros(n,bool)
    exhausted=np.zeros(n,bool)
    counts=np.zeros(n,np.int32)
    pairs=np.zeros(n,np.int32)
    tree=shapely.STRtree(shapely.points(xy))
    corners=common.body_corners(states,vehicle)
    radius=np.hypot(vehicle.L,vehicle.width/2)
    for k in range(len(time)-1):
        delta=states[k+1]-states[k]
        # Each rotating corner's chord error is bounded by max second derivative / 8.
        curvature=(abs(vehicle.l_h)*delta[2]**2+radius*(delta[2]-delta[3])**2)/8
        endpoints=np.concatenate((corners[k],corners[k+1]),axis=0)
        pad=tolerance_m+spatial_error_m+curvature+1e-12
        minimum=endpoints.min(axis=0)-pad
        maximum=endpoints.max(axis=0)+pad
        ids=tree.query(shapely.box(*minimum,*maximum))
        # Nan lower means noncontact claim, so the entire supplied path is audited.
        duration=time[k+1]-time[k]
        end=np.minimum(1.,(limit[ids]-time[k])/duration)
        keep=(end>0)&~(witness[ids]|uncertain[ids])
        ids,end=ids[keep],end[keep]
        if not len(ids):
            continue
        pairs[ids]+=1
        full_motion=np.hypot(delta[0],delta[1])+abs(vehicle.l_h*delta[2])+radius*abs(delta[2]-delta[3])
        stack=[(ids,np.zeros(len(ids)),end)]
        while stack:
            selected,a,b=stack.pop()
            keep=~(witness[selected]|uncertain[selected])
            selected,a,b=selected[keep],a[keep],b[keep]
            if not len(selected):
                continue
            limited=counts[selected]>=max_evaluations_per_point
            uncertain[selected[limited]]=True
            exhausted[selected[limited]]=True
            selected,a,b=selected[~limited],a[~limited],b[~limited]
            if not len(selected):
                continue
            middle=(a+b)/2
            poses=states[k]+middle[:,None]*delta
            polygons=shapely.polygons(common.body_corners(poses,vehicle))
            distances=shapely.distance(shapely.points(xy[selected]),polygons)
            counts[selected]+=1
            early=distances+spatial_error_m<=tolerance_m
            witness[selected[early]]=True
            possible=~early&(distances-spatial_error_m-full_motion*(b-a)/2-1e-12<=tolerance_m)
            selected,a,b,middle=selected[possible],a[possible],b[possible],middle[possible]
            if not len(selected):
                continue
            budget=counts[selected]>=max_evaluations_per_point
            leaf=(b-a)*duration<=time_resolution_s
            unknown=budget|leaf
            uncertain[selected[unknown]]=True
            exhausted[selected[budget]]=True
            selected,a,b,middle=selected[~unknown],a[~unknown],b[~unknown],middle[~unknown]
            if len(selected):
                stack.append((selected,middle,b))
                stack.append((selected,a,middle))
    return {'prefix_excluded':~(witness|uncertain),'early_contact_witness':witness,
            'prefix_undetermined':uncertain,'budget_exhausted':exhausted,
            'GEOS_evaluations':counts,'candidate_interval_pairs':pairs,'audited_until_s':limit}
