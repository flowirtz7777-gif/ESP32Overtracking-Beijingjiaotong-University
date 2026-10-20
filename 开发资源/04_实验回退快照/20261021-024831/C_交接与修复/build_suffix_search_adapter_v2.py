"""New frozen search adapter reuses complete accepted refinement/face checker without ancestor edits."""
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_unwitnessed_probe_merge_20261022_v1'))
import probe_merge_driver as parent
r=parent.r
SOURCE=ROOT/'src_s4_suffix_witness_search_20261022_v2'
DEV=parent.AUTH/'runtime_sessions/suffix_witness_search_development_tests_v2'


def replace_function(text,name,replacement):
    start=text.index('\ndef '+name+'(')+1
    end=text.find('\ndef ',start+1)
    if end<0: end=len(text)
    return text[:start]+replacement.strip()+'\n\n'+text[end:]


def core_source():
    source=(ROOT/'src_s4_unwitnessed_probe_20261022_v1/probe_core.py').read_text(encoding='utf-8')
    source=source.replace('FORWARD_STEPS = 64','FORWARD_STEPS = 256')
    source=source.replace('import local_motion_core as motion','import local_motion_core as motion\nimport search_control as suffix')
    # Preserve the exact legacy refinement and full-bracket finite-face/Decimal70 checks.
    begin=source.index('\ndef empty_trace(')+1; finish=source.index('\ndef distances(',begin)
    old_empty=source[begin:finish].replace('def empty_trace(','def legacy_empty_trace(',1)
    new_empty=r'''
def empty_trace(n,chosen):
    trace=legacy_empty_trace(n,chosen)
    del trace['search_reached_horizon_without_witness']
    for key in suffix.FLOAT_FIELDS:
        trace['search__'+key]=np.full((n,FORWARD_STEPS),np.nan)
    for key in suffix.INT_FIELDS:
        trace['search__'+key]=np.zeros((n,FORWARD_STEPS),np.int32)
    trace['suffix_initial_witness_upper_s']=np.full(n,np.nan)
    trace['suffix_query_budget']=np.zeros(n,np.int32)
    for key in ('suffix_resolution_unresolved','suffix_strict_predicate_pruned','suffix_not_noncontact_or_earliest'):
        trace[key]=np.zeros(n,bool)
    return trace
'''
    source=source[:begin]+old_empty+'\n'+new_empty+'\n'+source[finish:]
    start=source.index('\ndef candidate(')+1; end=source.index('\ndef independent_check(',start)
    old_candidate=source[start:end]
    refine=old_candidate[old_candidate.index('    for j in range(REFINE_STEPS):'):]
    new_candidate=r'''
def candidate(xy,time,states,original,error,vehicle,geometry):
    chosen=validate(xy,time,states,original,error,vehicle)
    n=len(chosen)
    out={k:v.copy() for k,v in original.items()}
    trace=empty_trace(n,chosen)
    variation=motion.segment_variation(time,states,vehicle)
    low=original['contact_lower_s'].copy()
    high=np.full(n,np.nan)
    def one(point,pose,v):
        body,faces=geometry(point.reshape(1,2),pose.reshape(1,4))
        return float(body[0]),faces[0]
    for i in np.flatnonzero(chosen):
        result=suffix.search(xy[i],time,states,float(low[i]),error,vehicle,one,
            variation=variation,budget=FORWARD_STEPS)
        count=len(result['query_s'])
        trace['forward_evaluations'][i]=count
        trace['forward_time_s'][i,:count]=result['query_s']
        trace['forward_body_distance_m'][i,:count]=result['body_distance_m']
        trace['forward_witness'][i,:count]=result['node_status']==suffix.WITNESS
        trace['last_forward_probe_s'][i]=result['query_s'][-1]
        trace['forward_budget_exhausted'][i]=result['independent_budget_exhausted'][0]
        trace['suffix_resolution_unresolved'][i]=result['resolution_unresolved'][0]
        trace['suffix_strict_predicate_pruned'][i]=result['strict_predicate_suffix_pruned'][0]
        trace['suffix_not_noncontact_or_earliest'][i]=result['not_a_noncontact_or_global_earliest_proof'][0]
        trace['suffix_query_budget'][i]=result['query_budget'][0]
        high[i]=result['candidate_upper_s'][0]
        trace['suffix_initial_witness_upper_s'][i]=high[i]
        for key in suffix.FLOAT_FIELDS+suffix.INT_FIELDS:
            trace['search__'+key][i,:count]=result[key]
    found=np.isfinite(high)
    trace['found_strict_witness']=found.copy()
    internal_low=low.copy()
'''
    source=source[:start]+new_candidate.strip()+'\n'+refine+'\n'+source[end:]
    start=source.index('        horizon = float(time[-1])',source.index('def independent_check('))
    end=source.index('        for prefix, total, used in ',start)
    checker=r'''
        count=int(trace['forward_evaluations'][i])
        if not 1<=count<=FORWARD_STEPS or not trace['selected_unwitnessed'][i]:
            raise ValueError('Every still-unwitnessed row requires its full bounded suffix search')
        saved={key:trace['search__'+key][i,:count].copy() for key in suffix.FLOAT_FIELDS+suffix.INT_FIELDS}
        saved.update(candidate_upper_s=trace['suffix_initial_witness_upper_s'][i:i+1].copy(),
            scientific_lower_s=np.asarray([lower],np.float64),query_budget=trace['suffix_query_budget'][i:i+1].copy(),
            independent_budget_exhausted=trace['forward_budget_exhausted'][i:i+1].copy(),
            resolution_unresolved=trace['suffix_resolution_unresolved'][i:i+1].copy(),
            strict_predicate_suffix_pruned=trace['suffix_strict_predicate_pruned'][i:i+1].copy(),
            not_a_noncontact_or_global_earliest_proof=trace['suffix_not_noncontact_or_earliest'][i:i+1].copy())
        if saved['query_budget'][0]!=FORWARD_STEPS:
            raise ValueError('The frozen independent query budget must remain exact')
        suffix.independently_check(xy[i],time,states,lower,error,vehicle,saved,geos,variation=variation)
        for key in suffix.FLOAT_FIELDS+suffix.INT_FIELDS:
            if not same(trace['search__'+key][i,count:],schema['search__'+key][i,count:]):
                raise ValueError('Every unused two-dimensional suffix slot must keep exact padding')
        if (not same(trace['forward_time_s'][i,:count],saved['query_s'])
            or not same(trace['forward_body_distance_m'][i,:count],saved['body_distance_m'])
            or not np.array_equal(trace['forward_witness'][i,:count],saved['node_status']==suffix.WITNESS)
            or trace['last_forward_probe_s'][i]!=saved['query_s'][-1]):
            raise ValueError('Every query and exact alias trace must bind')
        high=float(saved['candidate_upper_s'][0])
        found=math.isfinite(high)
        if bool(trace['found_strict_witness'][i])!=found:
            raise ValueError('Only an actual accepted strict suffix witness may set found')
        queries+=count
'''
    source=source[:start]+checker+source[end:]
    source=source.replace('"no_global_earliest_or_exhaustive_search_claim": True}',
        '"no_global_earliest_or_exhaustive_search_claim": True, "complete_suffix_control_budget_and_frontier_checked": True}')
    compile(source,'search_core.py','exec')
    return source.encode('utf-8')


def main():
    r.require(r.before_deadline() and not SOURCE.exists() and not DEV.exists(),'Version used or cutoff')
    h,_=parent.execution()
    with h.exclusive() as mutex:
        _,idle=parent.execution()
        base_tests=(HERE/'test_suffix_search_v1.py').read_text(encoding='utf-8').replace('import suffix_search_core as c','import search_control as c')
        # The tests explicitly place the preserved v1 search core on sys.path for staging.
        base_tests=base_tests.replace("sys.path.insert(0,str(ROOT/'src_s4_local_motion_20261022_v2'))",
            "sys.path.insert(0,str(ROOT/'src_s4_suffix_witness_search_20261022_v1'))\n"
            "sys.path.insert(0,str(ROOT/'src_s4_local_motion_20261022_v2'))")
        files={'search_control.py':(HERE/'search_control_v2.py').read_bytes(),'search_core.py':core_source(),
            'test_search_control.py':base_tests.encode('utf-8'),
            'test_search_adapter.py':(HERE/'test_search_adapter_v2.py').read_bytes()}
        stage=HERE/'suffix_search_staging_v2'; stage.mkdir(exist_ok=False)
        for name,blob in files.items(): (stage/name).write_bytes(blob)
        results=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(stage),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        r.batch([(DEV/'builder_source.py',Path(__file__).read_bytes()),
            (DEV/'result.json',r.encoded(dict(time=r.now(),returncode=results.returncode,stdout=results.stdout,
                stderr=results.stderr,execution=idle,mutex=mutex,pure_synthetic_only=True,
                original_v1_preserved=True,final_refinement_and_full_bracket_decimal70_checks_reused=True)))]
            +[(DEV/name,blob) for name,blob in files.items()])
        print(results.stderr,flush=True)
        r.require(results.returncode==0,'Synthetic failure preserved; no real driver or worker')
        r.batch([(SOURCE/name,blob) for name,blob in files.items()])
    print('V2 FULL TRACE ADAPTER AND CONTROL FROZEN; REAL DRIVER/PREPARE/RUN/CLOSE STILL NOT USED',flush=True)


if __name__=='__main__': main()
