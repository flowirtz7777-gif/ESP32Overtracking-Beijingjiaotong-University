from __future__ import annotations

from pathlib import Path
import json
import os
import sys
sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_density_repair_v2'))
import run_density_repair_v2 as dep

np, base = dep.np, dep.base
PROTOCOL = ROOT / 'protocol_sampling_diagnostic_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_sampling_diagnostic_v1'
REPORTS = RUN / 'reports'
METRICS = ('right_pct', 'negative_fp_pct', 'common_2s_reference_fpr_pct', 'right_lead_p10_s')


def guard(policy):
    dep.pipeline.common.storage_guard()
    used = sum(p.stat().st_size for p in RUN.rglob('*') if p.is_file()) if RUN.exists() else 0
    if used > policy['execution']['new_run_budget_bytes']:
        raise RuntimeError('Diagnostic run budget reached; preserve history and stop')


def save_progress(path, progress):
    base.write_json_retry(path, progress)
    payload = path.read_bytes()
    digest = base.file_hash(path)
    base.save_checkpoint_gzip(RUN / 'checkpoint_snapshots' / (digest+'.json.gz'), payload)


def shared_indices(group, count, seed):
    rng = np.random.Generator(np.random.PCG64(seed))
    selected = []
    for layer in range(3):
        available = np.flatnonzero(group == layer)
        wanted = count // 3 + (layer < count % 3)
        if wanted > len(available):
            raise ValueError('Cannot sample more unique points than exist')
        selected.append(rng.permutation(available)[:wanted])
    return np.concatenate(selected).astype(np.int32)


def metrics(targets, points, tag, ids, score_end):
    contact = targets['contact_time'][ids]
    first = points[tag+'_first'][ids]
    valid = points[tag+'_valid'][ids]
    right = ((~targets['front_ignored'][ids]) & (targets['edge'][ids] == 2)
             & np.isfinite(contact) & (contact >= 2-1e-9) & (contact <= score_end+1e-9))
    missing = ~np.isfinite(valid)
    late = np.isfinite(valid) & (contact-valid < 1-1e-9)
    negative = ~np.isfinite(contact)
    false = np.isfinite(first) & (first >= 2-1e-9) & (first <= score_end+1e-9)
    rn, nn = int(right.sum()), int(negative.sum())
    fp = int((negative & false).sum())
    ref_fp = int(points[tag+'_ref_FP'][ids].sum())
    ref_n = int(points[tag+'_ref_negative_opportunities'][ids].sum())
    lead = contact[right & ~missing]-valid[right & ~missing]
    return {'target_count': len(ids), 'right_contacts': rn, 'right_miss': int((right & missing).sum()),
            'right_late': int((right & late).sum()), 'right_pct': 100*int((right & (missing | late)).sum())/rn if rn else None,
            'negative_count': nn, 'negative_fp': fp, 'negative_fp_pct': 100*fp/nn if nn else None,
            'common_2s_reference_fpr_pct': 100*ref_fp/ref_n if ref_n else None,
            'right_lead_p10_s': float(np.quantile(lead, .1)) if len(lead) else None}


def nested_fp_decomposition(old, new, full):
    if old['negative_count']+new['negative_count'] != full['negative_count']:
        raise AssertionError('Negative denominators do not add')
    if old['negative_fp']+new['negative_fp'] != full['negative_fp']:
        raise AssertionError('False-positive counts do not add')
    if not old['negative_count'] or not new['negative_count']:
        return None
    component = new['negative_count']/full['negative_count']*(new['negative_fp_pct']-old['negative_fp_pct'])
    change = full['negative_fp_pct']-old['negative_fp_pct']
    if not np.isclose(component, change, rtol=0, atol=1e-12):
        raise AssertionError('Nested FP decomposition failed')
    return {'full_minus_previous_negative_fp_pp': change, 'added_fraction_of_negative_denominator': new['negative_count']/full['negative_count'],
            'new_minus_old_negative_fp_pp': new['negative_fp_pct']-old['negative_fp_pct'], 'decomposition_component_pp': component}


def main():
    kernel, mutex = dep.pipeline.core.acquire_lock()
    try:
        if (REPORTS / 'sampling_diagnosis.json').exists():
            raise RuntimeError('Frozen diagnosis already exists; do not overwrite')
        policy = base.read_json(PROTOCOL)
        if base.read_json(dep.RUN / 'runner_lock.json')['status'] != 'stopped':
            raise RuntimeError('Prediction runner has not stopped')
        cp_path = dep.RUN / 'checkpoint.json'
        if base.file_hash(cp_path) != policy['dependency_checkpoint_sha256']:
            raise AssertionError('Closed prediction checkpoint changed')
        acceptance_path = dep.RUN / 'reports' / 'acceptance_v3' / 'density_acceptance.json'
        acceptance = base.read_json(acceptance_path)
        if not acceptance['all_outputs_inputs_and_lossless_reconstruction_verified']:
            raise AssertionError('Independent acceptance must finish first')
        dep.pipeline.common.storage_guard.__defaults__ = (policy['execution']['reserve_bytes'], policy['execution']['research_budget_bytes'])
        dep.pipeline.common.storage_guard()
        source = {p.relative_to(ROOT).as_posix(): base.file_hash(p) for p in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]}
        source.update(dep.signature())
        RUN.mkdir(parents=True, exist_ok=True)
        for relative, sha in source.items():
            path = ROOT / relative
            saved = RUN / 'source' / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and base.file_hash(saved) != sha:
                raise AssertionError('Frozen source snapshot changed')
            if not saved.exists():
                saved.write_bytes(path.read_bytes())
        cp = base.read_json(cp_path)
        progress_path = RUN / 'checkpoint.json'
        if progress_path.exists():
            progress = base.read_json(progress_path)
            if progress['source_signature'] != source:
                raise AssertionError('Diagnostic source changed after start')
        else:
            progress = {'status': 'running_analysis', 'source_signature': source, 'completed': {}, 'new_prediction_jobs': 0}
        base.write_json_retry(RUN / 'runner_lock.json', {'status': 'running_analysis', 'pid': os.getpid(), 'time': base.utc_now()})
        masks = {}
        for job in dep.jobs():
            guard(policy)
            if any(base.file_hash(ROOT / path) != sha for path, sha in source.items()):
                raise AssertionError('Diagnostic source changed during execution')
            out = RUN / 'jobs' / job['id'] / 'result.json'
            if job['id'] in progress['completed']:
                if base.file_hash(out) != progress['completed'][job['id']]:
                    raise AssertionError('Completed diagnostic result changed')
                continue
            scores, report = dep.verify(job, cp['completed'][job['id']])
            with np.load(dep.target_path(job['case_id'], job['contact_tolerance_m'])) as data:
                targets = {key: data[key] for key in data.files}
            _, old = dep.baseline_for(job)
            with np.load(dep.RUN / 'jobs' / job['id'] / 'new_target_results.npz') as data:
                delta = {key: data[key] for key in data.files}
            points = dep.reconstruct_delta(old, delta, targets['previous_ids'], targets['new_ids'], len(targets['xy']))
            if any(base.array_hash(points[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
                raise AssertionError('Full point arrays changed')
            case = job['case_id']
            if case not in masks:
                masks[case] = [shared_indices(targets['group'], policy['resample_count'], policy['sampling_seed_start']+i)
                               for i in range(policy['replicates'])]
            main = np.zeros(len(targets['xy']), dtype=bool)
            main[targets['main_ids']] = True
            previous = np.zeros(len(main), dtype=bool)
            previous[targets['previous_ids']] = True
            cohorts = {'main_70000': targets['main_ids'], 'added_70000': np.flatnonzero(previous & ~main),
                       'previous_140000': targets['previous_ids'], 'added_140000': targets['new_ids'],
                       'full_280000': np.arange(len(main), dtype=np.int32)}
            coordinates = np.rint(targets['xy']/.0125).astype(np.int64)
            if not np.allclose(coordinates*.0125, targets['xy'], rtol=0, atol=1e-10):
                raise AssertionError('Target not on frozen .0125m raster')
            phase = coordinates[:, 0] % 2+2*(coordinates[:, 1] % 2)
            cohort_rows, phase_rows, resample_rows, decompositions = [], [], [], []
            for vdict in base.read_json(dep.PROTOCOL)['variants']:
                v = dep.pipeline.Variant(**vdict)
                full = metrics(targets, points, v.tag, cohorts['full_280000'], report['score_end_s'])
                low = metrics(targets, points, v.tag, cohorts['previous_140000'], report['score_end_s'])
                for count, observed in ((140000, low), (280000, full)):
                    expected = next(row for row in scores if row['target_count'] == count and row['margin_m'] == v.margin and row['confirmation_s'] == v.confirmation)
                    for key, value in observed.items():
                        if value != expected[key]:
                            raise AssertionError('Metric reconstruction differs: '+key)
                for name, ids in cohorts.items():
                    cohort_rows.append({'variant': v.tag, 'cohort': name, **metrics(targets, points, v.tag, ids, report['score_end_s'])})
                    for layer in range(3):
                        for q in range(4):
                            selected = ids[(targets['group'][ids] == layer) & (phase[ids] == q)]
                            phase_rows.append({'variant': v.tag, 'cohort': name, 'stratum': layer, 'lattice_phase': q,
                                               **metrics(targets, points, v.tag, selected, report['score_end_s'])})
                added = metrics(targets, points, v.tag, targets['new_ids'], report['score_end_s'])
                decompositions.append({'variant': v.tag, **nested_fp_decomposition(low, added, full)})
                for i, ids in enumerate(masks[case]):
                    sample = metrics(targets, points, v.tag, ids, report['score_end_s'])
                    resample_rows.append({'variant': v.tag, 'seed': policy['sampling_seed_start']+i,
                                          'indices_sha256': base.array_hash(ids), **sample,
                                          **{metric+'_minus_full': sample[metric]-full[metric] if sample[metric] is not None and full[metric] is not None else None for metric in METRICS}})
            result = {'job_id': job['id'], 'case_id': case, 'core_id': job['core_id'], 'condition': job['condition']['id'],
                      'contact_tolerance_m': job['contact_tolerance_m'], 'cohorts': cohort_rows, 'lattice': phase_rows,
                      'resamples': resample_rows, 'decompositions': decompositions,
                      'prediction_report_sha256': cp['completed'][job['id']]['report_sha256'], 'new_prediction_jobs': 0}
            base.write_json_retry(out, result)
            progress['completed'][job['id']] = base.file_hash(out)
            save_progress(progress_path, progress)
            print(f'DONE SAMPLING ANALYSIS {len(progress["completed"])}/54 {job["id"]}', flush=True)
        cohort_rows, lattice_rows, resample_rows, decompositions = [], [], [], []
        for job in dep.jobs():
            r = base.read_json(RUN / 'jobs' / job['id'] / 'result.json')
            keys = {key: r[key] for key in ('job_id', 'case_id', 'core_id', 'condition', 'contact_tolerance_m')}
            for target, key in ((cohort_rows, 'cohorts'), (lattice_rows, 'lattice'), (resample_rows, 'resamples'), (decompositions, 'decompositions')):
                target.extend({**keys, **row} for row in r[key])
        prefix = [r for r in cohort_rows if r['cohort'] == 'previous_140000']
        full_rows = {(r['job_id'], r['variant']): r for r in cohort_rows if r['cohort'] == 'full_280000'}
        summaries = []
        for row in prefix:
            ref = full_rows[(row['job_id'], row['variant'])]
            sampled = [s for s in resample_rows if s['job_id'] == row['job_id'] and s['variant'] == row['variant']]
            for metric in METRICS:
                values = [s[metric+'_minus_full'] for s in sampled if s[metric+'_minus_full'] is not None]
                delta = row[metric]-ref[metric] if row[metric] is not None and ref[metric] is not None else None
                summaries.append({**{key: row[key] for key in ('job_id', 'case_id', 'core_id', 'condition', 'contact_tolerance_m', 'variant')},
                                  'metric': metric, 'observed_prefix_minus_full': delta,
                                  'conditional_resample_q025': float(np.quantile(values, .025)) if values else None,
                                  'conditional_resample_q975': float(np.quantile(values, .975)) if values else None,
                                  'conditional_resample_max_abs': max(map(abs, values)) if values else None,
                                  'replicates': len(values)})
        for name, rows in (('cohort_rates.csv', cohort_rows), ('lattice_rates.csv', lattice_rows), ('resample_rates.csv', resample_rows),
                           ('nested_fp_decomposition.csv', decompositions), ('conditional_resample_summary.csv', summaries)):
            base.csv_rows(REPORTS / name, rows)
        result = {'status': 'complete_read_only_diagnostic', 'verified_prediction_jobs_reused': len(progress['completed']),
                  'new_prediction_jobs': 0, 'resampling_rows': len(resample_rows), 'replicates': policy['replicates'],
                  'density_acceptance_overridden': False, 'density_gate_still_failed': not acceptance['passes_subset_density_gate'],
                  'scope': 'conditional_on_existing_280000_not_an_independent_population_or_real_vehicle_validation',
                  'source_signature': source, 'dependency_checkpoint_sha256': base.file_hash(cp_path),
                  'dependency_acceptance_sha256': base.file_hash(acceptance_path), 'captured_at_utc': base.utc_now()}
        progress['status'] = 'complete_read_only_diagnostic'
        guard(policy)
        save_progress(progress_path, progress)
        base.write_json_retry(REPORTS / 'sampling_diagnosis.json', result)
        base.write_json_retry(REPORTS / 'manifest.json', {'source_signature': source, 'jobs': progress['completed'],
            'outputs_sha256': {p.name: base.file_hash(p) for p in sorted(REPORTS.iterdir()) if p.is_file()}})
        print(json.dumps({key: value for key, value in result.items() if key != 'source_signature'}), flush=True)
    finally:
        if RUN.exists():
            base.write_json_retry(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
