"""Complete the missing group and refine every unresolved prefix, without rerunning exclusions."""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
sys.path.insert(0, str(ROOT / 'src_s4_interval_prefix_audit_20261019_v1'))
import run_audit as old
sys.path.insert(0, str(ROOT / '管理脚本'))
import close_authorization_20261019_1200_v1 as admin
import numpy as np

base, r = old.base, old.r
PRIOR = old.RUN
AUTH = ROOT / 'runs/resume_20261019_2400_truth_authorization_v1'
RUN = ROOT / 'runs/resume_20261019_2400_prefix_completion_v1'
PROTOCOL = ROOT / 'protocol_prefix_completion_20261019_2400_v1.json'
PLAN = ROOT / 'resume_plan_20261019_2400_v1.json'
SESSION = AUTH / 'runtime_sessions/prefix_completion_launch_v1'
FINAL_NOON = ROOT / 'runs/authorization_close_20261019_1200_v1/final_receipt.json'
PRIOR_CP = 'c97050d88493d0cc5e10b33a42a11f42a9c338450bcb0e7417fa09b0c2d18f22'
FINAL_SHA = '4de96cc8658e48a9f9c5c197fa0dccff4f9ae7d7ebea136e29214b2d33ecd706'
FIELDS = ('prefix_excluded', 'early_contact_witness', 'prefix_undetermined', 'budget_exhausted')
REFINE_BUDGET = 131072
RESERVATION = 96 * 1024**2


def configure():
    r.AUTH, r.RUN, r.RUN_CAP = AUTH, RUN, 128 * 1024**2
    r.DEADLINE = dt.datetime(2026, 10, 19, 16, tzinfo=dt.timezone.utc)


configure()


def execution():
    try:
        h, evidence = admin.execution()
    finally:
        configure()
    for path in RUN.glob('*runner_lock.json'):
        r.require(r.read(path)['status'] == 'stopped', 'Current runner/analysis is active')
    return h, evidence


def parent():
    r.require(r.file_hash(FINAL_NOON) == FINAL_SHA, 'Noon closure differs')
    r.require(r.file_hash(PRIOR / 'checkpoint.json') == PRIOR_CP, 'Stopped audit CP differs')
    cp = r.read(PRIOR / 'checkpoint.json')
    r.require(cp['status'] == 'stopped_failure_or_deadline' and len(cp['completed']) == 11,
              'All eleven prior complete groups must be retained')
    return cp


def signature():
    paths = [ROOT / rel for rel in r.read(PRIOR / 'source_manifest.json')]
    paths += [*SOURCE.glob('*.py'), PROTOCOL, PLAN, AUTH / 'authorization.json', FINAL_NOON,
        PRIOR / 'checkpoint.json', PRIOR / 'source_manifest.json',
        ROOT / '管理脚本/close_authorization_20261019_1200_v1.py',
        ROOT / '管理脚本/close_authorization_20261019_0800_v2.py']
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(set(paths))}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen source/protocol differs')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Source snapshot differs')
    for root, name in ((PRIOR, 'prior_audit_files.json'), (old.OLD, 'original_population_files.json')):
        for rel, digest in r.read(RUN / name).items():
            r.require(r.file_hash(root / rel) == digest, 'Prior frozen file differs: ' + rel)


def read_prefix(folder):
    saved = r.read(folder / 'result.json')
    r.require(r.file_hash(folder / 'prefix_audit.npz') == saved['npz_sha256'], 'Prefix NPZ SHA differs')
    with np.load(folder / 'prefix_audit.npz', allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    r.require(base.array_meta(arrays) == saved['arrays'], 'Every decoded prefix array must match')
    return arrays, saved


def path_arrays(arrays, tag):
    return {k.split('__', 1)[1]: v for k, v in arrays.items()
            if k.startswith(tag + '__') and not k.endswith('__packbits')}


def validate_prefix(prefix, expected_end):
    result = old.summarize_prefix(prefix)
    r.require(np.array_equal(prefix['audited_until_s'], expected_end), 'Full original prefix endpoints differ')
    r.require(np.all(prefix['GEOS_evaluations'] >= 0), 'Negative evaluation count')
    return result


def merge_refinement(seed, refined, indices):
    indices = np.asarray(indices)
    r.require(np.array_equal(indices, np.flatnonzero(seed['prefix_undetermined'])),
              'Refinement must include every and only unresolved original point')
    r.require(set(seed) == set(refined), 'Refinement fields differ')
    final = {k: v.copy() for k, v in seed.items()}
    for name in seed:
        r.require(refined[name].shape == (len(indices),) and refined[name].dtype == seed[name].dtype,
                  'Refinement shape/dtype differs')
        final[name][indices] = refined[name]
    old.summarize_prefix(final)
    return final


def load_all():
    cp = parent()
    loaded, groups, assets = old.load_all()
    prior_arrays = {}
    for key, entry in cp['completed'].items():
        arrays, saved = read_prefix(PRIOR / 'groups' / key)
        r.require(r.file_hash(PRIOR / 'groups' / key / 'result.json') == entry['result_sha256'], 'Prior CP report differs')
        r.require(saved['original_group_result_sha256'] == r.file_hash(old.OLD / 'groups' / key / 'result.json'),
                  'Prior prefix audit did not bind the same input group')
        for tag in ('oldpath', 'independent'):
            prefix = path_arrays(arrays, tag)
            lower = assets[key][2][tag]['contact_lower_s']
            end = np.where(np.isnan(lower), loaded[groups[key][0]]['trajectory']['fine_time'][-1], lower)
            r.require(validate_prefix(prefix, end) == saved['summary'][tag]['prefix'], 'Prior full-array statistics differ')
            for name in FIELDS:
                r.require(np.array_equal(np.unpackbits(arrays[tag + '__' + name + '__packbits'],
                    bitorder='little', count=len(lower)), prefix[name]), 'Prior full state indices differ')
        prior_arrays[key] = (arrays, saved)
    return loaded, groups, assets, prior_arrays


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (AUTH, RUN, PLAN, PROTOCOL)),
              'Already prepared or hard deadline')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        cp = parent()
        tests = []
        for folder in (old.SOURCE, SOURCE):
            result = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
                '-s', str(folder), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin',
                capture_output=True, encoding='utf-8', timeout=180)
            r.require(result.returncode == 0, 'Pre-freeze tests failed: ' + result.stderr)
            tests.append({'folder': str(folder), 'stdout': result.stdout, 'stderr': result.stderr})
        authorization = {'time': r.now(), 'human_request': '继续，做到晚上12:00',
            'human_priority_addendum': '今晚的进度要加快，马上要中期检查了',
            'deadline_local': '2026-10-20T00:00:00+08:00', 'deadline_utc': '2026-10-19T16:00:00Z',
            'primary_objective': 'Correct every affected experiment; scientific truth and reliability first',
            'previous_noon_close_sha256': FINAL_SHA, 'no_automatic_extension': True,
            'historical_ledger': {'formal': 2238, 'accepted_diagnostics': 66, 'numeric_records': 2304},
            'new_formal': 0, 'new_accepted_diagnostics': 0, 'corrected_truth_revalidated_prediction_jobs': 0,
            'E_read_only': True, 'all_frozen_history_preserved': True, 'workers': 1, 'inflight': 1,
            'total_E_Z_cap_bytes': r.CAP, 'Z_reserve_bytes': r.RESERVE}
        protocol = {'version': 'complete-missing-and-all-unknown-prefixes-v1',
            'deadline_local': authorization['deadline_local'], 'parent_cp_sha256': PRIOR_CP,
            'all_original_input_files': 57, 'all_existing_generated_groups': 12, 'all_generated_dataset_files': 30,
            'prior_complete_groups_exact_reuse': list(cp['completed']),
            'group_order': r.read(old.PROTOCOL)['groups'], 'missing_group_full_audit_budget': 8192,
            'all_unresolved_points_refinement_budget': REFINE_BUDGET, 'time_resolution_s': 1e-8,
            'tolerance_m': base.TOLERANCE, 'same_frozen_pose_and_empirical_error_envelope': True,
            'refinement_selection': 'all and only prefix_undetermined, both paths, no algorithm-performance selection',
            'no_change_to_acceptance_criteria': True, 'unknown_budget_conflicts_preserved': True,
            'rerun_excluded_points': False, 'new_predictions': 0, 'not_formal_ODE_truth': True,
            'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION,
            'no_new_scientific_submission_or_close_after_deadline': True}
        plan = {'version': '20261019-2400-v1-prefix-completion', 'deadline': authorization['deadline_local'],
            'authorization': str(AUTH / 'authorization.json'), 'previous_plan': 'resume_plan_20261019_1200_deadline_close_v1.json',
            'protocol': str(PROTOCOL), 'run_directory': str(RUN), 'entrypoint': str(Path(__file__)),
            'stage_status': 'prepared_not_admitted', 'scientific_remediation_complete': False,
            'new_formal': 0, 'new_accepted_diagnostics': 0, 'corrected_truth_revalidated_prediction_jobs': 0,
            'ordered_remaining': ['complete last prefix group and refine every unresolved prefix; independent close',
                'remaining 27 baseline assets in a separately admitted version, with proved exact reuse',
                'full coarse/fine populations, controls and counterexamples', 'all affected scores/reports or exact unaffected proofs'],
            'M2_allowed': False, 'S5_allowed': False, 'no_completion_claim_from_plan': True}
        overlay = {**r.read(ROOT / 'research_validity_overlay_20261019_v6.json'), 'time': r.now(),
            'previous_overlay': 'research_validity_overlay_20261019_v6.json', 'authorization_status': 'explicitly_renewed_to_midnight',
            'deadline': authorization['deadline_local'], 'administrative_close': None,
            'complete_research_remediation': False, 'currently_revalidated_prediction_jobs_under_corrected_truth': 0}
        report = ('# 10月19日24点授权与中期检查进度边界\n\n'
            '人类授权继续至今天晚上12点，明确为北京时间2026年10月20日00:00；不自动续期。'
            '中午封存保持原样，本新授权正式0、已验诊断0起，历史2238/66/2304不重复计数。\n\n'
            '目前57份基线原输入已登记；条件区间资产生成30/57份、12/39共享几何组；此前前缀审计保存11/12组，未独立验收。'
            '今晚优先复用已完成排除结果，只计算最后一组和全部未定点，再独立全数组及GEOS验收。'
            '追加预算固定131072次/点，空间误差、1mm角点阈值、时间分辨及通过标准不变；未定/预算不删除、不当负例。\n\n'
            '修正真值重验预测仍0。所有依赖标签的旧评分、排名、安全推荐继续暂停引用；经验数值包络不是形式化ODE或实车证书。'
            '待修包括27份基线资产、完整粗细总体/负控制/反例和全部受波及评分报告。S4整体/M2/S5未完成，不承诺午夜前全部修好。\n\n'
            '中期检查只能把真实执行、文件一致性、条件模型验证和待修事项分开陈述，不把计划、单测或部分输出当完整成果。\n').encode('utf-8')
        r.batch([(AUTH / 'authorization.json', r.encoded(authorization)), (PROTOCOL, r.encoded(protocol)),
            (PLAN, r.encoded(plan)), (ROOT / 'research_validity_overlay_20261019_v7.json', r.encoded(overlay)),
            (ROOT / 'reports/10月19日24点授权与中期检查进度边界_v1.md', report),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex, 'tests': tests,
                'resources': r.guard(RESERVATION, RESERVATION)})),
            (RUN / 'prior_audit_files.json', r.encoded({p.relative_to(PRIOR).as_posix(): r.file_hash(p)
                for p in PRIOR.rglob('*') if p.is_file()})),
            (RUN / 'original_population_files.json', r.encoded(r.read(PRIOR / 'original_all_file_sha256.json')))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
                [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
        active = r.read(ROOT / 'active_research_run.json')
        active.update(status='midnight_prefix_completion_prepared', authorization_status='active',
            deadline=authorization['deadline_local'], authorization=str(AUTH / 'authorization.json'),
            run_directory=str(RUN), protocol=str(PROTOCOL), plan=str(PLAN), entrypoint=str(Path(__file__)),
            pid=None, running_analysis=False, running_predictions=False, running_preflight=False,
            input_worker_admitted=False, input_worker_admission_pending=True,
            new_formal_predictions=0, new_diagnostics_accepted_this_authorization=0,
            automatic_scientific_continuation_allowed=True, final_administrative_receipt=None,
            scientific_validity_overlay=str(ROOT / 'research_validity_overlay_20261019_v7.json'),
            stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'),
            next_action=plan['ordered_remaining'][0])
        r.mutable(ROOT / 'active_research_run.json', active)
    print('MIDNIGHT COMPLETION PREPARED; no actual input admission yet', flush=True)


def paths_for(key, loaded, groups, asset):
    arrays, record, paths = asset
    original = loaded[groups[key][0]]
    trajectory = original['trajectory']
    vehicle = base.common.Vehicle(**original['profile']['vehicle'])
    for tag, time, state, error in (
        ('oldpath', trajectory['fine_time'], trajectory['fine_state'], record['reference_meta']['old_path_spatial_envelope_m']),
        ('independent', arrays['independent_time'], arrays['independent_state'], record['reference_meta']['independent_path_spatial_envelope_m'])):
        yield tag, time, state, error, vehicle, paths[tag]


def audit_group(key, loaded, groups, asset, reused):
    xy = asset[0]['xy']
    output, summaries = {}, {}
    for tag, time, state, error, vehicle, labels in paths_for(key, loaded, groups, asset):
        if reused is not None:
            seed = path_arrays(reused[0], tag)
            geometry = reused[1]['summary'][tag]['geometry']
            origin = 'exact_prior_complete_full_arrays'
        else:
            print('START MISSING FULL PREFIX ' + key + ' ' + tag, flush=True)
            geometry = base.validate_path(xy, time, state, labels, error, vehicle)
            seed = old.audit_prefixes(xy, time, state, labels['contact_lower_s'], vehicle=vehicle,
                spatial_error_m=error, tolerance_m=base.TOLERANCE, time_resolution_s=1e-8, max_evaluations_per_point=8192)
            origin = 'previously_unsubmitted_group'
        indices = np.flatnonzero(seed['prefix_undetermined'])
        print('START ALL-UNKNOWN REFINEMENT ' + json.dumps({'group': key, 'path': tag, 'points': len(indices)}), flush=True)
        refined = old.audit_prefixes(xy[indices], time, state, labels['contact_lower_s'][indices], vehicle=vehicle,
            spatial_error_m=error, tolerance_m=base.TOLERANCE, time_resolution_s=1e-8,
            max_evaluations_per_point=REFINE_BUDGET)
        final = merge_refinement(seed, refined, indices)
        summary = validate_prefix(final, np.where(np.isnan(labels['contact_lower_s']), time[-1], labels['contact_lower_s']))
        summaries[tag] = {'origin': origin, 'geometry_as_previously_checked': geometry,
            'seed': old.summarize_prefix(seed), 'all_unknown_points_refined': len(indices), 'prefix': summary}
        for prefix, arrays in ((tag, final), ('seed_' + tag, seed), ('refined_' + tag, refined)):
            output.update({prefix + '__' + name: value for name, value in arrays.items()})
        output[tag + '__refined_indices'] = indices
        for name in FIELDS:
            output[tag + '__' + name + '__packbits'] = np.packbits(final[name], bitorder='little')
        print('DONE COMPLETION PREFIX ' + json.dumps({'group': key, 'path': tag, **summary}), flush=True)
    blob = base.npz_bytes(output)
    saved = {'group': key, 'summary': summaries, 'arrays': base.array_meta(output), 'npz_sha256': r.sha(blob),
        'original_group_result_sha256': r.file_hash(old.OLD / 'groups' / key / 'result.json'),
        'prior_prefix_result_sha256': r.file_hash(PRIOR / 'groups' / key / 'result.json') if reused else None,
        'original_dataset_ids': groups[key], 'corrected_truth_revalidated_prediction_jobs': 0}
    folder = RUN / 'groups' / key
    r.batch([(folder / 'prefix_audit.npz', blob), (folder / 'result.json', r.encoded(saved))])
    return {'result_sha256': r.file_hash(folder / 'result.json'), 'summary': summaries}


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Already run or deadline')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        cp = {'status': 'preflight', 'completed': {}, 'source_signature': signature(), 'new_predictions': 0,
              'corrected_truth_revalidated_prediction_jobs': 0}
        try:
            loaded, groups, assets, reused = load_all()
            r.require(list(assets) == r.read(PROTOCOL)['group_order'], 'All original group membership/order differs')
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'python': sys.executable,
                'loaded_baseline_files': len(loaded), 'loaded_generated_groups': len(assets),
                'fully_decoded_prior_complete_prefix_groups': len(reused),
                'loaded_generated_dataset_files': sum(len(groups[k]) for k in assets),
                'all_original_array_metadata': {i: {'target': base.array_meta(v['target']),
                    'trajectory': base.array_meta(v['trajectory'])} for i, v in loaded.items()},
                'all_prior_prefix_arrays_metadata': {k: base.array_meta(v[0]) for k, v in reused.items()},
                'all_original_unresolved_indices_retained': True, 'execution': idle, 'mutex': mutex,
                'BLAS': {k: os.environ[k] for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                'resources': r.guard(RESERVATION, RESERVATION)}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='midnight_prefix_completion_running', pid=os.getpid(), running_analysis=True,
                input_worker_admission_pending=False, input_worker_admitted=True)
            r.mutable(ROOT / 'active_research_run.json', active)
            print('MIDNIGHT PREFLIGHT PASSED ALL 57 INPUTS / 12 GENERATED GROUPS / 11 FULL PREFIX REUSE', flush=True)
            for key, asset in assets.items():
                r.require(r.before_deadline(), '24:00 new completion group submission cutoff')
                verify()
                cp['completed'][key] = audit_group(key, loaded, groups, asset, reused.get(key))
                r.checkpoint(cp)
                r.require(not any(v['prefix']['early_contact_witness'] for v in cp['completed'][key]['summary'].values()),
                          'Independent early-contact counterexample saved; no further propagation')
            cp['status'] = 'complete_pending_independent_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('MIDNIGHT COMPLETION EXITING; prediction recertification remains zero', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Closed or deadline')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_close' and len(cp['completed']) == 12, 'Incomplete')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, reused = load_all()
            rows = []
            for key, entry in cp['completed'].items():
                arrays, saved = read_prefix(RUN / 'groups' / key)
                r.require(r.file_hash(RUN / 'groups' / key / 'result.json') == entry['result_sha256'], 'CP/report differs')
                for tag, time, state, error, vehicle, labels in paths_for(key, loaded, groups, assets[key]):
                    final = path_arrays(arrays, tag)
                    indices = final.pop('refined_indices')
                    seed, refined = path_arrays(arrays, 'seed_' + tag), path_arrays(arrays, 'refined_' + tag)
                    expected = merge_refinement(seed, refined, indices)
                    r.require(base.array_meta(final) == base.array_meta(expected), 'Unresolved merge or unchanged-array reuse differs')
                    if key in reused:
                        r.require(base.array_meta(seed) == base.array_meta(path_arrays(reused[key][0], tag)), 'Prior exact reuse differs')
                    end = np.where(np.isnan(labels['contact_lower_s']), time[-1], labels['contact_lower_s'])
                    summary = validate_prefix(final, end)
                    r.require(summary == saved['summary'][tag]['prefix'] and summary['early_contact_witness'] == 0,
                              'Statistics differ or early-contact counterexample exists')
                    for name in FIELDS:
                        r.require(np.array_equal(np.unpackbits(arrays[tag + '__' + name + '__packbits'],
                            bitorder='little', count=len(end)), final[name]), 'Full original state indices differ')
                    base.validate_path(assets[key][0]['xy'], time, state, labels, error, vehicle)
                rows.append({'group': key, 'dataset_files': len(groups[key]), 'summary': saved['summary']})
            strict = all(v['prefix']['strict_prefix_gate_passed'] for row in rows for v in row['summary'].values())
            acceptance = {'time': r.now(), 'status': 'conditional_prefix_completion_full_arrays_and_GE0S_checked',
                'strict_all_point_prefix_gate_passed': strict, 'generated_groups_audited': 12,
                'generated_dataset_files': 30, 'baseline_files_remaining_ungenerated': 27, 'rows': rows,
                'all_unknowns_preserved': True, 'all_old_label_claims_withheld': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex}
            data = r.encoded(acceptance)
            r.batch([(RUN / 'acceptance.json', data), (RUN / 'acceptance.json.gz', gzip.compress(data, mtime=0))])
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261019-2400-v2-prefix-completion-closed', 'previous_plan': PLAN.name,
        'stage_status': 'independently_closed_conditional_unknowns_retained',
        'strict_all_point_prefix_gate_passed': strict, 'next_action': 'inspect unresolved evidence before any remaining baseline propagation'}
    report = ('# 已生成基线资产的前缀补齐与全未定点追加核验\n\n'
        '本批逐数组证明复用此前11组全部已完成排除结果，只计算最后一组与两路径全部未定点。'
        '完整57份原输入及12生成组先实际准入；独立close重解所有输出/packbits、复用和追加索引，并核全部GEOS见证/有限面/非接触。\n\n'
        + '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows)
        + '\n\n严格全点前缀门：' + str(strict)
        + '。任何未定/预算继续保留，不算负例或通过。范围仍仅30份已生成资产，非全部57份、完整扩展总体或评分纠错。'
        '修正真值重验预测0；原1mm角点阈值与新旧面分类语义差异明示，经验数值界不冒充形式化ODE或实车证书。相关旧结论继续暂停。\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'execution_after': after,
        'mutex_reacquired_and_released': released, 'corrected_truth_prediction_jobs': 0})),
        (ROOT / 'resume_plan_20261019_2400_v2.json', r.encoded(plan)),
        (ROOT / 'reports/已生成基线资产前缀补齐与未定点追加核验_20261019_2400_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='midnight_prefix_completion_closed', running_analysis=False, pid=None,
        plan=str(ROOT / 'resume_plan_20261019_2400_v2.json'), next_action=plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print(json.dumps({'closed_groups': 12, 'strict_prefix_gate_passed': strict, 'corrected_prediction_jobs': 0}), flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Already launched or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(__file__)), 'run']
        r.freeze(SESSION / 'policy.json', r.encoded({'time': r.now(), 'argv': argv, 'cwd': r'C:\Users\Admin',
            'parent_mutex_released_before_Popen': True, 'execution': idle, 'mutex': mutex,
            'resources': r.guard(RESERVATION, RESERVATION)}))
    with (SESSION / 'stdout.log').open('xb') as stdout, (SESSION / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=stderr, env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_input_admission_proof': True}))
    print('MIDNIGHT COMPLETION LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
