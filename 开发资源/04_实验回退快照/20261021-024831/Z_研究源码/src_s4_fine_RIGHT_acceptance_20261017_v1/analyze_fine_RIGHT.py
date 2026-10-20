from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src_s4_fine_RIGHT_census_20261017_v1'))
import run_fine_RIGHT as f

base, np, pipeline = f.base, f.np, f.pipeline
PROTOCOL = ROOT/'protocol_fine_RIGHT_acceptance_20261017_v1.json'
RUN = ROOT/'runs/resume_20261017_fine_RIGHT_acceptance_v1'
EXPECTED_PROTOCOL = '93f18b3759922bbff2d9c4a45baf86688ebccc18ee43bb65b67a0a7f9e23b29d'
EXPECTED_PREDICTION_CP = '96166078c1b6b75ee36d620a0e01a08349f167e47d44cf0eea25294fea79572d'
ANNOTATIONS = {'case_id', 'core_id', 'condition', 'variant', 'cohort', 'independent_validation',
               'changed_population_not_ranked_with_old_weighting', 'changed_population_not_used_for_old_rankings'}


def protocol():
    return base.read_json(PROTOCOL)


def signature():
    paths = [PROTOCOL, *sorted(Path(__file__).parent.glob('*.py'))]
    return {**f.signature(), **{p.relative_to(ROOT).as_posix(): base.file_hash(p) for p in paths}}


def worker_init():
    p = protocol()['execution']
    pipeline.common.storage_guard.__defaults__ = (p['reserve_bytes'], p['experiment_budget_bytes'])


def resources(extra=0):
    p = protocol()['execution']
    result = pipeline.common.storage_guard(p['reserve_bytes'], p['experiment_budget_bytes'])
    used = sum(x.stat().st_size for x in RUN.rglob('*') if x.is_file()) if RUN.exists() else 0
    if used+extra > p['new_run_budget_bytes'] or result['experiment_bytes']+extra > p['experiment_budget_bytes'] or result['free_bytes']-extra < p['reserve_bytes']:
        raise RuntimeError('Read-only acceptance resource checkpoint; preserve existing files')
    return {**result, 'analysis_run_bytes': used}


def put(path, value):
    resources(len(f.coarse.json_bytes(value))+8192)
    base.write_json_retry(path, value)


def freeze(path, payload):
    if path.exists():
        raise AssertionError('Frozen output exists; do not overwrite or rerun')
    resources(len(payload)+8192)
    path.parent.mkdir(parents=True, exist_ok=True)
    until = time.monotonic()+30
    while True:
        try:
            with path.open('xb') as stream:
                stream.write(payload)
            break
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or time.monotonic() >= until or path.exists():
                raise
            time.sleep(.1)
    if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(payload).digest():
        raise AssertionError('Written payload differs')


def save_cp(cp):
    put(RUN/'checkpoint.json', cp)
    blob = (RUN/'checkpoint.json').read_bytes()
    freeze(RUN/'checkpoint_snapshots'/(base.file_hash(RUN/'checkpoint.json')+'.json.gz'), gzip.compress(blob, compresslevel=1, mtime=0))


def phases(xy):
    xy = np.asarray(xy)
    cells = np.rint(xy/.00625).astype(np.int64)
    if not np.allclose(cells*.00625, xy, rtol=0, atol=1e-8):
        raise AssertionError('Coordinates left frozen fine lattice')
    return (cells[:, 0] % 2 + 2*(cells[:, 1] % 2)).astype(np.int8)


def cohorts(targets, cut, prefix):
    eligible = f.coarse.geometry.eligible_right(targets, cut)
    phase = phases(targets['xy'])
    ids = {'full_fine_RIGHT': np.flatnonzero(eligible).astype(np.int32)}
    for k in range(4):
        ids['phase'+str(k)+'_RIGHT'] = np.flatnonzero(eligible & (phase == k)).astype(np.int32)
    old = np.flatnonzero(eligible[:prefix]).astype(np.int32)
    if not np.array_equal(old, ids['phase0_RIGHT']):
        raise AssertionError('Phase0 is not the complete frozen coarse RIGHT prefix')
    if not np.array_equal(np.sort(np.concatenate([ids['phase'+str(k)+'_RIGHT'] for k in range(4)])), ids['full_fine_RIGHT']):
        raise AssertionError('Phases are not disjoint and complete')
    return ids, phase


def encode_miss_mask(mask):
    mask = np.asarray(mask)
    if mask.dtype != np.bool_ or mask.ndim != 1:
        raise ValueError('One-dimensional boolean mask required')
    packed = np.packbits(mask, bitorder='little')
    ids = np.flatnonzero(mask).astype(np.int32)
    metadata = {'bitorder': 'little', 'target_length': len(mask), 'miss_count': len(ids),
        'packed_array_sha256': base.array_hash(packed), 'sorted_index_dtype': ids.dtype.str,
        'sorted_index_array_sha256': base.array_hash(ids)}
    if base.array_hash(decode_miss_mask(packed, metadata)) != base.array_hash(ids):
        raise AssertionError('Miss indices did not round-trip')
    return packed, metadata


def decode_miss_mask(packed, metadata):
    packed = np.asarray(packed)
    n = metadata['target_length']
    if type(n) is not int or n < 0 or metadata['bitorder'] != 'little' or packed.dtype != np.uint8 or packed.ndim != 1 or len(packed) != (n+7)//8:
        raise AssertionError('Invalid lossless bit mask representation')
    if base.array_hash(packed) != metadata['packed_array_sha256']:
        raise AssertionError('Packed mask SHA differs')
    bits = np.unpackbits(packed, bitorder='little')
    if bits[n:].any():
        raise AssertionError('Nonzero mask padding')
    ids = np.flatnonzero(bits[:n]).astype(np.dtype(metadata['sorted_index_dtype']))
    if len(ids) != metadata['miss_count'] or base.array_hash(ids) != metadata['sorted_index_array_sha256']:
        raise AssertionError('Decoded sorted miss index SHA/count differs')
    return ids


def miss_pair(full_misses, subset_ids, prefix):
    subset_misses = np.intersect1d(full_misses, subset_ids, assume_unique=True).astype(np.int32)
    added = np.setdiff1d(full_misses, subset_misses, assume_unique=True).astype(np.int32)
    removed = np.setdiff1d(subset_misses, full_misses, assume_unique=True).astype(np.int32)
    return {'subset_misses': len(subset_misses), 'reference_misses': len(full_misses),
        'added_count': len(added), 'removed_count': len(removed),
        'added_index_sha256': base.array_hash(added), 'removed_index_sha256': base.array_hash(removed),
        'subset_miss_index_sha256': base.array_hash(subset_misses),
        'added_indices_in_new_target_suffix_count': int((added >= prefix).sum()),
        'zero_miss_claim_lost': len(subset_misses) == 0 and len(full_misses) > 0}


def difference(a, b, p, effect=False):
    values, undefined, passed = {}, [], []
    for field in p['absolute_rate_fields']+p['lead_quantile_fields']:
        if a[field] is None or b[field] is None:
            delta = None
            undefined.append(field)
            ok = False
        else:
            delta = a[field]-b[field]
            rate = field in p['absolute_rate_fields']
            limit = p['paired_method_minus_hold_rate_effect_max_change_pp' if rate else 'paired_method_minus_hold_lead_effect_max_change_s'] if effect else p['absolute_rate_max_change_pp' if rate else 'lead_max_change_s']
            ok = abs(delta) <= limit+1e-12
        values[field] = {'difference': delta, 'within_prespecified_limit': ok}
        passed.append(ok)
    return {'metrics': values, 'undefined_metrics': undefined, 'numeric_limits_met': all(passed)}


def method_effect(method, hold, p):
    return {field: method[field]-hold[field] if method[field] is not None and hold[field] is not None else None
            for field in p['absolute_rate_fields']+p['lead_quantile_fields']}


def composition(subset, full):
    a = {int(r['group']): r for r in subset['stratum_right_rows']}
    b = {int(r['group']): r for r in full['stratum_right_rows']}
    n, total = subset['right_contacts'], full['right_contacts']
    exact = bool(n and total) and all(a.get(k, {}).get('right_contacts', 0)*total == b.get(k, {}).get('right_contacts', 0)*n for k in range(3))
    result = {'integer_stratum_proportions_exactly_equal': exact, 'raw_population_composition_may_differ': not exact}
    if not n or not total or set(a) != set(b):
        return {**result, 'within_stratum_term_pp': None, 'composition_term_pp': None, 'reconstruction_residual_pp': None}
    within = sum(a[k]['right_contacts']/n*(a[k]['right_insufficient_pct']-b[k]['right_insufficient_pct']) for k in a)
    mix = sum((a[k]['right_contacts']/n-b[k]['right_contacts']/total)*b[k]['right_insufficient_pct'] for k in a)
    residual = subset['right_pct']-full['right_pct']-within-mix
    if abs(residual) > 1e-10:
        raise AssertionError('Rate decomposition is inconsistent')
    return {**result, 'within_stratum_term_pp': within, 'composition_term_pp': mix, 'reconstruction_residual_pp': residual}


def describe_layers(targets, state, ids):
    result = []
    for layer in range(3):
        chosen = ids[targets['group'][ids] == layer]
        if not len(chosen):
            continue
        valid = state['valid'][chosen]
        contact = targets['contact_time'][chosen]
        first = state['first'][chosen]
        miss = ~np.isfinite(valid)
        late = np.isfinite(valid) & (contact-valid < 1-1e-9)
        lead = contact[~miss]-valid[~miss]
        result.append({'group': layer, 'eligible_RIGHT_count': len(chosen), 'miss_count': int(miss.sum()),
            'late_count': int(late.sum()), 'no_before_count': int((~np.isfinite(first) | (first > contact+1e-9)).sum()),
            'insufficient_pct': 100*int((miss | late).sum())/len(chosen),
            'valid_only_lead_p10_s': float(np.quantile(lead, .1)) if len(lead) else None,
            'valid_only_lead_median_s': float(np.quantile(lead, .5)) if len(lead) else None})
    by_layer = {r['group']: r for r in result}
    equal = .5*(by_layer[0]['insufficient_pct']+by_layer[1]['insufficient_pct']) if 0 in by_layer and 1 in by_layer else None
    return result, equal


def numeric_summary(row):
    return {k:v for k,v in row.items() if k not in ANNOTATIONS}


def frozen_dependency():
    p = protocol()
    if base.file_hash(PROTOCOL) != EXPECTED_PROTOCOL:
        raise AssertionError('Rules frozen before predictions changed')
    if base.read_json(f.RUN/'runner_lock.json')['status'] != 'stopped':
        raise AssertionError('Prediction runner still active; do not open checkpoint')
    if base.file_hash(f.RUN/'checkpoint.json') != EXPECTED_PREDICTION_CP:
        raise AssertionError('Closed fine prediction checkpoint differs')
    cp = base.read_json(f.RUN/'checkpoint.json')
    if cp['status'] != 'fine_RIGHT_spatial_diagnostic_complete' or len(cp['completed']) != 9 or cp['source_signature'] != f.signature():
        raise AssertionError('Nine closed diagnostic jobs with exact source required')
    if base.file_hash(ROOT/'src_s4_fine_RIGHT_census_20261017_v1/run_fine_RIGHT.py') != p['prediction_source_sha256'] or base.file_hash(f.PROTOCOL) != p['prediction_protocol_sha256']:
        raise AssertionError('Frozen predictor implementation differs')
    f.dependencies()
    manifest = base.read_json(f.RUN/'reports/manifest.json')
    if manifest['jobs'] != cp['completed'] or manifest['checkpoint_sha256'] != EXPECTED_PREDICTION_CP:
        raise AssertionError('Closed predictor manifest differs')
    for name, sha in manifest['outputs_sha256'].items():
        if base.file_hash(f.RUN/'reports'/name) != sha:
            raise AssertionError('Frozen predictor summary changed')
    registration = base.read_json(f.RUN/'runtime_sessions/20261017_sampling_rules_before_new_predictions/registration.json')
    if not registration['no_new_prediction_start_or_completion_in_log_at_freeze']:
        raise AssertionError('Missing pre-prediction rule freeze evidence')
    frozen_protocol = f.RUN/'runtime_sessions/20261017_sampling_rules_before_new_predictions'/PROTOCOL.name
    if base.file_hash(frozen_protocol) != EXPECTED_PROTOCOL:
        raise AssertionError('Pre-prediction protocol snapshot differs')
    for name, sha in cp['source_signature'].items():
        if base.file_hash(ROOT/name) != sha or base.file_hash(f.RUN/'source'/name) != sha:
            raise AssertionError('Frozen predictor source snapshot differs')
    for path in (f.RUN/'checkpoint_snapshots').glob('*.json.gz'):
        if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != path.name.split('.')[0]:
            raise AssertionError('Predictor checkpoint snapshot differs')
    return cp


def reconstruct(job, report):
    old, _, _ = f.read_coarse(job)
    folder = f.RUN/'jobs'/job['id']
    ref = job['coarse_reference']['reference']
    raw, _ = pipeline.load_observation(ref['partition'], ref['case_id'], ref['condition'])
    with np.load(folder/'packed_delta.npz') as saved:
        delta = f.coarse.unpack_points({k:saved[k] for k in saved.files}, base.read_json(folder/'packed_metadata.json'), raw['time'])
    full = f.merge_outputs(old, delta, report['full_target_count'])
    if {k:base.array_hash(v) for k,v in full.items()} != report['full_point_arrays_sha256']:
        raise AssertionError('Independent full point-array reconstruction differs')
    if any(base.array_hash(full[k][:len(old[k])]) != base.array_hash(old[k]) for k in old):
        raise AssertionError('Old coarse point outcome differs')
    return full


def verify_controls(job, new_rows):
    folder = f.coarse.RUN/'jobs'/job['coarse_reference']['id']
    old_rows = base.read_json(folder/'summary.json')
    for variant in protocol()['variants']:
        for new_name, old_name in [('original_70000', 'original_70000'), ('old_280000_near_negative_controls', 'original_280000_near_negative_controls'), ('complete_coarse_RIGHT', 'full_eligible_RIGHT_finite_population')]:
            before = next(r for r in old_rows if r['variant'] == variant and r['cohort'] == old_name)
            after = next(r for r in new_rows if r['variant'] == variant and r['cohort'] == new_name)
            if numeric_summary(before) != numeric_summary(after):
                raise AssertionError('Original main/coarse/negative control summary differs')


def probe():
    return {'python': sys.executable, 'root': str(ROOT), 'source_signature': signature(),
        'guard_defaults': list(pipeline.common.storage_guard.__defaults__),
        'deadline': protocol()['execution']['deadline_local'], 'read_only_new_predictions': 0}


def main():
    p = protocol()
    if datetime.now(timezone.utc) >= datetime.fromisoformat(p['execution']['deadline_local']):
        raise RuntimeError('New independent analysis cannot start after today 14:00')
    kernel, mutex = pipeline.core.acquire_lock()
    started, cp = False, None
    try:
        if (RUN/'checkpoint.json').exists() or (RUN/'reports/fine_spatial_acceptance.json').exists():
            raise AssertionError('Prior analysis attempt exists; do not rerun or overwrite')
        worker_init()
        dependency = frozen_dependency()
        source = signature()
        bit_bound = 6*sum((c['full_target_count']+7)//8 for c in f.protocol()['cases'])
        resources(bit_bound+4*1024**2)
        for name, sha in source.items():
            freeze(RUN/'source'/name, (ROOT/name).read_bytes())
        put(RUN/'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': base.utc_now(), 'read_only_analysis': True})
        started = True
        cp = {'status': 'readonly_fine_spatial_acceptance_running', 'source_signature': source,
              'prediction_checkpoint_sha256': EXPECTED_PREDICTION_CP, 'completed': {}, 'new_prediction_jobs': 0}
        save_cp(cp)
        with ProcessPoolExecutor(max_workers=1, initializer=worker_init) as pool:
            actual = pool.submit(probe).result(timeout=180)
        if actual['source_signature'] != source or Path(actual['python']) != Path(r'C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe') or actual['guard_defaults'] != [p['execution']['reserve_bytes'], p['execution']['experiment_budget_bytes']] or actual['deadline'] != p['execution']['deadline_local']:
            raise AssertionError('Actual Windows read-only analysis worker differs')
        freeze(RUN/'actual_worker.json', f.coarse.json_bytes(actual))
        rows, pairs, index_records, verified, fairness = [], [], [], [], {}
        for j, job in enumerate(f.jobs()):
            if datetime.now(timezone.utc) >= datetime.fromisoformat(p['execution']['deadline_local']):
                raise RuntimeError('Analysis deadline checkpoint; preserve partial output')
            saved_rows, report = f.verify(job, dependency['completed'][job['id']])
            verify_controls(job, saved_rows)
            targets, proof, target_sha = f.load_targets(job['case']['id'])
            ids_by_cohort, phase = cohorts(targets, report['score_end_s'], job['case']['coarse_prefix_count'])
            cohort_proofs = {name: {'count': len(ids), 'index_sha256': base.array_hash(ids),
                'coordinate_sha256': base.array_hash(targets['xy'][ids]),
                'label_sha256': {k:base.array_hash(targets[k][ids]) for k in f.coarse.geometry.LABEL_KEYS},
                'stratum_counts': {str(k):int((targets['group'][ids] == k).sum()) for k in range(3)}} for name,ids in ids_by_cohort.items()}
            case = job['case']['id']
            common = {'cohorts': cohort_proofs, **{k:report[k] for k in ('input_hashes', 'raw_sensor_hashes', 'estimated_state_sha256', 'estimated_alpha_sha256', 'score_start_s', 'score_end_s')}}
            if case in fairness and fairness[case] != common:
                raise AssertionError('Method target/label/observation/estimate/score input fairness differs')
            fairness[case] = common
            full = reconstruct(job, report)
            data, _, _ = pipeline.core.load_case(f.protocol()['partition'], case)
            masks, metadata, job_rows, job_pairs = {}, {}, [], []
            for vdict in job['coarse_reference']['reference']['variants']:
                variant = pipeline.Variant(**vdict)
                state = {k:full[variant.tag+'_'+k] for k in ('raw', 'first', 'valid')}
                state.update(variant=variant, point_counts={k:full[variant.tag+'_'+k] for k in f.COUNT_FIELDS})
                part_rows = {}
                for cohort, ids in ids_by_cohort.items():
                    summary = f.coarse.projected_summary(data, targets, state, ids)
                    layer_rows, equal = describe_layers(targets, state, ids)
                    row = {**summary, 'case_id': case, 'core_id': job['core_id'], 'condition': 'noise100_s1',
                        'variant': variant.tag, 'cohort': cohort, 'index_sha256': cohort_proofs[cohort]['index_sha256'],
                        'layer_descriptions': layer_rows, 'half_half_strata_insufficient_pct_descriptive_only': equal,
                        'window_miss_pct_descriptive': 100*summary['right_miss']/summary['right_contacts'] if summary['right_contacts'] else None,
                        'not_full_foundation_or_independent_validation': True}
                    part_rows[cohort] = row
                    job_rows.append(row)
                expected_full = next(r for r in saved_rows if r['variant'] == variant.tag and r['cohort'] == 'complete_fine_RIGHT')
                if any(part_rows['full_fine_RIGHT'][k] != v for k,v in numeric_summary(expected_full).items()):
                    raise AssertionError('Full finite population summary differs from frozen predictor output')
                mask = np.zeros(len(targets['xy']), bool)
                full_ids = ids_by_cohort['full_fine_RIGHT']
                mask[full_ids] = ~np.isfinite(state['valid'][full_ids])
                packed, meta = encode_miss_mask(mask)
                masks[variant.tag] = packed
                metadata[variant.tag] = meta
                full_misses = decode_miss_mask(packed, meta)
                for cohort, ids in ids_by_cohort.items():
                    if cohort == 'full_fine_RIGHT':
                        continue
                    pair = {'case_id': case, 'core_id': job['core_id'], 'variant': variant.tag, 'cohort': cohort,
                        **difference(part_rows[cohort], part_rows['full_fine_RIGHT'], p),
                        **miss_pair(full_misses, ids, job['case']['coarse_prefix_count']),
                        **composition(part_rows[cohort], part_rows['full_fine_RIGHT']),
                        'subset_stratum_right_rows': part_rows[cohort]['stratum_right_rows'],
                        'reference_stratum_right_rows': part_rows['full_fine_RIGHT']['stratum_right_rows'],
                        'mask_file': 'miss_masks/'+job['id']+'.npz', 'mask_key': variant.tag,
                        'subset_index_sha256': cohort_proofs[cohort]['index_sha256'],
                        'index_regeneration': 'decode_full_mask; phase0..3 from frozen xy; difference/intersection of sorted int32 indices'}
                    job_pairs.append(pair)
            stream = io.BytesIO()
            np.savez_compressed(stream, **masks)
            mask_path = RUN/'miss_masks'/(job['id']+'.npz')
            freeze(mask_path, stream.getvalue())
            with np.load(mask_path) as saved:
                for variant, meta in metadata.items():
                    decoded = decode_miss_mask(saved[variant], meta)
                    for pair in [x for x in job_pairs if x['variant'] == variant]:
                        restored = miss_pair(decoded, ids_by_cohort[pair['cohort']], job['case']['coarse_prefix_count'])
                        if any(pair[k] != v for k,v in restored.items()):
                            raise AssertionError('Added/removed miss indices do not round-trip from saved bit mask')
            record = {'id': job['id'], 'predictor_record': dependency['completed'][job['id']],
                'target_manifest_sha256': target_sha, 'mask_file_sha256': base.file_hash(mask_path),
                'mask_metadata': metadata, 'cohort_proofs': cohort_proofs,
                'all_inputs_outputs_and_full_array_reconstruction_verified': True,
                'original_main_coarse_and_negative_controls_exact': True,
                'rows': job_rows, 'pairs': job_pairs}
            path = RUN/'jobs'/(job['id']+'.json')
            freeze(path, f.coarse.json_bytes(record))
            cp['completed'][job['id']] = {'report_sha256': base.file_hash(path), 'mask_file_sha256': base.file_hash(mask_path)}
            save_cp(cp)
            rows.extend(job_rows)
            pairs.extend(job_pairs)
            index_records.append({'job_id':job['id'], 'mask_file':str(mask_path.relative_to(RUN)), 'mask_metadata':metadata})
            verified.append({'id':job['id'], **cp['completed'][job['id']]})
            print('VERIFIED FINE RIGHT READONLY '+str(j+1)+'/9 '+job['id'], flush=True)
        lookup = {(r['case_id'],r['core_id'],r['variant'],r['cohort']):r for r in rows}
        effects = []
        for case in p['cases']:
            for variant in p['variants']:
                for core in [c for c in p['core_ids'] if c != 'hold']:
                    full_effect = method_effect(lookup[case,core,variant,'full_fine_RIGHT'],lookup[case,'hold',variant,'full_fine_RIGHT'],p)
                    for k in p['phases_all_reported']:
                        cohort = 'phase'+str(k)+'_RIGHT'
                        subset_effect = method_effect(lookup[case,core,variant,cohort],lookup[case,'hold',variant,cohort],p)
                        effects.append({'case_id':case, 'core_id':core, 'variant':variant, 'cohort':cohort,
                            'subset_method_minus_hold':subset_effect, 'reference_method_minus_hold':full_effect,
                            **difference(subset_effect,full_effect,p,effect=True)})
        if (len(rows),len(pairs),len(effects)) != (90,72,48):
            raise AssertionError('Pre-specified 90/72/48 matrix incomplete')
        numerical_bad = [r for r in pairs if not r['numeric_limits_met']]
        effect_bad = [r for r in effects if not r['numeric_limits_met']]
        zero_lost = [r for r in pairs if r['zero_miss_claim_lost']]
        summary = {'status':'readonly_spatial_acceptance_complete', 'source_signature':source,
            'prediction_checkpoint_sha256':EXPECTED_PREDICTION_CP, 'summary_rows':len(rows), 'phase_comparisons':len(pairs),
            'effect_comparisons':len(effects), 'numeric_limit_failed_pairs':len(numerical_bad),
            'numeric_limit_failed_effects':len(effect_bad), 'zero_miss_claim_lost_pairs':len(zero_lost),
            'RIGHT_spatial_component_passed':not numerical_bad and not effect_bad and not zero_lost,
            'all_nine_inputs_outputs_full_reconstruction_and_common_inputs_verified':True,
            'common_input_case_groups':len(fairness), 'all_miss_masks_and_added_removed_indices_roundtripped':True,
            'new_prediction_jobs':0, 'new_diagnostic_predictions_in_dependency':9,
            'formal_total':2238, 'accepted_diagnostic_total':30, 'accepted_numeric_total':2268,
            'old_full_density_failure_overridden':False, 'complete_foundation_accepted':False,
            'algorithm_search_M2_or_S5_admitted':False, 'S4_complete':False, 'S5_complete':False,
            'finite_grid_not_random_sampling_error_or_algorithm_improvement':True,
            'not_independent_truth_or_vehicle_safety_proof':True,
            'phase0_and_named_coarse_are_same_evidence':True}
        outputs = {'summary_rows.json':{'rows':rows}, 'phase_comparisons.json':{'rows':pairs},
            'effect_comparisons.json':{'rows':effects}, 'miss_index_reconstruction.json':{'records':index_records},
            'common_input_proofs.json':fairness, 'verified_jobs.json':{'jobs':verified}, 'fine_spatial_acceptance.json':summary}
        for name, value in outputs.items():
            freeze(RUN/'reports'/name, f.coarse.json_bytes(value))
        cp['status'] = 'readonly_spatial_acceptance_complete'
        cp['RIGHT_spatial_component_passed'] = summary['RIGHT_spatial_component_passed']
        save_cp(cp)
        manifest = {'source_signature':source, 'prediction_checkpoint_sha256':EXPECTED_PREDICTION_CP,
            'checkpoint_sha256':base.file_hash(RUN/'checkpoint.json'), 'jobs':cp['completed'],
            'outputs_sha256':{name:base.file_hash(RUN/'reports'/name) for name in outputs}}
        freeze(RUN/'reports/manifest.json',f.coarse.json_bytes(manifest))
        if base.file_hash(f.RUN/'checkpoint.json') != EXPECTED_PREDICTION_CP:
            raise AssertionError('Frozen prediction checkpoint changed during analysis')
        print(json.dumps({k:v for k,v in summary.items() if k != 'source_signature'}),flush=True)
    except BaseException as error:
        if cp is not None:
            cp.update(status='analysis_failed_checkpoint_saved',error=repr(error))
            save_cp(cp)
        raise
    finally:
        if started:
            put(RUN/'runner_lock.json',{'status':'stopped','pid':os.getpid(),'time':base.utc_now()})
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
