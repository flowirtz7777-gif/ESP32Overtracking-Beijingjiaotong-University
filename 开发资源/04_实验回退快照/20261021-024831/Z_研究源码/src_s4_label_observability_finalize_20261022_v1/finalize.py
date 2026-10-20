"""Pure-file/exit-evidence finalization; never repeats scientific close."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src_s4_label_observability_20261022_v1'))
import observability as science

r = science.r
PARENT = science.RUN
AUTH = science.AUTH
SESSION = AUTH / 'runtime_sessions/label_observability_first_close_v1'
FAILURE = AUTH / 'runtime_sessions/label_observability_postcheck_failure_v1'
RUN = ROOT / 'runs/resume_20261022_0000_label_observability_admin_finalize_v1'
PROTOCOL = ROOT / 'protocol_label_observability_admin_finalize_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v20.json'


def configure():
    science.configure()
    r.RUN, r.RUN_CAP = RUN, 64 * 1024**2


configure()


def execution():
    try:
        return science.execution()
    finally:
        configure()


def monitor_failure(stderr, session):
    marker = 'RuntimeError: Research processes remain: '
    if marker not in stderr or '_, after = execution()' not in stderr:
        raise ValueError('Failure was not the known post-scientific execution evidence check')
    processes = json.loads(stderr.rsplit(marker, 1)[1].strip())
    if len(processes) != 1:
        raise ValueError('Do not reinterpret any additional related process')
    monitor = processes[0]
    tail = ("Get-Content -LiteralPath '" + str(session / 'stdout.log') + "' -Tail 3\n"
        + "Get-Content -LiteralPath '" + str(session / 'stderr.log') + "' -Tail 12\n"
        + "Get-CimInstance Win32_Process -Filter 'ProcessId=37204' | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine | ConvertTo-Json\"")
    if (monitor['Name'].lower() != 'pwsh.exe' or not monitor['ExecutablePath'].lower().endswith('powershell\\pwsh.exe')
            or not monitor['CommandLine'].endswith(tail)):
        raise ValueError('Only the exact recorded read-only log/CIM tool invocation is explained')
    return monitor


def eligible(cp, accepted, exit_record, stdout):
    if (exit_record['actual_wait_exit_code'] != 1 or cp['status'] != 'complete_pending_independent_observability_close'
            or accepted['status'] != 'all_remaining_label_post_prefix_diagnostics_independently_checked_no_relabeling'
            or not accepted['labels_and_prefix_proofs_unchanged'] or accepted['truth_asset_promotion_allowed']
            or accepted['accounting'] != cp['accounting'] or len(cp['completed']) != 39
            or set(accepted['checks']) != set(cp['completed'])):
        raise ValueError('Full scientific acceptance must already exist; do not create or infer one')
    prefix = 'CLOSE CHECKED ALL UNKNOWN DIAGNOSTIC ROWS GROUP '
    logged = [line[len(prefix):] for line in stdout.splitlines() if line.startswith(prefix)]
    if len(logged) != 39 or set(logged) != set(cp['completed']):
        raise ValueError('Every original completed independent group must be logged exactly once')
    for name, value in (('geometry_groups', 39), ('dataset_files', 57), ('group_unique_scope_points', 43670),
                        ('selected_point_file_records', 51606), ('group_point_path_records_not_independent_samples', 87340)):
        if accepted['accounting'][name] != value:
            raise ValueError('Only the complete original frozen diagnostic scope may be finalized')
    for key, entry in cp['completed'].items():
        for tag in ('oldpath', 'independent'):
            if accepted['checks'][key][tag]['all_records'] != entry['group']['summary']['points']:
                raise ValueError('Every selected diagnostic record must have been checked')
    return accepted['accounting']


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')}
    paths.update(PARENT / name for name in ('checkpoint.json', 'acceptance.json', 'source_manifest.json'))
    paths.update(p for p in SESSION.rglob('*') if p.is_file())
    paths.update(p for p in FAILURE.rglob('*') if p.is_file())
    paths.update(SOURCE.glob('*.py'))
    paths.add(PROTOCOL)
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def prepare():
    r.require(not RUN.exists() and not PROTOCOL.exists() and not PLAN.exists(), 'Administrative version already attempted')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        science.verify()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True, encoding='utf-8')
        r.require(tests.returncode == 0, 'Pure-file administrative tests failed: ' + tests.stderr)
        protocol = {'version': 'observability-existing-scientific-acceptance-pure-file-administrative-finalize-v1',
            'original_scientific_close_exit_code': 1, 'original_scientific_close_not_repeated': True,
            'original_close_receipt_must_remain_absent': True, 'no_parent_files_modified': True,
            'new_array_decodes': 0, 'new_geometry_queries': 0, 'new_labels_or_predictions': 0,
            'old_execution_guard_unchanged_and_required_to_pass_now': True,
            'known_incident': 'unrecognized concurrent read-only log/CIM shell conservatively rejected by unchanged guard',
            'not_a_scientific_counterexample': True, 'administrative_receipt_location': str(RUN / 'receipt.json')}
        inventory = {p.relative_to(PARENT).as_posix(): r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.batch([(PROTOCOL, r.encoded(protocol)), (RUN / 'parent_files_sha256.json', r.encoded(inventory)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(48 * 1024**2, 48 * 1024**2)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))]
            + [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('PURE FILE ADMINISTRATIVE FINALIZATION PREPARED', flush=True)


def finalize():
    r.require(not (RUN / 'receipt.json').exists() and not PLAN.exists(), 'Administrative finalize already attempted')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        science.verify()
        expected = r.read(RUN / 'source_manifest.json')
        r.require(signature() == expected, 'Frozen administrative inputs changed')
        for rel, digest in expected.items():
            r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Frozen administrative source copy differs')
        inventory = r.read(RUN / 'parent_files_sha256.json')
        r.require({p.relative_to(PARENT).as_posix() for p in PARENT.rglob('*') if p.is_file()} == set(inventory),
                  'Original scientific run gained or lost files')
        for rel, digest in inventory.items():
            r.require(r.file_hash(PARENT / rel) == digest, 'Original scientific bytes changed')
        r.require(not (PARENT / 'close_receipt.json').exists(), 'Do not replace or fake the original receipt')
        cp, accepted = r.read(PARENT / 'checkpoint.json'), r.read(PARENT / 'acceptance.json')
        r.require(accepted['checkpoint_sha256'] == r.file_hash(PARENT / 'checkpoint.json')
                  and accepted['source_signature'] == science.signature(), 'Original independent acceptance binding differs')
        exit_record = r.read(SESSION / 'exit.json')
        counts = eligible(cp, accepted, exit_record, (SESSION / 'stdout.log').read_text('utf-8'))
        monitor = monitor_failure((SESSION / 'stderr.log').read_text('utf-8'), SESSION)
        hashes = {n: r.file_hash(PARENT / n) for n in ('checkpoint.json', 'acceptance.json', 'source_manifest.json')}
        receipt = {'time': r.now(), 'status': 'existing_full_scientific_acceptance_administratively_finalized_after_monitor_rejection',
            'original_scientific_run': str(PARENT), 'original_scientific_hashes': hashes,
            'original_scientific_close_exit': exit_record, 'original_close_receipt_remains_absent': True,
            'explained_original_related_process': monitor, 'original_guard_not_modified_or_bypassed': True,
            'execution': idle, 'mutex': mutex, 'all_normal_runner_analysis_stopped': True,
            'new_array_decodes': 0, 'new_geometry_queries': 0, 'new_scientific_analyses': 0,
            'accounting_from_existing_scientific_acceptance_only': counts, 'truth_asset_promotion_allowed': False,
            'corrected_truth_revalidated_prediction_jobs': 0, 'resources': r.resources(), 'source_signature': expected}
    with h.exclusive() as released:
        _, after = execution()
    receipt.update(execution_after=after, mutex_reacquired_and_released=released)
    plan = {**r.read(science.PLAN), 'version': '20261022-0000-v20-observability-pure-file-administrative-recovery',
        'stage_status': 'full_unknown_diagnostic_scientific_acceptance_present_admin_finalized_separately',
        'scientific_acceptance_exists': True, 'scientific_acceptance_scope': 'complete remaining-label diagnostic only',
        'original_close_exit_code': 1, 'original_close_receipt_remains_absent': True,
        'administrative_finalize_receipt': str(RUN / 'receipt.json'), 'diagnostic_accounting': counts,
        'next_action': 'new version tighter valid witness/time/edge proofs where possible; all unknowns retained; expanded populations and score repairs pending'}
    report = ('# Existing Observability Acceptance: Separate Administrative Finalization\n\n'
        'All scientific checks and acceptance were already written. Original close exited 1 only when the unchanged '
        'post-check guard conservatively rejected a concurrent read-only log/CIM shell. All original bytes and failure '
        'evidence retained, no original close_receipt created and no old entrypoint repeated. The unmodified guard now '
        'passes, real scientific processes are absent, normal locks stopped, mutex acquired/released twice. '
        'This new version only verifies raw file hashes and JSON execution records; zero array decodes, GEOS queries, '
        'label calculations or predictions. The receipt is separate and is not an old-run success rewrite.\n\n'
        + str(counts) + '\n\nHypothetical same-midpoint spatial-only rules do not prove global '
        'nonidentifiability or repaired labels. All original labels, prefixes, predictions and scores unchanged.\n').encode('utf-8')
    r.batch([(RUN / 'receipt.json', r.encoded(receipt)), (PLAN, r.encoded(plan)),
        (ROOT / 'reports/label_observability_admin_finalize_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='label_observability_scientific_acceptance_separately_admin_finalized', pid=None,
        running_analysis=False, plan=str(PLAN), next_action=plan['next_action'],
        administrative_finalize_receipt=str(RUN / 'receipt.json'), original_scientific_close_exit_code=1,
        original_scientific_close_receipt_absent=True)
    r.mutable(ROOT / 'active_research_run.json', active)
    print(json.dumps({'administrative_receipt': str(RUN / 'receipt.json'), 'receipt_sha256': r.file_hash(RUN / 'receipt.json'),
                      'original_scientific_hashes': hashes, 'new_geometry_queries': 0}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'finalize'))
    globals()[parser.parse_args().action]()
