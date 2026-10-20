"""Administrative registration; scientific waits verified, manager exit code not inferred."""
import os
import sys
from pathlib import Path
sys.dont_write_bytecode=True
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src_s4_remediation_scope_20261022_v1'))
import scope_driver as d
r=d.r

def main():
    d.configure()
    closed=d.AUTH/'runtime_sessions/remediation_scope_closed_v1'
    dest=closed/'administrative_registration_v1.json'
    r.require(not dest.exists(),'Administrative registration already used')
    h,_=d.execution()
    with h.exclusive() as mutex:
        _,stopped=d.execution(); d.verify()
        actual={p.relative_to(d.RUN).as_posix():r.file_hash(p) for p in sorted(d.RUN.rglob('*')) if p.is_file()}
        r.require(actual==r.read(closed/'all_closed_run_files_sha256.json'),'Every closed scope file differs')
        reg=r.read(closed/'registration.json')
        r.require(reg['scientific_close_succeeded'] and reg['all_closed_file_count']==len(actual)
            and reg['actual_first_close_wait']['actual_wait_exit_code']==0
            and reg['actual_worker_wait']['actual_wait_exit_code']==0,'Actual scientific waits required')
        locks={p.name:r.read(p) for p in d.RUN.glob('*runner_lock.json')}
        r.require(set(locks)=={'runner_lock.json','analysis_runner_lock.json'}
            and all(v['status']=='stopped' for v in locks.values()),'Both current locks stopped required')
        acceptance=r.read(d.RUN/'acceptance.json'); counts=acceptance['accounting']
        r.require(counts['output_file_records_not_experiments']==6609
            and counts['packed_expanded_population_records']==27
            and counts['packed_full_coordinate_descriptor_links_resolved']==9
            and counts['packed_full_coordinate_descriptor_links_unresolved']==18,'Complete observed accounting required')
        evidence=dict(time=r.now(),execution=stopped,mutex=mutex,locks=locks,
            manager_exec_session=45064,manager_separate_tool_wait_exit_code=None,
            manager_final_completion_output_observed=True,manager_absent_in_fresh_generic_CIM=True,
            completed_session_followup_poll_rejected='Unknown process id45064; no retry of scientific entrypoints',
            all_closed_run_files_rehashed=len(actual),accounting=counts,
            scientific_close_sha256=actual['acceptance.json'],checkpoint_sha256=actual['checkpoint.json'],
            close_receipt_sha256=actual['close_receipt.json'],source_manifest_sha256=actual['source_manifest.json'],
            corrected_truth_or_scores_accepted=False,all_scientific_entrypoints_used_never_repeat=True)
        report=('# 完整输出来源范围核查行政登记\n\n'
            '首次prepare、run、独立close均实际wait退出0；行政manager已输出完整登记，实时CIM不再存在。'
            '工具完成返回未提供管理器单独退出码，不推断为0；完成后再次轮询返回Unknown process id，未重试科学入口。'
            '停止/原mutex/全部旧锁及本run双锁核对后，全部闭合文件重新核签。\n\n'
            '核查6609输出文件记录（不是独立实验数），27条packed扩展总体记录；'
            '9条完整坐标描述对应已找到，18条保留未解决；未完整重建坐标、修正标签或认证在线预测复用。'
            '后续需补齐扩展总体/容差/负控制并修复全部受影响评分。\n\n'+str(counts)+'\n').encode('utf-8')
        r.batch([(dest,r.encoded(evidence)),(ROOT/'reports/remediation_scope_close_registration_20261021_v1.md',report)])
        active=r.read(ROOT/'active_research_run.json')
        r.require(active['version']=='20261022-0000-v43-full-remediation-scope-lineage-closed','Latest accepted version differs')
        active.update(scientific_close_actual_wait_exit_code=0,
            scientific_close_wait_record=str(d.AUTH/'runtime_sessions/remediation_scope_first_close_v1/exit.json'),
            scientific_close_registration=str(dest),administrative_manager_separate_exit_code=None,
            pid=None,running_analysis=False,running_preflight=False,running_predictions=False)
        r.mutable(ROOT/'active_research_run.json',active)
    append=('\n\n## 最新完整来源验收 v43（'+r.now()+'）\n\n'
        '覆盖上方在途快照：工具session45064已返回完整闭合登记输出并结束，manager28320在实时通用CIM不再存在；'
        '返回未提供管理器单独退出码，不声称管理器exit0。完成后再次轮询已返回Unknown process id45064，不再轮询；未重试科学入口。'
        '首次prepare28432、worker47228、首次close47468均真实wait0。'
        'AUTH/runtime_sessions/remediation_scope_closed_v1/{registration.json,all_closed_run_files_sha256.json,administrative_registration_v1.json}；'
        '全部'+str(len(actual))+'闭合文件重新核签，本run双锁stopped与原mutex/停止证据核实。'
        '报告ROOT/reports/remediation_scope_close_registration_20261021_v1.md；v42/v43已生成并首次闭合，'
        '全部prepare/run/close入口已使用禁重跑。active实际科学close wait0已行政补齐。\n\n'
        '结果6609输出文件记录/27packed，完整坐标描述对应resolved9、unresolved18。'
        '仅来源/文件完整性认证，无实际数组重建、标签/评分修复或预测复用认证。'
        '科学真值基线仍v41标签census；纠错评分验收仍0。'
        '下一步：完整扩展坐标构建（粗细/容差/负控制不可漏），以及完整报警序列来源和RIGHT评分候选真实适配协议；'
        'C盘paired_interval_metric_core_v1.py已有13合成测试含300穷举，但非真实评分源。'
        '原E只读/期限/32GiB/3GiB/单worker/一在途及训练门不变。\n').encode('utf-8')
    status=HERE/'STATUS.md'; payload=status.read_bytes()+append
    r.guard(len(payload),0)
    with status.open('wb') as out: out.write(payload)
    r.require(status.read_bytes()==payload,'C status readback differs')
    print('V43 CLOSED; ALL'+str(len(actual))+' FILES REHASHED; SCIENTIFIC WAIT0 REGISTERED; NO SCIENTIFIC WORKER',flush=True)

if __name__=='__main__': main()
