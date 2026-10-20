"""Versioned all-baseline-point conditional truth assets, not repaired scores."""
from __future__ import annotations
import argparse
import dataclasses
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
sys.path.insert(0,str(ROOT/'src_s4_repair_review_20261019_v1'))
import runtime as r
from population import label_population,common,finite_face_geometry,interval_candidates
from reference import independent_reference,combine,maneuver_for
from interval_contact import motion_bound,original_corner_rule
import numpy as np
import shapely

RUN=ROOT/'runs/resume_20261019_interval_population_v1'
PROTOCOL=ROOT/'protocol_interval_population_20261019_v1.json'
PLAN=ROOT/'resume_plan_20261019_v8.json'
DEPENDENCY=ROOT/'runs/resume_20261019_contact_mechanism_v1'
PARTITIONS={'development':(9,35000),'development_v2':(9,35000),
            'development_v2_n70000':(27,70000),'selection_v2':(12,70000)}
E_ROOT=Path('E:/大创内轮差项目/工具/转弯全过程盲区分析软件/科研实验_2026-10-14')
RESERVATION=480*1024**2
TIME_RESOLUTION=1e-7
EVALUATIONS=2048
TOLERANCE=.050000001


def scan_size(root):
    stack=[Path(root)]
    total=0
    while stack:
        folder=stack.pop()
        if not folder.exists():
            continue
        with os.scandir(folder) as entries:
            for item in entries:
                if item.is_dir(follow_symlinks=False):
                    stack.append(Path(item.path))
                elif item.is_file(follow_symlinks=False):
                    total+=item.stat(follow_symlinks=False).st_size
                else:
                    raise RuntimeError('Nonregular research asset: '+item.path)
    return total


r.RUN,r.RUN_CAP,r.tree_bytes=RUN,512*1024**2,scan_size


def signature():
    paths=[*SOURCE.glob('*.py'),PROTOCOL,*sorted((ROOT/'src_v3').glob('*.py')),
        ROOT/'src_s4_repair_review_20261019_v1/runtime.py',r.AUTH/'authorization.json',
        ROOT/'管理脚本/launch_interval_population_20261019_v1.py',
        *[ROOT/'src_s4_truth_remediation_20261019_v1'/p for p in
          ('contact_primitives.py','interval_contact.py','test_contact_primitives.py','test_interval_contact.py')],
        *[DEPENDENCY/p for p in ('source_manifest.json','acceptance.json','close_receipt.json')],
        ROOT/'runs/truth_label_dependency_resolution_20261019_v1/dependency_resolution.json',
        ROOT/'research_validity_overlay_20261019_v3.json']
    return {p.relative_to(ROOT).as_posix():r.file_hash(p) for p in sorted(paths)}


def verify():
    expected=r.read(RUN/'source_manifest.json')
    r.require(signature()==expected,'Population-stage source changed')
    for rel,digest in expected.items():
        r.require(r.file_hash(RUN/'source'/rel)==digest,'Population source snapshot changed')


def execution():
    h=r.helper()
    names=('resume_20261019_geometry_delay_recovery_v1','resume_20261019_geometry_labels_v1',
           'resume_20261019_geometry_labels_v2',DEPENDENCY.name)
    h.NAMES=(*h.NAMES,*names)
    evidence=r.execution(h,include_new=(RUN/'runner_lock.json').exists())
    for name in names:
        for p in (ROOT/'runs'/name).glob('*runner_lock.json'):
            r.require(r.read(p)['status']=='stopped','Dependency analysis lock busy')
            evidence['all_runner_and_analysis_locks'][str(p)]={'sha256':r.file_hash(p),'value':r.read(p)}
    return h,evidence


def specifications():
    rows=[]
    for partition,(number,count) in PARTITIONS.items():
        manifests=sorted((ROOT/'datasets'/partition).glob('*/manifest.json'))
        r.require(len(manifests)==number,'Frozen dataset partition differs')
        for path in manifests:
            manifest=r.read(path)
            r.require(manifest['target_count']==count,'Frozen count differs')
            files={'manifest.json':r.file_hash(path),**manifest['files']}
            mirrors=[]
            for root in (ROOT,E_ROOT):
                folder=root/path.parent.relative_to(ROOT)
                r.require(folder.is_dir(),'Original mirror missing')
                for filename,digest in files.items():
                    r.require(r.file_hash(folder/filename)==digest,'Original E/Z input differs')
                mirrors.append(str(folder))
            rows.append({'id':partition+'/'+path.parent.name,'count':count,
                         'folder':str(path.parent),'files':files,'mirrors':mirrors})
    r.require(len(rows)==57,'Whole baseline matrix required')
    receipt=r.read(DEPENDENCY/'close_receipt.json')
    r.require(receipt['acceptance_sha256']==r.file_hash(DEPENDENCY/'acceptance.json'),'Mechanism closure differs')
    r.require(r.read(DEPENDENCY/'acceptance.json')['checkpoint_sha256']==r.file_hash(DEPENDENCY/'checkpoint.json'),
              'Mechanism closed checkpoint differs')
    return rows


def load_inputs(matrix):
    loaded={}
    groups={}
    for spec in matrix:
        folder=Path(spec['folder'])
        for mirror in spec['mirrors']:
            for filename,digest in spec['files'].items():
                r.require(r.file_hash(Path(mirror)/filename)==digest,'Worker input changed')
        with np.load(folder/'targets.npz',allow_pickle=False) as z:
            target={k:z[k] for k in z.files}
        with np.load(folder/'trajectory.npz',allow_pickle=False) as z:
            trajectory={k:z[k] for k in z.files}
        profile=r.read(folder/'profile.json')
        xy=target['xy']
        r.require(xy.shape==(spec['count'],2) and np.isfinite(xy).all()
                  and len(np.unique(xy,axis=0))==len(xy),'All original unique coordinates required')
        manifest=r.read(folder/'manifest.json')
        r.require(common.array_hash(xy)==manifest['target_coordinates_sha256'],'Frozen coordinate array SHA differs')
        r.require(set(target)=={'xy','group','contact_time','contact_index','edge','front_ignored'},'Target contract differs')
        r.require(all(len(v)==len(xy) for v in target.values()),'Full old labels required')
        r.require(set(trajectory)>={'fine_time','fine_state','time','state','alpha'},'Original full reference missing')
        maneuver,vehicle=maneuver_for(profile)
        control=dataclasses.asdict(maneuver)
        r.require(control==profile['control'],'Control reconstruction differs')
        r.require(np.allclose(maneuver.alpha(trajectory['time']),trajectory['alpha'],rtol=0,atol=1e-13),
                  'Original controls differ')
        r.require(trajectory['fine_state'].shape==(len(trajectory['fine_time']),4)
                  and np.isfinite(trajectory['fine_state']).all()
                  and np.all(np.diff(trajectory['fine_time'])>0),'Invalid complete reference')
        key=r.sha(r.encoded({'time':common.array_hash(trajectory['fine_time']),
            'state':common.array_hash(trajectory['fine_state']),'control':control,'vehicle':profile['vehicle']}))
        loaded[spec['id']]={'spec':spec,'target':target,'trajectory':trajectory,'profile':profile,'group':key}
        groups.setdefault(key,[]).append(spec['id'])
    return loaded,groups


def array_meta(arrays):
    return {k:{'sha256':common.array_hash(v),'dtype':v.dtype.str,'shape':list(v.shape)} for k,v in arrays.items()}


def npz_bytes(arrays):
    stream=io.BytesIO()
    np.savez_compressed(stream,**arrays)
    blob=stream.getvalue()
    with np.load(io.BytesIO(blob),allow_pickle=False) as decoded:
        r.require(set(decoded.files)==set(arrays),'NPZ keys differ')
        r.require(array_meta({k:decoded[k] for k in decoded.files})==array_meta(arrays),'Full NPZ roundtrip differs')
    return blob


def save_arrays(folder,arrays,record):
    blob=npz_bytes(arrays)
    record={**record,'arrays':array_meta(arrays),'npz_sha256':r.sha(blob)}
    r.batch([(folder/'arrays.npz',blob),(folder/'result.json',r.encoded(record))])
    return {'result_sha256':r.file_hash(folder/'result.json'),'summary':record.get('summary')}


def read_arrays(folder):
    record=r.read(folder/'result.json')
    r.require(r.file_hash(folder/'arrays.npz')==record['npz_sha256'],'NPZ file differs')
    with np.load(folder/'arrays.npz',allow_pickle=False) as z:
        arrays={k:z[k] for k in z.files}
    r.require(array_meta(arrays)==record['arrays'],'Complete decoded arrays differ')
    return arrays,record


def old_discrepancies(target,combined):
    old_contact=np.isfinite(target['contact_time'])
    status=combined['contact_status']
    bits=combined['possible_edge_codes']
    known=status<2
    edge=np.left_shift(np.uint16(1),np.maximum(target['edge'].astype(np.int32)-1,0).astype(np.uint16))
    edge_difference=known & old_contact & ((bits&edge)==0)
    existence=known & (old_contact!=(status==1))
    timing=(status==1)&old_contact&((target['contact_time']<combined['contact_lower_s']-1e-10)
            |(target['contact_time']>combined['contact_upper_s']+1e-10))
    return {'old_existence_incompatible':existence,'old_edge_incompatible':edge_difference,
            'old_time_outside_new_interval':timing,'all_undetermined':status>=2,
            'all_model_conflicts':combined['model_conflict']}


def prepare():
    r.require(r.before_deadline() and not RUN.exists() and not PROTOCOL.exists() and not PLAN.exists(),
              'Already prepared or cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution()
        matrix=specifications()
        tests=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(SOURCE),'-p','test_*.py','-v'],
             cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        r.require(tests.returncode==0,'Population tests failed: '+tests.stderr)
        protocol={'version':'all-baseline-conditional-interval-assets-v1','matrix':matrix,
            'baseline_dataset_files':57,'baseline_point_records':3360000,'tolerance_m':TOLERANCE,
            'corner_rule_m':.001,'instantaneous_finite_faces_not_old_swept_face_semantics':True,
            'time_resolution_s':TIME_RESOLUTION,'maximum_per_point_interval_evaluations':EVALUATIONS,
            'spatial_envelope':'max(all-old-corner-vs-DOP853,dual-DOP853-disagreement)+1e-7 plus acceleration*h^2/8 plus pose-chord bound',
            'reference':'original RK4 .005 and independent DOP853 sampled .0025; secondary independent solver tolerance/maxstep',
            'not_formally_certified_ODE_error_bound':True,'unknown_and_budget_never_noncontact_or_excluded':True,
            'combine':'union intervals and edge sets; definite only if both; retain every conflict',
            'no_algorithm_prediction_or_score_repair':True,'corrected_truth_revalidated_prediction_jobs':0,
            'expanded_coarse_fine_counterexamples_still_require_subsequent_full_relabel':True,
            'deadline':'2026-10-19T08:00:00+08:00','workers':1,'inflight':1,
            'run_cap_bytes':r.RUN_CAP,'reservation_bytes':RESERVATION,'total_E_Z_cap_bytes':r.CAP,'Z_reserve_bytes':r.RESERVE}
        plan={**r.read(ROOT/'resume_plan_20261019_v7.json'),'version':'20261019-v8-all-baseline-interval-assets',
            'previous_plan':'resume_plan_20261019_v7.json','run_directory':str(RUN),'protocol':str(PROTOCOL),
            'entrypoint':str(Path(__file__)),'corrected_truth_revalidated_prediction_jobs':0,
            'next_action':'worker full 57-dataset admission then conditional all-point asset generation; no rescore until independently checked'}
        r.batch([(PROTOCOL,r.encoded(protocol)),(PLAN,r.encoded(plan)),
                 (RUN/'prelaunch.json',r.encoded({'time':r.now(),'mutex':mutex,'idle':idle,
                     'test_stdout':tests.stdout,'test_stderr':tests.stderr,'resources':r.guard(RESERVATION,RESERVATION)}))])
        frozen=signature()
        r.batch([(RUN/'source_manifest.json',r.encoded(frozen))]+
                [(RUN/'source'/rel,(ROOT/rel).read_bytes()) for rel in frozen])
        active=r.read(ROOT/'active_research_run.json')
        active.update(status='interval_population_prepared_not_running',pid=None,plan=str(PLAN),
            run_directory=str(RUN),protocol=str(PROTOCOL),entrypoint=str(Path(__file__)),
            running_analysis=False,running_predictions=False,running_preflight=False,
            input_worker_admission_pending=True,input_worker_admitted=False,next_action=plan['next_action'])
        r.mutable(ROOT/'active_research_run.json',active)
    print('ALL-POINT POPULATION PREPARED; real worker admission still required',flush=True)


def process_group(key,ids,loaded):
    first=loaded[ids[0]]
    all_xy=np.concatenate([loaded[i]['target']['xy'] for i in ids])
    xy,inverse=np.unique(all_xy,axis=0,return_inverse=True)
    old=first['trajectory']
    reference,meta=independent_reference(first['profile'],old['fine_time'],old['fine_state'])
    vehicle=common.Vehicle(**first['profile']['vehicle'])
    outputs={}
    for tag,time,state,error in (('oldpath',old['fine_time'],old['fine_state'],meta['old_path_spatial_envelope_m']),
                               ('independent',reference['time'],reference['state'],meta['independent_path_spatial_envelope_m'])):
        print('START PATH '+key+' '+tag+' '+str(len(xy)),flush=True)
        arrays=label_population(xy,time,state,vehicle=vehicle,spatial_error_m=error,tolerance_m=TOLERANCE,
            time_resolution_s=TIME_RESOLUTION,max_evaluations_per_interval=EVALUATIONS,
            progress=lambda k,n,w:print('PATH PROGRESS '+tag+' '+str(k)+'/'+str(n)+' witnesses='+str(w),flush=True))
        arrays.pop('witness_pose')
        outputs[tag]=arrays
    combined=combine(outputs['oldpath'],outputs['independent'])
    full={'xy':xy,'independent_time':reference['time'],'independent_state':reference['state'],
          'secondary_state':reference['secondary_state']}
    for tag,arrays in (*outputs.items(),('combined',combined)):
        full.update({tag+'__'+k:v for k,v in arrays.items()})
    group_summary={'unique_coordinates':len(xy),'model_conflicts':int(combined['model_conflict'].sum()),
        'undetermined':int((combined['contact_status']>=2).sum()),'budget_points':int((combined['contact_status']==3).sum())}
    group_record=save_arrays(RUN/'groups'/key,full,{'ids':ids,'reference_meta':meta,'summary':group_summary,
                              'old_reference_input':first['spec'],'profile':first['profile']})
    reports={}
    offset=0
    for dataset_id in ids:
        item=loaded[dataset_id]
        n=len(item['target']['xy'])
        projection=inverse[offset:offset+n]
        offset+=n
        r.require(np.array_equal(xy[projection],item['target']['xy']),'Exact original coordinate projection differs')
        projected={k:v[projection] for k,v in combined.items()}
        masks=old_discrepancies(item['target'],projected)
        out={'union_index':projection.astype(np.int32)}
        out.update({'combined__'+k:v for k,v in projected.items()})
        out.update({k+'__packbits':np.packbits(v,bitorder='little') for k,v in masks.items()})
        summary={'dataset_id':dataset_id,'points':n,'contact_certain':int((projected['contact_status']==1).sum()),
            'noncontact_certain':int((projected['contact_status']==0).sum()),
            **{k:int(v.sum()) for k,v in masks.items()},'corrected_prediction_jobs':0}
        reports[dataset_id]=save_arrays(RUN/'datasets'/dataset_id,out,
            {'input':item['spec'],'group':key,'original_xy_sha256':common.array_hash(item['target']['xy']),
             'summary':summary,'mask_length':n,'bitorder':'little'})
        print('DONE DATASET '+json.dumps(summary),flush=True)
    return {'group':group_record,'datasets':reports}


def run():
    r.require(r.before_deadline() and not (RUN/'checkpoint.json').exists(),'Already started or cutoff')
    h,_=execution()
    cp={'status':'preflight','completed':{},'new_predictions':0,'corrected_prediction_jobs':0,
        'source_signature':signature(),'protocol_sha256':r.file_hash(PROTOCOL)}
    with h.exclusive() as mutex:
        _,idle=execution()
        verify()
        r.mutable(RUN/'runner_lock.json',{'status':'running','pid':os.getpid(),'time':r.now()})
        try:
            matrix=specifications()
            r.require(matrix==r.read(PROTOCOL)['matrix'],'Frozen 57-case matrix differs')
            loaded,groups=load_inputs(matrix)
            r.freeze(RUN/'preflight.json',r.encoded({'time':r.now(),'python':sys.executable,'root':str(ROOT),
                'source_signature':signature(),'loaded_datasets':57,'point_records':sum(v['spec']['count'] for v in loaded.values()),
                'groups':groups,'all_array_sha256':{k:{'target':array_meta(v['target']),
                       'trajectory':array_meta(v['trajectory'])} for k,v in loaded.items()},
                'loaded_modules':{m.__name__:str(Path(m.__file__).resolve()) for m in
                    (sys.modules[label_population.__module__],sys.modules[independent_reference.__module__],
                     sys.modules[finite_face_geometry.__module__],common,sys.modules['scenarios'])},
                'BLAS':{k:os.environ[k] for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
                'execution':idle,'mutex':mutex,'resources':r.guard(RESERVATION,RESERVATION)}))
            active=r.read(ROOT/'active_research_run.json')
            active.update(status='interval_population_running',pid=os.getpid(),running_analysis=True,
                running_predictions=False,running_preflight=False,input_worker_admission_pending=False,input_worker_admitted=True)
            r.mutable(ROOT/'active_research_run.json',active)
            print('POPULATION PREFLIGHT PASSED ALL 57 COMPLETE BASELINE DATASETS',flush=True)
            for key,ids in groups.items():
                r.require(r.before_deadline(),'08:00 group submission cutoff')
                verify()
                remaining=max(0,RESERVATION-scan_size(RUN))
                r.guard(remaining,remaining)
                print('START FULL POPULATION GROUP '+key+' '+json.dumps(ids),flush=True)
                cp['completed'][key]=process_group(key,ids,loaded)
                r.checkpoint(cp)
            cp['status']='complete_pending_independent_acceptance'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline',failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN/'runner_lock.json',{'status':'stopped','pid':os.getpid(),'time':r.now()})
    print('POPULATION WORKER EXITING; independent close still required',flush=True)


def independent_GE0S_exclusion(points,time,states,error,vehicle):
    """Check every broad-phase candidate using GEOS distances and distance bounds."""
    if not len(points):
        return 0
    hulls,curve=interval_candidates(states,vehicle)
    speeds=motion_bound(states,time,length=vehicle.L,width=vehicle.width,hitch_offset=vehicle.l_h)
    tree=shapely.STRtree(shapely.points(points))
    checked=0
    for k,hull in enumerate(hulls):
        ids=tree.query(hull,predicate='dwithin',distance=TOLERANCE+error+curve[k]+1e-12)
        if not len(ids):
            continue
        checked+=len(ids)
        stack=[(ids,0.,1.,0)]
        while stack:
            selected,a,b,depth=stack.pop()
            middle=(a+b)/2
            pose=states[k]+middle*(states[k+1]-states[k])
            polygon=shapely.polygons(common.body_corners(pose[None,:],vehicle)[0])
            d=shapely.distance(shapely.points(points[selected]),polygon)
            potential=d-error-speeds[k]*(b-a)*(time[k+1]-time[k])/2-1e-12<=TOLERANCE
            selected=selected[potential]
            if not len(selected):
                continue
            r.require(depth<28 and (b-a)*(time[k+1]-time[k])>TIME_RESOLUTION,
                      'Independent GEOS exclusion cannot certify saved noncontact')
            stack.append((selected,middle,b,depth+1))
            stack.append((selected,a,middle,depth+1))
    return checked


def validate_path(xy,time,states,arrays,error,vehicle):
    status=arrays['contact_status']
    lower,upper=arrays['contact_lower_s'],arrays['contact_upper_s']
    r.require(np.isin(status,[0,1,2,3]).all() and not np.any((status==0)&np.isfinite(lower)),'Invalid contact status')
    good=np.isfinite(upper)
    r.require(np.all(np.isfinite(lower[good])) and np.all(lower[good]<=upper[good]),'Invalid time bracket')
    ids=np.flatnonzero(good)
    pose=np.column_stack([np.interp(upper[ids],time,states[:,j]) for j in range(4)])
    corners=common.body_corners(pose,vehicle)
    points=shapely.points(xy[ids])
    body_distance=shapely.distance(points,shapely.polygons(corners))
    r.require(np.all(body_distance+error<=TOLERANCE+1e-10),'Independent witness not inside error envelope')
    _,analytic=finite_face_geometry(xy[ids],pose,length=vehicle.L,width=vehicle.width,hitch_offset=vehicle.l_h)
    face=np.column_stack([shapely.distance(points,shapely.linestrings(corners[:,pair,:]))
                          for pair in ([3,0],[0,1],[1,2],[2,3])])
    r.require(np.allclose(face,analytic,rtol=0,atol=1e-10),'GEOS finite-face distances differ')
    middle=(lower[ids]+upper[ids])/2
    midpoint_pose=np.column_stack([np.interp(middle,time,states[:,j]) for j in range(4)])
    midpoint_corners=common.body_corners(midpoint_pose,vehicle)
    midpoint_face=np.column_stack([shapely.distance(points,shapely.linestrings(midpoint_corners[:,pair,:]))
                                  for pair in ([3,0],[0,1],[1,2],[2,3])])
    nominal=original_corner_rule(midpoint_face)
    r.require(np.array_equal(nominal,arrays['nominal_instantaneous_edge'][ids]),'GEOS midpoint nominal edge differs')
    speed=motion_bound(states,time,length=vehicle.L,width=vehicle.width,hitch_offset=vehicle.l_h)
    envelope=error+float(speed.max())*(upper[ids]-lower[ids])/2
    ordered=np.sort(midpoint_face,axis=1)
    order=np.sort(np.argsort(midpoint_face,axis=1)[:,:2],axis=1)
    adjacent=np.zeros(len(ids),bool)
    for pair in ((0,1),(1,2),(0,3),(2,3)):
        adjacent|=np.all(order==pair,axis=1)
    single=ordered[:,1]-ordered[:,0]-2*envelope>.001
    corner=(ordered[:,1]-ordered[:,0]+2*envelope<.001)&(ordered[:,2]-ordered[:,1]>2*envelope)&adjacent
    stable=(single|corner)&~arrays['budget_exhausted'][ids]
    r.require(np.array_equal(stable,arrays['edge_certain'][ids]),'Independent edge confidence differs')
    expected_bits=np.full(len(ids),255,np.uint16)
    expected_bits[stable]=np.left_shift(np.uint16(1),nominal[stable].astype(np.uint16)-1)
    r.require(np.array_equal(expected_bits,arrays['possible_edge_codes'][ids]),'Independent edge candidate sets differ')
    r.require(np.all(arrays['possible_edge_codes'][status>=2]==255),'Unknown edge possibilities lost')
    noncontact=xy[status==0]
    checked=independent_GE0S_exclusion(noncontact,time,states,error,vehicle)
    return {'full_witnesses_GE0S_checked':len(ids),'noncontact_points_checked':len(noncontact),
            'noncontact_candidate_interval_pairs_GE0S_checked':checked}


def close():
    r.require(r.before_deadline() and not (RUN/'acceptance.json').exists(),'Already accepted or cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution()
        verify()
        cp=r.read(RUN/'checkpoint.json')
        r.require(cp['status']=='complete_pending_independent_acceptance','Population incomplete')
        matrix=specifications()
        loaded,groups=load_inputs(matrix)
        r.require(set(cp['completed'])==set(groups),'Incomplete group matrix')
        r.mutable(RUN/'analysis_runner_lock.json',{'status':'running','pid':os.getpid(),'time':r.now()})
        rows=[]
        geometry_checks={}
        try:
            for key,ids in groups.items():
                arrays,record=read_arrays(RUN/'groups'/key)
                r.require(r.file_hash(RUN/'groups'/key/'result.json')==cp['completed'][key]['group']['result_sha256'],
                          'Group checkpoint differs')
                xy=arrays['xy']
                first=loaded[ids[0]]
                old=first['trajectory']
                vehicle=common.Vehicle(**first['profile']['vehicle'])
                paths={tag:{k.split('__',1)[1]:v for k,v in arrays.items() if k.startswith(tag+'__')}
                       for tag in ('oldpath','independent')}
                recombined=combine(paths['oldpath'],paths['independent'])
                r.require(array_meta(recombined)==array_meta({k.split('__',1)[1]:v for k,v in arrays.items()
                    if k.startswith('combined__')}),'Paired interval combination differs')
                geometry_checks[key]={}
                for tag,time,state,error in (
                    ('oldpath',old['fine_time'],old['fine_state'],record['reference_meta']['old_path_spatial_envelope_m']),
                    ('independent',arrays['independent_time'],arrays['independent_state'],record['reference_meta']['independent_path_spatial_envelope_m'])):
                    geometry_checks[key][tag]=validate_path(xy,time,state,paths[tag],error,vehicle)
                for dataset_id in ids:
                    out,meta=read_arrays(RUN/'datasets'/dataset_id)
                    r.require(r.file_hash(RUN/'datasets'/dataset_id/'result.json')==cp['completed'][key]['datasets'][dataset_id]['result_sha256'],
                              'Dataset checkpoint differs')
                    target=loaded[dataset_id]['target']
                    index=out['union_index']
                    r.require(np.array_equal(xy[index],target['xy']),'Original coordinate order not preserved')
                    projection={k:v[index] for k,v in recombined.items()}
                    r.require(array_meta(projection)==array_meta({k.split('__',1)[1]:v for k,v in out.items()
                        if k.startswith('combined__')}),'Full original point projection differs')
                    masks=old_discrepancies(target,projection)
                    for name,mask in masks.items():
                        r.require(np.array_equal(np.unpackbits(out[name+'__packbits'],bitorder='little',count=len(index)),mask),
                                  'Full change/unknown/conflict indices differ')
                        r.require(meta['summary'][name]==int(mask.sum()),'Recomputed mask count differs')
                    rows.append(meta['summary'])
                print('ACCEPTED CONDITIONAL GROUP '+key,flush=True)
            acceptance={'time':r.now(),'status':'all_57_conditional_interval_assets_decoded_and_GE0S_checked',
                'rows':rows,'geometry_checks':geometry_checks,'checkpoint_sha256':r.file_hash(RUN/'checkpoint.json'),
                'source_signature':signature(),'execution':idle,'mutex':mutex,
                'corrected_truth_revalidated_prediction_jobs':0,'expanded_populations_and_rescores_still_pending':True,
                'conditional_empirical_reference_not_certified_ODE_truth':True,
                'all_label_dependent_historical_claims_remain_withheld':True}
            r.batch([(RUN/'acceptance.json',r.encoded(acceptance)),
                (RUN/'acceptance.json.gz',gzip.compress(r.encoded(acceptance),mtime=0))])
        finally:
            r.mutable(RUN/'analysis_runner_lock.json',{'status':'stopped','pid':os.getpid(),'time':r.now()})
    with h.exclusive() as released:
        _,after=execution()
    receipt={'time':r.now(),'acceptance_sha256':r.file_hash(RUN/'acceptance.json'),
             'checkpoint_sha256':r.file_hash(RUN/'checkpoint.json'),'execution_after':after,
             'mutex_reacquired_and_released':released,'corrected_prediction_jobs':0}
    plan={**r.read(PLAN),'version':'20261019-v9-baseline-interval-assets-independently-closed',
          'previous_plan':PLAN.name,'next_action':'review unknown/conflicting truth bounds; expanded populations and dependent scoring remain pending'}
    report=('# 原57基线目标集条件区间标签核验\n\n'
        '坐标不变，覆盖全部57份基线目标文件。原0.005 RK4与独立DOP853 0.0025参考分别进行全点区间接触搜索。'
        '保持1mm角点阈值，但瞬时有限面分类与旧整段扫掠面分类是明确的语义对照，不伪装为同一定义的无差异修复。'
        '空间包络含经验求解器差异及解析插值界，不是形式化ODE误差证书；未定、预算耗尽、模型冲突均保留，不当负例删去。\n\n'
        +'\n'.join(json.dumps(row,ensure_ascii=False) for row in rows)
        +'\n\n本批只生成并复核条件标签资产，不修复任何算法评分。修正真值下重新认证预测仍0。完整粗/细总体、反例和全部依赖评分仍待修，所有相关旧结论继续暂停引用。\n').encode('utf-8')
    r.batch([(RUN/'close_receipt.json',r.encoded(receipt)),(ROOT/'resume_plan_20261019_v9.json',r.encoded(plan)),
             (ROOT/'reports/原57基线全点条件区间标签核验_20261019_v1.md',report)])
    active=r.read(ROOT/'active_research_run.json')
    active.update(status='interval_population_independently_closed_not_running',pid=None,
        running_analysis=False,running_predictions=False,running_preflight=False,plan=str(ROOT/'resume_plan_20261019_v9.json'),
        next_action=plan['next_action'])
    r.mutable(ROOT/'active_research_run.json',active)
    print(json.dumps({'accepted_datasets':len(rows),'corrected_prediction_jobs':0}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','run','close'))
    globals()[parser.parse_args().action]()
