"""Preserve v2 precheck; write evidence only after mutex release completes."""
import continue_remediation_admin_20261021_v2 as admin
text=(admin.HERE/'client_readonly_admission_check_v2.py').read_text(encoding='utf-8')
text=text.replace('import argparse\n','import argparse\nimport hashlib\n')
old="        admin.save(evidence,r.encoded(result))\n    if args.start_client_hour:"
new="    result['named_mutex_context_exited_normally']=True\n    result['snapshot_program_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()\n    admin.save(evidence,r.encoded(result))\n    if args.start_client_hour:"
if text.count(old)!=1: raise RuntimeError('Exact post-mutex publication site required')
text=text.replace(old,new).replace('p0_snapshot=str(evidence),scientific_admission_still_required=True',
    'p0_snapshot=str(evidence),pending_actual_client_tool_exit0=True,scientific_admission_still_required=True')
compile(text,'client_readonly_admission_check_v3.py','exec')
admin.save(admin.HERE/'client_readonly_admission_check_v3.py',text.encode('utf-8'))
print('v3 health evidence published only after original mutex context exits; source digest bound')
