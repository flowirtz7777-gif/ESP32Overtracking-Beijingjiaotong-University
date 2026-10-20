"""Evidence-status and continuation guards; not a source of real evidence.

Actual signed artifacts, process inspection and the original frozen runtime
remain mandatory. A JSON boolean cannot manufacture or certify observations.
"""
from datetime import datetime

P0_REQUIRED=('system_wide_exact_argv','all_runner_analysis_locks','named_mutex_exclusive_and_release',
    'append_log_evidence','one_use_entry_history','fresh_full_resource_scan','runtime_and_deadline',
    'client_permission_channel','health_completed_without_error')

class NotAdmitted(RuntimeError): pass

def check_p0(evidence):
    missing=[key for key in P0_REQUIRED if evidence.get(key) is not True]
    if missing or evidence.get('live_scientific_processes')!=0 or evidence.get('unresolved_conflicts')!=0:
        raise NotAdmitted('P0_NOT_ADMITTED; missing='+','.join(missing)+'; no substitution with PID/zero-write/old snapshot')
    return 'P0_evidence_contract_satisfied_requires_actual_artifact_verification'

def check_p1(evidence):
    if (evidence.get('kind')!='complete_coordinate_reconstruction'
        or evidence.get('source_output_records')!=6609 or evidence.get('packed_records')!=27
        or evidence.get('full_array_reconstruction_verified') is not True
        or evidence.get('all_original_orders_groups_tolerances_controls_preserved') is not True
        or evidence.get('independent_close_actual_wait_exit_code')!=0
        or evidence.get('complete_frozen_inventory_rehashed') is not True
        or evidence.get('valid_close_receipt_binding') is not True):
        raise NotAdmitted('P1_NOT_CLOSED; paths/counts/file digests/metadata v43 are insufficient')
    return 'P1_contract_satisfied_requires_actual_artifact_verification'

def permit_next(stage,p0,p1=None):
    if stage in ('P1-real','P2-real','P3-real'): check_p0(p0)
    if stage in ('P2-real','P3-real'): check_p1(p1 or {})
    if stage not in ('P0-readonly','P1-real','P2-synthetic-prep','P2-real','P3-real','P4-administrative'):
        raise NotAdmitted('Unregistered transition')
    return True

def continuation(now,deadline,*,permission_error=None,scientific_inflight=False,complete=False):
    if permission_error: return 'STOP_AND_REPORT_PERMISSION_CHANNEL'
    if now>=deadline: return 'MONITOR_NATURAL_FINISH_ONLY' if scientific_inflight else 'STOP_NEW_SUBMISSIONS'
    if scientific_inflight: return 'MONITOR_ONLY'
    if complete: return 'HAND_BACK_FOR_REVIEW'
    return 'CONTINUE_FIXED_PLAN'

def decode_edge_mask(mask):
    if type(mask) is not int or not 0<=mask<=255: raise ValueError('Original uint8 edge bitmask required')
    return tuple(code for code in range(1,9) if mask&(1<<(code-1)))
