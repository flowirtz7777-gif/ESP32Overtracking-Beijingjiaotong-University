"""New C launcher revision using the installed desktop's bundled provider file."""
from pathlib import Path
import continue_remediation_admin_20261021_v2 as admin
p=admin.HERE/'deepseek_trial_health_20261021_v1.py'
text=p.read_text(encoding='utf-8').replace('20261021-v1','20261021-v2')
old='creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ))'
new="creationflags=subprocess.CREATE_NO_WINDOW,env={**dict(os.environ), 'ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE':r'C:\\Users\\Admin\\AppData\\Local\\Programs\\ZCode\\resources\\config\\provider\\zcode-builtin.json', 'ZCODE_PERSONAL_PROVIDER_CONFIG_FILE':r'C:\\Users\\Admin\\.zcode\\v2\\provider_config.json'})"
if text.count(old)!=1: raise RuntimeError('Exact launcher environment site required')
text=text.replace(old,new)
compile(text,'deepseek_trial_health_20261021_v2.py','exec')
admin.save(admin.HERE/'deepseek_trial_health_20261021_v2.py',text.encode('utf-8'))
print('New administrative launcher v2 created; v1 missing bundled-config failure preserved')
