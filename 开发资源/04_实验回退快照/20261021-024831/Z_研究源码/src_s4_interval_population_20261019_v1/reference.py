"""Independent numerical references; empirical envelopes, not interval-ODE proofs."""
import math
import numpy as np
from scipy.integrate import solve_ivp
from population import common
from scenarios import Maneuver, SinusoidalManeuver


def maneuver_for(profile):
    cls=SinusoidalManeuver if profile['design'].get('control_shape')=='sinusoidal' else Maneuver
    vehicle=common.Vehicle(**profile['vehicle'])
    return cls.from_spec(profile['design'],vehicle),vehicle


def rhs(time,state,maneuver,vehicle):
    angle=float(maneuver.alpha(time))
    speed=maneuver.speed
    yaw=speed*math.tan(angle)/vehicle.l
    trailer=(speed*math.sin(state[3])+vehicle.l_h*yaw*math.cos(state[3]))/vehicle.L
    return [speed*math.cos(state[2]),speed*math.sin(state[2]),yaw,yaw-trailer]


def acceleration_bound(maneuver,vehicle):
    speed=abs(maneuver.speed)
    yaw=speed*math.tan(abs(maneuver.peak))/vehicle.l
    yaw_dot=speed/max(math.cos(maneuver.peak)**2,1e-12)*max(maneuver.entry_rate,maneuver.return_rate)/vehicle.l
    trailer=(speed+abs(vehicle.l_h)*yaw)/vehicle.L
    phi_dot=yaw+trailer
    trailer_dot=(speed*phi_dot+abs(vehicle.l_h)*yaw_dot+abs(vehicle.l_h)*yaw*phi_dot)/vehicle.L
    return speed*yaw+abs(vehicle.l_h)*(yaw_dot+yaw*yaw)+math.hypot(vehicle.L,vehicle.width/2)*(trailer_dot+trailer*trailer)


def curve_bound(states,vehicle):
    delta=np.diff(states,axis=0)
    return float(np.max((abs(vehicle.l_h)*delta[:,2]**2+math.hypot(vehicle.L,vehicle.width/2)*(delta[:,2]-delta[:,3])**2)/8))


def independent_reference(profile,old_time,old_state):
    maneuver,vehicle=maneuver_for(profile)
    if (old_state.shape!=(len(old_time),4) or len(old_time)<2
            or not np.isfinite(old_state).all() or not np.isfinite(old_time).all()
            or not np.all(np.diff(old_time)>0) or abs(old_time[0])>1e-12):
        raise ValueError('Invalid frozen full reference')
    end=float(old_time[-1])
    if abs(end-maneuver.end)>1e-8 or not np.allclose(old_state[0],[0,0,math.pi/2,0],rtol=0,atol=1e-12):
        raise ValueError('Frozen control duration/initial pose differs')
    solutions=[]
    for rtol,atol,step in ((1e-11,1e-13,.01),(1e-10,1e-12,.02)):
        sol=solve_ivp(lambda t,s:rhs(t,s,maneuver,vehicle),(0,end),old_state[0],method='DOP853',
                      rtol=rtol,atol=atol,max_step=step,dense_output=True)
        if not sol.success:
            raise RuntimeError(sol.message)
        solutions.append(sol)
    time=np.arange(round(end/.0025)+1)*.0025
    if abs(time[-1]-end)>1e-9:
        raise ValueError('Independent reference grid must preserve exact duration')
    state=solutions[0].sol(time).T
    secondary=solutions[1].sol(time).T
    old_corners=common.body_corners(old_state,vehicle)
    old_comparison=common.body_corners(solutions[0].sol(old_time).T,vehicle)
    primary_corners=common.body_corners(state,vehicle)
    secondary_corners=common.body_corners(secondary,vehicle)
    old_error=float(np.max(np.linalg.norm(old_corners-old_comparison,axis=2)))
    solver_error=float(np.max(np.linalg.norm(primary_corners-secondary_corners,axis=2)))
    if max(old_error,solver_error)>.005 or np.max(np.abs(state[:,3]))>math.pi/4:
        raise ValueError('Independent reference geometric/design admission failed')
    endpoint=max(old_error,solver_error)+1e-7
    acc=acceleration_bound(maneuver,vehicle)
    errors=[endpoint+acc*float(np.max(np.diff(t)))**2/8+curve_bound(s,vehicle)
            for t,s in ((old_time,old_state),(time,state))]
    meta={'old_all_corner_vs_DOP853_m':old_error,'primary_vs_secondary_all_corner_m':solver_error,
          'endpoint_empirical_envelope_m':endpoint,'corner_acceleration_bound_mps2':acc,
          'old_path_spatial_envelope_m':errors[0],'independent_path_spatial_envelope_m':errors[1],
          'numerical_error_is_empirical_not_certified_ODE_bound':True,
          'two_integrations_not_linear_subdivision':True}
    return {'time':time,'state':state,'secondary_state':secondary},meta


def combine(a,b):
    sa,sb=a['contact_status'],b['contact_status']
    both=(sa==1)&(sb==1)
    none=(sa==0)&(sb==0)
    status=np.full(len(sa),2,np.int8)
    status[both]=1
    status[none]=0
    status[(sa==3)|(sb==3)]=3
    lower=np.fmin(a['contact_lower_s'],b['contact_lower_s'])
    upper=np.fmax(a['contact_upper_s'],b['contact_upper_s'])
    bits=a['possible_edge_codes']|b['possible_edge_codes']
    bits[~(both|none)]=255
    disjoint_time=both & ((a['contact_lower_s']>b['contact_upper_s'])|(b['contact_lower_s']>a['contact_upper_s']))
    disjoint_edge=both & ((a['possible_edge_codes']&b['possible_edge_codes'])==0)
    conflict=((sa==0)&(sb==1))|((sb==0)&(sa==1))|disjoint_time|disjoint_edge
    return {'contact_status':status,'contact_lower_s':lower,'contact_upper_s':upper,
            'possible_edge_codes':bits,'model_conflict':conflict,
            'time_interval_conflict':disjoint_time,'edge_set_conflict':disjoint_edge}
