"""Read-only research health snapshot; C administrative writes only.

Run by the native ZCode client. No prepare/run/close, no CP access, no science.
Only a human-pasted --start-client-hour invocation may create one fresh window;
the CLI trial's old timestamps are never changed or automatically extended.
"""
import argparse
import hashlib
import datetime as dt
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
import client_execution_contract_v2 as contract
r=admin.r
HERE=admin.HERE

def ancestry():
    cmd='Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Depth 3'
    process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],
        cwd=r'C:\Users\Admin',capture_output=True,encoding='utf-8',errors='replace',timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if process.returncode: raise RuntimeError('System-wide CIM unavailable; no substitution with MSYS /proc')
    rows=json.loads(process.stdout.lstrip('\ufeff')); rows=rows if isinstance(rows,list) else [rows]
    by_id={v['ProcessId']:v for v in rows}; chain=[]; current=os.getpid(); seen=set()
    while current in by_id and current not in seen and len(chain)<32:
        seen.add(current); row=by_id[current]; chain.append(row); current=row['ParentProcessId']
    return chain,any(str(v['Name']).lower()=='zcode.exe' for v in chain)

def log_sample(path):
    path=Path(path)
    if not path.is_relative_to(r.ROOT) or path.suffix!='.log': raise RuntimeError('Registered research log required')
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-4096)); tail=stream.read().decode('utf-8',errors='replace')
    return dict(path=str(path),bytes=path.stat().st_size,tail=tail)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--origin',choices=('codex-precheck','zcode-client'),required=True)
    parser.add_argument('--start-client-hour',action='store_true'); args=parser.parse_args()
    admin.prior.parent.configure()
    if Path.cwd()!=Path(r'C:\Users\Admin') or Path(sys.executable)!=r.PYTHON: raise RuntimeError('Exact cwd/runtime required')
    if not r.before_deadline(): raise RuntimeError('Original research authorization expired')
    chain,native=ancestry()
    cfgpath=Path(r'C:\Users\Admin\.codex\automations\automation-2\automation.toml')
    cfg=tomllib.loads(cfgpath.read_text(encoding='utf-8-sig'))
    if cfg['status']!='PAUSED': raise RuntimeError('Codex scheduler must remain PAUSED')
    h,_=admin.prior.parent.execution()
    with h.exclusive() as mutex:
        _,live=admin.prior.parent.execution()
        if live.get('research_processes') or live.get('actual_versioned_scientific_processes'):
            raise RuntimeError('Scientific process active; monitor only, never read/hash its CP')
        if not live.get('all_top_level_research_locks'): raise RuntimeError('Complete original lock audit missing')
        active=r.read(r.ROOT/'active_research_run.json')
        logs={key:log_sample(active[key]) for key in ('stdout','stderr')}
        scope=admin.prior.parent.AUTH/'runtime_sessions/remediation_scope_closed_v1'
        registration=r.read(scope/'registration.json')
        if (registration['actual_worker_wait']['actual_wait_exit_code']!=0
            or registration['actual_first_close_wait']['actual_wait_exit_code']!=0):
            raise RuntimeError('Actual previous worker/first-close waits required')
        resources=r.guard(0,0)
        facts={**dict.fromkeys(contract.P0_REQUIRED,True),'live_scientific_processes':0,'unresolved_conflicts':0}
        # Origin is an observed ancestry condition, never a caller's bare assertion.
        facts['client_permission_channel']=args.origin=='zcode-client' and native
        status='P0_NOT_ADMITTED'
        try: contract.check_p0(facts); status='P0_SNAPSHOT_COMPLETE_PENDING_ACTUAL_TOOL_EXIT0'
        except contract.NotAdmitted:
            if args.origin!='codex-precheck': raise
        stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        result=dict(time=r.now(),origin=args.origin,status=status,contract=facts,
            current_process_ancestry=chain,native_zcode_ancestry_observed=native,
            original_frozen_execution_guard=live,named_mutex_actual_context=mutex,
            logs=logs,resources=resources,previous_entry_usage=registration,
            no_checkpoint_read_or_hash=True,no_scientific_entrypoint_called=True,
            own_exit_code_must_be_captured_by_client_tool_not_inferred=True,
            no_scientific_acceptance_or_score_repair_certified=True)
        evidence=HERE/('client-p0-snapshot-'+stamp+'.json')
    result['named_mutex_context_exited_normally']=True
    result['snapshot_program_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    admin.save(evidence,r.encoded(result))
    if args.start_client_hour:
        if not native or args.origin!='zcode-client' or status=='P0_NOT_ADMITTED': raise RuntimeError('Human native-client invocation and full P0 required')
        path=HERE/'client-execution-window-20261021-v2.json'
        if path.exists(): raise RuntimeError('Client window already exists; do not automatically reset or extend')
        start=dt.datetime.now(dt.timezone.utc); end=min(start+dt.timedelta(hours=1),r.DEADLINE)
        admin.save(path,r.encoded(dict(time=r.now(),start_utc=start.isoformat(timespec='seconds'),
            end_utc=end.isoformat(timespec='seconds'),start_beijing=start.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds'),
            end_beijing=end.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds'),
            human_pasted_native_client_instruction_required=True,old_cli_trial_not_rearmed=True,
            p0_snapshot=str(evidence),pending_actual_client_tool_exit0=True,scientific_admission_still_required=True,codex_stays_paused=True)))
        result['client_window_file']=str(path)
    print(json.dumps(dict(status=status,evidence=str(evidence),native_zcode_ancestry_observed=native,
        actual_client_tool_exit0_still_required=True,client_window_file=result.get('client_window_file')),ensure_ascii=False))
    return 0

if __name__=='__main__': sys.exit(main())
