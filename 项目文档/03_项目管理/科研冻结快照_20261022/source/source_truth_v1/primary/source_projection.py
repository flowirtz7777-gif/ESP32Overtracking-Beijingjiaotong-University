"""Pure source-step polynomial geometry candidate; no labels or real inputs."""
from fractions import Fraction as F
from math import comb,isfinite
from .correlated_projection import project

def scalar(x):
    if type(x) not in (int,float,F) or (type(x) is float and not isfinite(x)):
        raise ValueError("Finite exact scalar; bool forbidden")
    return F(x)

def centered_range(coefficients,a,b):
    """Exact polynomial shift, no sample/minimum argument."""
    c=(a+b)/2;radius=(b-a)/2
    shifted=[sum((scalar(v)*comb(k,j)*c**(k-j) for k,v in enumerate(coefficients) if k>=j),F(0)) for j in range(len(coefficients))]
    spread=sum((abs(v)*radius**j for j,v in enumerate(shifted) if j),F(0))
    return shifted[0]-spread,shifted[0]+spread

def compile_step(point,center,P,n,h,full_step_errors,lh,length,width):
    """Compile once from the ORIGINAL step; keep full numerical tube."""
    if type(n) is not int or n<4:raise ValueError("Exact degree >=4")
    h,lh,length,width=map(scalar,(h,lh,length,width))
    if h<=0 or length<=0 or width<=0:raise ValueError("Positive horizon/dimensions")
    for values,size in ((point,2),(center,4),(full_step_errors,4)):
        if type(values) not in (list,tuple) or len(values)!=size:raise ValueError("Complete source shape")
        for v in values:scalar(v)
    if type(P) not in (list,tuple) or len(P)!=4:raise ValueError("Four source polynomials")
    for row in P:
        if type(row) not in (list,tuple) or len(row)!=n+1 or scalar(row[0])!=0:raise ValueError("Complete zero-origin source polynomial")
        for v in row:scalar(v)
    errors=tuple(map(scalar,full_step_errors))
    if any(e<0 for e in errors):raise ValueError("Full nonnegative inherited tube")
    out=project(point,center,P,(F(0),h),n,h,errors,lh,length,width)
    if any(type(out["nominal_polynomials"][key]) not in (list,tuple) for key in ("q","r")):
        raise ValueError("Dense coefficient representation required; sparse keys are not coefficients")
    return dict(q=tuple(out["nominal_polynomials"]["q"]),
        r=tuple(out["nominal_polynomials"]["r"]),
        errors=(out["total_coordinate_error"]["q"],out["total_coordinate_error"]["r"]),
        original_h=h,source_full_step_errors=errors,length=length,width=width,
        degree=n,source_trig_and_tube_domain=(F(0),h),
        scientific_admission_allowed=False)

def axis_bounds(value,left,right):
    lo,hi=value
    def d(x):return max(left-x,F(0),x-right)
    return max(left-hi,F(0),lo-right),max(d(lo),d(hi))

def evaluate_cell(compiled,a,b):
    """Only range evaluation per cell, without source residual recertification."""
    a,b=map(scalar,(a,b));h=compiled["original_h"]
    if not 0<=a<b<=h:raise ValueError("Cell must stay in original source step")
    q=centered_range(compiled["q"],a,b);r=centered_range(compiled["r"],a,b)
    eq,er=compiled["errors"];q=(q[0]-eq,q[1]+eq);r=(r[0]-er,r[1]+er)
    length,width=compiled["length"],compiled["width"]
    long=axis_bounds(q,-length,F(0));lat=axis_bounds(r,-width/2,width/2)
    d2=(long[0]**2+lat[0]**2,long[1]**2+lat[1]**2)
    def edge(axis,value,outside):
        d=axis_bounds(axis,value,value)
        return d[0]**2+outside[0]**2,d[1]**2+outside[1]**2
    faces=(edge(q,F(0),lat),edge(r,width/2,long),edge(q,-length,lat),edge(r,-width/2,long))
    return dict(distance_squared=d2,finite_edge_distance_squared=faces,
        finite_edge_order=("front","right","rear","left"),q=q,r=r,cell=(a,b),
        source_full_step_errors=compiled["source_full_step_errors"],
        source_trig_and_tube_domain=compiled["source_trig_and_tube_domain"],
        geometry_evaluations=1,face_candidate_mask=255,
        face_certification_complete=False,scientific_admission_allowed=False)
