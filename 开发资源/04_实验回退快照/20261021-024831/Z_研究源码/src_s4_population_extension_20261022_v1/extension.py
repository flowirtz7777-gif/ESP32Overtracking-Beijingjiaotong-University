"""Explicitly renewed, exact-reuse continuation; never calls historical entrypoints."""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import traceback

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
sys.path.insert(0, str(ROOT / 'src_s4_population_recovery_20261019_v1'))
import recovery as previous
import numpy as np

base, r = previous.base, previous.r
admin = previous.follow.admin.prior
PARENT = previous.RUN
OLD_AUTH = ROOT / 'runs/resume_20261019_0800_authorization_v1'
AUTH = ROOT / 'runs/resume_20261022_0000_truth_authorization_v1'
RUN = ROOT / 'runs/resume_20261022_0000_population_extension_v1'
CLOSE = ROOT / 'runs/authorization_boundary_20261020_0000_renewed_v1'
PROTOCOL = ROOT / 'protocol_population_extension_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v1.json'
OVERLAY = ROOT / 'research_validity_overlay_20261020_v1.json'
SESSION = AUTH / 'runtime_sessions/population_extension_launch_v1'
CONFIG = Path(r'C:\Users\Admin\.codex\automations\automation-2\automation.toml')
LEGACY = Path(r'C:\Users\Admin\.codex\automations\automation\automation.toml')
DEADLINE = dt.datetime(2026, 10, 21, 16, tzinfo=dt.timezone.utc)
DEADLINE_LOCAL = '2026-10-22T00:00:00+08:00'
CAP = 32 * 1024**3
RESERVATION = 480 * 1024**2
LEDGER = {'formal': 2238, 'accepted_diagnostics': 66, 'numeric_records': 2304}


def configure():
    r.RUN, r.AUTH, r.RUN_CAP = RUN, AUTH, 512 * 1024**2
    r.CAP, r.RESERVE, r.DEADLINE, r.tree_bytes = CAP, 3 * 1024**3, DEADLINE, base.scan_size


configure()


def execution():
    r.AUTH = OLD_AUTH
    try:
        return admin.stopped_evidence()
    finally:
        configure()


def check_parent(cp):
    r.require(cp['status'] == 'stopped_failure_or_deadline' and
              '24:00 new population group submission cutoff' in cp.get('failure', ''),
              'Parent must have stopped at its unchanged deadline')
    r.require(len(cp['completed']) == 23 and len(cp['exact_reused_groups']) == 12 and
              len(cp['new_generated_groups']) == 11, 'Stopped parent accounting differs')
    ids = [key for entry in cp['completed'].values() for key in entry['datasets']]
    r.require(len(ids) == len(set(ids)) == 41, 'Every parent dataset must be unique')
    r.require(not (PARENT / 'acceptance.json').exists(), 'Parent partial run is not independently accepted')


def read_parent(expected=None):
    if expected is not None:
        r.require(r.file_hash(PARENT / 'checkpoint.json') == expected, 'Stopped parent CP changed')
    cp = r.read(PARENT / 'checkpoint.json')
    check_parent(cp)
    previous.verify()
    previous.gate()
    configure()
    return cp


def signature():
    paths = [ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')]
    paths += [*SOURCE.glob('*.py'), PROTOCOL, PLAN, OVERLAY, AUTH / 'authorization.json',
              PARENT / 'checkpoint.json', PARENT / 'source_manifest.json', CLOSE / 'receipt.json']
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(set(paths))}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen extension source or dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Extension source snapshot differs')
    for rel, digest in r.read(RUN / 'parent_files_sha256.json').items():
        r.require(r.file_hash(PARENT / rel) == digest, 'Stopped parent asset changed')


def packed(value):
    blob = r.encoded(value)
    compressed = gzip.compress(blob, mtime=0)
    r.require(gzip.decompress(compressed) == blob, 'Lossless administrative RAM encoding differs')
    return compressed


def verify_completed_files(cp):
    for key, entry in cp['completed'].items():
        folders = [(PARENT / 'groups' / key, entry['group'])]
        folders += [(PARENT / 'datasets' / dataset_id, record) for dataset_id, record in entry['datasets'].items()]
        for folder, saved in folders:
            r.require(r.file_hash(folder / 'result.json') == saved['result_sha256'], 'Parent CP/report differs')
            record = r.read(folder / 'result.json')
            r.require(r.file_hash(folder / 'arrays.npz') == record['npz_sha256'], 'Parent NPZ file differs')
            r.require(record['summary'] == saved['summary'], 'Parent CP/summary differs')


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in
        (AUTH, RUN, CLOSE, PROTOCOL, PLAN, OVERLAY)), 'Extension already attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        cp = read_parent()
        verify_completed_files(cp)
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin',
            capture_output=True, encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Pre-freeze extension tests failed: ' + tests.stderr)
        current_blob, legacy_blob = CONFIG.read_bytes(), LEGACY.read_bytes()
        current, legacy = tomllib.loads(current_blob.decode('utf-8-sig')), tomllib.loads(legacy_blob.decode('utf-8-sig'))
        r.require(current['id'] == 'automation-2' and current['created_at'] == 1792412413756
                  and current['status'] == 'ACTIVE' and legacy['status'] == 'PAUSED', 'Automation identity differs')
        print('RENEWAL ADMIN: stopped parent 23 groups / 41 files; complete E/Z SHA snapshot', flush=True)
        whole = {'Z': admin.file_snapshot(ROOT, CLOSE), 'E': admin.file_snapshot(base.E_ROOT, None)}
        r.AUTH = OLD_AUTH
        try:
            registered = admin.check_registered_files(whole)
        finally:
            configure()
        for folder in ('authorization_close_20261019_0800_v2', 'authorization_close_20261019_1200_v1'):
            prior_close = ROOT / 'runs' / folder
            for rel, metadata in r.read(prior_close / 'final_file_manifest.json')['files'].items():
                r.require(whole['Z'][(prior_close / rel).relative_to(ROOT).as_posix()]['sha256'] == metadata['sha256'],
                          'Prior sealed administrative evidence differs')
        parent_hashes = {p.relative_to(PARENT).as_posix(): r.file_hash(p)
                         for p in sorted(PARENT.rglob('*')) if p.is_file()}
        digest = parent_hashes['checkpoint.json']
        receipt = {'time': r.now(), 'status': 'old_deadline_boundary_files_checked_new_human_authorization_received',
            'old_deadline': '2026-10-20T00:00:00+08:00', 'new_deadline': DEADLINE_LOCAL,
            'old_worker_stop': r.read(PARENT / 'runner_lock.json'), 'execution': idle, 'mutex': mutex,
            'parent_checkpoint_sha256': digest, 'parent_generated_groups': 23, 'parent_generated_dataset_files': 41,
            'old_authorization_added': {'formal': 0, 'accepted_diagnostics': 0, 'new_generated_baseline_files': 11},
            'historical_ledger': LEDGER, 'corrected_truth_revalidated_prediction_jobs': 0,
            'registered_individual_sha_checks': registered['individual_sha_checks'],
            'file_counts': {k: len(v) for k, v in whole.items()}, 'old_scientific_close_not_called': True,
            'no_array_decode_or_metric_recompute_in_administrative_snapshot': True,
            'no_fake_old_final_close_or_heartbeat_deletion': True,
            'existing_monitor_updated_in_place_for_explicit_renewal': True,
            'file_integrity_not_scientific_acceptance': True}
        authorization = {'time': r.now(), 'status': 'explicit_human_renewal', 'deadline': DEADLINE_LOCAL,
            'deadline_utc': DEADLINE.isoformat(), 'literal_tomorrow_resolved_from_client_date': '2026-10-20',
            'human_request': '截止时间调整到明天24:00，今天不计额度全力实验，推进进度',
            'human_quota_clarification': '不限制计算时长或实验批次，保留磁盘预算',
            'human_disk_expansion_confirmation': '提高到32 GiB',
            'total_E_Z_research_cap_bytes': CAP, 'Z_physical_reserve_bytes': r.RESERVE,
            'E_read_only': True, 'scientific_workers': 1, 'inflight': 1,
            'no_batch_count_ceiling_within_deadline_and_resource_gates': True,
            'scientific_reliability_gates_unchanged': True, 'new_formal': 0, 'new_accepted_diagnostics': 0,
            'prior_deadline_boundary_receipt': str(CLOSE / 'receipt.json'),
            'priority': 'all affected truth assets, expanded populations and dependent scores; no winner tuning',
            'M2_allowed': False, 'S5_allowed': False, 'automatic_extension_allowed': False}
        protocol = {**r.read(previous.PROTOCOL), 'version': 'renewed-all-baseline-exact-reuse-extension-v1',
            'deadline': DEADLINE_LOCAL, 'parent_run': str(PARENT), 'parent_cp_sha256': digest,
            'reuse_complete_group_ids': list(cp['completed']), 'reuse_groups': 23, 'reuse_dataset_files': 41,
            'missing_groups': 16, 'missing_dataset_files': 16, 'workers': 1, 'inflight': 1,
            'total_E_Z_cap_bytes': CAP, 'Z_reserve_bytes': r.RESERVE,
            'new_groups_first_time_prefix_audit_still_required': True,
            'prefix_proven_old_groups': 12, 'all_other_27_groups_prefix_pending': True,
            'no_new_experimental_sample_from_recovery': True}
        plan = {'version': '20261022-0000-v1-exact-population-extension', 'deadline': DEADLINE_LOCAL,
            'authorization': str(AUTH / 'authorization.json'), 'run_directory': str(RUN),
            'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)), 'stage_status': 'prepared_not_admitted',
            'research_cap_bytes': CAP, 'historical_ledger': LEDGER, 'corrected_truth_revalidated_prediction_jobs': 0,
            'prior_generated_baseline_files': 41, 'planned_baseline_files': 57,
            'ordered_remaining': ['exact reuse all 23 groups / 41 original-order projections; generate missing 16 only',
                'independently close all 39 groups / 57 baseline conditional assets',
                'new-version independent first-time full-point prefix audit all 27 new groups; prove reuse of 12 accepted groups',
                'full coarse/fine populations, negative controls, counterexamples and every unknown point',
                'all affected prediction scores/reports, or exact unaffected proof; original-simulation verification'],
            'all_label_dependent_claims_withheld': True, 'S4_overall_complete': False,
            'M2_allowed': False, 'S5_allowed': False, 'no_completion_claim_from_plan': True}
        overlay = {**r.read(ROOT / 'research_validity_overlay_20261019_v7.json'), 'time': r.now(),
            'previous_overlay': 'research_validity_overlay_20261019_v7.json', 'deadline': DEADLINE_LOCAL,
            'authorization_status': 'explicitly_renewed_to_20261021_2400', 'new_authorization': str(AUTH / 'authorization.json'),
            'total_E_Z_cap_bytes': CAP, 'administrative_boundary_receipt': str(CLOSE / 'receipt.json'),
            'population_generated_datasets': 41, 'population_generated_groups': 23,
            'prefix_independently_accepted_groups': 12, 'new_baseline_generation_pending_files': 16,
            'complete_research_remediation': False, 'currently_revalidated_prediction_jobs_under_corrected_truth': 0}
        report = ('# 10月20日续研授权与32GiB资源边界\n\n'
            '人类于10月20日明确授权至明天24:00，按当前日期解释为北京时间2026年10月22日00:00。'
            '不限制计算时长或批次，但E+Z研究目录合计32GiB、Z物理预留3GiB、单科学worker及全部可靠性门不变，不自动续期。\n\n'
            '旧worker40916于00:00:09完成已提交块后因旧固定截止停止；实际退出、runner stopped、mutex取得释放已核，'
            '旧源码/协议/失败/CP原样保留，没有重跑旧入口或伪称旧科学close。完整E/Z文件SHA与登记对照为文件一致性检查，不是科学认证。\n\n'
            '累计生成23/39共享几何组、41/57基线分文件，其中原12组30份精确复用，午夜授权仅新生成11组11份。'
            '原12组首次时间前缀已独立通过；新11组及后续16组仍待独立首次时间前缀审计。'
            '本新版本完整原输入及全数组精确复用后只计算缺失16份，再独立验收。\n\n'
            '尚须完整粗细总体、负控制/反例、所有未定与所有波及评分报告。旧RIGHT/FRONT/时间/漏报/混淆/排名及推荐继续暂停，'
            '修正真值重验预测0，历史2238/66/2304不重复计数。经验空间界非形式ODE/实车证书；瞬时有限面与旧扫掠面的语义区别明示。'
            '不调参择赢家、不降低阈值或删除角点；S4整体/M2/S5未完成、不准入。\n').encode('utf-8')
        r.batch([(CLOSE / 'receipt.json', r.encoded(receipt)), (CLOSE / 'whole_E_Z_sha256.json.gz', packed(whole)),
            (CLOSE / 'registered_file_comparisons.json.gz', packed(registered)),
            (CLOSE / 'parent_stopped_checkpoint.json', (PARENT / 'checkpoint.json').read_bytes()),
            (CLOSE / 'parent_stdout.log', (previous.SESSION / 'stdout.log').read_bytes()),
            (CLOSE / 'parent_stderr.log', (previous.SESSION / 'stderr.log').read_bytes()),
            (CLOSE / 'active_before.json', (ROOT / 'active_research_run.json').read_bytes()),
            (CLOSE / 'current_automation_renewed.toml', current_blob), (CLOSE / 'legacy_automation_paused.toml', legacy_blob),
            (AUTH / 'authorization.json', r.encoded(authorization)), (PROTOCOL, r.encoded(protocol)),
            (PLAN, r.encoded(plan)), (OVERLAY, r.encoded(overlay)),
            (ROOT / 'reports/10月20日续研授权与32GiB资源边界_v1.md', report),
            (RUN / 'parent_files_sha256.json', r.encoded(parent_hashes)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
            [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
        active = r.read(ROOT / 'active_research_run.json')
        active.update(status='renewed_population_extension_prepared', authorization_status='active', deadline=DEADLINE_LOCAL,
            authorization=str(AUTH / 'authorization.json'), run_directory=str(RUN), protocol=str(PROTOCOL), plan=str(PLAN),
            entrypoint=str(Path(__file__)), pid=None, running_analysis=False, running_predictions=False, running_preflight=False,
            input_worker_admitted=False, input_worker_admission_pending=True, scientific_validity_overlay=str(OVERLAY),
            research_cap_bytes=CAP, automatic_scientific_continuation_allowed=True,
            administrative_close=str(CLOSE), final_administrative_receipt=None,
            stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'),
            next_action=plan['ordered_remaining'][0], corrected_truth_revalidated_prediction_jobs=0)
        r.mutable(ROOT / 'active_research_run.json', active)
        r.batch([(CLOSE / 'active_after.json', (ROOT / 'active_research_run.json').read_bytes())])
    print('RENEWED EXTENSION PREPARED; actual full-input admission still required', flush=True)


def validate_asset(key, entry, loaded, groups, folder):
    ids = groups[key]
    r.require(set(ids) == set(entry['datasets']), 'Complete group projections required')
    arrays, record = base.read_arrays(folder / 'groups' / key)
    r.require(r.file_hash(folder / 'groups' / key / 'result.json') == entry['group']['result_sha256'], 'Group report differs')
    xy = np.unique(np.concatenate([loaded[i]['target']['xy'] for i in ids]), axis=0)
    r.require(np.array_equal(arrays['xy'], xy), 'All group coordinates differ')
    paths = {tag: {k.split('__', 1)[1]: v for k, v in arrays.items() if k.startswith(tag + '__')}
             for tag in ('oldpath', 'independent')}
    combined = base.combine(paths['oldpath'], paths['independent'])
    stored = {k.split('__', 1)[1]: v for k, v in arrays.items() if k.startswith('combined__')}
    r.require(base.array_meta(stored) == base.array_meta(combined), 'Every combined quantity differs')
    for dataset_id in ids:
        out, meta = base.read_arrays(folder / 'datasets' / dataset_id)
        r.require(r.file_hash(folder / 'datasets' / dataset_id / 'result.json') == entry['datasets'][dataset_id]['result_sha256'],
                  'Projection report differs')
        target = loaded[dataset_id]['target']
        index = out['union_index']
        r.require(index.dtype.kind in 'iu' and np.all((index >= 0) & (index < len(xy))), 'Invalid complete projection index')
        r.require(np.array_equal(xy[index], target['xy']), 'Original coordinate order differs')
        projected = {k: v[index] for k, v in combined.items()}
        r.require(base.array_meta(projected) == base.array_meta({k.split('__', 1)[1]: v for k, v in out.items()
                  if k.startswith('combined__')}), 'All projection quantities differ')
        for name, mask in base.old_discrepancies(target, projected).items():
            bits = out[name + '__packbits']
            r.require(np.array_equal(bits, np.packbits(mask, bitorder='little')) and int(mask.sum()) == meta['summary'][name],
                      'Full change/unknown packbits or counts differ')
    return arrays, record, paths


def copy_group(key, entry):
    paths = [PARENT / 'groups' / key / name for name in ('arrays.npz', 'result.json')]
    for dataset_id in entry['datasets']:
        paths += [PARENT / 'datasets' / dataset_id / name for name in ('arrays.npz', 'result.json')]
    payload = [(RUN / p.relative_to(PARENT), p.read_bytes()) for p in paths]
    r.batch(payload)
    for path, blob in payload:
        r.require(r.file_hash(path) == r.sha(blob), 'Copied complete asset differs')
    return entry


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Already attempted or cutoff')
    h, _ = execution()
    cp = {'status': 'preflight', 'completed': {}, 'exact_reused_groups': [], 'new_generated_groups': [],
          'new_predictions': 0, 'corrected_truth_revalidated_prediction_jobs': 0, 'source_signature': signature()}
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        parent = read_parent(r.read(PROTOCOL)['parent_cp_sha256'])
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            matrix = base.specifications()
            r.require(matrix == r.read(PROTOCOL)['matrix'], 'Whole original matrix changed')
            loaded, groups = base.load_inputs(matrix)
            reused, missing = previous.partition(groups, parent['completed'])
            r.require((len(loaded), len(groups), len(reused), len(missing)) == (57, 39, 23, 16), 'Whole population accounting differs')
            for key in reused:
                validate_asset(key, parent['completed'][key], loaded, groups, PARENT)
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'loaded_baseline_datasets': len(loaded),
                'point_file_records': sum(v['spec']['count'] for v in loaded.values()), 'groups': groups,
                'reuse_groups': reused, 'missing_groups': missing,
                'all_23_parent_groups_and_41_projections_fully_decoded': True,
                'all_original_array_metadata': {k: {'target': base.array_meta(v['target']),
                    'trajectory': base.array_meta(v['trajectory'])} for k, v in loaded.items()},
                'parent_cp_sha256': r.file_hash(PARENT / 'checkpoint.json'), 'execution': idle, 'mutex': mutex,
                'resources': r.guard(RESERVATION, RESERVATION)}))
            print('EXTENSION PREFLIGHT PASSED ALL 57 INPUTS / EXACT 23 GROUPS AND 41 FILES / MISSING 16 GROUPS', flush=True)
            for key in reused:
                r.require(r.before_deadline(), '2026-10-22 00:00 new reuse block cutoff')
                remaining = max(0, RESERVATION - base.scan_size(RUN))
                r.guard(remaining, remaining)
                cp['completed'][key] = copy_group(key, parent['completed'][key])
                validate_asset(key, cp['completed'][key], loaded, groups, RUN)
                cp['exact_reused_groups'].append(key)
                r.checkpoint(cp)
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='renewed_population_extension_running', pid=os.getpid(), running_analysis=True,
                input_worker_admitted=True, input_worker_admission_pending=False, running_preflight=False)
            r.mutable(ROOT / 'active_research_run.json', active)
            generate = previous.bound_group_kernel(destination=RUN)
            for key in missing:
                r.require(r.before_deadline(), '2026-10-22 00:00 new population group cutoff')
                verify()
                remaining = max(0, RESERVATION - base.scan_size(RUN))
                r.guard(remaining, remaining)
                print('START MISSING EXTENSION GROUP ' + key, flush=True)
                cp['completed'][key] = generate(key, groups[key], loaded)
                cp['new_generated_groups'].append(key)
                r.checkpoint(cp)
            cp['status'] = 'complete_pending_independent_acceptance'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('EXTENSION EXITING; independent conditional close and new-group prefixes pending', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Already accepted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_acceptance', 'Incomplete population cannot close')
        loaded, groups = base.load_inputs(r.read(PROTOCOL)['matrix'])
        r.require(set(cp['completed']) == set(groups) and len(groups) == 39 and len(loaded) == 57, 'All baseline files required')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            geometry, rows = {}, []
            for key, ids in groups.items():
                arrays, record, paths = validate_asset(key, cp['completed'][key], loaded, groups, RUN)
                first = loaded[ids[0]]
                vehicle = base.common.Vehicle(**first['profile']['vehicle'])
                trajectory = first['trajectory']
                geometry[key] = {}
                for tag, time, state, error in (
                    ('oldpath', trajectory['fine_time'], trajectory['fine_state'], record['reference_meta']['old_path_spatial_envelope_m']),
                    ('independent', arrays['independent_time'], arrays['independent_state'], record['reference_meta']['independent_path_spatial_envelope_m'])):
                    geometry[key][tag] = base.validate_path(arrays['xy'], time, state, paths[tag], error, vehicle)
                rows += [r.read(RUN / 'datasets' / dataset_id / 'result.json')['summary'] for dataset_id in ids]
            value = {'time': r.now(), 'status': 'all_57_conditional_assets_decoded_GE0S_checked_prefix_extension_pending',
                'rows': rows, 'geometry': geometry, 'exact_reused_parent_groups': 23, 'new_generated_groups': 16,
                'new_27_group_first_contact_prefix_audit_still_required': True, 'old_prefix_accepted_groups': 12,
                'all_unknowns_preserved': True, 'corrected_truth_revalidated_prediction_jobs': 0,
                'all_label_dependent_claims_withheld': True, 'not_formal_ODE_truth': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex}
            blob = r.encoded(value)
            r.batch([(RUN / 'acceptance.json', blob), (RUN / 'acceptance.json.gz', gzip.compress(blob, mtime=0))])
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    next_plan = {**r.read(PLAN), 'version': '20261022-0000-v2-all-baseline-conditional-close',
        'stage_status': 'baseline_conditional_assets_closed_new_27_group_prefix_and_all_scores_pending',
        'next_action': 'new-version first-contact prefix audit all 27 new groups; exact reuse original 12 accepted groups'}
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v2.json', r.encoded(next_plan)),
        (ROOT / 'reports/57份基线条件资产续算独立核验_20261022_0000_v1.md',
            ('# 57份基线条件资产续算独立核验\n\n全57份资产全数组及GEOS独立核验，23组精确复用、仅生成缺失16组。'
             '新27组首次时间前缀、完整扩展总体及评分仍待修。经验空间界非形式ODE或实车证书；所有未定保留，修正预测重验0。\n').encode('utf-8'))])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='renewed_all_baseline_conditionally_closed', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v2.json'), next_action=next_plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('ALL 57 CONDITIONAL ASSETS CLOSED; 27 new-group prefix audits and scores remain pending', flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Already launched or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(__file__)), 'run']
        r.freeze(SESSION / 'policy.json', r.encoded({'time': r.now(), 'argv': argv, 'cwd': r'C:\Users\Admin',
            'execution': idle, 'mutex': mutex, 'parent_mutex_released_before_Popen': True,
            'resources': r.guard(RESERVATION, RESERVATION)}))
    for name in ('stdout.log', 'stderr.log'):
        r.guard(0, 0)
        with (SESSION / name).open('xb'):
            pass
    with (SESSION / 'stdout.log').open('ab') as stdout, (SESSION / 'stderr.log').open('ab') as stderr:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=stderr, env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_admission_proof': True}))
    print('RENEWED EXTENSION LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
