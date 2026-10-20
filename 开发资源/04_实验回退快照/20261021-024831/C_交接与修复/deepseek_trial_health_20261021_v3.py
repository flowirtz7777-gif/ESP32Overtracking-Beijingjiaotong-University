"""Read-only handoff health prompt to the human-named existing ZCode session."""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
r=admin.r
HERE=admin.HERE
SID='sess_d355bd21-3bd6-4884-a0e0-0f66ac854cfe'
CLI=Path(r'C:\Users\Admin\AppData\Local\Programs\ZCode\resources\glm\zcode.cjs')
NODE=Path(r'C:\Program Files\nodejs\node.exe')

def save(name,blob): admin.save(HERE/name,blob)

def main():
    admin.prior.parent.configure()
    r.require(r.before_deadline(),'Original cutoff')
    db=sqlite3.connect('file:C:/Users/Admin/.zcode/cli/db/db.sqlite?mode=ro',uri=True)
    row=db.execute('SELECT directory,title,permission FROM session WHERE id=?',(SID,)).fetchone()
    r.require(row is not None,'Named session absent')
    selection=db.execute("SELECT data FROM session_entry WHERE session_id=? AND type='runtime/model_selection'",(SID,)).fetchone()
    model=json.loads(selection[0])['modelSelection']
    r.require(model['modelId']=='deepseek-flash','Must preserve user-named DeepSeek model')
    running=db.execute("SELECT turn_id FROM turn_usage WHERE session_id=? AND status='running'",(SID,)).fetchall()
    r.require(not running,'Target session already running; no duplicate submission')
    db.close()
    h,_=admin.prior.parent.execution()
    with h.exclusive() as mutex:
        _,idle=admin.prior.parent.execution()
        prompt=(r'''人类在Codex中明确授权先暂停Codex科研，让你在本会话试运行一小时评估效果。Codex已原生PAUSED automation-2，科学进程目前无在途。
这是接管前首次只读健康回合，不是正式一小时推进任务：不要写/编辑任何项目或研究文件，不启动分析、输入构建、预测、评分、close、训练或新worker。不要把旧历史执行计数/旧评分/你之前的区间建议当已纠错认证。
请只读C:\Users\Admin\.codex\thread-recovery\20261020-context-recovery-v1\RESULT_REPAIR_AND_DEEPSEEK_HANDOFF_20261021_v1.md和STATUS.md；按需读HANDOFF.md，不读/hash任何活动CP，不全量历史追加回上下文。shell即使会话归属E也必须显式workdir C:\Users\Admin；此回合没有shell许可，缺少实时进程工具则如实说明，不用状态字段冒充进程证据。
关键更新：来源元数据v43已独立闭合（6609输出记录/27packed，其中完整坐标描述对应9已解18未解），真值基线仍v41，真实纠错评分验收0。全部规则以交接文件为准：E只读，32GiB/3GiB，单worker/一在途，逐写RAM计量及fresh全量scandir，冻存和失败不删改搬移，旧入口不重跑，原科学阈值/截止北京时间2026-10-22 00:00不变，未准入不训练。
请回复：(1)确认当前会话模型与本地读文件能力；(2)复述最重要的硬边界与当前真实进度；(3)给出一小时内优先打通评分闭环的可执行计划及证据交付清单，说明不会固定旧valid/不会无证剪边集合/配对共享真值/负分子分母联合极值及正差代表B较好；(4)明确本健康回合未启动真实任务。收到后续带明确起止时间的试运行指令才可开始。此回合必须正常完成，无错误；不要改变原模型或会话目标。''')
        argv=[str(NODE),str(CLI),'--resume',SID,'--cwd',r'C:\Users\Admin',
            '--mode','plan','--allowed-tools','Read,Glob,Grep','--max-turns','6','--json','--no-color','--prompt',prompt]
        save('deepseek-trial-health-request-20261021-v3.txt',prompt.encode('utf-8'))
        save('deepseek-trial-handoff-pending-20261021-v3.json',r.encoded(dict(time=r.now(),session_id=SID,
            human_authorized_one_hour_trial=True,session_title=row[1],model_id=model['modelId'],
            prior_session_permission=json.loads(row[2]),health_only=True,trial_clock_started=False,
            scientific_submission_authorized_by_this_health_prompt=False,execution=idle,mutex=mutex,
            codex_scientific_scheduler='PAUSED',codex_will_not_submit_science=True)))
    # App output logs are C administrative artifacts; one bounded admission reserve.
    save('deepseek-trial-health-stdout-20261021-v3.jsonl',b'')
    save('deepseek-trial-health-stderr-20261021-v3.log',b'')
    r.guard(8*1024**2,0)
    with (HERE/'deepseek-trial-health-stdout-20261021-v3.jsonl').open('ab') as out,(HERE/'deepseek-trial-health-stderr-20261021-v3.log').open('ab') as err:
        child=subprocess.Popen(argv,cwd=r'C:\Users\Admin',stdin=subprocess.DEVNULL,stdout=out,stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW,env={**dict(os.environ), 'ZCODE_BUILTIN_PROVIDER_CONFIG_FILE':r'C:\Users\Admin\AppData\Local\Programs\ZCode\resources\config\provider\zcode-builtin.json', 'ZCODE_PERSONAL_PROVIDER_CONFIG_FILE':r'C:\Users\Admin\.zcode\v2\provider_config.json'})
        save('deepseek-trial-health-launched-20261021-v3.json',r.encoded(dict(time=r.now(),pid=child.pid,session_id=SID,
            mode='plan',allowed_tools=['Read','Glob','Grep'],max_turns=6,read_only_health_not_trial_start=True)))
        print('DEEPSEEK READ-ONLY HEALTH SUBMITTED PID '+str(child.pid),flush=True)
        code=child.wait()
    save('deepseek-trial-health-exit-20261021-v3.json',r.encoded(dict(time=r.now(),actual_wait_exit_code=code,pid=child.pid)))
    print('DEEPSEEK READ-ONLY HEALTH ACTUAL WAIT EXIT '+str(code),flush=True)
    return code

if __name__=='__main__': sys.exit(main())
