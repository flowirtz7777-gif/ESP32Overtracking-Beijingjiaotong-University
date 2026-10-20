"""Complete remaining-label diagnostic; original labels and proofs unchanged."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'
sys.path.insert(0, str(ROOT / 'src_s4_label_merge_20261022_v1'))
import merge_driver as parent
import observability_core as core
import numpy as np

base, r, AUTH = parent.base, parent.r, parent.AUTH
PARENT = parent.RUN
RUN = ROOT / 'runs/resume_20261022_0000_label_observability_v1'
PROTOCOL = ROOT / 'protocol_label_observability_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v19.json'
SESSION = AUTH / 'runtime_sessions/label_observability_launch_v1'
RESERVATION = 224 * 1024**2
PARENT_HASHES = {
    'checkpoint.json': 'e109f83adfb59b183b1bee923d091f742eb39000706e221c23da80d5cc50ed88',
    'acceptance.json': 'e06a69c19cbd5542ab30062e68a5b141f402392782d1ca9b2d53e621f1adcab9',
    'close_receipt.json': '4ff407351bb0944bbbebe63563f24443f4bd8b923979b5a3a7b42127bcdbd285'}


def configure():
    parent.configure()
    r.RUN, r.RUN_CAP = RUN, 256 * 1024**2


configure()


def execution():
    try:
        return parent.execution()
    finally:
        configure()


def gate():
    parent.verify()
    for name, digest in PARENT_HASHES.items():
        r.require(r.file_hash(PARENT / name) == digest, 'Independently closed merged dependency changed')
    a = r.read(PARENT / 'acceptance.json')
    r.require(a['strict_merged_all_point_prefix_coverage_passed'] is True and a['truth_asset_promotion_allowed'] is False
              and a['accounting']['complete_census_point_file_records'] == 51606
              and a['accounting']['complete_census_group_unique_points'] == 43670,
              'Whole updated census and complete bound prefix coverage required')


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')}
    paths.update(PARENT / name for name in (*PARENT_HASHES, 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json',
                  AUTH / 'runtime_sessions/label_merge_closed_v1/registration.json'))
    for version in (1, 2):
        paths.update(p for p in (AUTH / ('runtime_sessions/label_observability_development_tests_v' + str(version))).rglob('*')
                     if p.is_file())
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify(*, full=True):
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen observability source dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Frozen observability source copy differs')
    if full:
        parent.verify()
        inventory = r.read(RUN / 'parent_files_sha256.json')
        r.require({p.relative_to(PARENT).as_posix() for p in PARENT.rglob('*') if p.is_file()} == set(inventory),
                  'Complete closed merged file set changed')
        for rel, digest in inventory.items():
            r.require(r.file_hash(PARENT / rel) == digest, 'Closed merged asset changed')


def admit():
    try:
        gate()
        loaded, groups, _, _, _, _ = parent.admit()
        cp = r.read(PARENT / 'checkpoint.json')
        accepted = r.read(PARENT / 'acceptance.json')
        assets = {}
        for key, ids in groups.items():
            arrays, record = base.read_arrays(PARENT / 'groups' / key)
            entry = cp['completed'][key]
            r.require(r.file_hash(PARENT / 'groups' / key / 'result.json') == entry['group']['result_sha256']
                      and record['original_dataset_ids'] == ids, 'Complete merged group binding differs')
            paths = {tag: parent.budget.prefixed(arrays, tag + '__') for tag in parent.core.TAGS}
            combined = parent.budget.prefixed(arrays, 'combined__')
            flags, scope = parent.census.core.classify(paths['oldpath'], paths['independent'], combined)
            r.require(np.array_equal(flags, arrays['all_reason_flags'])
                      and np.array_equal(np.packbits(scope, bitorder='little'), arrays['all_scope_packbits']),
                      'Updated complete scope, reasons or mask padding differ')
            unknown, meta = base.read_arrays(PARENT / 'census/groups' / key)
            r.require(base.array_meta(unknown) == base.array_meta(parent.census.core.group_payload(
                arrays['xy'], paths, combined, flags, scope))
                and r.file_hash(PARENT / 'census/groups' / key / 'result.json') == entry['census_group']['result_sha256'],
                'Full updated selected records differ')
            for dataset_id in ids:
                out, _ = base.read_arrays(PARENT / 'datasets' / dataset_id)
                index = out['union_index']
                expected = parent.core.project(index, arrays['xy'], loaded[dataset_id]['target']['xy'],
                    paths, combined, flags, scope, arrays)
                r.require(base.array_meta({k: out[k] for k in expected}) == base.array_meta(expected)
                          and r.file_hash(PARENT / 'datasets' / dataset_id / 'result.json') == entry['datasets'][dataset_id]['result_sha256'],
                          'Every original-order full-field merged projection required')
                projected, _ = base.read_arrays(PARENT / 'census/datasets' / dataset_id)
                r.require(base.array_meta(projected) == base.array_meta(parent.census.core.projection_payload(
                    index, arrays['xy'], loaded[dataset_id]['target']['xy'], flags, scope))
                    and r.file_hash(PARENT / 'census/datasets' / dataset_id / 'result.json') == entry['census_datasets'][dataset_id]['result_sha256'],
                    'Every updated unknown original-order projection required')
            assets[key] = arrays, record, paths
        r.require(len(groups) == 39 and len(loaded) == 57 and sum(int((v[0]['all_reason_flags'] != 0).sum())
                  for v in assets.values()) == 43670, 'Complete updated unknown population required')
        return loaded, groups, assets, accepted['accounting']
    finally:
        configure()


def build_group(key, loaded, groups, asset):
    full = asset[0]
    scope = full['all_reason_flags'] != 0
    index = np.flatnonzero(scope)
    out = {'union_index': index, 'xy': full['xy'][index], 'reason_flags': full['all_reason_flags'][index],
           'full_scope_packbits': np.packbits(scope, bitorder='little')}
    summaries = {}
    for tag, time, state, error, vehicle, original_labels in parent.census.p.follow.paths_for(key, loaded, groups, asset):
        labels = {k: v[index] for k, v in original_labels.items()}
        params = dict(length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
        geometry = lambda xy, pose: base.finite_face_geometry(xy, pose, **params)
        speeds = base.motion_bound(state, time, **params)
        metrics = core.diagnose(out['xy'], time, state, labels, error, vehicle, geometry, speeds, base.original_corner_rule)
        out.update({tag + '__label__' + k: v for k, v in labels.items()})
        out.update({tag + '__metric__' + k: v for k, v in metrics.items()})
        summaries[tag] = core.summary(labels, metrics)
    return out, {'points': len(index), 'paths': summaries}


def project(dataset_id, loaded, full, group_arrays):
    source, _ = base.read_arrays(PARENT / 'datasets' / dataset_id)
    indices = source['union_index']
    scope = full['all_reason_flags'] != 0
    selected = np.flatnonzero(scope[indices])
    lookup = np.full(len(scope), -1, np.int64)
    lookup[group_arrays['union_index']] = np.arange(len(group_arrays['union_index']))
    rows = lookup[indices[selected]]
    r.require(np.all(rows >= 0) and np.array_equal(full['xy'][indices], loaded[dataset_id]['target']['xy']),
              'All original coordinates and selected projection rows required')
    out = {'original_index': selected, 'union_index': indices[selected],
        'xy': loaded[dataset_id]['target']['xy'][selected], 'reason_flags': full['all_reason_flags'][indices[selected]],
        'full_scope_packbits': np.packbits(scope[indices], bitorder='little')}
    for name, values in group_arrays.items():
        if '__label__' in name or '__metric__' in name:
            out[name] = values[rows]
    summaries = {tag: core.summary(parent.budget.prefixed(out, tag + '__label__'),
        parent.budget.prefixed(out, tag + '__metric__')) for tag in parent.core.TAGS}
    return out, {'points': len(selected), 'paths': summaries}


def record(key, summary, dataset=None):
    folder = PARENT / ('groups' if dataset is None else 'datasets') / (key if dataset is None else dataset)
    return {'summary': summary, 'group': key, 'parent_result_sha256': r.file_hash(folder / 'result.json'),
        'parent_checkpoint_sha256': PARENT_HASHES['checkpoint.json'], 'labels_and_prefix_proofs_unchanged': True,
        'hypothetical_zero_temporal_envelope_not_a_new_label': True, 'not_global_nonidentifiability_proof': True}


def accounting(completed):
    groups = [v['group']['summary'] for v in completed.values()]
    rows = [v['summary'] for entry in completed.values() for v in entry['datasets'].values()]
    return {'geometry_groups': len(groups), 'dataset_files': len(rows),
        'group_unique_scope_points': sum(v['points'] for v in groups),
        'selected_point_file_records': sum(v['points'] for v in rows),
        'group_point_path_records_not_independent_samples': 2 * sum(v['points'] for v in groups),
        'weighted_path_diagnostics': {tag: {name: sum(v['paths'][tag][name] for v in rows)
            for name in ('known_noncontact_exact_proof_reuse', 'possible_without_witness',
                'possible_without_witness_initial_origin', 'possible_without_witness_time_leaf_origin', 'witnessed',
                'witnessed_edge_uncertain', 'uncertain_edge_spatial_only_midpoint_rule_passes',
                'uncertain_edge_spatial_only_midpoint_rule_fails', 'budget_flags')} for tag in parent.core.TAGS}}


def source_rules_pass(summary):
    return all(v['budget_flags'] == 0 and v['all_saved_initial_and_edge_rules_exact']
        and v['all_reconstructed_leaf_lowers_exact'] and v['all_retained_leaf_predicates_reproduced']
        for v in summary['paths'].values())


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Observability synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'complete-remaining-label-post-prefix-observability-v1',
            'deadline': r.read(AUTH / 'authorization.json')['deadline'], 'parent': str(PARENT), 'parent_hashes': PARENT_HASHES,
            'selection': 'every and only current full updated combined census scope, both paths; all 39 groups and 57 projections',
            'expected_group_scope_points': 43670, 'expected_point_file_scope_records': 51606,
            'constructor_provenance': 'frozen nonbudget source logic: initial possible or exact reconstructed dyadic retained time leaf',
            'not_historical_trace_or_global_nonidentifiability_proof': True,
            'queries': 'initial only when lower equals initial time; retained leaf midpoint; witnessed bracket midpoint and upper',
            'no_query_before_proven_lower_and_no_known_noncontact_geometry_recomputed': True,
            'same_space_error_tol_and_corner_rule': True, 'time_resolution_s': core.RESOLUTION,
            'zero_temporal_envelope_is_hypothetical_same_midpoint_rule_only': True,
            'negative_margins_kept_exact_never_cleared': True, 'independent_close_scalar_trig_and_GE0S_all_selected_records': True,
            'no_new_labels_prefix_proofs_prediction_or_score_changes': True, 'truth_asset_promotion_allowed': False,
            'development_fixture_failure_preserved': str(AUTH / 'runtime_sessions/label_observability_development_tests_v1'),
            'unfrozen_fixture_correction_only': 'positive-y front-left corner code7, not front-right code5',
            'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION, 'total_E_Z_cap_bytes': r.CAP,
            'Z_reserve_bytes': r.RESERVE, 'workers': 1, 'inflight': 1,
            'submitted_block': 'one complete group and all its original-order diagnostic projections; drain after cutoff',
            'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v18.json'),
            'version': '20261022-0000-v19-complete-remaining-label-observability', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'scientific_acceptance_exists': False, 'next_action': 'full post-prefix diagnostic all current unknown records; no relabeling'}
        inventory = {p.relative_to(PARENT).as_posix(): r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'parent_files_sha256.json', r.encoded(inventory)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))]
                + [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('COMPLETE LABEL OBSERVABILITY PREPARED; actual full-input admission pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'labels_and_prefix_proofs_unchanged': True}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, parent_counts = admit()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'groups': groups,
                'parent_accounting': parent_counts, 'execution': idle, 'mutex': mutex,
                'all_57_inputs_full_merged_fields_and_current_census_bound': True}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='complete_remaining_label_observability_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                running_predictions=False, input_worker_admitted=True, input_worker_admission_pending=False,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'))
            r.mutable(ROOT / 'active_research_run.json', active)
            print('OBSERVABILITY PREFLIGHT PASSED ALL 57 INPUTS / 39 MERGED GROUPS / FULL UPDATED SCOPE', flush=True)
            for key, ids in groups.items():
                r.require(r.before_deadline(), 'No new complete observability group after cutoff')
                verify(full=False)
                arrays, summary = build_group(key, loaded, groups, assets[key])
                entry = {'group': base.save_arrays(RUN / 'groups' / key, arrays, record(key, summary)), 'datasets': {}}
                for dataset_id in ids:
                    projected, values = project(dataset_id, loaded, assets[key][0], arrays)
                    entry['datasets'][dataset_id] = base.save_arrays(RUN / 'datasets' / dataset_id,
                        projected, record(key, values, dataset_id))
                cp['completed'][key] = entry
                r.checkpoint(cp)
                r.require(source_rules_pass(summary), 'Full diagnostic/source discrepancy saved; stop propagation')
                print('DONE COMPLETE OBSERVABILITY GROUP ' + key, flush=True)
            counts = accounting(cp['completed'])
            r.require(counts['geometry_groups'] == 39 and counts['dataset_files'] == 57
                      and counts['group_unique_scope_points'] == 43670 and counts['selected_point_file_records'] == 51606,
                      'Complete current unknown population required')
            for tag, possible, edges in (('oldpath', 13956, 37650), ('independent', 13710, 32449)):
                values = counts['weighted_path_diagnostics'][tag]
                r.require(values['possible_without_witness'] == possible and values['witnessed_edge_uncertain'] == edges
                          and values['budget_flags'] == 0, 'Every current per-path reason required, not a subset')
            cp.update(status='complete_pending_independent_observability_close', accounting=counts)
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('COMPLETE OBSERVABILITY WORKER EXITING; independent close pending; labels unchanged', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_observability_close' and len(cp['completed']) == 39,
                  'Incomplete diagnostic cannot close')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, assets, _ = admit()
            checks = {}
            for key, ids in groups.items():
                expected, summary = build_group(key, loaded, groups, assets[key])
                entry = cp['completed'][key]
                parent.checked_output(RUN / 'groups' / key, expected, record(key, summary), entry['group'])
                r.require(source_rules_pass(summary), 'Original constructor or finite-face rule differs')
                checks[key] = {}
                for tag, time, state, error, vehicle, _ in parent.census.p.follow.paths_for(key, loaded, groups, assets[key]):
                    labels = parent.budget.prefixed(expected, tag + '__label__')
                    metrics = parent.budget.prefixed(expected, tag + '__metric__')
                    checks[key][tag] = core.independently_check(expected['xy'], time, state, labels, error, vehicle, metrics)
                r.require(set(entry['datasets']) == set(ids), 'Every original diagnostic projection required')
                for dataset_id in ids:
                    output, values = project(dataset_id, loaded, assets[key][0], expected)
                    parent.checked_output(RUN / 'datasets' / dataset_id, output,
                        record(key, values, dataset_id), entry['datasets'][dataset_id])
                print('CLOSE CHECKED ALL UNKNOWN DIAGNOSTIC ROWS GROUP ' + key, flush=True)
            counts = accounting(cp['completed'])
            r.require(counts == cp['accounting'], 'Complete independently checked diagnostic accounting differs')
            value = {'time': r.now(), 'status': 'all_remaining_label_post_prefix_diagnostics_independently_checked_no_relabeling',
                'accounting': counts, 'checks': checks, 'labels_and_prefix_proofs_unchanged': True,
                'not_global_nonidentifiability_proof': True, 'not_historical_trace': True,
                'zero_temporal_envelope_is_hypothetical_same_midpoint_rule_only': True,
                'no_known_noncontact_or_pre_lower_exclusion_recomputed': True, 'truth_asset_promotion_allowed': False,
                'corrected_truth_revalidated_prediction_jobs': 0, 'all_label_dependent_claims_withheld': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex, 'not_formal_ODE_or_real_vehicle_certificate': True}
            r.freeze(RUN / 'acceptance.json', r.encoded(value))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    plan = {**r.read(PLAN), 'version': '20261022-0000-v20-complete-label-observability-closed',
        'stage_status': 'complete_unknown_diagnostic_closed_no_relabeling', 'scientific_acceptance_exists': True,
        'scientific_acceptance_scope': 'all current unknown constructor/geometry diagnostics only',
        'diagnostic_accounting': counts, 'next_action': 'new valid full-domain proofs where possible; retain identifiability limits; full expanded population and score repair pending'}
    report = ('# Complete Remaining Label Observability Diagnostic\n\n'
        'All current unknown records, both paths, all 39 groups / 57 original-order projections. '
        'Exact saved constructor provenance and dyadic retained leaves, current edge-confidence margins and '
        'hypothetical zero-temporal-envelope margins; every negative margin retained. '
        'Independent scalar trigonometry/GEOS checks, no pre-lower or known-noncontact geometry recomputed. '
        'Not a historical trace, global nonidentifiability proof, new label, prefix proof or score repair.\n\n'
        + str(counts) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v20.json', r.encoded(plan)),
        (ROOT / 'reports/label_observability_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='complete_remaining_label_observability_closed_no_relabeling', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v20.json'), next_action=plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('COMPLETE REMAINING LABEL DIAGNOSTIC CLOSED; no relabeling ' + str(counts), flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        argv = [str(r.PYTHON), '-X', 'utf8', '-B', '-u', str(Path(__file__)), 'run']
        r.freeze(SESSION / 'policy.json', r.encoded({'time': r.now(), 'argv': argv, 'execution': idle,
            'mutex': mutex, 'resources': r.guard(RESERVATION, RESERVATION), 'cwd': r'C:\Users\Admin'}))
    for name in ('stdout.log', 'stderr.log'):
        r.freeze(SESSION / name, b'')
    with (SESSION / 'stdout.log').open('ab') as stdout, (SESSION / 'stderr.log').open('ab') as stderr:
        child = subprocess.Popen(argv, cwd=r'C:\Users\Admin', stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            env=dict(os.environ), creationflags=subprocess.CREATE_NO_WINDOW)
    r.freeze(SESSION / 'launched.json', r.encoded({'time': r.now(), 'pid_historical_identity_only': child.pid,
        'poll': child.poll(), 'not_admission_proof': True}))
    print('COMPLETE LABEL OBSERVABILITY LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
