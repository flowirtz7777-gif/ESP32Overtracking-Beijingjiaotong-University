"""All frozen output lineage and complete-population descriptor audit; no labels/scores."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import traceback
sys.dont_write_bytecode=True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[key]='1'
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src_s4_edge_cover_merge_20261022_v1'))
import edge_cover_merge_driver as parent
import remediation_scope_core as core
r=parent.r
AUTH=parent.AUTH
PARENT=parent.RUN
RUN=ROOT/'runs/resume_20261022_0000_remediation_scope_v1'
PROTOCOL=ROOT/'protocol_remediation_scope_20261022_0000_v1.json'
PLAN=ROOT/'resume_plan_20261022_0000_v42.json'
CLOSED_PLAN=ROOT/'resume_plan_20261022_0000_v43.json'
SESSION=AUTH/'runtime_sessions/remediation_scope_launch_v1'
CLOSURE=AUTH/'runtime_sessions/edge_cover_merge_closed_v1'
FIRST=ROOT/'runs/truth_label_impact_registry_20261019_v1/impact_inventory.json'
REGISTRY=ROOT/'runs/truth_label_dependency_resolution_20261019_v1/dependency_resolution.json'
HASHES={'checkpoint.json':'b718044369b2636110b17e8bbc0d5fa79d9211d808432a9e67335dff0793297b',
    'acceptance.json':'364e3c486ab665649c710cb68400f99e9de79aaa7f359ddea39713d15e66e45e',
    'close_receipt.json':'0d1f7a462179926a8df1ec42d61c4e408f265af0aa4f8bdb20b4838ef8193d51',
    'source_manifest.json':'23b7be8b8d855ff9bb56728603a4c5786836e82415cbd028348369361515cb87'}
RESERVATION=448*1024**2
BLOCK=128


def configure():
    parent.configure()
    r.RUN,r.RUN_CAP=RUN,512*1024**2


configure()


def execution():
    try: return parent.execution()
    finally: configure()


def gate():
    try:
        parent.verify()
        for name,sha in HASHES.items(): r.require(r.file_hash(PARENT/name)==sha,'Complete accepted v41 parent changed')
        inventory=r.read(CLOSURE/'all_closed_run_files_sha256.json')
        actual={p.relative_to(PARENT).as_posix():r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.require(actual==inventory and len(actual)==1119,'Every closed v41 file required')
        reg=r.read(CLOSURE/'registration.json')
        r.require(reg['actual_first_close_wait']['actual_wait_exit_code']==0
            and reg['actual_worker_wait']['actual_wait_exit_code']==0,'Actual closed v41 waits required')
        r.require(r.file_hash(FIRST)=='e414953306f23bec8c17721e5da6bbe80d4ca61d68db4604b40bd9c398b66e70'
            and r.file_hash(REGISTRY)=='63d56366ab8054cb8f67f039df4aa57c1d4db897dc01e6366340f7c958229fc3',
            'Complete original scope registries required')
        reg=r.read(REGISTRY); first=r.read(FIRST)
        r.require(not reg['errors'] and not first['errors'] and len(reg['prediction_output_records'])==6609
            and reg['packed_population_records']==27,'Full source scope and original errors required')
        rows={v['report']:v['report_sha256'] for v in reg['prediction_output_records']}
        r.require(len(rows)==6609 and all(rows.get(v['report'])==v['report_sha256'] for v in first['prediction_job_records']),
            'Every original output report must remain covered')
    finally: configure()


def signature():
    files={ROOT/name for name in r.read(PARENT/'source_manifest.json')}
    files.update(PARENT/name for name in HASHES)
    files.update(SOURCE.glob('*.py'))
    files.update((FIRST,REGISTRY,PROTOCOL,PLAN,AUTH/'authorization.json'))
    files.update(p for p in CLOSURE.rglob('*') if p.is_file())
    for folder in (AUTH/'runtime_sessions').glob('remediation_scope_development_tests_v*'):
        files.update(p for p in folder.rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix():r.file_hash(p) for p in sorted(files)}


def verify(*,full=True):
    signed=r.read(RUN/'source_manifest.json')
    r.require(signature()==signed,'Every source/protocol/closed lineage byte required')
    core.verify_bundle((RUN/'source_bundle.zip').read_bytes(),signed)
    if full: gate()


def metadata_inputs():
    registry=r.read(REGISTRY); first=r.read(FIRST)
    hash_cache={}; json_cache={}
    def checked(path,expected=None):
        p=Path(path)
        if p not in hash_cache: hash_cache[p]=r.file_hash(p)
        r.require(expected is None or hash_cache[p]==expected,'Frozen metadata/output file changed: '+str(p))
        return hash_cache[p]
    def read(path,expected=None):
        p=Path(path); sha=checked(p,expected)
        if p not in json_cache: json_cache[p]=r.read(p)
        return sha,json_cache[p]
    descriptors=[]; seen={}
    refs=[dict(path=v['manifest'],sha256=v['manifest_sha256']) for v in first['datasets']]
    refs.extend(registry['closed_derived_asset_records'])
    for value in refs:
        path=Path(value['path']); expected=value['sha256']
        if path in seen:
            r.require(seen[path]==expected,'Conflicting descriptor binding')
            continue
        seen[path]=expected
        sha,contents=read(path,expected)
        descriptors.append(core.descriptor(str(path),sha,contents))
    indices=core.index_descriptors(descriptors)
    r.require(len(registry['prediction_output_records'])==6609,'All registry rows required')
    return registry,descriptors,indices,checked,read


def block_rows(start,registry,indices,checked,read):
    result=[]
    for number in range(start,min(start+BLOCK,6609)):
        row=registry['prediction_output_records'][number]
        path=Path(row['report'])
        _,report=read(path,row['report_sha256'])
        cfg=path.with_name('configuration.json')
        config_sha,config=read(cfg) if cfg.exists() else (None,{})
        for filename,sha in row['point_outputs'].items():
            local=Path(filename)
            r.require(not local.is_absolute() and '..' not in local.parts,'Local output member required')
            checked(path.parent/local,sha)
        for ancestor in row['inherited_input_trace']: checked(ancestor['path'],ancestor['sha256'])
        item=core.record(number,row,report,config,indices)
        item['configuration_sha256']=config_sha
        item['configuration_present']=cfg.exists()
        result.append(item)
    return result


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN,PROTOCOL,PLAN,CLOSED_PLAN)),'Used or cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution(); gate()
        test=subprocess.run([str(r.PYTHON),'-X','utf8','-B','-m','unittest','discover','-s',str(SOURCE),'-p','test_*.py','-v'],
            cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',timeout=180)
        r.require(test.returncode==0,'Synthetic scope/snapshot tests failed: '+test.stderr)
        protocol=dict(version='full-output-and-expanded-population-metadata-lineage-v1',deadline=r.read(AUTH/'authorization.json')['deadline'],
            original_registry=str(REGISTRY),original_inventory=str(FIRST),output_records_not_experiments=6609,packed_population_records=27,
            current_complete_truth_parent=str(PARENT),parent_hashes=HASHES,
            scope='every6609 original E/Z frozen output report, signed point-output file, configuration, inherited input and every registered target/derived JSON descriptor',
            no_real_array_contents_read=True,no_relabeling_no_prediction_no_training_no_score_recomputation=True,
            descriptor_link_is_not_complete_coordinate_reconstruction_or_corrected_truth=True,
            all_unknowns_and_unresolved_links_preserved=True,no_unsupported_input_or_prediction_reuse_claim=True,
            independent_close='independently reread/hash every complete registry report/output and descriptor, exact full-row recomputation/conservation',
            snapshot='RAM deterministic ZIP of every individually signed source; complete byte-exact readback before freeze and during verify',
            resources='every research write RAM-encoded/count and fresh full E/Z scandir through unchanged runtime',
            workers=1,inflight=1,block_records=BLOCK,run_cap_bytes=r.RUN_CAP,reservation_bytes=RESERVATION,
            total_E_Z_cap_bytes=r.CAP,Z_physical_reserve_bytes=r.RESERVE,truth_asset_promotion_allowed=False)
        plan=dict(version='20261022-0000-v42-full-remediation-scope-lineage',deadline=protocol['deadline'],run_directory=str(RUN),
            protocol=str(PROTOCOL),entrypoint=str(Path(__file__)),stage_status='prepared_not_admitted',
            scientific_acceptance_exists=False,truth_asset_promotion_allowed=False,corrected_truth_revalidated_prediction_jobs=0,
            S4_overall_complete=False,M2_allowed=False,S5_allowed=False,
            next_action='full frozen output/expanded-coordinate descriptor lineage; complete coordinate reconstruction and truth/score repair still required')
        r.batch([(PROTOCOL,r.encoded(protocol)),(PLAN,r.encoded(plan)),
            (RUN/'prelaunch.json',r.encoded(dict(time=r.now(),execution=idle,mutex=mutex,stdout=test.stdout,stderr=test.stderr,
                resources=r.guard(RESERVATION,RESERVATION))))])
        signed=signature()
        bundle=core.source_bundle({name:(ROOT/name).read_bytes() for name in signed})
        r.batch([(RUN/'source_manifest.json',r.encoded(signed)),(RUN/'source_bundle.zip',bundle)])
    print('FULL REMEDIATION SCOPE PREPARED; actual full admission pending',flush=True)


def run():
    r.require(r.before_deadline() and not (RUN/'checkpoint.json').exists(),'Used or cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution(); verify()
        cp=dict(status='preflight',completed={})
        r.mutable(RUN/'runner_lock.json',dict(status='running',pid=os.getpid(),time=r.now()))
        try:
            registry,descriptors,indices,checked,read=metadata_inputs()
            r.freeze(RUN/'descriptors.json',r.encoded(descriptors))
            active=r.read(ROOT/'active_research_run.json')
            active.update(version='20261022-0000-v42-full-remediation-scope-running',run_directory=str(RUN),protocol=str(PROTOCOL),plan=str(PLAN),
                entrypoint=str(Path(__file__)),pid=os.getpid(),running_analysis=True,running_predictions=False,
                scientific_acceptance=None,scientific_close_receipt=None,scientific_close_actual_wait_exit_code=None,
                input_worker_admitted=True,input_worker_admission_pending=False,stdout=str(SESSION/'stdout.log'),stderr=str(SESSION/'stderr.log'))
            r.mutable(ROOT/'active_research_run.json',active)
            print('FULL REMEDIATION SCOPE PREFLIGHT PASSED ALL6609 /27 PACKED /COMPLETE DECLARED DESCRIPTORS /V41 PARENT',flush=True)
            all_rows=[]
            for start in range(0,6609,BLOCK):
                r.require(r.before_deadline(),'No new metadata block after cutoff'); verify(full=False)
                rows=block_rows(start,registry,indices,checked,read)
                dest=RUN/'blocks'/f'{start:06d}.json'; blob=r.encoded(rows)
                r.freeze(dest,blob)
                cp['completed'][str(start)]=dict(sha256=r.sha(blob),summary=core.summarize(rows))
                all_rows.extend(rows); r.checkpoint(cp)
                print('DONE FULL REMEDIATION SCOPE '+str(start+len(rows))+'/6609',flush=True)
            counts=core.summarize(all_rows)
            r.require(counts['output_file_records_not_experiments']==6609 and counts['packed_expanded_population_records']==27,'Full conservation required')
            cp.update(status='complete_pending_independent_remediation_scope_close',accounting=counts); r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline',failure=traceback.format_exc()); r.checkpoint(cp); raise
        finally: r.mutable(RUN/'runner_lock.json',dict(status='stopped',pid=os.getpid(),time=r.now()))
    print('FULL REMEDIATION SCOPE WORKER EXITING; independent close pending',flush=True)


def close():
    r.require(r.before_deadline() and not (RUN/'analysis_runner_lock.json').exists() and not (RUN/'acceptance.json').exists(),'Used or cutoff')
    h,_=execution()
    with h.exclusive() as mutex:
        _,idle=execution(); verify()
        cp=r.read(RUN/'checkpoint.json')
        r.require(cp['status']=='complete_pending_independent_remediation_scope_close' and len(cp['completed'])==52,'Complete scope required')
        r.mutable(RUN/'analysis_runner_lock.json',dict(status='running',pid=os.getpid(),time=r.now()))
        try:
            registry,descriptors,indices,checked,read=metadata_inputs()
            r.require(r.read(RUN/'descriptors.json')==descriptors,'Every descriptor differs')
            rows=[]
            for start in range(0,6609,BLOCK):
                block=block_rows(start,registry,indices,checked,read); path=RUN/'blocks'/f'{start:06d}.json'
                r.require(r.file_hash(path)==cp['completed'][str(start)]['sha256']
                    and r.read(path)==block and core.summarize(block)==cp['completed'][str(start)]['summary'],'Whole registry block differs')
                rows.extend(block)
                print('CLOSE FULL REMEDIATION SCOPE '+str(start+len(block))+'/6609',flush=True)
            counts=core.summarize(rows)
            r.require(counts==cp['accounting'] and len({v['report'] for v in rows})==6609,'Every complete source report required')
            acceptance=dict(time=r.now(),status='all_registered_outputs_and_descriptors_independently_hashed_lineage_only',accounting=counts,
                descriptor_records=len(descriptors),all_original_output_records_and_signed_files_checked=True,
                all_unknown_links_and_different_tolerances_preserved=True,complete_coordinate_arrays_reconstructed=False,
                corrected_labels_accepted=False,corrected_scores_accepted=False,raw_prediction_reuse_proven=False,
                truth_asset_promotion_allowed=False,S4_overall_complete=False,M2_allowed=False,S5_allowed=False,
                checkpoint_sha256=r.file_hash(RUN/'checkpoint.json'),execution=idle,mutex=mutex)
            r.freeze(RUN/'acceptance.json',r.encoded(acceptance))
        finally: r.mutable(RUN/'analysis_runner_lock.json',dict(status='stopped',pid=os.getpid(),time=r.now()))
    with h.exclusive() as released: _,after=execution()
    plan={**r.read(PLAN),'version':'20261022-0000-v43-full-remediation-scope-lineage-closed',
        'stage_status':'lineage_closed_not_truth_or_score_repair','scientific_acceptance_exists':True,'accounting':counts,
        'next_action':'complete every expanded/coarse/fine/negative/control coordinate input reconstruction; conditional truth and every affected score/report repair'}
    report=('Full frozen output scope and target descriptor lineage verified. This certifies metadata/file integrity only; '
        'no corrected truth/score or raw prediction reuse is accepted. Declared counts are not independently verified coordinate lengths.\n'+str(counts)+'\n').encode('utf-8')
    r.batch([(RUN/'close_receipt.json',r.encoded(dict(time=r.now(),checkpoint_sha256=r.file_hash(RUN/'checkpoint.json'),
        acceptance_sha256=r.file_hash(RUN/'acceptance.json'),execution_after=after,mutex_acquired_released=released))),
        (CLOSED_PLAN,r.encoded(plan)),(ROOT/'reports/remediation_full_scope_lineage_20261022_0000_v1.md',report)])
    active=r.read(ROOT/'active_research_run.json')
    active.update(version=plan['version'],status=plan['stage_status'],plan=str(CLOSED_PLAN),pid=None,running_analysis=False,
        scientific_acceptance=str(RUN/'acceptance.json'),scientific_close_receipt=str(RUN/'close_receipt.json'),next_action=plan['next_action'],
        complete_scope_lineage_accounting=counts,complete_coordinate_reconstruction_still_required=True)
    r.mutable(ROOT/'active_research_run.json',active)
    print('FULL REMEDIATION SCOPE LINEAGE CLOSED; TRUTH/SCORE REPAIR STILL REQUIRED '+str(counts),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=('prepare','run','close'))
    globals()[parser.parse_args().action]()
