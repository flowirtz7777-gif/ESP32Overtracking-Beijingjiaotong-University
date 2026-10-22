"""Pure full-source ODE chain audit; no geometry classifications."""
from fractions import Fraction as F
from .independent_math import source_control_enclosure as control_core
from .independent_math import independent_step_verifier as independent
from .independent_math import entry_interval_geometry as interval
_NAMES=("x","y","theta","phi")
def audit(artifact,control,vehicle,speed,end,initial,points,limits,check=lambda:None,progress=lambda text:None):
    expected=(("control",control),("vehicle",vehicle),("speed",speed),("end",F(end)),("initial",list(map(F,initial))),("points",points),("limits",limits))
    for key,value in expected:
        if artifact.get(key)!=value: raise ValueError("Full source artifact binding differs: "+key)
    records=artifact.get("steps")
    if not isinstance(records,list) or not records: raise ValueError("Complete source step list required")
    end=F(end);times=control_core.partition(control,end,F(limits["maximum_step"]))
    if len(records)!=len(times)-1 or len(records)>int(limits["maximum_steps"]): raise ValueError("Whole original source partition required")
    for k,r in enumerate(records):
        check();left,right=F(r["start"]),F(r["end"])
        if left!=times[k] or right!=times[k+1] or right<=left: raise ValueError("Source gap, overlap, or partition mismatch")
        if int(r["n"])!=int(limits["degree"]) or len(r["center"])!=4 or len(r["P"])!=4 or len(r["alpha"])!=int(limits["degree"])+1:
            raise ValueError("Complete source polynomial contract")
        alpha,ae,trace=control_core.enclose(control,left,right-left,F(limits["time_error"]),limits["degree"])
        if (r["alpha"],r["alpha_error"],r["source_branch_trace"])!=(alpha,ae,trace): raise ValueError("Original source control/error/branch trace mismatch")
    if F(records[0]["start"])!=0 or F(records[-1]["end"])!=end: raise ValueError("Complete source horizon required")
    params=dict(v=F(speed),l=F(vehicle["l"]),lh=F(vehicle["l_h"]),L=F(vehicle["L"]))
    if F(vehicle["width"])<=0:raise ValueError("Positive vehicle width for source body bound")
    chain=independent.verify_chain(records,initial,0,end,**params,check=check)
    width=F(vehicle["width"]);scale=[F(1),F(1),abs(params["lh"])+params["L"]+width/2,params["L"]+width/2]
    max_body=F(0);max_inherited_body=F(0)
    rows=[];maxvar=[F(0)]*4;maxrad=[F(0)]*4;maxratio=[F(0)]*4
    for k,(r,own) in enumerate(zip(records,chain["steps"])):
        check()
        h=F(r["end"])-F(r["start"]);states=[]
        for j,(name,poly) in enumerate(zip(_NAMES,r["P"])):
            lo,hi=interval.polynomial_range(poly,(0,h));variation=max(abs(lo),abs(hi))
            ir=F(own["initial_errors"][j]);er=F(own["end_errors"][j]);ratio=None if er==0 else variation/er
            states.append(dict(state=name,nominal_polynomial_range=(lo,hi),nominal_variation_radius=variation,own_initial_radius=ir,own_end_radius=er,variation_to_own_end_radius=ratio))
            maxvar[j]=max(maxvar[j],variation);maxrad[j]=max(maxrad[j],er)
            if ratio is not None:maxratio[j]=max(maxratio[j],ratio)
        claim=r.get("worker_full_errors")
        if claim is None: cmp=dict(present=False,values=None,minus_independent_end=None,componentwise_contains_independent_end=None)
        else:
            claim=list(map(F,claim))
            if len(claim)!=4 or any(x<0 for x in claim):raise ValueError("Malformed worker error claim")
            cmp=dict(present=True,values=claim,minus_independent_end=[a-b for a,b in zip(claim,own["end_errors"])],componentwise_contains_independent_end=all(a>=b for a,b in zip(claim,own["end_errors"])))
        body=sum((q*F(e) for q,e in zip(scale,own["end_errors"])),F(0));inherited=sum((q*F(e) for q,e in zip(scale,own["initial_errors"])),F(0))
        max_body=max(max_body,body);max_inherited_body=max(max_inherited_body,inherited)
        rows.append(dict(body_position_radius_upper_m=body,inherited_body_position_radius_upper_m=inherited,body_bound_contributions_m=[q*F(e) for q,e in zip(scale,own["end_errors"])],step_index=k,start=F(r["start"]),end=F(r["end"]),independent_initial_errors=list(own["initial_errors"]),independent_end_errors=list(own["end_errors"]),state_scale=states,worker_claim_comparison=cmp))
        if k%16==0:progress("AUDITED SOURCE STEP "+str(k+1)+"/"+str(len(records)))
    j=max(range(4),key=lambda x:maxratio[x])
    return dict(independent_full_source_chain_verified=True,complete_source_time_covered=True,independent_chain=chain,steps=rows,
        aggregate=dict(max_body_position_radius_upper_m=max_body,max_inherited_body_position_radius_upper_m=max_inherited_body,max_nominal_variation_by_state=dict(zip(_NAMES,maxvar)),max_independent_end_radius_by_state=dict(zip(_NAMES,maxrad)),max_variation_to_end_radius_by_state=dict(zip(_NAMES,maxratio)),dominant_state_by_max_ratio=_NAMES[j],dominant_max_ratio=maxratio[j]),
        geometry_evaluations=0,geometry_or_contact_claims_made=False,original_points_retained=len(points),original_conditional_domains_mutated=False,corrected_truth_or_score_certificates=0,scientific_label_promotion_allowed=False,physical_ambiguity_inference_made=False)
