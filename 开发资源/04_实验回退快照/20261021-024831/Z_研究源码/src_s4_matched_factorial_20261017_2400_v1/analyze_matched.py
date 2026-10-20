"""Read closed predictions; never invoke an old experiment entrypoint."""
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src_s4_fine_factorial_20261017_1900_v1'))
import run_factorial as q

np = q.np
PROTOCOL = ROOT/'protocol_matched_factorial_20261017_2400_v1.json'
EXPECTED = 'de8a67496357a960688348a1c8f7f1ef775a294256f7f97ec1ec37f999788140'
RUN = ROOT/'runs/resume_20261017_matched_factorial_2400_v1'
REPORT = ROOT/'reports/同点提前量配对与误报双预算只读核验_20261017_2400_v1.md'
PYTHON = Path(r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe')


def require(value, message):
    if not value:
        raise AssertionError(message)


def protocol():
    require(q.base.file_hash(PROTOCOL) == EXPECTED, 'Frozen matched protocol differs')
    return q.base.read_json(PROTOCOL)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def signature():
    paths = [PROTOCOL, ROOT/protocol()['authorization_file'],
             ROOT/'管理脚本/register_20261017_2400_authorization_v1.py',
             ROOT/'管理脚本/launch_matched_factorial_20261017_2400_v1.py',
             *sorted(Path(__file__).parent.glob('*.py'))]
    return {**q.signature(), **{p.relative_to(ROOT).as_posix(): q.base.file_hash(p) for p in paths}}


def administrative_helper():
    path = ROOT/'管理脚本/register_20261017_2400_authorization_v1.py'
    saved = ROOT/'runs/resume_20261017_2400_authorization_v1/source'/path.name
    require(q.base.file_hash(path) == q.base.file_hash(saved), 'Frozen registration helper differs')
    spec = importlib.util.spec_from_file_location('bounded_write_only_matched', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def resources(extra=0):
    p = protocol()['execution']
    measured = administrative_helper().guard(extra)
    used = sum(x.stat().st_size for x in RUN.rglob('*') if x.is_file()) if RUN.exists() else 0
    require(used+extra <= p['run_cap_bytes'], 'Read-only run quota exhausted')
    return {**measured, 'run_bytes': used}


def freeze(path, payload):
    resources(len(payload)+65536)
    administrative_helper().freeze(path, payload)


def put(path, value):
    payload = encoded(value)
    resources(len(payload)+65536)
    q.base.write_json_retry(path, value)


def save_cp(cp):
    put(RUN/'checkpoint.json', cp)
    blob = (RUN/'checkpoint.json').read_bytes()
    freeze(RUN/'checkpoint_snapshots'/(hashlib.sha256(blob).hexdigest()+'.json.gz'),
           gzip.compress(blob, mtime=0))


def expired():
    return datetime.now(timezone.utc) >= datetime.fromisoformat(protocol()['execution']['deadline_local'])


def worker_init():
    p = protocol()['execution']
    q.pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def exact_budget(numerator, denominator, scale):
    require(type(numerator) is int and type(denominator) is int and 0 <= numerator <= denominator,
            'Exact valid integer counts required')
    return numerator*scale <= denominator if denominator else None


def distribution(values):
    values = np.asarray(values, dtype=np.float64)
    require(values.ndim == 1 and np.isfinite(values).all(), 'Finite one-dimensional values required')
    if not len(values):
        return {'count': 0, 'mean_s': None, 'p10_s': None, 'median_s': None,
                'min_s': None, 'max_s': None}
    return {'count': len(values), 'mean_s': float(values.mean()),
            'p10_s': float(np.quantile(values, .1, method='linear')),
            'median_s': float(np.quantile(values, .5, method='linear')),
            'min_s': float(values.min()), 'max_s': float(values.max())}


def scalar_quantile(values, fraction):
    ordered = sorted(float(x) for x in values)
    if not ordered:
        return None
    x = (len(ordered)-1)*fraction
    lo, hi = math.floor(x), math.ceil(x)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(x-lo)


def eligible_positions(target, positions, cut):
    contact = target['contact_time'][positions]
    ok = (~target['front_ignored'][positions]) & (target['edge'][positions] == 2)
    ok &= np.isfinite(contact) & (contact >= 2-1e-9) & (contact <= cut+1e-9)
    positions = positions[ok]
    return positions[np.argsort(target['reference_ids'][positions])]


def summarize_delta(delta):
    return {**distribution(delta), 'decreased_count': int((delta < -1e-9).sum()),
            'unchanged_count': int((np.abs(delta) <= 1e-9).sum()),
            'increased_count': int((delta > 1e-9).sum())}


def matched(target, point, positions, cut, cells=None, pairs=None):
    p = protocol() if cells is None else None
    cells = p['cells'] if cells is None else cells
    pairs = p['pairs'] if pairs is None else pairs
    eligible = eligible_positions(target, positions, cut)
    contact = target['contact_time']
    rows, arrays = [], {}
    detected = {tag: eligible[np.isfinite(point[tag+'_valid'][eligible])] for tag in cells}
    for name, before, after in pairs:
        tag0, tag1 = cells[before], cells[after]
        ids = eligible[np.isfinite(point[tag0+'_valid'][eligible]) & np.isfinite(point[tag1+'_valid'][eligible])]
        left = (contact[ids]-point[tag0+'_valid'][ids]).astype(np.float64)
        right = (contact[ids]-point[tag1+'_valid'][ids]).astype(np.float64)
        delta = right-left
        arrays[name+'__ids'] = target['reference_ids'][ids].astype(np.int32)
        arrays[name+'__before_lead_s'] = left
        arrays[name+'__after_lead_s'] = right
        arrays[name+'__delta_s'] = delta
        all0 = distribution(contact[detected[tag0]]-point[tag0+'_valid'][detected[tag0]])
        all1 = distribution(contact[detected[tag1]]-point[tag1+'_valid'][detected[tag1]])
        left_summary, right_summary = distribution(left), distribution(right)
        rows.append({'contrast': name, 'before_variant': tag0, 'after_variant': tag1,
                     'eligible_right_points': len(eligible), 'matched_points': len(ids),
                     'before_detected_points': len(detected[tag0]), 'after_detected_points': len(detected[tag1]),
                     'before_only_detected': len(detected[tag0])-len(ids),
                     'after_only_detected': len(detected[tag1])-len(ids),
                     'matched_before': left_summary, 'matched_after': right_summary,
                     'paired_delta_after_minus_before': summarize_delta(delta),
                     'same_set_quantile_differences': {k: None if not len(ids) else right_summary[k]-left_summary[k]
                                                      for k in ('p10_s', 'median_s')},
                     'different_set_original_conditionals_before': all0,
                     'different_set_original_conditionals_after': all1,
                     'different_set_conditional_quantile_differences': {
                         k: None if all0[k] is None or all1[k] is None else all1[k]-all0[k]
                         for k in ('p10_s', 'median_s')},
                     'post_treatment_selection_not_causal_effect': True})
    common = eligible[np.logical_and.reduce([np.isfinite(point[tag+'_valid'][eligible]) for tag in cells])]
    leads = np.column_stack([contact[common]-point[tag+'_valid'][common] for tag in cells]).astype(np.float64)
    delta = (leads[:, 3]-leads[:, 2])-(leads[:, 1]-leads[:, 0])
    arrays['interaction__ids'] = target['reference_ids'][common].astype(np.int32)
    arrays['interaction__four_leads_s'] = leads
    arrays['interaction__delta_s'] = delta
    rows.append({'contrast': 'margin_confirmation_interaction', 'eligible_right_points': len(eligible),
                 'matched_points': len(common), 'all_four_detected_only': True,
                 'paired_difference_of_differences': summarize_delta(delta),
                 'post_treatment_selection_not_causal_effect': True})
    return rows, arrays


def independent_check(target, point, positions, cut, rows, arrays):
    p = protocol()
    reference = target['reference_ids']
    eligible = {int(i) for i in positions if not target['front_ignored'][i]
                and target['edge'][i] == 2 and np.isfinite(target['contact_time'][i])
                and 2-1e-9 <= target['contact_time'][i] <= cut+1e-9}
    sets = [{i for i in eligible if np.isfinite(point[tag+'_valid'][i])} for tag in p['cells']]
    for row, (name, left, right) in zip(rows[:4], p['pairs'], strict=True):
        ids = sorted(sets[left] & sets[right], key=lambda i: int(reference[i]))
        expect = np.array([int(reference[i]) for i in ids], np.int32)
        require(np.array_equal(expect, arrays[name+'__ids']), 'Independent pair set differs')
        v0 = np.array([float(target['contact_time'][i])-float(point[p['cells'][left]+'_valid'][i]) for i in ids], np.float64)
        v1 = np.array([float(target['contact_time'][i])-float(point[p['cells'][right]+'_valid'][i]) for i in ids], np.float64)
        delta = np.array([b-a for a, b in zip(v0, v1, strict=True)], np.float64)
        for suffix, value in [('before_lead_s', v0), ('after_lead_s', v1), ('delta_s', delta)]:
            require(np.array_equal(value, arrays[name+'__'+suffix]), 'Independent paired lead differs')
        for key, frac in [('p10_s', .1), ('median_s', .5)]:
            value = scalar_quantile(delta, frac)
            got = row['paired_delta_after_minus_before'][key]
            require(value is None and got is None or value is not None and math.isclose(value, got, abs_tol=1e-12),
                    'Independent sorted quantile differs')
    ids = sorted(set.intersection(*sets), key=lambda i: int(reference[i]))
    require(np.array_equal(np.array([reference[i] for i in ids], np.int32), arrays['interaction__ids']),
            'Independent four-way set differs')
    matrix = np.array([[float(target['contact_time'][i])-float(point[tag+'_valid'][i]) for tag in p['cells']]
                       for i in ids], np.float64).reshape(-1, 4)
    delta = np.array([(r[3]-r[2])-(r[1]-r[0]) for r in matrix], np.float64)
    require(np.array_equal(matrix, arrays['interaction__four_leads_s'])
            and np.array_equal(delta, arrays['interaction__delta_s']), 'Independent interaction differs')
    return len(arrays)


def dependency_check():
    p = protocol()
    require(Path(sys.executable) == PYTHON, 'Exact Python required')
    require(q.base.file_hash(ROOT/p['authorization_file']) == p['authorization_sha256'], 'Authorization differs')
    for run in (q.RUN, q.PREVIOUS, q.c.RUN, q.a.RUN, q.f.RUN):
        require(q.base.read_json(run/'runner_lock.json')['status'] == 'stopped', 'Reference runner active')
    require(q.base.read_json(q.RUN/'analysis_runner_lock.json')['status'] == 'stopped', 'Reference analysis active')
    require(q.base.file_hash(q.RUN/'checkpoint.json') == p['reference_checkpoint_sha256'], 'Closed reference CP differs')
    require(q.base.file_hash(Path(q.__file__)) == p['reference_source_sha256'], 'Reference source differs')
    require(q.base.file_hash(q.PROTOCOL) == p['reference_protocol_sha256'], 'Reference protocol differs')
    audit_path = q.RUN/'runtime_sessions/20261017_1900_factorial_output_recheck/acceptance.json'
    require(q.base.file_hash(audit_path) == p['reference_output_audit_sha256'], 'Closed output audit differs')
    audit = q.base.read_json(audit_path)
    for name, value in audit['all_existing_run_file_sha256'].items():
        require(q.base.file_hash(q.RUN/name) == value, 'Frozen reference file differs: '+name)
    for name, value in q.signature().items():
        require(q.base.file_hash(q.RUN/'source'/name) == value, 'Frozen reference source snapshot differs')
    return {'verified_reference_run_files': len(audit['all_existing_run_file_sha256']),
            'reference_source_files': len(q.signature())}


def load_job(job, verify_common=True):
    folder = q.RUN/'jobs'/job['id']
    report = q.base.read_json(folder/'report.json')
    target, proof = q.load_targets(job['case']['id'])
    require(q.base.read_json(folder/'configuration.json') == job, 'Reference configuration differs')
    require(report['source_signature'] == q.signature(), 'Reference signature differs')
    for filename, value in report['output_sha256'].items():
        require(q.base.file_hash(folder/filename) == value, 'Reference job file differs')
    point = q.c.readback((folder/'point_results.npz').read_bytes(), report['point_arrays'])
    q.c.readback((folder/'frame_results.npz').read_bytes(), report['frame_arrays'])
    if verify_common:
        require(q.common_input(job['case'], target, proof) == report['common_inputs'], 'Common input identity differs')
    data, _, _ = q.pipeline.core.load_case(q.protocol()['partition'], job['case']['id'])
    config = job['fine_reference_job']['coarse_reference']['reference']
    raw, _ = q.pipeline.load_observation(config['partition'], job['case']['id'], config['condition'])
    variants = [q.pipeline.Variant(**cell) for cell in q.protocol()['variants']]
    scores = q.main_scores({**data, **raw}, target, point, variants)
    require(scores == q.base.read_json(folder/'main_scores.json'), 'Original 70000 summaries differ')
    return target, point, proof, scores


def probe():
    require(not expired(), 'No new preflight after midnight')
    dep = dependency_check()
    groups = []
    for case in protocol()['cases']:
        jobs = [j for j in q.jobs() if j['case']['id'] == case]
        require(len(jobs) == 3, 'All three methods required')
        common = []
        for job in jobs:
            target, point, proof, scores = load_job(job)
            common.append(proof['common_inputs'])
        require(common[0] == common[1] == common[2], 'Cross-method common input differs')
        groups.append({'case': case, 'target_count': len(target['xy']),
                       'catalog_count': len(target['catalog_positions']), 'jobs_loaded': len(jobs),
                       'common_input': common[0]})
    return {'python': sys.executable, 'root': str(ROOT), 'source_signature': signature(), 'cases': groups,
            'deadline': protocol()['execution']['deadline_local'],
            'guard_defaults': list(q.pipeline.common.storage_guard.__defaults__),
            'dependency_checks': dep, 'resources': resources(protocol()['execution']['batch_reservation_bytes']),
            'new_predictions': 0}


def analyze_case(case):
    require(not expired(), 'No new analysis submission after midnight')
    rows, budgets, arrays = [], [], {}
    for job in [j for j in q.jobs() if j['case']['id'] == case]:
        target, point, proof, scores = load_job(job)
        cut = proof['common_inputs']['score_end_s']
        for score in scores:
            point_pass = exact_budget(score['negative_fp'], score['negative_count'], 20)
            frame_pass = exact_budget(score['frame_FP'], score['frame_FP']+score['frame_TN'], 200)
            budgets.append({'case_id': case, 'method': job['core_id'], 'variant': score['variant'],
                            'point_fp_numerator': score['negative_fp'], 'point_fp_denominator': score['negative_count'],
                            'frame_fp_numerator': score['frame_FP'], 'frame_fp_denominator': score['frame_FP']+score['frame_TN'],
                            'point_fp_budget_passed': point_pass, 'frame_fp_budget_passed': frame_pass,
                            'both_false_alarm_budgets_passed': None if point_pass is None or frame_pass is None
                            else point_pass and frame_pass, 'original_main_summary': score,
                            'not_full_foundation_gate': True})
        for cohort, positions in [('original_70000', target['main_ids']),
                                  ('development_catalog', target['catalog_positions'])]:
            got, packed = matched(target, point, positions, cut)
            prefix = job['core_id']+'__'+cohort+'__'
            rows.extend({'case_id': case, 'method': job['core_id'], 'cohort': cohort, 'array_prefix': prefix, **row}
                        for row in got)
            arrays.update({prefix+key: value for key, value in packed.items()})
    blob = q.f.coarse.npz_bytes(arrays)
    desc = q.c.descriptors(arrays)
    q.c.readback(blob, desc)
    require(len(blob)+len(encoded(rows))+len(encoded(budgets))+len(encoded(desc)) <= 48*1024**2,
            'Measured complete case payload exceeds reserved quota')
    return {'case': case, 'rows': rows, 'budgets': budgets, 'descriptors': desc, 'npz': blob}


def main():
    require(not expired(), 'No new read-only analysis after midnight')
    require(not RUN.exists(), 'New run already exists; do not rerun')
    worker_init()
    kernel, mutex = q.pipeline.core.acquire_lock()
    cp = {'status': 'preflight', 'source_signature': signature(), 'completed': {}, 'new_predictions': 0}
    try:
        resources(protocol()['execution']['batch_reservation_bytes'])
        for name, value in signature().items():
            freeze(RUN/'source'/name, (ROOT/name).read_bytes())
        put(RUN/'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': q.base.utc_now(),
                                    'phase': 'readonly_matched_preflight_not_prediction'})
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result()
            require(actual['source_signature'] == signature() and actual['python'] == str(PYTHON)
                    and actual['root'] == str(ROOT) and len(actual['cases']) == 3
                    and actual['guard_defaults'] == [3*1024**3, 16*1024**3]
                    and actual['deadline'] == protocol()['execution']['deadline_local'], 'Actual worker admission failed')
            freeze(RUN/'actual_worker.json', encoded(actual))
            freeze(RUN/'preflight.json', encoded({'status': 'all_three_complete_inputs_passed_no_analysis_submitted',
                                                'actual_worker': actual, 'new_predictions': 0}))
            print('PREFLIGHT MATCHED PASSED ALL THREE CASES', flush=True)
            cp['status'] = 'readonly_matched_running'
            save_cp(cp)
            for case in protocol()['cases']:
                if expired():
                    cp['status'] = 'deadline_checkpoint_saved'
                    break
                resources(48*1024**2+2*1024**2)
                print('SUBMIT READONLY MATCHED '+case, flush=True)
                result = pool.submit(analyze_case, case).result()
                payloads = {'pairs.npz': result['npz'], 'arrays.json': encoded(result['descriptors']),
                            'contrasts.json': encoded(result['rows']), 'false_alarm_budgets.json': encoded(result['budgets'])}
                resources(sum(map(len, payloads.values()))+65536)
                for name, blob in payloads.items():
                    freeze(RUN/'cases'/case/name, blob)
                cp['completed'][case] = {name: hashlib.sha256(blob).hexdigest() for name, blob in payloads.items()}
                save_cp(cp)
                print('DONE READONLY MATCHED '+case, flush=True)
        if len(cp['completed']) == 3:
            cp['status'] = 'readonly_matched_complete_pending_independent_close'
        save_cp(cp)
    except BaseException as error:
        cp['status'] = 'readonly_failed_preserved'
        cp['error'] = repr(error)
        save_cp(cp)
        raise
    finally:
        put(RUN/'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': q.base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


def close():
    require(not expired(), 'Do not submit a new independent scientific close after midnight')
    require(not (RUN/'acceptance.json').exists() and not REPORT.exists(), 'Closure already exists; never overwrite')
    require(q.base.read_json(RUN/'runner_lock.json')['status'] == 'stopped', 'Worker parent not stopped')
    kernel, mutex = q.pipeline.core.acquire_lock()
    try:
        dependency_check()
        cp = q.base.read_json(RUN/'checkpoint.json')
        require(cp['status'] == 'readonly_matched_complete_pending_independent_close' and len(cp['completed']) == 3,
                'Three completed read-only cases required')
        require(cp['source_signature'] == signature(), 'New frozen source differs')
        for name, value in signature().items():
            require(q.base.file_hash(RUN/'source'/name) == value, 'New source snapshot differs')
        rows, budgets, checks = [], [], 0
        for case in protocol()['cases']:
            folder = RUN/'cases'/case
            for name, value in cp['completed'][case].items():
                require(q.base.file_hash(folder/name) == value, 'Read-only output differs')
            descriptors = q.base.read_json(folder/'arrays.json')
            arrays = q.c.readback((folder/'pairs.npz').read_bytes(), descriptors)
            case_rows = q.base.read_json(folder/'contrasts.json')
            case_budgets = q.base.read_json(folder/'false_alarm_budgets.json')
            for job in [j for j in q.jobs() if j['case']['id'] == case]:
                target, point, proof, scores = load_job(job)
                for cohort, positions in [('original_70000', target['main_ids']),
                                          ('development_catalog', target['catalog_positions'])]:
                    prefix = job['core_id']+'__'+cohort+'__'
                    selected = [r for r in case_rows if r['method'] == job['core_id'] and r['cohort'] == cohort]
                    values = {k.removeprefix(prefix): v for k, v in arrays.items() if k.startswith(prefix)}
                    checks += independent_check(target, point, positions, proof['common_inputs']['score_end_s'], selected, values)
                    reconstructed, _ = matched(target, point, positions, proof['common_inputs']['score_end_s'])
                    require(reconstructed == [{k: v for k, v in row.items() if k not in
                            ('case_id', 'method', 'cohort', 'array_prefix')} for row in selected], 'All matched summaries differ')
                for score in scores:
                    b = next(x for x in case_budgets if x['method'] == job['core_id'] and x['variant'] == score['variant'])
                    require(score == b['original_main_summary'], 'Full original summary differs at closure')
                    pnum, pden = b['point_fp_numerator'], b['point_fp_denominator']
                    fnum, fden = b['frame_fp_numerator'], b['frame_fp_denominator']
                    from fractions import Fraction
                    pp = Fraction(pnum, pden) <= Fraction(5, 100) if pden else None
                    fp = Fraction(fnum, fden) <= Fraction(5, 1000) if fden else None
                    require(pp == b['point_fp_budget_passed'] and fp == b['frame_fp_budget_passed'],
                            'Independent exact rational budget differs')
            rows.extend(case_rows)
            budgets.extend(case_budgets)
        require(len(rows) == 90 and len(budgets) == 36 and checks == 342, 'Complete comparison matrix required')
        acceptance = {'status': 'readonly_matched_independently_accepted', 'time': q.base.utc_now(),
                      'source_signature': signature(), 'checkpoint_sha256': q.base.file_hash(RUN/'checkpoint.json'),
                      'readonly_cases_accepted': 3, 'contrasts': len(rows), 'main_false_alarm_rows': len(budgets),
                      'independent_array_checks': checks, 'new_formal_predictions': 0, 'new_diagnostic_predictions': 0,
                      'formal_total': 2238, 'accepted_diagnostic_total': 48, 'accepted_numeric_total': 2286,
                      'false_alarm_both_pass_rows': sum(x['both_false_alarm_budgets_passed'] is True for x in budgets),
                      'false_alarm_both_pass_all_three_cases_by_cell_and_method': [
                          {'method': method, 'variant': tag,
                           'all_three_pass': all(x['both_false_alarm_budgets_passed'] is True for x in budgets
                                                 if x['method'] == method and x['variant'] == tag)}
                          for method in protocol()['methods'] for tag in protocol()['cells']],
                      'foundation_passed': False, 'RIGHT_spatial_component_passed': False,
                      'not_causal_or_unseen_validation_or_full_fine_cross_cell_result': True,
                      'outputs': cp['completed']}
        text = '# 同点提前量配对与误报双预算只读核验\n\n'
        text += '本阶段仅重读已冻结结果，新增正式预测0、新诊断预测0。累计正式2238、已验诊断48、数值2286。\n\n'
        text += f'已验三轨迹、九个方法组合、90项配对/交互与36行原7万误报预算；独立集合交集及逐点值核对{checks}数组。\n\n'
        text += f"原7万36行中，点误报与帧误报双预算同时通过{acceptance['false_alarm_both_pass_rows']}行；这只核两项误报预算，不是完整基础门通过。\n\n"
        text += '| 方法 | 固定处理 | 三轨迹均满足双误报预算 |\n| --- | --- | --- |\n'
        for item in acceptance['false_alarm_both_pass_all_three_cases_by_cell_and_method']:
            text += f"| {item['method']} | {item['variant']} | {'是' if item['all_three_pass'] else '否'} |\n"
        text += '\n## 原7万同点比较\n\n| 轨迹 | 方法 | 对比 | 共同检出数 | 配对差值中位数/秒 | 配对差值P10/秒 |\n| --- | --- | --- | ---: | ---: | ---: |\n'
        for row in rows:
            if row['cohort'] != 'original_70000':
                continue
            d = row.get('paired_delta_after_minus_before', row.get('paired_difference_of_differences'))
            show = lambda x: '未定义' if x is None else f'{x:.9f}'
            text += f"| {row['case_id']} | {row['method']} | {row['contrast']} | {row['matched_points']} | {show(d['median_s'])} | {show(d['p10_s'])} |\n"
        text += '\n## 解释边界\n\n全部90行、原条件分位数与同点分位数变化、逐点ID及两侧提前量和差值见本run的cases目录。原7万与367个事后反例分别报告，第三轨迹空反例未省略；空集分位数保持null。共同检出交集仍是处理后的选择集，配对差值分位数不等于两组分位数之差，也不证明因果效应。两交叉格没有完整细总体结果。\n\n保留原完整基础/密度与空间覆盖门失败，84配置0可行；S4整体/M2/S5未完成，不选优、不调参、不启动M2/S5。有限栅格低速运动学仿真不是连续空间或实车安全证明。\n'
        payloads = [(RUN/'acceptance.json', encoded(acceptance)), (RUN/'reports/all_contrasts.json', encoded(rows)),
                    (RUN/'reports/false_alarm_budgets.json', encoded(budgets)), (REPORT, text.encode('utf-8'))]
        resources(sum(len(v) for _, v in payloads)+65536)
        for path, blob in payloads:
            freeze(path, blob)
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)
    kernel, mutex = q.pipeline.core.acquire_lock()
    kernel.ReleaseMutex(mutex)
    kernel.CloseHandle(mutex)
    freeze(RUN/'close_receipt.json', encoded({'status': 'closed', 'time': q.base.utc_now(),
           'acceptance_sha256': q.base.file_hash(RUN/'acceptance.json'), 'report_sha256': q.base.file_hash(REPORT),
           'mutex_reacquired_and_released_after_close': True, 'new_predictions': 0}))
    print(json.dumps(acceptance, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    close() if args.close else main()
