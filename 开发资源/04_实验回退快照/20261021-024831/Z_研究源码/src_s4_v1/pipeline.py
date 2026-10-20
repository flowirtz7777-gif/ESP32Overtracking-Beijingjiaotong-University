from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
sys.path.insert(0, str(ROOT / 'src_v3'))
import numpy as np
import common
from common import array_hash, file_hash, read_json, write_json, utc_now
from evaluation_scored import evaluate, summarize, Variant
from observations import observe, conditions
from prediction import Method, future_alpha
from reporting import csv_rows, statistics, rank_key
import run_night as core
from state_estimation import estimate, PROCESSORS

PROTOCOL_FILE = ROOT / 'protocol_s4_v1.json'
RUN = ROOT / 'runs' / 'afternoon_S4_v1'
DEPENDENCY = ROOT / 'runs' / 'overnight_20261014_v3'
SENSOR_KEYS = ('time', 'state', 'alpha', 'v_B', 'measurement_time', 'source_index')


class DeadlineReached(Exception):
    pass


def signature():
    paths = [*sorted((ROOT / 'src_v3').glob('*.py')), *sorted((ROOT / 'src_s4_v1').glob('*.py')), PROTOCOL_FILE]
    return {p.relative_to(ROOT).as_posix(): file_hash(p) for p in paths}


def worker_init():
    policy = read_json(PROTOCOL_FILE)['execution']
    common.storage_guard.__defaults__ = (policy['reserve_bytes'], policy['experiment_budget_bytes'])


def dependency_checkpoint():
    protocol = read_json(PROTOCOL_FILE)
    transfer = read_json(ROOT.parent / 'transfer_verification.json')
    original = Path(transfer['source_root'])
    if file_hash(original / 'plan.json') != transfer['canonical_plan_sha256']:
        raise RuntimeError('Canonical E plan changed')
    if file_hash(original / 'runs' / 'overnight_20261014_v3' / 'checkpoint.json') != transfer['original_checkpoint_sha256']:
        raise RuntimeError('Preserved E checkpoint changed')
    if file_hash(DEPENDENCY / 'checkpoint.json') != protocol['S3_dependency_checkpoint_sha256']:
        raise RuntimeError('Completed S3 checkpoint changed')
    cp = read_json(DEPENDENCY / 'checkpoint.json')
    if not all(cp['stages'].get(s, {}).get('done') for s in ('S0', 'S3', 'S3_baseline')):
        raise RuntimeError('S3 or its hold baseline is incomplete')
    if cp['source_signature'] != core.signature():
        raise RuntimeError('Frozen v3 source differs from S3')
    audited = read_json(DEPENDENCY / 'reports' / 'completed_prefix_audit.json')
    if audited['checkpoint_bytes_sha256'] != protocol['S3_dependency_checkpoint_sha256'] or not audited['all_completed_output_hashes_verified']:
        raise RuntimeError('S3 completion audit does not match its checkpoint')
    return cp


def config_id(method):
    if method.mode == 'hold':
        return 'hold'
    return f'{method.mode}_g{round(method.gain * 1000):04d}_d{round(method.decay_s * 1000):04d}'


def selected_methods():
    report = read_json(ROOT / 'reports' / 'S3_analysis.json')
    return [Method(**m) for m in report['finalists']] + [Method('hold')]


def condition_list():
    mapping = {c['id']: c for c in conditions()}
    return [mapping[name] for name in read_json(PROTOCOL_FILE)['observation_conditions']]


def observation_dir(partition, case, condition):
    return RUN / 'observations' / partition / case / condition['id']


def freeze_observation(partition, case, condition, dependency):
    data, targets, manifest = core.load_case(partition, case)
    if len(targets['xy']) != 70000 or len(np.unique(targets['xy'], axis=0)) != 70000:
        raise AssertionError('Formal targets must remain 70000 unique points')
    raw = observe(data, condition)
    folder = observation_dir(partition, case, condition)
    sensor_hashes = {key: array_hash(raw[key]) for key in SENSOR_KEYS}
    original_id = '__'.join(['S3_baseline', case, 'hold', condition['id'], 'raw'])
    record = dependency['completed'][original_id]
    report_file = DEPENDENCY / 'jobs' / original_id / 'report.json'
    if file_hash(report_file) != record['report_sha256']:
        raise AssertionError('Raw reference report changed')
    old = read_json(report_file)
    if old['observed_state_sha256'] != sensor_hashes['state'] or old['observed_alpha_sha256'] != sensor_hashes['alpha']:
        raise AssertionError('New raw observation differs from completed S3')
    descriptor = {'condition': condition, 'input_hashes': manifest['files'], 'sensor_array_hashes': sensor_hashes,
                  'target_coordinates_sha256': manifest['target_coordinates_sha256'],
                  'contact_label_sha256': manifest['contact_label_sha256'], 'target_count': len(targets['xy'])}
    if (folder / 'manifest.json').exists():
        saved = read_json(folder / 'manifest.json')
        if saved['descriptor'] != descriptor or file_hash(folder / 'sensors.npz') != saved['sensors_file_sha256']:
            raise AssertionError('Frozen observation changed')
        return
    folder.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(folder / 'sensors.npz', **{key: raw[key] for key in SENSOR_KEYS})
    write_json(folder / 'manifest.json', {'status': 'frozen', 'descriptor': descriptor,
                                         'sensors_file_sha256': file_hash(folder / 'sensors.npz')})


def load_observation(partition, case, condition):
    folder = observation_dir(partition, case, condition)
    manifest = read_json(folder / 'manifest.json')
    if file_hash(folder / 'sensors.npz') != manifest['sensors_file_sha256']:
        raise AssertionError('Raw observation file hash mismatch')
    with np.load(folder / 'sensors.npz') as stored:
        arrays = {key: stored[key] for key in SENSOR_KEYS}
    if {key: array_hash(value) for key, value in arrays.items()} != manifest['descriptor']['sensor_array_hashes']:
        raise AssertionError('Raw observation array hash mismatch')
    return arrays, manifest


def make_job(stage, partition, case, method, processor, condition, variants, source):
    job = {'stage': stage, 'partition': partition, 'case_id': case, 'method': asdict(method),
           'config_id': config_id(method), 'processor': processor, 'condition': condition,
           'variants': [asdict(v) for v in variants], 'source_signature': source}
    digest = hashlib.sha256(json.dumps(job, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:12]
    job['id'] = '__'.join([stage, case, job['config_id'], condition['id'], processor, digest])
    return job


def execute_job(job):
    if signature() != job['source_signature']:
        raise AssertionError('Frozen active source changed during S4')
    common.storage_guard()
    start = time.perf_counter()
    data, targets, manifest = core.load_case(job['partition'], job['case_id'])
    raw, observations = load_observation(job['partition'], job['case_id'], job['condition'])
    if observations['descriptor']['input_hashes'] != manifest['files']:
        raise AssertionError('Observation and target inputs differ')
    estimated = estimate(raw, job['processor'])
    inputs = {**data, **estimated}
    result = evaluate(inputs, targets, Method(**job['method']), [Variant(**v) for v in job['variants']])
    rows = []
    for row in result['summaries']:
        row.update({key: job[key] for key in ('partition', 'case_id', 'config_id', 'stage')})
        row.update(job_id=job['id'], processor=job['processor'], condition=job['condition']['id'])
        rows.append(row)
    folder = RUN / 'jobs' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(folder / 'target_results.npz', **result['point_output'])
    np.savez_compressed(folder / 'frame_results.npz', counts=result['frame_counts'], time=inputs['time'], phase=result['observed_phase'])
    write_json(folder / 'configuration.json', job)
    write_json(folder / 'summary.json', rows)
    write_json(folder / 'timing.json', {**result['timing'], 'target_count': len(targets['xy']), 'desktop_not_MCU': True})
    outputs = ['configuration.json', 'summary.json', 'target_results.npz', 'frame_results.npz', 'timing.json']
    report = {'id': job['id'], 'source_signature': job['source_signature'], 'input_hashes': manifest['files'],
              'observation_manifest_sha256': file_hash(observation_dir(job['partition'], job['case_id'], job['condition']) / 'manifest.json'),
              'target_coordinates_sha256': manifest['target_coordinates_sha256'], 'contact_label_sha256': manifest['contact_label_sha256'],
              'raw_sensor_hashes': observations['descriptor']['sensor_array_hashes'],
              'estimated_state_sha256': array_hash(estimated['state']), 'estimated_alpha_sha256': array_hash(estimated['alpha']),
              'score_start_s': 2., 'score_end_s': float(data['time'][-1] - 3), 'target_count': len(targets['xy']),
              'output_sha256': {name: file_hash(folder / name) for name in outputs}, 'wall_s': time.perf_counter() - start}
    write_json(folder / 'report.json', report)
    return {'id': job['id'], 'report_sha256': file_hash(folder / 'report.json'), 'summaries': rows, 'wall_s': report['wall_s']}


def verify_job(job, record=None):
    folder = RUN / 'jobs' / job['id']
    report = read_json(folder / 'report.json')
    if record is not None and file_hash(folder / 'report.json') != record['report_sha256']:
        raise AssertionError('Checkpoint/report hash mismatch')
    if read_json(folder / 'configuration.json') != job or report['source_signature'] != job['source_signature']:
        raise AssertionError('Frozen configuration/source mismatch')
    for name, sha in report['output_sha256'].items():
        if file_hash(folder / name) != sha:
            raise AssertionError('Output hash mismatch: ' + name)
    mf = read_json(ROOT / 'datasets' / job['partition'] / job['case_id'] / 'manifest.json')
    if (report['input_hashes'] != mf['files'] or report['target_coordinates_sha256'] != mf['target_coordinates_sha256']
            or report['contact_label_sha256'] != mf['contact_label_sha256']):
        raise AssertionError('Input manifest mismatch')
    raw, observation = load_observation(job['partition'], job['case_id'], job['condition'])
    if report['raw_sensor_hashes'] != observation['descriptor']['sensor_array_hashes']:
        raise AssertionError('Raw sensor descriptor mismatch')
    restored = estimate(raw, job['processor'])
    if (array_hash(restored['state']) != report['estimated_state_sha256']
            or array_hash(restored['alpha']) != report['estimated_alpha_sha256']):
        raise AssertionError('Causal state estimate cannot be reproduced')
    if file_hash(observation_dir(job['partition'], job['case_id'], job['condition']) / 'manifest.json') != report['observation_manifest_sha256']:
        raise AssertionError('Observation manifest mismatch')
    return {'id': job['id'], 'report_sha256': file_hash(folder / 'report.json'),
            'summaries': read_json(folder / 'summary.json'), 'wall_s': report['wall_s']}


def run_jobs(stage, jobs, cp, workers, deadline):
    pending = []
    for job in jobs:
        if job['id'] in cp['completed']:
            result = verify_job(job, cp['completed'][job['id']])
            if result['summaries'] != [r for r in cp['summaries'] if r['job_id'] == job['id']]:
                raise AssertionError('Checkpoint summaries differ')
        elif (RUN / 'jobs' / job['id'] / 'report.json').exists():
            result = verify_job(job)
            cp['completed'][job['id']] = {'report_sha256': result['report_sha256']}
            cp['summaries'].extend(result['summaries'])
            write_json(RUN / 'checkpoint.json', cp)
            print('RECOVERED ' + job['id'], flush=True)
        else:
            pending.append(job)
    print(f'STAGE {stage} {len(pending)}/{len(jobs)} remaining', flush=True)
    iterator = iter(pending)
    with ProcessPoolExecutor(max_workers=workers, initializer=worker_init) as pool:
        active = {}
        def send():
            if time.time() >= deadline:
                return
            job = next(iterator, None)
            if job is not None:
                common.storage_guard()
                active[pool.submit(execute_job, job)] = job
        for _ in range(workers):
            send()
        finished = 0
        while active:
            ready, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
            for future in ready:
                result = future.result()
                active.pop(future)
                cp['completed'][result['id']] = {'report_sha256': result['report_sha256']}
                cp['summaries'].extend(result['summaries'])
                write_json(RUN / 'checkpoint.json', cp)
                finished += 1
                print(f"DONE {stage} {finished}/{len(pending)} {result['id']} {result['wall_s']:.1f}s", flush=True)
                send()
        if finished != len(pending):
            raise DeadlineReached('Afternoon deadline reached; completed jobs saved')


def research_statistics(rows):
    result = statistics(rows)
    result['passes_original_own_window_budget'] = result['passes_research_budget']
    result['passes_research_budget'] &= result['worst_2s_reference_fpr_pct'] <= .5
    return result


def processor_order(result):
    adjusted = {**result, 'worst_frame_fpr_pct': max(result['worst_frame_fpr_pct'], result['worst_2s_reference_fpr_pct'])}
    return rank_key(adjusted)


def raw_pilot_rows(cp, protocol):
    rows = [r for r in cp['summaries'] if r['stage'] in ('S3_scoring_repair', 'S3_hold_scoring_repair')
            and r['case_id'] in protocol['pilot_cases'] and r['condition'] in protocol['observation_conditions']
            and (r['EXIT_W_s'], r['margin_m'], r['confirmation_s']) == (2, 0, 0)]
    if len(rows) != 144 or len({(r['case_id'], r['config_id'], r['condition']) for r in rows}) != 144:
        raise AssertionError('Raw pilot baseline is incomplete or duplicated')
    reused = []
    for row in rows:
        folder = RUN / 'jobs' / row['job_id']
        report = read_json(folder / 'report.json')
        if file_hash(folder / 'report.json') != cp['completed'][row['job_id']]['report_sha256']:
            raise AssertionError('Raw dependency report changed')
        for name, sha in report['output_sha256'].items():
            if file_hash(folder / name) != sha:
                raise AssertionError('Raw dependency output changed')
        reused.append({**row, 'processor': 'raw', 'stage': 'S4_processor_raw_dependency', 'origin_job_id': row['job_id']})
    return reused


def summarize_S3(dependency):
    report = read_json(ROOT / 'reports' / 'S3_analysis.json')
    rows = [r for r in dependency['summaries'] if r['stage'] == 'S3']
    blocks = defaultdict(dict)
    for row in rows:
        blocks[(row['job_id'], row['margin_m'], row['confirmation_s'])][row['EXIT_W_s']] = row
    paired = []
    for (_, margin, confirmation), block in blocks.items():
        a, b = block[2], block[3]
        paired.append({'config_id': a['config_id'], 'case_id': a['case_id'], 'partition': a['partition'],
                       'condition': a['condition'], 'margin_m': margin, 'confirmation_s': confirmation,
                       'right_delta_pp': b['right_pct'] - a['right_pct'],
                       'exit_right_delta_pp': b['exit_right_pct'] - a['exit_right_pct'] if a['exit_right_pct'] is not None else None,
                       'common_fpr_delta_pp': b['common_2s_reference_fpr_pct'] - a['common_2s_reference_fpr_pct'],
                       'near_point_fp_delta_pp': b['negative_fp_pct'] - a['negative_fp_pct'],
                       'right_miss_delta': b['right_miss'] - a['right_miss']})
    csv_rows(ROOT / 'reports' / 'S3_complete_window_differences.csv', paired)
    grouped = []
    for method in sorted({r['config_id'] for r in rows}):
        for margin in (0., .02, .05):
            for confirmation in (0., .1):
                part = [r for r in paired if (r['config_id'], r['margin_m'], r['confirmation_s']) == (method, margin, confirmation)]
                grouped.append({'config_id': method, 'margin_m': margin, 'confirmation_s': confirmation,
                                'paired_conditions': len(part), 'trajectory_count': len({r['case_id'] for r in part}),
                                'mean_right_delta_pp': float(np.mean([r['right_delta_pp'] for r in part])),
                                'mean_common_fpr_delta_pp': float(np.mean([r['common_fpr_delta_pp'] for r in part])),
                                'mean_near_point_fp_delta_pp': float(np.mean([r['near_point_fp_delta_pp'] for r in part])),
                                'right_miss_delta_sum': sum(r['right_miss_delta'] for r in part)})
    csv_rows(ROOT / 'reports' / 'S3_complete_window_summary.csv', grouped)
    scope = {'prediction_jobs': 624, 'hold_baseline_jobs': 312, 'variant_scores': 7488,
             'trajectories': 39, 'observation_conditions_per_trajectory': 8, 'joint_configurations': 24,
             'feasible_configurations': report['feasible_configurations'], 'source_checkpoint_sha256': file_hash(DEPENDENCY / 'checkpoint.json'),
             'window_paired_rows': len(paired), 'scope_is_simulation_only': True, 'S4_winner_selected': False,
             'v3_scoring_start_inconsistent': True, 'v3_frame_start_s': 0, 'contact_eligibility_start_s': 2,
             'new_consistent_scoring_start_s': 2, 'v4_rescoring_required': True}
    write_json(ROOT / 'reports' / 'S3_complete_summary.json', scope)
    lines = ['# S3 v3完整结果与评分修正记录', '', '重要：复核发现v3评价器仅排除前2秒接触点，却仍计入前2秒逐帧误报和首次确认。下列数字保留为历史诊断，不能用于修正后的正式候选选择。新评价器统一从2秒评分，按原目标、原观测和原配置重跑624项联合预测及312项保持基线后另报结果。', '', '624项联合预测和312项保持基线全部完成，共7,488组联合评分。39条轨迹均使用冻结的70,000个唯一目标点，8种观测条件共用相同原始观测。', '',
             '24个联合配置没有任何一个同时达到零RIGHT窗口漏报、零接触前完全无报警、近场点误报不超过5%、逐帧误报不超过0.5%的研究预算，因此不能称当前排序第一为最优或达标方案。', '',
             '下表只展示出弯W从2秒变3秒的受控差异。负的RIGHT差值表示不足率降低，正的共同2秒误报差值表示误报代价增加。每行覆盖39条轨迹和8种观测条件，密集目标、帧与种子不作为独立车辆试验。', '',
             '| 核心配置 | 膨胀m | 确认s | RIGHT平均差值/百分点 | 共同2秒误报平均差值/百分点 | 近场点误报平均差值/百分点 |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in grouped:
        lines.append(f"| {row['config_id']} | {row['margin_m']} | {row['confirmation_s']} | {row['mean_right_delta_pp']:.6f} | {row['mean_common_fpr_delta_pp']:.6f} | {row['mean_near_point_fp_delta_pp']:.6f} |")
    lines += ['', '扩窗收益依赖膨胀和确认规则，并不等于各处理收益相加。此处EXIT是方向盘/前轮转角回正阶段，不是整辆挂车恢复直行；无法证明挂车恢复期扩窗的效果。', '',
              '全组仍有RIGHT迟报。0.05m膨胀可消除本组窗口漏报，但噪声下误报明显超过预算；0.1秒连续确认降低误报，也可能造成漏报或推迟报警。以上为重复条件下的接触评分实例，不是独立事故次数。', '',
              'S3未包含S2中的2倍噪声、200ms延迟等更强条件，不能将结论外推到这些条件。下一阶段先定位状态噪声影响，登记共同因果估计器，再进行统一预算的趋势强度/联合处理精化。当前没有冻结实车可用算法。', '']
    (ROOT / 'reports' / 'S3完整联合处理结论.md').write_text('\n'.join(lines), encoding='utf-8')


def probe():
    protocol = read_json(PROTOCOL_FILE)
    raw, manifest = load_observation(protocol['partition'], protocol['pilot_cases'][0], condition_list()[0])
    estimated = estimate(raw, 'phi_ekf_q025')
    return {'root': str(common.ROOT), 'run': str(RUN), 'guard_defaults': list(common.storage_guard.__defaults__),
            'source_signature': signature(), 'raw_state_sha256': array_hash(raw['state']),
            'estimated_state_sha256': array_hash(estimated['state']),
            'target_count': manifest['descriptor']['target_count']}


def audit_completed(cp):
    if signature() != cp['source_signature']:
        raise AssertionError('Audit source differs from the frozen S4 source')
    raw_groups, estimated_groups = {}, {}
    indexed = defaultdict(list)
    for row in cp['summaries']:
        indexed[row['job_id']].append(row)
    for identifier, record in cp['completed'].items():
        job = read_json(RUN / 'jobs' / identifier / 'configuration.json')
        result = verify_job(job, record)
        if result['summaries'] != indexed[identifier]:
            raise AssertionError('Summary audit mismatch')
        report = read_json(RUN / 'jobs' / identifier / 'report.json')
        key = (job['partition'], job['case_id'], job['condition']['id'])
        value = (report['target_coordinates_sha256'], report['contact_label_sha256'], report['score_start_s'], report['score_end_s'],
                 json.dumps(report['raw_sensor_hashes'], sort_keys=True))
        if key in raw_groups and raw_groups[key] != value:
            raise AssertionError('Targets, labels, raw inputs or scoring period differ')
        raw_groups[key] = value
        key += (job['processor'],)
        value = (report['estimated_state_sha256'], report['estimated_alpha_sha256'])
        if key in estimated_groups and estimated_groups[key] != value:
            raise AssertionError('Same processor differs across core algorithms')
        estimated_groups[key] = value
    record = {'status': 'verified_completed_prefix', 'completed_jobs': len(cp['completed']),
              'source_signature': signature(), 'raw_shared_groups': len(raw_groups),
              'estimated_shared_groups': len(estimated_groups), 'target_coordinates_labels_times_equal': True,
              'all_outputs_hash_verified': True, 'captured_at_utc': utc_now(), 'physical_validation': False}
    write_json(RUN / 'reports' / 'completed_prefix_audit.json', record)
    return record


def main():
    if ROOT.drive.upper() != 'Z:':
        raise RuntimeError('S4 executor must run in the authorized Z copy')
    protocol = read_json(PROTOCOL_FILE)
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--until', default=protocol['execution']['deadline_local'])
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    until = datetime.fromisoformat(args.until)
    maximum = datetime.fromisoformat(protocol['execution']['deadline_local'])
    if not 1 <= args.workers <= 8 or until.tzinfo is None or until > maximum:
        parser.error('Invalid workers or afternoon deadline')
    if not args.check_only and until <= datetime.now(timezone.utc):
        parser.error('Do not submit experiments after the afternoon deadline')
    kernel, mutex = core.acquire_lock()
    RUN.mkdir(parents=True, exist_ok=True)
    cp, session = None, None
    lock = RUN / 'runner_lock.json'
    try:
        worker_init()
        common.storage_guard()
        source = signature()
        dependency = dependency_checkpoint()
        cp_path = RUN / 'checkpoint.json'
        cp = read_json(cp_path) if cp_path.exists() else {'source_signature': source, 'completed': {}, 'summaries': [], 'stages': {}}
        if cp['source_signature'] != source:
            raise RuntimeError('S4 source/protocol changed; create a new research version')
        for name, sha in source.items():
            target = RUN / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and file_hash(target) != sha:
                raise AssertionError('S4 frozen source snapshot mismatch')
            if not target.exists():
                target.write_bytes((ROOT / name).read_bytes())
        selection = sorted({r['case_id'] for r in dependency['summaries'] if r['partition'] == protocol['refinement_partition']})
        if len(selection) != 12:
            raise AssertionError('Selection trajectory list is not the frozen 12-case set')
        stage_cases = sorted({(r['partition'], r['case_id']) for r in dependency['summaries'] if r['stage'] == 'S3'})
        if len(stage_cases) != 39:
            raise AssertionError('The complete shared raw observation set requires 39 cases')
        for partition, case in stage_cases:
            for condition in condition_list():
                freeze_observation(partition, case, condition, dependency)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        session_path = RUN / 'runtime_sessions' / (stamp + '.json')
        session = {'status': 'preflight', 'pid': os.getpid(), 'source_signature': source, 'deadline': until.isoformat(),
                   'workers': args.workers, 'resource_policy': protocol['execution'],
                   'S3_checkpoint_sha256': protocol['S3_dependency_checkpoint_sha256'], 'check_only': args.check_only,
                   'E_existing_files_modified': False, 'physical_validation': False}
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            session['worker_probe'] = pool.submit(probe).result(timeout=180)
        if session['worker_probe']['source_signature'] != source or session['worker_probe']['target_count'] != 70000:
            raise AssertionError('Actual worker source/target probe failed')
        if Path(session['worker_probe']['root']) != ROOT or session['worker_probe']['guard_defaults'] != list(common.storage_guard.__defaults__):
            raise AssertionError('Actual worker root/resource policy mismatch')
        cp['selection_cases'] = selection
        write_json(session_path, session)
        if args.check_only:
            session['status'] = 'preflight_passed_no_prediction_jobs_started'
            print(json.dumps({'status': session['status'], 'observations_frozen': len(stage_cases) * 8, 'worker_probe': session['worker_probe']}, ensure_ascii=False), flush=True)
            write_json(session_path, session)
            return
        cp['status'] = 'running'
        cp.pop('error', None)
        write_json(cp_path, cp)
        write_json(lock, {'pid': os.getpid(), 'status': 'running', 'time': utc_now()})
        session['status'] = 'running'
        write_json(session_path, session)
        summarize_S3(dependency)
        methods = selected_methods()
        variants = [Variant(w, margin, confirmation) for w in (2, 3) for margin in (0, .02, .05) for confirmation in (0, .1)]
        if not cp['stages'].get('scoring_repair'):
            cases = sorted({(r['partition'], r['case_id']) for r in dependency['summaries'] if r['stage'] == 'S3'})
            jobs = [make_job('S3_scoring_repair', partition, case, m, 'raw', c, variants, source)
                    for partition, case in cases for m in methods if m.mode != 'hold' for c in condition_list()]
            jobs += [make_job('S3_hold_scoring_repair', partition, case, Method('hold'), 'raw', c, [Variant()], source)
                     for partition, case in cases for c in condition_list()]
            if len(jobs) != 936:
                raise AssertionError('Scoring repair must preserve the full 39-case/8-condition design')
            for partition, case in cases:
                for condition in condition_list():
                    freeze_observation(partition, case, condition, dependency)
            run_jobs('S3_scoring_repair', jobs, cp, args.workers, until.timestamp())
            repaired = [r for r in cp['summaries'] if r['stage'] == 'S3_scoring_repair']
            comparison = []
            for m in methods:
                if m.mode == 'hold':
                    continue
                for variant in variants:
                    block = [r for r in repaired if r['config_id'] == config_id(m) and
                             (r['EXIT_W_s'], r['margin_m'], r['confirmation_s']) == (variant.exit_W, variant.margin, variant.confirmation)]
                    if len(block) != 312:
                        raise AssertionError('Incomplete rescored method/variant block')
                    comparison.append({'config_id': config_id(m), **asdict(variant), **research_statistics(block)})
            comparison.sort(key=processor_order)
            write_json(RUN / 'reports' / 'S3_consistent_scoring_analysis.json', {'status': 'completed_consistent_scoring',
                       'ranked': comparison, 'feasible_configurations': sum(r['passes_research_budget'] for r in comparison),
                       'score_start_s': 2, 'confirmation_history_preserved': True, 'physical_validation': False})
            csv_rows(RUN / 'reports' / 'S3_consistent_scoring_scores.csv', repaired)
            cp['stages']['scoring_repair'] = {'done': True, 'prediction_jobs': 936, 'score_start_s': 2., 'source_version': 'src_s4_v1'}
            write_json(cp_path, cp)
        if not cp['stages'].get('processor_pilot'):
            jobs = [make_job('S4_processor_pilot', protocol['partition'], case, method, pp, c, [Variant()], source)
                    for case in protocol['pilot_cases'] for method in methods for pp in PROCESSORS for c in condition_list()]
            if len(jobs) != protocol['new_pilot_prediction_jobs']:
                raise AssertionError('Unexpected pilot budget')
            run_jobs('S4_processor_pilot', jobs, cp, args.workers, until.timestamp())
            raw_rows = raw_pilot_rows(cp, protocol)
            pilot_rows = raw_rows + [r for r in cp['summaries'] if r['stage'] == 'S4_processor_pilot']
            ranked = [{'processor': pp, **research_statistics([r for r in pilot_rows if r['processor'] == pp])} for pp in protocol['pilot_processors']]
            ranked.sort(key=processor_order)
            pp = ranked[0]['processor']
            cp['stages']['processor_pilot'] = {'done': True, 'prediction_jobs': len(jobs), 'reused_raw_score_rows': len(raw_rows),
                                               'chosen_shared_processor': pp, 'chosen_is_exploratory': not ranked[0]['passes_research_budget']}
            write_json(RUN / 'reports' / 'S4_processor_analysis.json', {'status': 'completed', 'ranked': ranked,
                       'shared_processor': pp, 'selection_based_on_all_three_methods': True, 'final_independent_test': False})
            csv_rows(RUN / 'reports' / 'S4_processor_scores.csv', pilot_rows)
            write_json(cp_path, cp)
        pp = cp['stages']['processor_pilot']['chosen_shared_processor']
        refined = [replace(m, gain=m.gain * g) for m in methods if m.mode != 'hold' for g in protocol['gain_multipliers']] + [Method('hold')]
        if not cp['stages'].get('joint_refinement'):
            jobs = [make_job('S4_joint_refinement', protocol['refinement_partition'], case, m, pp, c, variants, source)
                    for case in selection for m in refined for c in condition_list()]
            if len(jobs) != protocol['refinement_prediction_jobs']:
                raise AssertionError('Unexpected refinement budget')
            run_jobs('S4_joint_refinement', jobs, cp, args.workers, until.timestamp())
            rows = [r for r in cp['summaries'] if r['stage'] == 'S4_joint_refinement']
            comparison = []
            for m in refined:
                for v in variants:
                    group = [r for r in rows if r['config_id'] == config_id(m) and (r['EXIT_W_s'], r['margin_m'], r['confirmation_s']) == (v.exit_W, v.margin, v.confirmation)]
                    if len(group) != 96:
                        raise AssertionError('Incomplete 12-trajectory/8-condition block')
                    comparison.append({'config_id': config_id(m), 'method': asdict(m), 'variant': asdict(v), **research_statistics(group)})
            comparison.sort(key=processor_order)
            families = [next(r for r in comparison if r['method']['mode'] == mode) for mode in ('damped_linear', 'linear')]
            write_json(RUN / 'reports' / 'S4_joint_analysis.json', {'status': 'completed_selection_refinement_only', 'ranked': comparison,
                       'family_candidates': families, 'shared_processor': pp, 'feasible_family_configurations': sum(r['passes_research_budget'] for r in comparison if r['method']['mode'] != 'hold'),
                       'replay_and_stability_not_completed': True, 'candidate_frozen_for_S5': False, 'physical_validation': False})
            csv_rows(RUN / 'reports' / 'S4_joint_scores.csv', rows)
            cp['stages']['joint_refinement'] = {'done': True, 'prediction_jobs': len(jobs), 'score_rows': len(rows)}
        cp['status'] = 'S4_refinement_complete_replay_stability_next'
        write_json(cp_path, cp)
        audit_completed(cp)
        print('S4 FILTER PILOT AND JOINT REFINEMENT COMPLETE; REPLAY/STABILITY/S5 NOT COMPLETE', flush=True)
    except DeadlineReached as error:
        cp['status'] = 'deadline_saved'
        write_json(RUN / 'checkpoint.json', cp)
        print(str(error), flush=True)
    except Exception as error:
        if cp is not None:
            cp.update(status='needs_repair', error=repr(error))
            write_json(RUN / 'checkpoint.json', cp)
        if session is not None:
            session.update(status='failed', error=repr(error))
        raise
    finally:
        if session is not None:
            session['ended_at_utc'] = utc_now()
            if session.get('status') != 'failed' and not args.check_only:
                session['status'] = cp.get('status', 'stopped')
            write_json(session_path, session)
        write_json(lock, {'pid': os.getpid(), 'status': 'stopped', 'time': utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
