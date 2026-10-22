"""Pure candidate source-model contact frontier; never a scientific acceptance."""
from fractions import Fraction as F
from math import isfinite

TARGET = "source-model-continuous-simulated-truth-v1"

def rat(x):
    if type(x) not in (int, float, F) or (type(x) is float and not isfinite(x)):
        raise ValueError("Finite plain scalar required; bool is forbidden")
    return F(x)

def interval(x):
    if type(x) not in (list, tuple) or len(x) != 2:
        raise ValueError("Complete interval required")
    a,b=map(rat,x)
    if a>b: raise ValueError("Reversed interval")
    return a,b

def source_distance_decision(distance_squared,tolerance):
    """No empirical-E parameter: this candidate targets the new source model."""
    lo,hi=interval(distance_squared);tol=rat(tolerance)
    if lo<0 or tol<0: raise ValueError("Nonnegative squared distance/tolerance")
    if lo>tol*tol: return "excluded"
    if hi<=tol*tol: return "contact_all_times_in_cell"
    return "unknown"

def summarize(steps,cells,end,tolerance,maximum_evaluations):
    """Check complete source-step partition and candidate chronological frontier.

    Each distance interval is already supposed to include full source numerical
    error. This pure reducer cannot establish that premise or certify any label.
    Earliest possible time is never replaced by a midpoint.
    """
    end=rat(end);tol=rat(tolerance)
    if end<=0 or tol<0 or type(maximum_evaluations) is not int or maximum_evaluations<1:
        raise ValueError("Positive horizon/budget and nonnegative tolerance")
    if type(steps) not in (list,tuple) or not steps:
        raise ValueError("Full original source partition required")
    spans=[];clock=F(0)
    for step in steps:
        a,b=interval(step)
        if a!=clock or b<=a: raise ValueError("Source time gap/overlap")
        spans.append((a,b));clock=b
    if clock!=end:raise ValueError("Incomplete source horizon")
    if type(cells) not in (list,tuple) or not cells:raise ValueError("Complete frontier required")
    clock=F(0);count=0;earliest=None;upper=None;unknown=0
    per_step=[0]*len(spans);classified=[]
    for cell in cells:
        index=cell["step_index"]
        if type(index) is not int or not 0<=index<len(spans):raise ValueError("Exact original step index")
        a,b=interval(cell["time"]);sa,sb=spans[index]
        if not (sa<=a<b<=sb) or a!=clock:raise ValueError("Cell gap/overlap/cross-step")
        # Null means explicitly uncomputed, not a claimed geometric exclusion.
        bounds=cell["distance_squared"]
        calls=cell["evaluations"]
        if type(calls) is not int or calls<0:raise ValueError("Exact nonnegative call count")
        if bounds is None:
            state="unknown"
        else:
            if calls<1:raise ValueError("Computed geometry requires a counted call")
            state=source_distance_decision(bounds,tol)
        count+=calls
        if count>maximum_evaluations:raise ValueError("Fixed geometry budget exceeded")
        per_step[index]+=1;clock=b;classified.append(state)
        if state!="excluded" and earliest is None:earliest=a
        if state=="contact_all_times_in_cell" and upper is None:upper=a
        unknown+=state=="unknown"
    if clock!=end or not all(per_step):raise ValueError("Whole original horizon/frontier required")
    status=("contact_exists" if upper is not None else
            "noncontact" if earliest is None else "unknown")
    return dict(target=TARGET,candidate_status=status,
        first_contact_interval=None if upper is None else (earliest,upper),
        earliest_unexcluded_s=earliest,certified_contact_time_upper_s=upper,
        unknown_cells=unknown,geometry_evaluations=count,cell_states=classified,
        entire_original_horizon_covered=True,
        face_candidate_mask=255,face_certification_complete=False,
        corrected_truth_certificates=0,scientific_admission_allowed=False)
