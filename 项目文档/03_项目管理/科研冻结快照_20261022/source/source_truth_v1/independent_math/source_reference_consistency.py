"""Exact full-horizon source/reference consistency bounds; no label promotion."""
from fractions import Fraction as F
from . import entry_interval_geometry as interval

def compare(steps, reference_time, reference_state, parameters, independent_chain=None,check=lambda:None):
    times=list(map(F,reference_time)); rows=[list(map(F,r)) for r in reference_state]
    if len(times)<2 or len(rows)!=len(times) or any(len(r)!=4 for r in rows): raise ValueError("Reference shape")
    if any(b<=x for x,b in zip(times,times[1:])): raise ValueError("Reference time must strictly increase")
    if not steps: raise ValueError("Complete source proof required")
    params={k:F(parameters[k]) for k in ("v","l","lh","L","width")}
    if min(params["v"],params["l"],params["L"],params["width"])<=0: raise ValueError("Positive physical parameters")
    own=independent_chain["steps"] if independent_chain is not None else None
    if own is not None and len(own)!=len(steps): raise ValueError("Independent chain partition")
    src=[]; clock=None
    for idx,st in enumerate(steps):
        left,right=F(st["start"]),F(st["end"])
        if right<=left or (clock is not None and clock!=left): raise ValueError("Source coverage gap or overlap")
        er=own[idx]["end_errors"] if own is not None else st.get("worker_full_errors")
        if er is None or len(er)!=4: raise ValueError("Full-step state error bounds required")
        er=list(map(F,er))
        if any(e<0 for e in er): raise ValueError("Nonnegative state error bounds required")
        if len(st["center"])!=4 or len(st["P"])!=4: raise ValueError("Four source states required")
        src.append((left,right,st,er)); clock=right
    if src[0][0]!=times[0] or src[-1][1]!=times[-1]: raise ValueError("Full matching horizon required")
    maxima=[F(0)]*4; count=0; i=j=0
    while i<len(src) and j<len(times)-1:
        check()
        left=max(src[i][0],times[j]); right=min(src[i][1],times[j+1])
        if left<right:
            st=src[i][2]; local_a=left-src[i][0]; local_b=right-src[i][0]
            for k in range(4):
                coeff=list(map(F,st["P"][k]))
                if not coeff: raise ValueError("Empty source polynomial")
                coeff[0]+=F(st["center"][k])
                slope=(rows[j+1][k]-rows[j][k])/(times[j+1]-times[j])
                ref0=rows[j][k]+slope*(src[i][0]-times[j])
                if len(coeff)<2: coeff.append(F(0))
                coeff[0]-=ref0; coeff[1]-=slope
                lo,hi=interval.polynomial_range(coeff,(local_a,local_b))
                maxima[k]=max(maxima[k],abs(lo)+src[i][3][k],abs(hi)+src[i][3][k])
            count+=1
        # Advance whichever interval ends at this overlap boundary; both on equality.
        se,re=src[i][1],times[j+1]
        if se<=re: i+=1
        if re<=se: j+=1
    covered=(i==len(src) and j==len(times)-1)
    corner=maxima[0]+maxima[1]+abs(params["lh"])*maxima[2]+(params["L"]+params["width"]/2)*(maxima[2]+maxima[3])
    return dict(max_state_bounds=maxima,corner_bound=corner,intersection_count=count,all_covered=covered,scientific_label_promotion_allowed=False)
