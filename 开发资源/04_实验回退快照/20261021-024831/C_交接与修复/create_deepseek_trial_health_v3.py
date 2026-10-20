"""Use the resolver's documented active+personal provider pair; preserve v1/v2 failures."""
import continue_remediation_admin_20261021_v2 as admin
p=admin.HERE/'deepseek_trial_health_20261021_v2.py'
text=p.read_text(encoding='utf-8').replace('20261021-v2','20261021-v3')
text=text.replace("'ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE':", "'ZCODE_BUILTIN_PROVIDER_CONFIG_FILE':")
compile(text,'deepseek_trial_health_20261021_v3.py','exec')
admin.save(admin.HERE/'deepseek_trial_health_20261021_v3.py',text.encode('utf-8'))
print('New administrative v3 provider-pair launcher created; no research/source/guard changes')
