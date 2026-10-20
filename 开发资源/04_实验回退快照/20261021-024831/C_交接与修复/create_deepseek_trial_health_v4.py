"""Use parser-supported denylist; never remove read-only health restrictions."""
import continue_remediation_admin_20261021_v2 as admin
text=(admin.HERE/'deepseek_trial_health_20261021_v3.py').read_text(encoding='utf-8').replace('20261021-v3','20261021-v4')
old="'--mode','plan','--allowed-tools','Read,Glob,Grep','--max-turns','6','--json','--no-color','--prompt',prompt]"
new="'--mode','plan','--disallowed-tools','Bash,Write,Edit,MultiEdit,NotebookEdit,Task,Agent,WebFetch,WebSearch','--json','--no-color','--prompt',prompt]"
if text.count(old)!=1: raise RuntimeError('Exact unsupported-flag site required')
text=text.replace(old,new).replace("allowed_tools=['Read','Glob','Grep'],max_turns=6", "denied_tools=['Bash','Write','Edit','MultiEdit','NotebookEdit','Task','Agent','WebFetch','WebSearch']")
compile(text,'deepseek_trial_health_20261021_v4.py','exec')
admin.save(admin.HERE/'deepseek_trial_health_20261021_v4.py',text.encode('utf-8'))
print('New v4 read-only launcher; no model/scientific/permission bypass')
