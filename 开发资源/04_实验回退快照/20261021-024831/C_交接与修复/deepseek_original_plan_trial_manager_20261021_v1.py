"""Human-authorized handoff: existing DeepSeek executes Codex's unchanged plan.

Codex scientific automation stays PAUSED. This manager only coordinates/logs;
it never executes a scientific stage itself and never kills scientific workers.
"""
import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
r=admin.r
HERE=admin.HERE
TRIAL=HERE/'deepseek_execution_trial_20261021_v1'
SID='sess_d355bd21-3bd6-4884-a0e0-0f66ac854cfe'
CONTROL=HERE/'deepseek-execution-trial-control-20261021-v1.json'
NODE=Path(r'C:\Program Files\nodejs\node.exe')
CLI=Path(r'C:\Users\Admin\AppData\Local\Programs\ZCode\resources\glm\zcode.cjs')
ENV={**dict(os.environ),
    'ZCODE_BUILTIN_PROVIDER_CONFIG_FILE':r'C:\Users\Admin\.zcode\v2\runtime\provider\windows-x86_64\3.12.3\endpoint-78d7c3bef4024722642626fe3669a799\zcode-builtin.json',
    'ZCODE_PERSONAL_PROVIDER_CONFIG_FILE':r'C:\Users\Admin\.zcode\v2\provider_config.json'}
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): ENV[k]='1'

PLAN=r'''# DeepSeek 一小时试运行：执行 Codex 原计划，禁止另定路线

## 授权性质和执行所有者
人类明确要求暂停Codex科研，让现有DeepSeek会话试运行一小时，观察它执行Codex既定计划的效果。人类随后纠正：不是让DeepSeek按自己的计划走。你仅作为原计划执行者；这是执行者更换，不是研究目标、顺序、科学方法或验收标准变更。

本次授权会话sess_d355bd21-3bd6-4884-a0e0-0f66ac854cfe（既有模型deepseek-flash不改）；本窗口内Codex不提交科研任务，automation-2保持PAUSED。原“仅额度不足才接管”的历史说明已被本次明确一小时试运行授权覆盖。不得恢复Codex定时任务、建立第二科学调度器或擅自扩大权限。

起止时间以同目录deepseek-execution-trial-control-20261021-v1.json为准，最多60分钟且不能越过原北京时间2026-10-22 00:00。每个新动作前核实时钟/control/STOP；到窗口结束不新提交科学任务或close，已提交科学块自然结束保存断点，不能强杀/清锁。新科学版本协议和块级入口须绑定min(本次trial_end,原deadline)，不改原冻结代码或原授权。

## 依次执行的原计划（不得自行改成只写建议或只做合成）

P0 接管实时准入。先核原自动化配置确为PAUSED、实时时钟/期限、全部真实进程argv、全部runner/analysis锁、Local\InnerWheelResearch20261014 mutex、追加日志，以及一次性入口使用记录。活动CP不读/hash；有在途仅监视。先正常完成一轮只读健康核对并保存证据，再开展真实阶段。你先前只读健康回合turn_411eb1db-5293-48dc-b874-c63d944fd851已completed、工具错误0，但那回合明确没有shell实时证据，不能用其文字替代本步骤。

P1 完整总体的坐标与来源链重建。以已独立闭合的v43为父依赖，沿全部6609输出文件记录/27packed（不是独立实验数）及原57基线来源，恢复完整粗细采样、容差、负控制和反例的真实坐标输入/原序投影。v43完整坐标描述对应9已解、18未解；未解不等于不可恢复，也不允许省略。沿原冻结生成代码/manifest/报告重建coarse前缀+delta以及fine/完整cross总体，逐项验证file/array SHA、坐标顺序、分组和容差；同一总体多方法引用不得当独立样本，不能拿delta digest冒充full digest。所有旧contact/edge/front字段保留为legacy未认证，不当修正真值。先代码/纯合成与原序契约检查，再新冻结source/protocol/prepare/run及独立close；严禁旧入口重跑。预期下一计划v44/v45只是候选编号，必须先确认未被使用，未实际生成不能声称存在。不是再重加总v43元数据counts。

P2 接入既有评分修复核心及完整报警来源。Codex已准备paired_interval_metric_core_v1.py和test_paired_interval_metric_core_v1.py，13测试通过（含300小总体完整笛卡尔穷举），证据paired-metric-candidate-synthetic-checks-20261021-v1.json。复用其正确部分并独立核查、必要时另新版本扩展，不要从你之前有漏洞的interval_bounds_b0.py直接恢复结论。接触时间变化必须重构首次supported confirmed alarm valid；A/B共用同一接触时间、标签和分母，分子分母联合求分式极值，保留零分母和EPS边界；Delta=insufficient_A-insufficient_B为正代表B较好。不得仅把分子区间和分母区间独立相除。跨点独立domain是几何约束的放松，只可称保守界，不称所有端点可达或修正真值。该核心仅RIGHT insufficient，不代表混淆/FP/提前量分位数全部修复。

复用在线预测必须证明完整输入/配置/方法/坐标/因果过程一致，并有足够完整确认报警序列。若原point_outputs只有first/raw/valid，不能据此重算所有新valid；按原计划另新冻结版本重建所需完整在线确认序列，不能重跑已用run，也不能用未来真值参与在线预测。保留各变体逐帧真实horizon和确认状态。明确哪些指标能复用、哪些必须新构建；不能把缺序列直接替换成旧valid、区间中点或旧nominal标签。

P3 按完整证据推进首批真实评分的冻结/准入/独立验收，然后再推广全总体。试点按原登记顺序预先固定，不能按表现择点/择赢家；必须包含选定总体完整点序及其所有不确定性。现有26116 census只涵盖存在/边/冲突，不是所有时间阈值不确定性全集。没有整段区间几何证明不把255缩为{1,2,5}。每个受影响评分/报告最终要新结果或逐项精确不受影响证明；尚未完成全总体时只能报告已完成子项，旧排名/部署安全推荐不恢复。若本窗口卡在P1或准入，就提交真实阻塞证据和下一动作，不得宣称已打通真实评分；也不得擅自改成仅写论文建议或重新规划研究。

P4 窗口结束交付。输出实际命令/开始退出时间/真实退出码、源/协议/输入输出哈希、测试、原守卫资源快照、闭合登记与receipt、完成与未完成清单。严格区分实现、提交、在途、候选、独立验收和真实评分认证。保留失败，不重试已用入口。提供HAND_BACK.md与trial_result.json（C仅行政摘要/代码/合成，真实科研资产仍在受控Z）；记录是否还有科学块自然收尾、谁拥有执行权。不要在无人复核时自动交回或恢复Codex科研。

## 原硬规则全部适用
完整规则见RESULT_REPAIR_AND_DEEPSEEK_HANDOFF_20261021_v1.md、HANDOFF.md及最新STATUS.md，后者旧ACTIVE快照已由本次PAUSED记录覆盖。
- E全部只读；E+Z两研究目录合计32GiB，Z物理预留3GiB；单科学worker/一在途，BLAS单线程。C不是复制真实数组/绕过科研预算的地方。
- 每次研究写前RAM无损编码计量+原冻结runtime fresh全量scandir；原资源/进程守卫不得改、绕、冒用。科研输出仅新Z受控run，C仅开发代码/合成/协议/行政摘要。
- 所有shell显式workdir C:\Users\Admin；Python精确C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8 -B；禁止临时python -c真实分析。
- 全部冻结源/协议/输入/结果/失败不删改搬移，旧prepare/launch/run/close禁重跑。新科学改动必须另新冻结版本、合成检查、完整父依赖准入和首次独立close。没有真实wait、签名、验收、receipt，不称通过。
- 活动CP不读/hash，有在途仅监视，不并行真实分析/输入/训练；close期间不另开含ROOT的外部监视shell，可用实际祖先管理器日志/wait和不含ROOT的通用CIM。
- 旧科学阈值/误差/角点/可靠性门一律不放宽；未知/冲突/预算不足不作负例。不按表现选点。旧标签依赖评分/排名/84配置可行性/部署推荐暂停。
- S4整体/M2/S5未完成，M2/S5不准入；全部纠错/评分/来源/整轨迹及同源分组/冻结训练协议通过才允许离线代理训练，最终测试不选参；无实际贝叶斯寻优/部署授权。本次不为一小时时间目标提前训练。
- 你此前在E新增的MD/PY全部原样保留，纳入原资源统计；不得搬走或通过排除清单逃避32GiB或完整性边界。当前不要求改变它们的冻结身份。
- 只在阶段完成、失败、需人类行动或最终交接时通知，不夸大计数；6609/27/2304都不等于修正真值认证。

## 辅助入口（不是科学准入替代）
C开发可用同目录deepseek_trial_io_v1.py：标准输入JSON{name,text}，通过RAM计量和fresh资源扫描向deepseek_execution_trial_20261021_v1/新增代码/合成文件，禁止覆盖旧文件，单件4MiB。使用精确Python和workdir C，不以该工具写真实数组。C代码经测试仍必须在Z另新冻结才可真实执行。该写入器与STOP只是额外试运行限制，不能代替原科学守卫、完整依赖核验或独立close。
'''

def csave(path,blob):
    if path.exists(): raise FileExistsError(str(path))
    if path.parent not in (HERE,TRIAL): raise ValueError('C administrative trial output required')
    r.guard(len(blob),0)
    with path.open('xb') as out: out.write(blob)
    if path.read_bytes()!=blob: raise RuntimeError('Administrative readback differs')

def status_append(text):
    path=HERE/'STATUS.md'; blob=path.read_bytes()+text.encode('utf-8')
    r.guard(len(blob),0)
    with path.open('wb') as out: out.write(blob)

def health_row():
    db=sqlite3.connect('file:C:/Users/Admin/.zcode/cli/db/db.sqlite?mode=ro',uri=True); db.row_factory=sqlite3.Row
    row=db.execute('SELECT status,tool_error_count,error_type,error_code FROM turn_usage WHERE session_id=? AND turn_id=?',
        (SID,'turn_411eb1db-5293-48dc-b874-c63d944fd851')).fetchone()
    active=db.execute("SELECT turn_id FROM turn_usage WHERE session_id=? AND status='running'",(SID,)).fetchall()
    db.close()
    if row is None or row['status']!='completed' or row['tool_error_count'] or row['error_type'] or row['error_code'] or active:
        raise RuntimeError('Completed clean health and idle target session required')
    return dict(row)

def main():
    admin.prior.parent.configure()
    r.require(r.before_deadline(),'Original cutoff')
    cfgpath=Path(r'C:\Users\Admin\.codex\automations\automation-2\automation.toml')
    cfgblob=cfgpath.read_bytes(); cfg=tomllib.loads(cfgblob.decode('utf-8-sig'))
    r.require(cfg['status']=='PAUSED','Codex scientific scheduler must stay paused')
    health=health_row()
    r.require(not TRIAL.exists() and not CONTROL.exists(),'Trial already submitted; never duplicate')
    h,_=admin.prior.parent.execution()
    with h.exclusive() as mutex:
        _,idle=admin.prior.parent.execution()
        start=dt.datetime.now(dt.timezone.utc); end=min(start+dt.timedelta(hours=1),r.DEADLINE)
        r.require(end>start,'Trial window expired')
        r.guard(1024**2,0); TRIAL.mkdir()
        control=dict(time=r.now(),trial_start_utc=start.isoformat(timespec='seconds'),trial_end_utc=end.isoformat(timespec='seconds'),
            trial_start_beijing=start.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds'),
            trial_end_beijing=end.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds'),
            session_id=SID,configured_model='deepseek-flash',execution_owner='DeepSeek trial of Codex original plan',
            codex_scientific_submissions_paused=True,codex_automation_status=cfg['status'],
            original_authorization_deadline=r.DEADLINE.isoformat(),plan_sha256=hashlib.sha256(PLAN.encode('utf-8')).hexdigest(),
            completed_clean_health=health,initial_execution=idle,initial_mutex=mutex,
            original_plan_not_deepseek_alternative=True,no_automatic_codex_scientific_resume=True,
            scientific_admission_still_required=True)
        csave(CONTROL,r.encoded(control))
        csave(HERE/'DEEPSEEK_ORIGINAL_PLAN_TRIAL_20261021_v1.md',PLAN.encode('utf-8'))
        csave(TRIAL/'automation-2.paused-before-trial.toml',cfgblob)
        csave(TRIAL/'manager_source.py',Path(__file__).read_bytes())
        csave(TRIAL/'initial_execution.json',r.encoded(control))
    status_append('\n\n## 人类要求暂停Codex并由DeepSeek执行原计划试跑一小时（'+r.now()+'）\n\n'
        '本条覆盖此前ACTIVE与“仅额度不足接管”的旧快照。automation-2已原生PAUSED，Codex停止提交科研。'
        '人类指定DeepSeek会话'+SID+'，本地ZCode会话“评估 GPT 自动化实验思路与结果”，配置模型deepseek-flash。'
        '首次只读健康turn_411eb1db-5293-48dc-b874-c63d944fd851已completed且tool_error_count0，CLI健康实际wait0；'
        '前v1/v2缺打包配置路径、v3不支持help所列allowed-tools/max-turns，均在模型回合前失败，日志和源码原样保存。'
        'v4使用原本地provider路径和plan+denylist完成只读健康，没有权限绕过。\n\n'
        '正式试运行时段北京时间'+control['trial_start_beijing']+'至'+control['trial_end_beijing']+'；'
        '唯一执行者DeepSeek，Codex不提交科研，原守卫和科学门全部保持。'
        '冻结执行清单DEEPSEEK_ORIGINAL_PLAN_TRIAL_20261021_v1.md，控制deepseek-execution-trial-control-20261021-v1.json。'
        '严格执行原P0实时准入→P1完整总体坐标/来源链新冻结独立闭合→P2既有评分核及完整报警来源→P3首批真实评分准入/独立验收→P4交付，'
        '不按DeepSeek自己的替代研究路线，不自行降为仅建议/合成。不具备准入时只能提交精确阻塞证据。'
        '一小时结束禁新科学任务/close，已提交块自然收尾，不强杀/清锁；不自动恢复Codex。'
        '结果与日志在deepseek_execution_trial_20261021_v1/；有在途先判活，活动CP不读/hash。\n')
    stopped=False
    def stop_new():
        nonlocal stopped
        if stopped: return
        stopped=True
        csave(TRIAL/'STOP_NEW_SUBMISSIONS.json',r.encoded(dict(time=r.now(),trial_end_utc=control['trial_end_utc'],
            no_new_scientific_task_or_close=True,allow_only_natural_finish_and_administrative_handback=True,
            do_not_kill_scientific_workers=True,codex_stays_paused=True)))
        print('ONE-HOUR TRIAL WINDOW CLOSED; NO NEW SUBMISSIONS; NATURAL SCIENTIFIC FINISH ONLY',flush=True)
    timer=threading.Timer(max(0,(end-dt.datetime.now(dt.timezone.utc)).total_seconds()),stop_new); timer.daemon=True; timer.start()
    last_code=None
    for wave in range(1,9):
        if stopped or dt.datetime.now(dt.timezone.utc)>=end: break
        prompt=(f'人类指定本会话执行Codex原计划的一小时试运行，第{wave}个接续回合。不要按你自己的新路线执行。'
            r'先读C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1\DEEPSEEK_ORIGINAL_PLAN_TRIAL_20261021_v1.md、'
            r'同目录deepseek-execution-trial-control-20261021-v1.json及STATUS.md最新尾部。'
            'Codex科研和automation-2已PAUSED，唯一执行者是你。窗口截止北京时间'+control['trial_end_beijing']+'。'
            '严格按P0→P1完整坐标与来源链→P2接入既有评分核与完整报警来源→P3真实评分独立验收→P4交付推进。'
            '不声称一小时不可能而自行改为建议或只跑合成；也不能为赶时间越过准入。'
            '上次完成处继续，已用科学入口不重跑，有在途仅监视；本轮开始前和每个新任务/close前核STOP与时钟。'
            '你此前建议移走/排除E新增资料不被采用：E全部只读，原样保留并计入预算。'
            '代码、测试、实际命令、资源与源/输入输出签名、闭合/receipt或明确阻塞必须可查证。'
            '所有shell workdir=C:\\Users\\Admin，Python精确原路径-X utf8 -B。'
            '回合结束给出完成/在途/阻塞及下一固定步骤；如原计划对应工作全部完成或确证无法再推进，写HAND_BACK.md和trial_result.json到C试运行目录再结束。'
            '不要恢复Codex定时任务，不扩大scope，不提前训练。')
        csave(TRIAL/f'wave-{wave:02d}-request.txt',prompt.encode('utf-8'))
        for label in ('stdout.json','stderr.log'): csave(TRIAL/f'wave-{wave:02d}-{label}',b'')
        argv=[str(NODE),str(CLI),'--resume',SID,'--cwd',r'C:\Users\Admin','--mode','build',
            '--disallowed-tools','WebFetch,WebSearch','--json','--no-color','--prompt',prompt]
        r.guard(16*1024**2,0)
        with (TRIAL/f'wave-{wave:02d}-stdout.json').open('ab') as out,(TRIAL/f'wave-{wave:02d}-stderr.log').open('ab') as err:
            child=subprocess.Popen(argv,cwd=r'C:\Users\Admin',stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                env=ENV,creationflags=subprocess.CREATE_NO_WINDOW)
            csave(TRIAL/f'wave-{wave:02d}-launched.json',r.encoded(dict(time=r.now(),pid=child.pid,session_id=SID,
                trial_end_utc=control['trial_end_utc'],no_scientific_admission_claim=True)))
            print('DEEPSEEK ORIGINAL-PLAN TRIAL WAVE '+str(wave)+' SUBMITTED PID '+str(child.pid)+' END '+control['trial_end_beijing'],flush=True)
            while True:
                try: last_code=child.wait(timeout=20); break
                except subprocess.TimeoutExpired:
                    if dt.datetime.now(dt.timezone.utc)>=end and not stopped: stop_new()
        csave(TRIAL/f'wave-{wave:02d}-exit.json',r.encoded(dict(time=r.now(),actual_wait_exit_code=last_code,pid=child.pid)))
        print('DEEPSEEK TRIAL WAVE '+str(wave)+' ACTUAL WAIT EXIT '+str(last_code),flush=True)
        if last_code or stopped or (TRIAL/'HAND_BACK.md').exists() or (TRIAL/'trial_result.json').exists(): break
        # Only a completed model call can receive another bounded continuation.
        db=sqlite3.connect('file:C:/Users/Admin/.zcode/cli/db/db.sqlite?mode=ro',uri=True)
        running=db.execute("SELECT count(*) FROM turn_usage WHERE session_id=? AND status='running'",(SID,)).fetchone()[0]; db.close()
        if running: raise RuntimeError('Session still running; cannot submit a duplicate continuation')
    timer.cancel()
    csave(TRIAL/'manager_finished.json',r.encoded(dict(time=r.now(),last_cli_actual_wait_exit_code=last_code,
        trial_start_utc=control['trial_start_utc'],trial_end_utc=control['trial_end_utc'],
        automatic_codex_resume=False,scientific_completion_not_inferred_from_cli_exit=True,
        human_review_required_before_codex_scientific_resume=True)))
    print('DEEPSEEK TRIAL CONTROLLER FINISHED; CODEX STAYS PAUSED; VERIFY SCIENTIFIC ARTIFACTS SEPARATELY',flush=True)
    return 0 if last_code==0 else 1

if __name__=='__main__': sys.exit(main())
