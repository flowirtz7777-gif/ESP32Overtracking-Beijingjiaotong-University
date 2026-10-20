"""C-only administrative records; original research write boundary remains unchanged."""
import sys
from pathlib import Path
import continue_remediation_20261021_v1 as prior
r=prior.r
HERE=prior.HERE

def save(path,blob):
    if not isinstance(blob,bytes): raise TypeError('Encode in RAM first')
    r.require(path.parent==HERE and not path.exists(),'New C administrative record required')
    r.guard(len(blob),0)
    with path.open('xb') as target: target.write(blob)

def main():
    prior.parent.configure()
    r.require(r.before_deadline(),'Cutoff')
    h,_=prior.parent.execution()
    with h.exclusive() as mutex:
        _,idle=prior.parent.execution()
        before=Path(r'C:\Users\Admin\.codex\automations\automation-2\automation.toml').read_bytes()
        evidence=dict(time=r.now(),execution=idle,mutex=mutex,human_authorized_resume_and_prompt_update=True,
            deepseek_entry='existing webpage/client',deepseek_local_execution_bridge_verified=False,
            automatic_fallback_enabled=False,controller='Codex thread 01a15939-12ba-77b2-aa63-ffb436065993',
            deadline='2026-10-22T00:00:00+08:00',preserve_existing_interval_minutes=15,
            original_automation_remains_paused=True,previous_admin_attempt=dict(exit_code=1,
                reason='Original runtime rejected C administrative destination; no record written, no scientific entrypoint used',
                original_guard_unchanged=True,source='continue_remediation_20261021_v1.py'))
        for name,blob in (
            ('automation-before-result-repair-20261021-v2.toml',before),
            ('RESULT_REPAIR_AND_DEEPSEEK_HANDOFF_20261021_v1.md',prior.HANDOFF.encode('utf-8')),
            ('automation-result-repair-prompt-20261021-v1.txt',prior.PROMPT.encode('utf-8')),
            ('result-repair-authority-20261021-v2.json',r.encoded(evidence))): save(HERE/name,blob)
    print('C ADMIN RECORDS SAVED WITH FRESH RESOURCE SCANS; RESEARCH GUARD UNCHANGED',flush=True)

if __name__=='__main__': main()
