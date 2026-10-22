"""Namespaced pure integration; exact original source binding before geometry."""
from fractions import Fraction as F
from .primary import source_control_enclosure as control_math
from . import worker,audit_core
TARGET="source-model-continuous-simulated-truth-v1"

def bind_source(artifact,args,check=lambda:None):
    keys=("control","vehicle","speed","end","initial","points","limits")
    for key in keys:
        if artifact.get(key)!=args[key]:raise ValueError("Complete original source identity differs: "+key)
    limits=args["limits"];records=artifact.get("steps")
    if (type(limits["degree"]) is not int or limits["degree"]!=6 or
        F(limits["maximum_step"])!=F(1,5) or
        limits["geometry_evaluations_per_point"]!=4096 or
        limits["maximum_geometry_depth"]!=24):
        raise ValueError("Original source step/order/geometry budgets unchanged")
    times=control_math.partition(args["control"],F(args["end"]),F(limits["maximum_step"]))
    if not records or len(records)!=len(times)-1 or len(records)>limits["maximum_steps"]:
        raise ValueError("All original source phases required")
    for k,record in enumerate(records):
        check()
        if (record["start"],record["end"])!=(times[k],times[k+1]) or record["n"]!=limits["degree"]:
            raise ValueError("Original source partition and degree")
        alpha,err,trace=control_math.enclose(args["control"],times[k],times[k+1]-times[k],
            F(limits["time_error"]),limits["degree"])
        if (record["alpha"],record["alpha_error"],record["source_branch_trace"])!=(alpha,err,trace):
            raise ValueError("Original complete control branch/float-input enclosure")
    return records

def worker_geometry(artifact,args,check=lambda:None,progress=lambda x:None):
    records=bind_source(artifact,args,check)
    v=args["vehicle"];params=dict(v=F(args["speed"]),l=F(v["l"]),lh=F(v["l_h"]),L=F(v["L"]))
    chain=worker.certify_chain(records,args["initial"],args["end"],params,check,progress)
    covers=[]
    for point in args["points"]:
        check();progress("SOURCE POINT START "+str(point["original_index"]))
        covers.append(worker.cover_point(records,chain,point,v,args["end"],args["limits"]["tolerance"],
            budget=args["limits"]["geometry_evaluations_per_point"],
            depth=args["limits"]["maximum_geometry_depth"],check=check,progress=progress))
        progress("SOURCE POINT END "+str(point["original_index"])+" "+covers[-1]["summary"]["candidate_status"])
    return dict(target=TARGET,primary_chain=chain,point_covers=covers,
        complete_source_control_bound=True,corrected_truth_certificates=0,
        full_population_admission_allowed=False,training_allowed=False)

def independent_geometry(artifact,args,worker_result,check=lambda:None,progress=lambda x:None):
    """Recompute source own-error chain, then independent full trace geometry."""
    from . import checker
    if worker_result.get("target")!=TARGET:raise ValueError("Explicit new source truth target required")
    a=args
    own=audit_core.audit(artifact,a["control"],a["vehicle"],a["speed"],a["end"],
        a["initial"],a["points"],a["limits"],check=check,progress=progress)
    progress("INDEPENDENT FULL SOURCE OWN-ERROR CHAIN COMPLETE")
    covers=worker_result.get("point_covers")
    if type(covers) not in (list,tuple) or len(covers)!=len(a["points"]):
        raise ValueError("All original source points required")
    v=a["vehicle"];out=[]
    for point,cover in zip(a["points"],covers):
        check()
        exact=dict(point,xy=tuple(F(x) for x in point["xy"]))
        progress("SOURCE CLOSE POINT START "+str(point["original_index"]))
        result=checker.check_point(artifact["steps"],own["independent_chain"],exact,cover,
            hitch_offset=F(v["l_h"]),trailer_length=F(v["L"]),width=F(v["width"]),
            tolerance=F(a["limits"]["tolerance"]),check=check)
        out.append(result)
        progress("SOURCE CLOSE POINT END "+str(point["original_index"])+" "+result["candidate_status"])
    return dict(target=TARGET,independent_source_audit=own,point_results=out,
        existence_candidates=sum(x["candidate_status"] in ("candidate_contact_exists_mutual","candidate_noncontact_mutual") for x in out),
        corrected_truth_or_score_certificates=0,full_population_admission_allowed=False,
        original_conditional_domains_mutated=False,training_allowed=False)
