from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_negative_census_v2'))
import run_census as v2

base, np = v2.base, v2.np
PROTOCOL = ROOT / 'protocol_geometric_sampling_audit_v1.json'
RUN = ROOT / 'runs' / 'resume_S4_geometric_sampling_audit_v1'


def geometric_order(xy, spacing=.0125):
    cells = np.rint(xy/spacing).astype(np.int64)
    if not np.allclose(cells*spacing, xy, atol=1e-10, rtol=0):
        raise AssertionError('Geometry-only sampling requires the frozen raster')
    cells -= cells.min(axis=0)
    bits = int(cells.max()).bit_length()
    if bits > 31:
        raise ValueError('Raster indices exceed the audited 64-bit Morton encoding')
    code = np.zeros(len(cells), dtype=np.uint64)
    for bit in range(bits):
        code |= ((cells[:, 0].astype(np.uint64) >> np.uint64(bit)) & np.uint64(1)) << np.uint64(2*bit)
        code |= ((cells[:, 1].astype(np.uint64) >> np.uint64(bit)) & np.uint64(1)) << np.uint64(2*bit+1)
    if len(np.unique(code)) != len(code):
        raise AssertionError('Raster points or Morton codes are not unique')
    return np.argsort(code, kind='stable')


def systematic_ids(order, count, offset):
    if not 0 < offset < 1 or not 0 < count <= len(order):
        raise ValueError('Invalid systematic sample design')
    ranks = np.floor((np.arange(count)+offset)*(len(order)/count)).astype(np.int64)
    ids = order[ranks].astype(np.int32)
    if len(np.unique(ids)) != count:
        raise AssertionError('Diagnostic sample contains duplicate points')
    return ids


def load_v1():
    path = ROOT / 'src_s4_negative_census_v1' / 'run_census.py'
    spec = importlib.util.spec_from_file_location('frozen_negative_census_v1', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    kernel, mutex = v2.pipeline.core.acquire_lock()
    try:
        if (RUN / 'reports' / 'sampling_audit.json').exists():
            raise RuntimeError('Frozen geometric sampling audit exists; do not overwrite')
        p = base.read_json(PROTOCOL)
        v2.pipeline.common.storage_guard.__defaults__ = (p['execution']['reserve_bytes'], p['execution']['research_budget_bytes'])
        v2.pipeline.common.storage_guard()
        source = {path.relative_to(ROOT).as_posix(): base.file_hash(path) for path in [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]}
        source.update(v2.signature())
        v1 = load_v1()
        source.update(v1.signature())
        rows, refs, masks = [], [], {}
        for module in (v1, v2):
            if base.read_json(module.RUN / 'runner_lock.json')['status'] != 'stopped':
                raise RuntimeError('Wait until every prediction runner has stopped')
            cp = base.read_json(module.RUN / 'checkpoint.json')
            if cp['source_signature'] != module.signature() or len(cp['completed']) != len(module.jobs()):
                raise AssertionError('Census checkpoint incomplete or source changed')
            for job in module.jobs():
                values, report = module.verify(job, cp['completed'][job['id']])
                ref = job['reference']
                path = module.RUN / 'targets.npz' if module is v1 else module.target_paths(ref['case_id'])[0]
                with np.load(path) as saved:
                    targets = {key: saved[key] for key in saved.files}
                old, _, _ = module.read_reference(ref)
                with np.load(module.RUN / 'jobs' / job['id'] / 'new_negative_results.npz') as saved:
                    delta = {key: saved[key] for key in saved.files}
                full = module.dep.reconstruct_delta(old, delta, targets['reference_ids'], targets['new_ids'], len(targets['xy']))
                if any(base.array_hash(full[key]) != sha for key, sha in report['full_point_arrays_sha256'].items()):
                    raise AssertionError('Census point reconstruction differs')
                case = ref['case_id']
                if case not in masks:
                    negative = np.flatnonzero(~np.isfinite(targets['contact_time']))
                    if not np.array_equal(negative, np.flatnonzero(targets['group'] == 2)):
                        raise AssertionError('Default tolerance negative population differs from frozen strata')
                    order = negative[geometric_order(targets['xy'][negative])]
                    masks[case] = {(count, offset): systematic_ids(order, count, offset)
                                   for count in p['negative_sample_counts'] for offset in p['within_rank_offsets']}
                for vdict in ref['variants']:
                    variant = module.pipeline.Variant(**vdict)
                    reference = next(row for row in values if row['variant'] == variant.tag and row['cohort'] == 'full_negative_census')
                    first = full[variant.tag+'_first']
                    false = np.isfinite(first) & (first >= 2-1e-9) & (first <= report['score_end_s']+1e-9)
                    for (count, offset), ids in masks[case].items():
                        if count < p['minimum_unique_diagnostic_points']:
                            raise AssertionError('Diagnostic point count below minimum')
                        rate = 100*int(false[ids].sum())/len(ids)
                        rows.append({'case_id': case, 'core_id': ref['core_id'], 'condition': ref['condition']['id'],
                                     'variant': variant.tag, 'negative_sample_count': count, 'offset': offset,
                                     'false_positive_points': int(false[ids].sum()), 'sample_negative_fp_pct': rate,
                                     'finite_population_negative_fp_pct': reference['negative_fp_pct'],
                                     'population_error_pp': rate-reference['negative_fp_pct'], 'indices_sha256': base.array_hash(ids)})
                refs.append({'source_run': module.RUN.name, 'job_id': job['id'], 'report_sha256': cp['completed'][job['id']]['report_sha256'],
                             'target_file_sha256': report['target_file_sha256'], 'checkpoint_sha256': base.file_hash(module.RUN / 'checkpoint.json')})
        lookup = {tuple(r[k] for k in ('case_id', 'core_id', 'condition', 'variant', 'negative_sample_count', 'offset')): r for r in rows}
        for row in rows:
            hold = lookup[(row['case_id'], 'hold', row['condition'], row['variant'], row['negative_sample_count'], row['offset'])]
            row['method_minus_hold_effect_error_pp'] = row['population_error_pp']-hold['population_error_pp']
            counts = p['negative_sample_counts']
            position = counts.index(row['negative_sample_count'])
            previous = lookup.get((row['case_id'], row['core_id'], row['condition'], row['variant'], counts[position-1], row['offset'])) if position else None
            row['adjacent_density_change_pp'] = row['sample_negative_fp_pct']-previous['sample_negative_fp_pct'] if previous else None
        if len(refs) != 18 or len(rows) != 324:
            raise AssertionError('Expected three cases, eighteen prediction references and 324 diagnostic scores')
        limits = p['limits']
        passed = all(abs(r['population_error_pp']) <= limits['absolute_population_error_pp']
                     and abs(r['method_minus_hold_effect_error_pp']) <= limits['method_minus_hold_effect_error_pp']
                     and (r['adjacent_density_change_pp'] is None or abs(r['adjacent_density_change_pp']) <= limits['adjacent_density_change_pp']) for r in rows)
        RUN.mkdir(parents=True, exist_ok=True)
        for name, sha in source.items():
            saved = RUN / 'source' / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and base.file_hash(saved) != sha:
                raise AssertionError('Frozen analysis source changed')
            if not saved.exists():
                saved.write_bytes((ROOT / name).read_bytes())
        base.csv_rows(RUN / 'reports' / 'geometric_sampling_scores.csv', rows)
        result = {'status': 'complete_negative_component_diagnostic', 'new_prediction_jobs': 0, 'reused_census_predictions': 18,
                  'score_rows': 324, 'geometry_only_negative_component_passed': passed, 'original_full_density_gate_override': False,
                  'source_signature': source, 'original_main_targets_and_rankings_unchanged': True,
                  'limits_pp_unchanged': limits, 'S4_complete': False, 'S5_complete': False, 'physical_validation': False,
                  'captured_at_utc': base.utc_now()}
        base.write_json_retry(RUN / 'reports' / 'sampling_audit.json', result)
        base.write_json_retry(RUN / 'reports' / 'manifest.json', {'source_signature': source, 'references': refs,
            'outputs_sha256': {name: base.file_hash(RUN / 'reports' / name) for name in ('geometric_sampling_scores.csv', 'sampling_audit.json')}})
        base.write_json_retry(RUN / 'checkpoint.json', {'status': result['status'], 'new_prediction_jobs': 0, 'references_verified': 18, 'source_signature': source})
        base.save_checkpoint_gzip(RUN / 'checkpoint.json.gz', (RUN / 'checkpoint.json').read_bytes())
        print(json.dumps({key: value for key, value in result.items() if key != 'source_signature'}), flush=True)
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
