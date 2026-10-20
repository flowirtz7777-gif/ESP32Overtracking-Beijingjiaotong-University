"""New-authorization independent audit of every previously generated group."""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'src_s4_interval_population_20261019_v1'))
import run_population as base
from prefix_audit import audit_prefixes
import numpy as np
r=base.r
OLD=base.RUN
AUTH=ROOT/'runs/resume_20261019_1200_truth_authorization_v2'
RUN=ROOT/'runs/resume_20261019_existing_prefix_audit_1200_v1'
PROTOCOL=ROOT/'protocol_existing_prefix_audit_20261019_1200_v1.json'
PLAN=ROOT/'resume_plan_20261019_1200_v3.json'
SESSION=AUTH/'runtime_sessions/existing_prefix_audit_launch_v1'
OLD_CP='be7baea660626d8bedc8c9dbdcac5af976702faa7edf1b285d18f15953576c82'
r.AUTH,r.RUN,r.RUN_CAP=AUTH,RUN,128*1024**2
r.DEADLINE=dt.datetime(2026,10,19,4,tzinfo=dt.timezone.utc)
RESERVATION=96*1024**2


def execution():
    h=r.helper()
    h.NAMES=(*h.NAMES,'resume_20261019_geometry_delay_recovery_v1','resume_20261019_geometry_labels_v1',
             'resume_20261019_geometry_labels_v2','resume_20261019_contact_mechanism_v1',OLD.name)
    if (RUN/'runner_lock.json').exists():
        h.NAMES=(*h.NAMES,RUN.name)
    evidence=h.execution_evidence()
    for name in h.NAMES:
        for path in (ROOT/'runs'/name).glob('*runner_lock.json'):
            r.require(r.read(path)['status']=='stopped','Runner/analysis still active: '+str(path))
    return h,evidence


def verify_parent():
    r.require(r.file_hash(OLD/'checkpoint.json')==OLD_CP,'Previously stopped parent CP differs')
    expected=r.read(OLD/'source_manifest.json')
    for rel,digest in expected.items():
        r.require(r.file_hash(ROOT/rel)==digest and r.file_hash(OLD/'source'/rel)==digest,
                  'Original frozen source/input dependency differs')
    r.require(r.file_hash(ROOT/'runs/authorization_close_20261019_0800_v2/final_receipt.json')
              =='198b1e37ac286bd88e49f43e51d84047b1df161231218c245c2af528b6c81598','Prior final close differs')
    cp=r.read(OLD/'checkpoint.json')
    r.require(cp['status']=='stopped_failure_or_deadline' and len(cp['completed'])==12
              and sum(len(v['datasets']) for v in cp['completed'].values())==30,
              'Do not select a performance-dependent subset')
    return cp


def signature():
    paths=[*SOURCE.glob('*.py'),PROTOCOL,PLAN,AUTH/'authorization.json',
        OLD/'checkpoint.json',OLD/'source_manifest.json',
        ROOT/'runs/authorization_close_20261019_0800_v2/final_receipt.json',
        ROOT/'research_validity_overlay_20261019_v5.json']
    paths.extend(ROOT/rel for rel in r.read(OLD/'source_manifest.json'))
    return {p.relative_to(ROOT).as_posix():r.file_hash(p) for p in sorted(set(paths))}


def verify():
    r.require(signature()==r.read(RUN/'source_manifest.json'),'New audit source/protocol changed')
    for rel,digest in signature().items():
        r.require(r.file_hash(RUN/'source'/rel)==digest,'New audit frozen snapshot differs')
    for rel,digest in r.read(RUN/'original_all_file_sha256.json').items():
        r.require(r.file_hash(OLD/rel)==digest,'Original generated/history file changed')


def summarize_prefix(arrays):
    excluded=arrays['prefix_excluded']
    early=arrays['early_contact_witness']
    unknown=arrays['prefix_undetermined']
    budget=arrays['budget_exhausted']
    r.require(excluded.dtype==early.dtype==unknown.dtype==budget.dtype==np.dtype(bool),'Prefix boolean contract differs')
    r.require(np.array_equal(excluded,~(early|unknown)) and not np.any(budget&~unknown)
              and not np.any(early&unknown),'Prefix states contradict or unknowns lost')
    return {'points':len(excluded),'prefix_excluded':int(excluded.sum()),
        'early_contact_witness':int(early.sum()),'prefix_undetermined':int(unknown.sum()),
        'budget_exhausted':int(budget.sum()),'strict_prefix_gate_passed':bool(excluded.all())}


def load_all():
    cp=verify_parent()
    matrix=r.read(base.PROTOCOL)['matrix']
    loaded,groups=base.load_inputs(matrix)
    assets={}
    for key,entry in cp['completed'].items():
        r.require(key in groups,'Generated group not in full frozen input matrix')
        folder=OLD/'groups'/key
        arrays,record=base.read_arrays(folder)
        r.require(r.file_hash(folder/'result.json')==entry['group']['result_sha256'],'Parent group CP/report differs')
        r.require(record['ids']==groups[key] and set(entry['datasets'])==set(groups[key]),'Complete group membership differs')
        paths={tag:{k.split('__',1)[1]:v for k,v in arrays.items() if k.startswith(tag+'__')}
               for tag in ('oldpath','independent')}
        combined=base.combine(paths['oldpath'],paths['independent'])
        saved={k.split('__',1)[1]:v for k,v in arrays.items() if k.startswith('combined__')}
        r.require(base.array_meta(combined)==base.array_meta(saved),'Saved full pair combination differs')
        for dataset_id in groups[key]:
            out,meta=base.read_arrays(OLD/'datasets'/dataset_id)
            r.require(r.file_hash(OLD/'datasets'/dataset_id/'result.json')==entry['datasets'][dataset_id]['result_sha256'],
                      'Parent original-order projection report differs')
            target=loaded[dataset_id]['target']
            index=out['union_index']
            r.require(np.array_equal(arrays['xy'][index],target['xy']),'Every original coordinate/order must be retained')
            projection={k:v[index] for k,v in combined.items()}
            r.require(base.array_meta(projection)==base.array_meta({k.split('__',1)[1]:v for k,v in out.items()
                      if k.startswith('combined__')}),'Saved full per-point projection differs')
            for name,mask in base.old_discrepancies(target,projection).items():
                r.require(np.array_equal(np.unpackbits(out[name+'__packbits'],count=len(index),bitorder='little'),mask)
                          and int(mask.sum())==meta['summary'][name],'Full old/new/uncertainty indices differ')
        assets[key]=(arrays,record,paths)
    return loaded,groups,assets


def prepare():
    r.require(r.before_deadline() and not RUN.exists() and not PROTOCOL.exists() and not PLAN.exists(),
              'Audit prepared or deadline')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution()
        cp=verify_parent()
        tests=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(SOURCE),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        r.require(tests.returncode==0,'Prefix audit tests failed: '+tests.stderr)
        protocol={'version':'existing-12-groups-full-independent-prefix-audit-v1','deadline':'2026-10-19T12:00:00+08:00',
            'parent_run':str(OLD),'parent_checkpoint_sha256':OLD_CP,'groups':list(cp['completed']),
            'group_selection':'all generated complete groups, no outcome selection','generated_group_count':12,
            'generated_dataset_file_count':30,'full_baseline_dataset_file_count':57,'remaining_not_generated_files':27,
            'time_resolution_s':1e-8,'max_GE0S_evaluations_per_point':8192,
            'tolerance_m':base.TOLERANCE,'unchanged_source_and_spatial_envelope_policy':True,
            'independent_GE0S_all_witnesses_noncontact_and_first_possible_time_prefix':True,
            'unknown_budget_and_counterexample_full_indices_preserved':True,
            'any_early_witness_stops_further_work_after_preserving_full_failure_arrays':True,
            'not_full_baseline_or_expanded_truth_fix_or_any_recertified_prediction':True,
            'numerical_error_envelope_still_empirical_conditional_not_formal_ODE':True,
            'run_cap_bytes':r.RUN_CAP,'reservation_bytes':RESERVATION,'total_E_Z_cap_bytes':r.CAP,
            'Z_reserve_bytes':r.RESERVE,'workers':1,'inflight':1}
        plan={**r.read(ROOT/'resume_plan_20261019_1200_v2.json'),
            'version':'20261019-1200-v3-existing-assets-independent-audit',
            'previous_plan':'resume_plan_20261019_1200_v2.json','run_directory':str(RUN),
            'entrypoint':str(Path(__file__)),'protocol':str(PROTOCOL),
            'stage_status':'prepared_actual_worker_input_admission_still_required',
            'next_action':'independent worker loads all 57 originals and decodes all 12 generated groups, then first-contact prefix audit'}
        inventory={p.relative_to(OLD).as_posix():r.file_hash(p) for p in OLD.rglob('*') if p.is_file()}
        r.batch([(PROTOCOL,r.encoded(protocol)),(PLAN,r.encoded(plan)),
            (RUN/'original_all_file_sha256.json',r.encoded(inventory)),
            (RUN/'prelaunch.json',r.encoded({'time':r.now(),'mutex':mutex,'execution':idle,
                'test_stdout':tests.stdout,'test_stderr':tests.stderr,'resources':r.guard(RESERVATION,RESERVATION)}))])
        signed=signature()
        r.batch([(RUN/'source_manifest.json',r.encoded(signed))]+
                [(RUN/'source'/rel,(ROOT/rel).read_bytes()) for rel in signed])
        active=r.read(ROOT/'active_research_run.json')
        active.update(status='existing_prefix_audit_prepared_not_running',run_directory=str(RUN),plan=str(PLAN),
            protocol=str(PROTOCOL),entrypoint=str(Path(__file__)),pid=None,running_analysis=False,
            running_predictions=False,running_preflight=False,input_worker_admission_pending=True,
            input_worker_admitted=False,stdout=str(SESSION/'stdout.log'),stderr=str(SESSION/'stderr.log'))
        r.mutable(ROOT/'active_research_run.json',active)
    print('EXISTING PREFIX AUDIT PREPARED; no scientific execution yet',flush=True)


def audit_case(key,loaded,groups,asset):
    arrays,record,paths=asset
    original=loaded[groups[key][0]]
    vehicle=base.common.Vehicle(**original['profile']['vehicle'])
    trajectory=original['trajectory']
    output={}
    result={}
    for tag,time,state,error in (
        ('oldpath',trajectory['fine_time'],trajectory['fine_state'],record['reference_meta']['old_path_spatial_envelope_m']),
        ('independent',arrays['independent_time'],arrays['independent_state'],record['reference_meta']['independent_path_spatial_envelope_m'])):
        print('START ALL-POINT GEOMETRY AND PREFIX '+key+' '+tag,flush=True)
        geometry=base.validate_path(arrays['xy'],time,state,paths[tag],error,vehicle)
        prefix=audit_prefixes(arrays['xy'],time,state,paths[tag]['contact_lower_s'],vehicle=vehicle,
            spatial_error_m=error,tolerance_m=base.TOLERANCE,time_resolution_s=1e-8,max_evaluations_per_point=8192)
        summary=summarize_prefix(prefix)
        result[tag]={'geometry':geometry,'prefix':summary}
        output.update({tag+'__'+name:value for name,value in prefix.items()})
        for name in ('prefix_excluded','early_contact_witness','prefix_undetermined','budget_exhausted'):
            output[tag+'__'+name+'__packbits']=np.packbits(prefix[name],bitorder='little')
        print('DONE PREFIX '+json.dumps({'group':key,'path':tag,**summary}),flush=True)
    folder=RUN/'groups'/key
    blob=base.npz_bytes(output)
    saved={'input_group':key,'original_group_result_sha256':r.file_hash(OLD/'groups'/key/'result.json'),
        'original_union_xy_sha256':base.common.array_hash(arrays['xy']),
        'original_dataset_ids':groups[key],'summary':result,'arrays':base.array_meta(output),'npz_sha256':r.sha(blob),
        'corrected_truth_revalidated_prediction_jobs':0}
    r.batch([(folder/'prefix_audit.npz',blob),(folder/'result.json',r.encoded(saved))])
    early=sum(result[tag]['prefix']['early_contact_witness'] for tag in result)
    r.require(early==0,'First-contact lower bound contradicted by independent early-contact witness; full evidence preserved')
    return {'result_sha256':r.file_hash(folder/'result.json'),'summary':result}


def run():
    r.require(r.before_deadline() and not (RUN/'checkpoint.json').exists(),'Audit already started or deadline')
    h,_=execution()
    cp={'status':'preflight','completed':{},'source_signature':signature(),
        'corrected_truth_revalidated_prediction_jobs':0,'new_predictions':0}
    with h.exclusive() as mutex:
        _,idle=execution()
        verify()
        r.mutable(RUN/'runner_lock.json',{'status':'running','pid':os.getpid(),'time':r.now(),'role':'independent_existing_asset_audit'})
        try:
            loaded,groups,assets=load_all()
            r.require(list(assets)==r.read(PROTOCOL)['groups'],'Fixed all-generated audit selection differs')
            r.freeze(RUN/'preflight.json',r.encoded({'time':r.now(),'python':sys.executable,'root':str(ROOT),
                'loaded_baseline_datasets':len(loaded),'loaded_generated_groups':len(assets),
                'loaded_generated_dataset_files':sum(len(groups[k]) for k in assets),
                'all_original_array_sha256':{i:{'target':base.array_meta(v['target']),
                    'trajectory':base.array_meta(v['trajectory'])} for i,v in loaded.items()},
                'all_generated_full_arrays_decoded_before_submit':True,'source_signature':signature(),
                'modules':{m.__name__:str(Path(m.__file__).resolve()) for m in
                    (base,sys.modules[audit_prefixes.__module__],base.common,sys.modules['population'],sys.modules['reference'])},
                'BLAS':{k:os.environ[k] for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
                'execution':idle,'mutex':mutex,'resources':r.guard(RESERVATION,RESERVATION)}))
            active=r.read(ROOT/'active_research_run.json')
            active.update(status='existing_prefix_audit_running',pid=os.getpid(),running_analysis=True,
                running_predictions=False,running_preflight=False,input_worker_admission_pending=False,input_worker_admitted=True)
            r.mutable(ROOT/'active_research_run.json',active)
            print('EXISTING PREFIX PREFLIGHT PASSED ALL 57 INPUTS AND 12 COMPLETE GENERATED GROUPS',flush=True)
            for key,asset in assets.items():
                r.require(r.before_deadline(),'12:00 new audit group submission cutoff')
                verify()
                cp['completed'][key]=audit_case(key,loaded,groups,asset)
                r.checkpoint(cp)
            cp['status']='complete_pending_independent_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline',failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN/'runner_lock.json',{'status':'stopped','pid':os.getpid(),'time':r.now()})
    print('EXISTING PREFIX AUDIT EXITING; no corrected prediction certified',flush=True)


def close():
    r.require(r.before_deadline() and not (RUN/'acceptance.json').exists(),'Audit closed or cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution()
        verify()
        cp=r.read(RUN/'checkpoint.json')
        r.require(cp['status']=='complete_pending_independent_close' and len(cp['completed'])==12,'Audit incomplete')
        loaded,groups,assets=load_all()
        r.mutable(RUN/'analysis_runner_lock.json',{'status':'running','pid':os.getpid(),'time':r.now()})
        rows=[]
        try:
            for key,entry in cp['completed'].items():
                folder=RUN/'groups'/key
                saved=r.read(folder/'result.json')
                r.require(r.file_hash(folder/'result.json')==entry['result_sha256']
                          and r.file_hash(folder/'prefix_audit.npz')==saved['npz_sha256'],'Audit CP/output differs')
                with np.load(folder/'prefix_audit.npz',allow_pickle=False) as z:
                    arrays={k:z[k] for k in z.files}
                r.require(base.array_meta(arrays)==saved['arrays'],'All decoded audit arrays differ')
                for tag in ('oldpath','independent'):
                    prefix={k.split('__',1)[1]:v for k,v in arrays.items()
                            if k.startswith(tag+'__') and not k.endswith('__packbits')}
                    summary=summarize_prefix(prefix)
                    r.require(summary==saved['summary'][tag]['prefix'],'Independent audit statistics differ')
                    r.require(summary['early_contact_witness']==0,'Early-contact counterexample cannot be accepted')
                    parent=assets[key][2][tag]['contact_lower_s']
                    wanted=np.where(np.isnan(parent),loaded[groups[key][0]]['trajectory']['fine_time'][-1],parent)
                    r.require(np.array_equal(wanted,prefix['audited_until_s']),'Full prefix endpoint set differs')
                    for name in ('prefix_excluded','early_contact_witness','prefix_undetermined','budget_exhausted'):
                        r.require(np.array_equal(np.unpackbits(arrays[tag+'__'+name+'__packbits'],
                            bitorder='little',count=len(parent)),prefix[name]),'Complete prefix state indices differ')
                rows.append({'group':key,'dataset_files':len(groups[key]),'summary':saved['summary']})
            acceptance={'time':r.now(),'status':'all_existing_12_groups_independently_decoded_geometry_and_prefix_audited',
                'generated_groups_audited':12,'generated_dataset_files_audited':30,
                'full_baseline_dataset_files':57,'remaining_ungenerated_baseline_files':27,'rows':rows,
                'checkpoint_sha256':r.file_hash(RUN/'checkpoint.json'),'source_signature':signature(),
                'corrected_truth_revalidated_prediction_jobs':0,'all_old_label_claims_remain_withheld':True,
                'numerical_reference_error_still_conditional_empirical_not_formal_ODE_bound':True,
                'all_prefix_unknowns_budget_and_model_uncertainty_remain_explicit':True,
                'execution':idle,'mutex':mutex}
            r.batch([(RUN/'acceptance.json',r.encoded(acceptance)),
                     (RUN/'acceptance.json.gz',gzip.compress(r.encoded(acceptance),mtime=0))])
        finally:
            r.mutable(RUN/'analysis_runner_lock.json',{'status':'stopped','pid':os.getpid(),'time':r.now()})
    with h.exclusive() as released:
        _,after=execution()
    receipt={'time':r.now(),'acceptance_sha256':r.file_hash(RUN/'acceptance.json'),
        'checkpoint_sha256':r.file_hash(RUN/'checkpoint.json'),'execution_after':after,
        'mutex_reacquired_and_released':released,'corrected_prediction_jobs':0}
    plan={**r.read(PLAN),'version':'20261019-1200-v4-existing-prefix-audit-closed',
        'previous_plan':PLAN.name,'stage_status':'independently_closed_not_running',
        'next_action':'inspect any prefix unknowns, then new-version exact reuse/recovery for remaining 27 baseline files; no old entrypoint rerun'}
    report=('# 已生成30份基线资产的独立几何与首次接触前缀核验\n\n'
        '范围固定为此前实际生成的全部12共享几何组/30份文件，不按方法表现或差异大小筛选。'
        '实际worker完整加载57份原输入，独立解码全部已生成资产和逐点投影、旧新差异与不确定性索引。'
        '逐路径GEOS见证/非接触排除、有限面边集合及首次可能下界前的完整前缀核验，未定/预算/反例不删。\n\n'
        +'\n'.join(json.dumps(row,ensure_ascii=False) for row in rows)
        +'\n\n本核验不等于完成57份基线或完整粗细总体纠错，不修复任何依赖评分，修正真值重验预测仍0。'
        '经验数值误差包络不是形式化ODE或实车证书，全部相关旧结论继续暂停，M2/S5不准入。\n').encode('utf-8')
    r.batch([(RUN/'close_receipt.json',r.encoded(receipt)),
        (ROOT/'resume_plan_20261019_1200_v4.json',r.encoded(plan)),
        (ROOT/'reports/已生成基线资产独立首次接触前缀核验_20261019_1200_v1.md',report)])
    active=r.read(ROOT/'active_research_run.json')
    active.update(status='existing_prefix_audit_independently_closed_not_running',pid=None,running_analysis=False,
        running_predictions=False,running_preflight=False,plan=str(ROOT/'resume_plan_20261019_1200_v4.json'),
        next_action=plan['next_action'])
    r.mutable(ROOT/'active_research_run.json',active)
    print(json.dumps({'closed_existing_groups':12,'dataset_files':30,'corrected_prediction_jobs':0}),flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN/'runner_lock.json').exists(),
              'Launch already attempted or cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution()
        verify()
        argv=[str(r.PYTHON),'-X','utf8','-B','-u',str(Path(__file__)),'run']
        r.freeze(SESSION/'policy.json',r.encoded({'time':r.now(),'argv':argv,'cwd':r'C:\Users\Admin',
            'parent_mutex':mutex,'execution':idle,'parent_mutex_released_before_Popen':True,
            'resources':r.guard(RESERVATION,RESERVATION)}))
    with (SESSION/'stdout.log').open('xb') as stdout,(SESSION/'stderr.log').open('xb') as stderr:
        child=subprocess.Popen(argv,cwd=r'C:\Users\Admin',stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
            env=dict(os.environ),creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION/'launched.json',r.encoded({'time':r.now(),'pid_historical_identity_only':child.pid,
        'poll':child.poll(),'not_worker_admission_proof':True}))
    print('EXISTING AUDIT LAUNCHED identity PID '+str(child.pid),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','launch','run','close'))
    globals()[parser.parse_args().action]()
