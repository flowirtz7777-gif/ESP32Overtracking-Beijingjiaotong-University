"""Full changed-point mechanism audit, not an admitted replacement truth dataset."""
from __future__ import annotations
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'src_s4_geometry_labels_20261019_v2'))
import run_labels as labels
sys.path.insert(0, str(ROOT/'src_s4_truth_remediation_20261019_v1'))
from contact_primitives import finite_face_geometry
from interval_contact import point_contact_interval, original_corner_rule
import numpy as np
import shapely

r = labels.bounded_io
DEP = labels.RUN
RUN = ROOT/'runs/resume_20261019_contact_mechanism_v1'
PROTOCOL = ROOT/'protocol_contact_mechanism_20261019_v1.json'
PLAN = ROOT/'resume_plan_20261019_v6.json'
r.RUN, r.RUN_CAP = RUN, 128*1024**2
RESERVATION = 64*1024**2
VEHICLE = labels.dep.common.Vehicle()
PARAMS = dict(length=VEHICLE.L, width=VEHICLE.width, hitch_offset=VEHICLE.l_h)

def signature():
    paths = [*SOURCE.glob('*.py'), PROTOCOL,
        *[ROOT/'src_s4_truth_remediation_20261019_v1'/name for name in
          ('contact_primitives.py','interval_contact.py','test_contact_primitives.py','test_interval_contact.py')],
        ROOT/'src_s4_geometry_labels_20261019_v2/run_labels.py',
        ROOT/'protocol_geometry_labels_20261019_v2.json',
        DEP/'source_manifest.json', DEP/'acceptance.json', DEP/'close_receipt.json',
        ROOT/'src_s4_repair_review_20261019_v1/runtime.py',
        ROOT/'src_s4_repair_review_20261019_v1/run_repair.py',
        ROOT/'src_v3/common.py', ROOT/'src_v3/geometry.py', r.AUTH/'authorization.json']
    return {p.relative_to(ROOT).as_posix():r.file_hash(p) for p in paths}

def verify():
    r.require(signature()==r.read(RUN/'source_manifest.json'), 'Mechanism source changed')
    for rel, digest in signature().items():
        r.require(r.file_hash(RUN/'source'/rel)==digest, 'Mechanism snapshot changed')
    labels.verify_sources()

def execution():
    h=r.helper()
    h.NAMES=(*h.NAMES, labels.DEPENDENCY.name, labels.FAILED.name, DEP.name)
    return h, r.execution(h, include_new=(RUN/'runner_lock.json').exists())

def specs():
    receipt=r.read(DEP/'close_receipt.json')
    accept=r.read(DEP/'acceptance.json')
    r.require(receipt['acceptance_sha256']==r.file_hash(DEP/'acceptance.json')
              and accept['checkpoint_sha256']==r.file_hash(DEP/'checkpoint.json'), 'G1 closure differs')
    result=[]
    for spec in r.read(labels.PROTOCOL)['specs']:
        folder=DEP/'cases'/spec['id']
        record=r.read(folder/'result.json')
        r.require(r.file_hash(folder/'targets.npz')==record['targets_npz_sha256'], 'G1 input changed')
        result.append({'id':spec['id'], 'reference':spec, 'folder':str(folder),
                       'targets_sha256':record['targets_npz_sha256'],
                       'result_sha256':r.file_hash(folder/'result.json')})
    r.require(len(result)==12, 'Do not cherry-pick new geometries')
    return result

def prepare():
    r.require(r.before_deadline() and not RUN.exists() and not PROTOCOL.exists() and not PLAN.exists(), 'Already prepared/cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution()
        labels.verify_sources()
        matrix=specs()
        test_runs=[]
        for folder, pattern in ((SOURCE,'test_mechanism.py'),
              (ROOT/'src_s4_truth_remediation_20261019_v1','test_*contact*.py')):
            test=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(folder),'-p',pattern,'-v'],
                                cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
            r.require(test.returncode==0,'Tests failed: '+test.stderr)
            test_runs.append({'stdout':test.stdout,'stderr':test.stderr,'pattern':pattern})
        protocol={'version':'changed-point-contact-mechanism-v1','deadline':'2026-10-19T08:00:00+08:00',
            'cases':matrix,'selection':'all edge/front/contact-existence changes; no prediction performance selection',
            'full_changed_point_arrays_no_sampling':True,'physical_contact_tolerance_m':.05,
            'existing_geometry_epsilon_m':labels.dep.geometry.GEOMETRY_EPS,
            'original_one_mm_corner_threshold_preserved':True,'interval_time_resolution_s':1e-7,
            'maximum_interval_evaluations_per_point':20000,
            'conditional_model':'piecewise-linear supplied pose; no certified ODE or physical error bound',
            'spatial_error_m':0.,'global_interval_exclusion_bound':'translation+hitch rotation+trailer corner rotation',
            'unresolved_or_budget_exhaustion_never_noncontact':True,
            'not_a_corrected_truth_population_or_any_repaired_historical_job':True,
            'no_algorithm_prediction_or_ranking':True,'workers':1,'inflight':1,
            'run_cap_bytes':r.RUN_CAP,'reservation_bytes':RESERVATION,
            'whole_E_Z_cap_bytes':r.CAP,'Z_reserve_bytes':r.RESERVE}
        plan={**r.read(ROOT/'resume_plan_20261019_v5.json'), 'version':'20261019-v6-contact-mechanism-audit',
              'previous_plan':'resume_plan_20261019_v5.json','run_directory':str(RUN),'protocol':str(PROTOCOL),
              'entrypoint':str(Path(__file__)),'corrected_truth_revalidated_prediction_jobs':0,
              'next_action':'actual worker full input admission then mechanism/conditional interval validation; keep claims withheld'}
        r.batch([(PROTOCOL,r.encoded(protocol)),(PLAN,r.encoded(plan)),
                 (RUN/'prelaunch.json',r.encoded({'time':r.now(),'mutex':mutex,'idle':idle,'tests':test_runs,
                   'resources':r.guard(RESERVATION,RESERVATION)}))])
        frozen=signature()
        r.batch([(RUN/'source_manifest.json',r.encoded(frozen))]+
                [(RUN/'source'/rel,(ROOT/rel).read_bytes()) for rel in frozen])
        active=r.read(ROOT/'active_research_run.json')
        active.update(status='contact_mechanism_registered_not_running',pid=None,plan=str(PLAN),
            run_directory=str(RUN),protocol=str(PROTOCOL),entrypoint=str(Path(__file__)),
            running_analysis=False,running_predictions=False,running_preflight=False,
            input_worker_admission_pending=True,input_worker_admitted=False,next_action=plan['next_action'])
        r.mutable(ROOT/'active_research_run.json',active)
    print('MECHANISM PREPARED: fixed all-changed-point matrix; no repaired predictions',flush=True)

def changed_ids(arrays):
    mask=((arrays['coarse_edge']!=arrays['fine_edge'])
          |(arrays['coarse_front_ignored']!=arrays['fine_front_ignored'])
          |(np.isfinite(arrays['coarse_contact_time'])!=np.isfinite(arrays['fine_contact_time'])))
    return np.flatnonzero(mask)

def load_case(spec):
    folder=Path(spec['folder'])
    r.require(r.file_hash(folder/'targets.npz')==spec['targets_sha256']
              and r.file_hash(folder/'result.json')==spec['result_sha256'], 'Frozen G1 inputs differ')
    with np.load(folder/'targets.npz',allow_pickle=False) as z:
        arrays={key:z[key] for key in z.files}
    return arrays,labels.reference_arrays(spec['reference'])

def pose_at(time, states, query):
    return np.column_stack([np.interp(np.asarray(query).reshape(-1),time,states[:,k]) for k in range(4)])

def swept_code(point, states, index):
    if index<0:
        return 0
    if index==0:
        return int(labels.dep.geometry.classify_edges(point[None,:],states[0],VEHICLE)[0])
    corners=labels.dep.common.body_corners(states[index-1:index+1],VEHICLE)
    faces=shapely.convex_hull(shapely.multipoints(np.stack([
        corners[:,pair,:].reshape(4,2) for pair in ([3,0],[0,1],[1,2],[2,3]) ])))
    distances=shapely.distance(shapely.points(point[None,:]),faces)
    return int(original_corner_rule(distances.reshape(1,4))[0])

def diagnose(spec, arrays, ref):
    ids=changed_ids(arrays)
    xy=arrays['xy'][ids]
    out={'indices':ids,'xy':xy,'old_coarse_edge':arrays['coarse_edge'][ids],
         'old_fine_edge':arrays['fine_edge'][ids]}
    for tag, step in (('coarse','005'),('fine','0025')):
        time,state=ref['time_'+step],ref['state_'+step]
        results=[]
        for point, index, expected in zip(xy,arrays[tag+'_contact_index'][ids],arrays[tag+'_edge'][ids]):
            r.require(swept_code(point,state,int(index))==int(expected),'Saved swept classifier not reproduced')
            results.append(point_contact_interval(point,time,state,**PARAMS,
                tolerance_m=.05+labels.dep.geometry.GEOMETRY_EPS))
        statuses={'noncontact':0,'contact':1,'possible_contact_unresolved':2,'unresolved_budget':3}
        out[tag+'_status']=np.array([statuses[v['status']] for v in results],np.int8)
        for key in ('lower_s','upper_s','witness_s'):
            out[tag+'_'+key]=np.array([v[key] if v[key] is not None else np.nan for v in results])
        out[tag+'_evaluations']=np.array([v['evaluations'] for v in results],np.int32)
        out[tag+'_initial_overlap']=np.array([v['initial_overlap'] for v in results],bool)
        witness=out[tag+'_witness_s']
        query=np.where(np.isfinite(witness),witness,time[0])
        pose=pose_at(time,state,query)
        distance,face=finite_face_geometry(xy,pose,**PARAMS)
        code=original_corner_rule(face)
        code[out[tag+'_status']!=1]=0
        out[tag+'_witness_pose']=pose
        out[tag+'_witness_body_distance']=distance
        out[tag+'_witness_face_distances']=face
        out[tag+'_instant_edge_at_witness']=code
    both=(out['coarse_status']==1)&(out['fine_status']==1)
    clock=np.fmax(out['coarse_witness_s'],out['fine_witness_s'])
    clock[~np.isfinite(clock)]=ref['time_005'][0]
    out['common_clock_s']=clock
    for tag,step in (('coarse','005'),('fine','0025')):
        pose=pose_at(ref['time_'+step],ref['state_'+step],clock)
        _,face=finite_face_geometry(xy,pose,**PARAMS)
        out[tag+'_common_clock_pose']=pose
        out[tag+'_common_clock_face_distances']=face
        out[tag+'_common_clock_edge']=original_corner_rule(face)
    summary={'case_id':spec['id'],'all_changed_points':len(ids),
        'original_changed_edge_points':int((out['old_coarse_edge']!=out['old_fine_edge']).sum()),
        'interval_status_disagreements':int((out['coarse_status']!=out['fine_status']).sum()),
        'unresolved_coarse':int((out['coarse_status']>=2).sum()),
        'unresolved_fine':int((out['fine_status']>=2).sum()),
        'both_verified_contact_points':int(both.sum()),
        'instantaneous_same_clock_edge_disagreements':int((both & (out['coarse_common_clock_edge']!=out['fine_common_clock_edge'])).sum()),
        'instantaneous_own_witness_edge_disagreements':int((both & (out['coarse_instant_edge_at_witness']!=out['fine_instant_edge_at_witness'])).sum()),
        'not_global_truth_certification':True,'historical_prediction_jobs_repaired':0}
    folder=RUN/'cases'/spec['id']
    blob=labels.dep.npz_blob(out)
    meta={k:{'sha256':labels.dep.common.array_hash(v),'dtype':v.dtype.str,'shape':list(v.shape)} for k,v in out.items()}
    record={'input':spec,'summary':summary,'arrays':meta,'witness_npz_sha256':r.sha(blob)}
    r.batch([(folder/'witnesses.npz',blob),(folder/'result.json',r.encoded(record))])
    return {'result_sha256':r.file_hash(folder/'result.json'),'summary':summary}

def run():
    r.require(r.before_deadline() and not (RUN/'checkpoint.json').exists(),'Already started/cutoff')
    h,_=execution()
    cp={'status':'preflight','completed':{},'new_predictions':0,'corrected_jobs':0}
    with h.exclusive() as mutex:
        _,idle=execution()
        verify()
        r.mutable(RUN/'runner_lock.json',{'status':'running','pid':os.getpid(),'time':r.now()})
        try:
            matrix=specs()
            r.require(matrix==r.read(PROTOCOL)['cases'],'Frozen matrix differs')
            loaded={spec['id']:load_case(spec) for spec in matrix}
            r.freeze(RUN/'preflight.json',r.encoded({'time':r.now(),'python':sys.executable,'root':str(ROOT),
                'source_signature':signature(),'input_cases_loaded':len(loaded),'mutex':mutex,'execution':idle,
                'loaded_modules':{m.__name__:str(Path(m.__file__).resolve()) for m in
                                  (labels.dep.common,labels.dep.geometry,sys.modules[point_contact_interval.__module__],
                                   sys.modules[finite_face_geometry.__module__])},
                'all_input_changed_point_counts':{k:len(changed_ids(v[0])) for k,v in loaded.items()},
                'resources':r.guard(RESERVATION,RESERVATION)}))
            active=r.read(ROOT/'active_research_run.json')
            active.update(status='contact_mechanism_audit_running',pid=os.getpid(),running_analysis=True,
                          running_predictions=False,running_preflight=False,input_worker_admission_pending=False,
                          input_worker_admitted=True)
            r.mutable(ROOT/'active_research_run.json',active)
            print('MECHANISM PREFLIGHT PASSED ALL 12 FULL INPUT CASES',flush=True)
            for spec in matrix:
                r.require(r.before_deadline(),'08:00 submission cutoff')
                verify()
                print('START MECHANISM '+spec['id'],flush=True)
                cp['completed'][spec['id']]=diagnose(spec,*loaded[spec['id']])
                r.checkpoint(cp)
                print('DONE MECHANISM '+json.dumps(cp['completed'][spec['id']]['summary']),flush=True)
            cp['status']='complete_pending_independent_acceptance'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure',failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN/'runner_lock.json',{'status':'stopped','pid':os.getpid(),'time':r.now()})
    print('MECHANISM EXITING; independent close still required',flush=True)

def close():
    r.require(r.before_deadline() and not (RUN/'acceptance.json').exists(),'Already closed/cutoff')
    h,_=execution()
    rows=[]
    with h.exclusive() as mutex:
        _,idle=execution()
        verify()
        cp=r.read(RUN/'checkpoint.json')
        r.require(cp['status']=='complete_pending_independent_acceptance' and len(cp['completed'])==12,'Incomplete mechanism audit')
        r.mutable(RUN/'analysis_runner_lock.json',{'status':'running','pid':os.getpid(),'time':r.now()})
        try:
            for spec in specs():
                folder=RUN/'cases'/spec['id']
                r.require(r.file_hash(folder/'result.json')==cp['completed'][spec['id']]['result_sha256'],'CP/report mismatch')
                record=r.read(folder/'result.json')
                r.require(r.file_hash(folder/'witnesses.npz')==record['witness_npz_sha256'],'Witness file differs')
                with np.load(folder/'witnesses.npz',allow_pickle=False) as z:
                    arrays={k:z[k] for k in z.files}
                r.require(set(arrays)==set(record['arrays']),'Complete witness arrays differ')
                for k,v in arrays.items():
                    r.require({'sha256':labels.dep.common.array_hash(v),'dtype':v.dtype.str,'shape':list(v.shape)}==record['arrays'][k], 'Array decode differs')
                original,_=load_case(spec)
                r.require(np.array_equal(changed_ids(original),arrays['indices']),'All changed point selection differs')
                for tag in ('coarse','fine'):
                    for suffix in ('witness','common_clock'):
                        poses=arrays[tag+'_'+('witness_pose' if suffix=='witness' else 'common_clock_pose')]
                        corners=labels.dep.common.body_corners(poses,VEHICLE)
                        points=shapely.points(arrays['xy'])
                        face=np.column_stack([shapely.distance(points,shapely.linestrings(corners[:,pair,:]))
                                               for pair in ([3,0],[0,1],[1,2],[2,3])])
                        wanted=arrays[tag+'_'+('witness_face_distances' if suffix=='witness' else 'common_clock_face_distances')]
                        r.require(np.allclose(face,wanted,rtol=0,atol=1e-10),'Independent finite-segment distances differ')
                        if suffix=='witness':
                            good=arrays[tag+'_status']==1
                            body=shapely.polygons(corners)
                            body_d=shapely.distance(points,body)
                            r.require(np.allclose(body_d,arrays[tag+'_witness_body_distance'],rtol=0,atol=1e-10),'Independent body distance differs')
                            r.require(np.all(body_d[good]<=.05+labels.dep.geometry.GEOMETRY_EPS+1e-10),'Contact witness lacks body evidence')
                r.require(record['summary']==cp['completed'][spec['id']]['summary'],'Saved summary differs')
                rows.append(record['summary'])
            acceptance={'status':'changed_point_mechanism_arrays_and_independent_geometry_checked','time':r.now(),
                'rows':rows,'all_changed_points':sum(x['all_changed_points'] for x in rows),
                'checkpoint_sha256':r.file_hash(RUN/'checkpoint.json'),'source_signature':signature(),
                'execution':idle,'mutex':mutex,'corrected_truth_revalidated_prediction_jobs':0,
                'not_full_population_relabel_or_global_truth_validation':True,'all_old_label_claims_remain_withheld':True}
            report=('# 接触标签步长敏感机制与条件区间诊断\n\n'
                '覆盖G1全部12轨迹的全部发生边/FRONT/接触存在变化点，不按算法表现选点。'
                '保持原1mm角点规则；区分整段扫掠面分类、瞬时有限面分类和统一时刻比较。'
                '区间结论仅针对给定分段线性姿态及指定空间误差界，不是已认证的连续ODE或实车真值。\n\n'
                + '\n'.join(json.dumps(x,ensure_ascii=False) for x in rows)
                + '\n\n全部未定点和预算耗尽点保留，不能当不接触。独立Shapely有限线段与车身距离复核只验证见证几何，不证明全局模型真值。'
                '旧57数据与完整细总体尚未全量修正，修正真值重验预测仍0，相关结论继续暂停。\n').encode('utf-8')
            r.batch([(RUN/'acceptance.json',r.encoded(acceptance)),
                (RUN/'acceptance.json.gz',gzip.compress(r.encoded(acceptance),mtime=0)),
                (ROOT/'reports/接触标签机制与条件区间诊断_20261019_v1.md',report)])
        finally:
            r.mutable(RUN/'analysis_runner_lock.json',{'status':'stopped','pid':os.getpid(),'time':r.now()})
    with h.exclusive() as released:
        _,after=execution()
    r.freeze(RUN/'close_receipt.json',r.encoded({'time':r.now(),'acceptance_sha256':r.file_hash(RUN/'acceptance.json'),
        'execution_after':after,'mutex_reacquired_and_released':released,'corrected_jobs':0}))
    plan={**r.read(PLAN),'version':'20261019-v7-contact-mechanism-independently-closed','previous_plan':PLAN.name,
          'next_action':'validate full correction and error bounds before full affected-population relabel and rescore'}
    r.freeze(ROOT/'resume_plan_20261019_v7.json',r.encoded(plan))
    active=r.read(ROOT/'active_research_run.json')
    active.update(status='contact_mechanism_independently_closed_not_running',pid=None,plan=str(ROOT/'resume_plan_20261019_v7.json'),
                  running_analysis=False,running_predictions=False,running_preflight=False,next_action=plan['next_action'])
    r.mutable(ROOT/'active_research_run.json',active)
    print(json.dumps({'closed':True,'changed_points':acceptance['all_changed_points'],'corrected_jobs':0}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','run','close'))
    globals()[parser.parse_args().action]()
