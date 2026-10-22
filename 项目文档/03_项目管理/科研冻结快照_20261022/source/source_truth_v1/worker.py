"""Pure source-model chain/frontier candidate. No data I/O or scientific acceptance."""
from fractions import Fraction as F
from .primary import general_step_residual as residual
from .primary import validated_entry_core as polynomial
from .primary.source_projection import compile_step,evaluate_cell,scalar
from .frontier import summarize,source_distance_decision

def _up(x,bits=100):
    x=scalar(x);scale=1<<bits
    return F((x.numerator*scale+x.denominator-1)//x.denominator,scale)

def certify_chain(records,initial,end,params,check=lambda:None,progress=lambda x:None):
    """Recompute primary residual/tubes, ignoring all worker-supplied error fields.

    Source-control semantics/branch proof is a separate mandatory driver gate.
    These end radii come from a monotone nonnegative all-time majorant on each step.
    """
    if type(records) not in (list,tuple) or not records or len(initial)!=4:
        raise ValueError("Complete source chain and exact initial state")
    end=scalar(end);clock=F(0);current=list(map(scalar,initial));errors=[F(0)]*4
    previous=None;out=[]
    for k,record in enumerate(records):
        check();left,right=map(scalar,(record["start"],record["end"]))
        if left!=clock or right<=left:raise ValueError("Full source partition has gap/overlap")
        center=list(map(scalar,record["center"]))
        if len(center)!=4:raise ValueError("Complete source center")
        if previous is None:
            if center!=current:raise ValueError("Exact original initial state required")
        else:
            prev,h=previous
            exact=[c+polynomial.value(row,h) for c,row in zip(current,prev["P"])]
            errors=[_up(e+abs(c-x)) for e,c,x in zip(errors,center,exact)]
        n=record["n"];h=right-left
        if type(n) is not int or n<4:raise ValueError("Exact source degree")
        proof=residual.certify(center,record["P"],record["alpha"],n,h,
            **params,initial_errors=errors,alpha_error=scalar(record["alpha_error"]))
        full=[_up(x) for x in proof["all_times_state_error_bounds"]]
        out.append(dict(start=left,end=right,initial_errors=list(errors),
            end_errors=full,all_times_state_error_bounds=full,
            residual_bounds=proof["residual_bounds"],lipschitz_phi=proof["lipschitz_phi"]))
        errors=full;current=center;previous=(record,h);clock=right
        if k%16==0:progress("PRIMARY SOURCE RESIDUAL STEP "+str(k+1)+"/"+str(len(records)))
    if clock!=end:raise ValueError("Complete source horizon required")
    return dict(steps=out,end_errors=errors,
        all_time_partitions_contiguous=True,source_semantics_validation_required=True,
        scientific_admission_allowed=False)

def cover_point(records,chain,point,vehicle,end,tolerance,budget=4096,depth=24,
                check=lambda:None,progress=lambda x:None):
    """All original steps, all evaluated parents and complete uncomputed frontier."""
    if type(budget) is not int or budget<1 or type(depth) is not int or not 0<=depth<=24:
        raise ValueError("Fixed positive call budget and depth<=24")
    end,tolerance=map(scalar,(end,tolerance))
    if end<=0 or tolerance<0:raise ValueError("Positive horizon and unchanged nonnegative tolerance")
    if type(point) is not dict or type(point.get("original_index")) is not int or type(point.get("union_index")) is not int or min(point["original_index"],point["union_index"])<0:
        raise ValueError("Full exact original point identity")
    xy=tuple(map(scalar,point["xy"]))
    if len(xy)!=2:raise ValueError("Two original coordinates")
    own=chain["steps"]
    if len(own)!=len(records) or not records:raise ValueError("Full source error chain")
    spans=[];clock=F(0)
    for k,(r,e) in enumerate(zip(records,own)):
        a,b=map(scalar,(r["start"],r["end"]))
        if a!=clock or b<=a or (scalar(e["start"]),scalar(e["end"]))!=(a,b):
            raise ValueError("Source/error time identity")
        if len(e["end_errors"])!=4 or any(scalar(v)<0 for v in e["end_errors"]):
            raise ValueError("All-time four-state tube required")
        spans.append((a,b));clock=b
    if clock!=end:raise ValueError("Complete original source horizon")
    parts=[];calls=0;flattened=[];compiled_count=0
    for k,(record,errors) in enumerate(zip(records,own)):
        check();start,stop=spans[k];h=stop-start
        compiled=None;trace=[];leaves=[];stack=[(F(0),h,0)]
        future=len(records)-k-1
        while stack:
            check();a,b,d=stack.pop()
            allowance=budget-calls-future
            if calls>=budget or allowance<1:
                leaves.append(dict(local_time=(a,b),depth=d,trace_index=None,
                    distance_squared=None,evaluations=0))
                continue
            if compiled is None:
                compiled=compile_step(xy,record["center"],record["P"],record["n"],h,
                    errors["end_errors"],vehicle["l_h"],vehicle["L"],vehicle["width"])
                compiled_count+=1;check()
            bound=evaluate_cell(compiled,a,b);check()
            index=len(trace)
            trace.append(dict(local_time=(a,b),depth=d,
                distance_squared=bound["distance_squared"],
                finite_edge_distance_squared=bound["finite_edge_distance_squared"],
                call_index=calls))
            calls+=1
            state=source_distance_decision(bound["distance_squared"],tolerance)
            if state=="unknown" and d<depth and budget-calls-future>=2:
                middle=(a+b)/2
                stack.append((middle,b,d+1));stack.append((a,middle,d+1))
            else:
                leaves.append(dict(local_time=(a,b),depth=d,trace_index=index,
                    distance_squared=bound["distance_squared"],evaluations=1))
        parts.append(dict(step_index=k,start=start,end=stop,evaluated_trace=trace,frontier=leaves))
        if k%16==0:progress("PRIMARY GEOMETRY STEP "+str(k+1)+"/"+str(len(records))+" point="+str(point["original_index"])+" calls="+str(calls))
        for leaf in leaves:
            a,b=leaf["local_time"]
            flattened.append(dict(step_index=k,time=(start+a,start+b),
                distance_squared=leaf["distance_squared"],evaluations=leaf["evaluations"]))
    summary=summarize(spans,flattened,end,tolerance,budget)
    # Reducer sees only leaves; all parent cost is authoritative separately here.
    summary["geometry_evaluations"]=calls
    return dict(point=dict(original_index=point["original_index"],union_index=point["union_index"],xy=xy),
        steps=parts,geometry_evaluations=calls,compiled_step_count=compiled_count,
        summary=summary,source_semantics_validation_required=True,
        worker_claimed_errors_ignored=True,corrected_truth_certificates=0)
