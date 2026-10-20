"""Bounded C-only scratch writer for the one-hour delegated execution trial.

Scientific artifacts remain subject to the unchanged frozen Z research runtime.
No data-array copying to C, no E writes, no science execution in this helper.
"""
import datetime as dt
import json
import sys
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
r=admin.r
HERE=admin.HERE
CONTROL=HERE/'deepseek-execution-trial-control-20261021-v1.json'
TRIAL=HERE/'deepseek_execution_trial_20261021_v1'

def check_window():
    control=json.loads(CONTROL.read_text(encoding='utf-8'))
    end=dt.datetime.fromisoformat(control['trial_end_utc'])
    if dt.datetime.now(dt.timezone.utc)>=end or (TRIAL/'STOP_NEW_SUBMISSIONS.json').exists():
        raise RuntimeError('One-hour trial ended; no new scientific task/close or development payload')
    return control

def put(name,text):
    check_window()
    rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts or len(rel.parts)!=1: raise ValueError('One C trial member name required')
    path=TRIAL/rel
    if path.exists(): raise FileExistsError('Keep every previous version/failure; use a new filename')
    blob=text.encode('utf-8')
    if len(blob)>4*1024**2: raise ValueError('Code/protocol/synthetic output only, no real arrays in C')
    r.guard(len(blob),0)
    with path.open('xb') as out: out.write(blob)
    if path.read_bytes()!=blob: raise RuntimeError('Full C write readback differs')
    return str(path)

if __name__=='__main__':
    value=json.load(sys.stdin)
    print(put(value['name'],value['text']))
