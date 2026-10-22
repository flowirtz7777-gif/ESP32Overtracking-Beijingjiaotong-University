"""Correlated polynomial projection into trailer body coordinates; auxiliary bounds only."""
from fractions import Fraction as F
from . import general_step_residual as step
from . import validated_entry_core as poly
from . import entry_interval_geometry as interval

def project(point,center,P,cell,n,h,state_errors,lh,L,width):
    """Enclose body-frame q/r and squared distance for one certified state tube.

    The caller supplies full state errors already certified from the original
    step initial tube and control error. This routine does not reset those errors.
    """
    n=int(n);h=F(h);a,b=map(F,cell);point=list(map(F,point));center=list(map(F,center))
    P=[list(map(F,row)) for row in P];E=list(map(F,state_errors));lh,L,width=map(F,(lh,L,width))
    if n<0 or h<=0 or len(center)!=4 or len(P)!=4 or len(E)!=4 or len(point)!=2:
        raise ValueError("Finite four-state polynomial projection contract")
    if any(len(row)!=n+1 or row[0]!=0 for row in P): raise ValueError("Full degree-n zero-origin state polynomials required")
    if not (0<=a<b<=h): raise ValueError("Projection cell must lie inside original step")
    if any(e<0 for e in E) or L<=0 or width<=0: raise ValueError("Nonnegative state errors and positive body dimensions required")
    psi0=center[2]-center[3];Ppsi=poly.sub(P[2],P[3])
    Spsi,eSpsi=step.trig_series(psi0,Ppsi,n,b);Cpsi,eCpsi=step.trig_series(psi0,Ppsi,n,b,True)
    Sphi,eSphi=step.trig_series(center[3],P[3],n,b);Cphi,eCphi=step.trig_series(center[3],P[3],n,b,True)
    A=poly.sub([point[0]-center[0]],P[0]);B=poly.sub([point[1]-center[1]],P[1])
    normA=poly.norm(A,b);normB=poly.norm(B,b)
    Q=poly.add(poly.add(poly.mul(A,Cpsi),poly.mul(B,Spsi)),poly.scale(Cphi,-lh))
    R=poly.add(poly.sub(poly.mul(A,Spsi),poly.mul(B,Cpsi)),poly.scale(Sphi,lh))
    eq=normA*eCpsi+normB*eSpsi+abs(lh)*eCphi
    er=normA*eSpsi+normB*eCpsi+abs(lh)*eSphi
    lipschitz=E[0]+E[1]+(normA+normB)*(E[2]+E[3])+abs(lh)*E[3]
    qerror=eq+lipschitz;rerror=er+lipschitz
    qbox=interval.inflate(interval.polynomial_range(Q,(a,b)),qerror)
    rbox=interval.inflate(interval.polynomial_range(R,(a,b)),rerror)
    longitudinal=interval.maximum(qbox,interval.neg(interval.add(L,qbox)),0)
    lateral=interval.maximum(interval.sub(rbox,width/2),interval.sub(interval.neg(rbox),width/2),0)
    distance=interval.add(interval.square(longitudinal),interval.square(lateral))
    return dict(q=qbox,r=rbox,distance_squared=distance,nominal_polynomials=dict(q=Q,r=R),
        nominal_trig_error=dict(q=eq,r=er),state_lipschitz_error=lipschitz,
        total_coordinate_error=dict(q=qerror,r=rerror),cell=(a,b),original_step_h=h,
        degree=n,geometry_evaluations=0,label_admission_allowed=False,
        physical_ambiguity_inference_made=False)

def conditional_decision(distance_squared,tolerance,original_spatial_error):
    """Classify only against the supplied original two-reference spatial margin."""
    lo,hi=map(F,distance_squared);tol=F(tolerance);err=F(original_spatial_error)
    if lo<0 or lo>hi or tol<0 or err<0: raise ValueError("Ordered squared-distance interval and nonnegative margins required")
    if lo>(tol+err)**2: return "strict_noncontact"
    if err<=tol and hi<=(tol-err)**2: return "certain_contact"
    return "unknown"
