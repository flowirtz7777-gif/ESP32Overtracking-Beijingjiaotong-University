"""File/exit-only registration after independently closed full merge; no scientific rerun."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_suffix_full_merge_20261022_v1'))
import suffix_full_merge_driver as d
r=d.r
REG=d.AUTH/'runtime_sessions/suffix_full_merge_closed_v1'
REPORT=ROOT/'reports/suffix_full_merge_close_registration_20261020_v1.md'


def main():
    r.require(not REPORT.exists(),'Registration report already frozen')
    h,_=d.execution()
    with h.exclusive() as mutex:
        _,idle=d.execution()
        registered=r.read(REG/'registration.json')
        inventory=r.read(REG/'all_closed_run_files_sha256.json')
        actual={p.relative_to(d.RUN).as_posix():r.file_hash(p) for p in sorted(d.RUN.rglob('*')) if p.is_file()}
        r.require(actual==inventory and len(actual)==1059,'Full current closed merge file set or bytes changed')
        r.require(registered['actual_first_close_wait']['actual_wait_exit_code']==0
            and registered['actual_worker_wait']['actual_wait_exit_code']==0,'Actual worker and first-close wait required')
        r.require(r.read(d.RUN/'runner_lock.json')['status']=='stopped'
            and r.read(d.RUN/'analysis_runner_lock.json')['status']=='stopped','Both normal locks must be stopped')
        receipt=r.read(d.RUN/'close_receipt.json'); accepted=r.read(d.RUN/'acceptance.json')
        r.require(receipt['acceptance_sha256']==actual['acceptance.json']
            and receipt['checkpoint_sha256']==actual['checkpoint.json'],'Close receipt must bind all current accepted bytes')
        counts=accepted['accounting']
        report=('全量补充见证合并独立闭合登记\n\n'
            '首次worker和首次科学close实际wait均退出0；完整1059个闭合文件逐一核签，正常runner/analysis锁均stopped，'
            '无科学进程并实际取得释放命名mutex。实际证据：'+str(REG)+'。\n\n'
            '完整39组、57原序双路径投影、3360000分文件点记录；45714组内scope路径行完整接入；'
            '全部114原序完整探测矩阵和原未知诊断投影逐字节保留。科学下界、原完整首次接触前缀、旧provenance不变。\n\n'
            '新完整census：接触状态未知13949，完整待核范围26878分文件点记录/22857组内唯一点；'
            '边集合未定12929。原因重叠不能相加，不能把4条组内点×路径新见证当作2个独立实验或直接扣减总范围。\n\n'
            '旧评分/排名/部署推荐继续暂停，修正真值重验预测0；S4整体/M2/S5未完成，M2/S5不准入。'
            '仍须所有接触/时间/边未知与可辨识性、完整粗细扩展总体、负控制/反例、全部波及评分报告修正或精确不受影响证明。\n\n'
            '后缀候选及本次全量合并均已独立接受；剩余未知继续保留，下一新方法尚未科学准入。'
            '其剪枝仅针对严格见证充分判据，绝非非接触/全局最早/物理不可辨识证明。\n\n'
            +str(counts)+'\n').encode('utf-8')
        r.freeze(REPORT,report)
        active=r.read(ROOT/'active_research_run.json')
        active.update(scientific_close_actual_wait_exit_code=0,
            scientific_close_stdout=str(d.AUTH/'runtime_sessions/suffix_full_merge_first_close_v1/stdout.log'),
            scientific_close_stderr=str(d.AUTH/'runtime_sessions/suffix_full_merge_first_close_v1/stderr.log'),
            scientific_close_execution_registration=str(REG/'registration.json'),
            running_analysis=False,running_predictions=False,pid=None,
            complete_current_census=counts,last_accepted_merged_run=str(d.RUN))
        r.mutable(ROOT/'active_research_run.json',active)
    print('CURRENT FULL MERGE STOP/RECEIPT/ALL1059FILES RECHECKED; ADMIN NAVIGATION UPDATED',flush=True)


if __name__=='__main__': main()
