"""New C-only candidate version; preserve every v1 source and test."""
import continue_remediation_admin_20261021_v2 as admin
source=(admin.HERE/'paired_interval_metric_core_v1.py').read_text(encoding='utf-8')
source=source.replace('def insufficiency(contact,alarms,eps=F(1,10**9),lead=F(1)):',
    'def insufficiency(contact,alarms,eps=F(1,10**9),lead=F(1),*,valid_alarm_start):')
source=source.replace('supported=[a.time for a in alarms if a.time-eps<=contact<=a.time+a.horizon+eps]',
    'supported=[a.time for a in alarms if (valid_alarm_start is None or a.time>=q(valid_alarm_start)-eps)\n        and a.time-eps<=contact<=a.time+a.horizon+eps]')
source=source.replace('eps=F(1,10**9),lead=1,timelines_complete=False):',
    'eps=F(1,10**9),lead=1,timelines_complete=False,valid_alarm_start):')
source=source.replace("if not timelines_complete: raise ValueError('Complete confirmed timelines required; first/raw/valid alone insufficient')",
    "if timelines_complete is not True: raise ValueError('Complete confirmed timelines required; first/raw/valid alone insufficient')\n    if type(can_be_noncontact) is not bool: raise ValueError('Explicit contact-domain boolean required')\n    alarms_a,alarms_b=tuple(alarms_a),tuple(alarms_b)")
source=source.replace('not isinstance(e,int) for e in edge_codes','not isinstance(e,int) or not 1<=e<=8 for e in edge_codes')
source=source.replace('insufficiency(contact,alarms_a,eps,lead)-insufficiency(contact,alarms_b,eps,lead)',
    'insufficiency(contact,alarms_a,eps,lead,valid_alarm_start=valid_alarm_start)-insufficiency(contact,alarms_b,eps,lead,valid_alarm_start=valid_alarm_start)')
source=source.replace("if base_denominator==0 and base_numerator!=0: raise ValueError('Nonzero numerator over empty base')",
    "if abs(base_numerator)>base_denominator: raise ValueError('Paired base numerator must be within eligible denominator')")
source=source.replace('"""Synthetic-only candidate for conservative paired RIGHT insufficiency bounds.',
    '"""Version2 synthetic-only candidate for conservative paired RIGHT insufficiency bounds.\n\nExplicit valid_alarm_start must match the exact frozen evaluator: 2 for scored\nevaluator, None only for the unscored legacy semantics. Atomic edge codes must\nbe1..8: decode original uint8 masks externally;255 is not one face. Rational\ncomparisons are not automatically a bitwise floating-point equivalence proof.')
compile(source,'paired_interval_metric_core_v2.py','exec')
admin.save(admin.HERE/'paired_interval_metric_core_v2.py',source.encode('utf-8'))
print('New v2 core created: explicit scored gate, edge mask distinction, iterator preservation, valid paired base')
