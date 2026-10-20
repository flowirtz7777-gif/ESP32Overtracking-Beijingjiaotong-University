"""New supplemental hull proof; all earlier conditional results stay frozen."""
from __future__ import annotations
import argparse
import io
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
sys.path.insert(0, str(ROOT / 'src_s4_prefix_leaf_diagnostic_20261022_v1'))
import driver as diagnostic
import hull
import numpy as np
import shapely

base, r, follow = diagnostic.base, diagnostic.r, diagnostic.follow
PARENT = diagnostic.RUN
AUTH = diagnostic.AUTH
RUN = ROOT / 'runs/resume_20261022_0000_prefix_hull_completion_v1'
PROTOCOL = ROOT / 'protocol_prefix_hull_completion_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v7.json'
SESSION = AUTH / 'runtime_sessions/prefix_hull_completion_launch_v1'
RESERVATION = 96 * 1024**2
PARENT_HASHES = {
    'checkpoint.json': '9cc4a3abb33bb3aa94895a1762a43c2a66dab024c4345dd7d52fcd39c6243b7f',
    'acceptance.json': '15484df2ba74ad8381dc8942c5b363d378760a84369505979b21cfb156806b78',
    'close_receipt.json': 'a53d0b778da05d3493cb64c169faa1a8dbdb1264c836e100699e3a74a29d2899'}


def configure():
    diagnostic.configure()
    r.RUN, r.RUN_CAP = RUN, 128 * 1024**2


configure()


def execution():
    try:
        return diagnostic.execution()
    finally:
        configure()


def gate():
    diagnostic.verify()
    for name, digest in PARENT_HASHES.items():
        r.require(r.file_hash(PARENT / name) == digest, 'Closed diagnostic parent changed')
    accepted = r.read(PARENT / 'acceptance.json')
    r.require(accepted['all_original_final_arrays_exact'] is True
              and accepted['strict_all_point_prefix_gate_passed'] is False
              and accepted['remaining_prefix_unknown_points'] == 1, 'Closed unknown evidence required')


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')}
    paths.update(PARENT / name for name in (*PARENT_HASHES, 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json'))
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Frozen hull proof dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Hull source snapshot differs')
    for rel, digest in r.read(RUN / 'parent_files_sha256.json').items():
        r.require(r.file_hash(PARENT / rel) == digest, 'Closed leaf diagnostic asset changed')


def independent_geometry(point, time, states, lower, error, vehicle, proof, summary):
    expected_dtypes = {'interval': np.dtype('int32'), 'status': np.dtype('uint8'), 'evaluations': np.dtype('int8'),
                       **{name: np.dtype('float64') for name in hull.FLOAT_FIELDS}}
    r.require(set(proof) == set(expected_dtypes) and all(v.ndim == 1 and v.dtype == expected_dtypes[k]
              for k, v in proof.items()) and len({len(v) for v in proof.values()}) == 1, 'Proof schema differs')
    until = float(time[-1] if np.isnan(lower) else lower)
    r.require(summary['audited_until_s'] == until and summary['original_lower_is_nan'] == bool(np.isnan(lower)),
              'Original lower/path endpoint changed')
    hull.validate_tree(proof, time, until, summary['all_required_prefix_excluded'])
    count, checked, analytic_checks = 0, 0, 0
    geos_point = shapely.Point(point)
    for i in range(len(proof['interval'])):
        k, code, evaluations = (int(proof[name][i]) for name in ('interval', 'status', 'evaluations'))
        a, b = proof['a'][i], proof['b'][i]
        r.require(evaluations in (0, 1, 2), 'Invalid evaluation accounting')
        count += evaluations
        r.require(count <= 131072, 'Fixed per-point GEOS budget exceeded')
        if evaluations == 0:
            r.require(code == hull.BUDGET and count == 131072
                      and all(np.isnan(proof[n][i]) for n in hull.FLOAT_FIELDS[2:]), 'Uncomputed geometry lost')
            continue
        delta = states[k + 1] - states[k]
        pose_a, pose_b = states[k] + a * delta, states[k] + b * delta
        endpoint_corners = diagnostic.leaf.common.body_corners(np.stack((pose_a, pose_b)), vehicle)
        polygon = shapely.convex_hull(shapely.MultiPoint(endpoint_corners.reshape(-1, 2)))
        distance = float(shapely.distance(geos_point, polygon))
        span_theta, span_heading = (b - a) * delta[2], (b - a) * (delta[2] - delta[3])
        curve = (abs(vehicle.l_h) * span_theta**2
                 + np.hypot(vehicle.L, vehicle.width / 2) * span_heading**2) / 8
        saved_curve = proof['curvature_m'][i]
        r.require(proof['hull_distance_m'][i] == distance and np.isclose(curve, saved_curve, rtol=1e-13, atol=1e-30),
                  'Independent endpoint hull/chord enclosure differs')
        saved_margin = distance - saved_curve - error - 1e-12 - base.TOLERANCE
        r.require(proof['exclusion_margin_m'][i] == saved_margin, 'Original error/guard/tolerance changed')
        conservative_margin = distance - max(float(curve), float(saved_curve)) - error - 1e-12 - base.TOLERANCE
        checked += 1
        if code == hull.EXCLUDED:
            r.require(conservative_margin > 0 and evaluations == 1 and np.isnan(proof['midpoint_distance_m'][i]),
                      'Nonpositive full-leaf distance bound cannot exclude')
        elif code == hull.BUDGET:
            r.require(count == 131072 and evaluations == 1 and saved_margin <= 0
                      and np.isnan(proof['midpoint_distance_m'][i]), 'Budget unknown must remain unknown')
        else:
            r.require(evaluations == 2 and saved_margin <= 0, 'Potential leaf cannot use exclusion evidence')
            pose = states[k] + (a + b) / 2 * delta
            corners = diagnostic.leaf.common.body_corners(pose[None], vehicle)[0]
            middle_distance = float(shapely.distance(geos_point, shapely.Polygon(corners)))
            analytic = diagnostic.analytic_body_distance(point, pose, vehicle)
            r.require(proof['midpoint_distance_m'][i] == middle_distance and abs(analytic - middle_distance) <= 1e-10,
                      'Independent midpoint body geometry differs')
            analytic_checks += 1
            witness = middle_distance + error <= base.TOLERANCE
            if code == hull.WITNESS:
                r.require(witness, 'Unverified early-contact witness')
            else:
                r.require(not witness and (code == hull.UNKNOWN) == ((b - a) * (time[k + 1] - time[k]) <= 1e-8),
                          'Time leaf or split policy changed')
    r.require(count == summary['GEOS_evaluations'] and len(proof['interval']) == summary['proof_rows'],
              'Full evaluation/proof accounting differs')
    terminal = int(proof['status'][-1]) if len(proof['status']) else hull.EXCLUDED
    expected_status = {hull.EXCLUDED: 'excluded', hull.UNKNOWN: 'unknown_time_leaf',
                       hull.WITNESS: 'early_contact_witness', hull.BUDGET: 'unknown_budget'}[terminal]
    r.require(summary['status'] == expected_status, 'Final supplemental status differs')
    return {'full_required_prefix_coverage_checked': bool(summary['all_required_prefix_excluded']),
            'all_recorded_hulls_checked': checked, 'midpoint_analytic_GE0S_checks': analytic_checks,
            'GEOS_evaluations': count, 'unknown_preserved': not summary['all_required_prefix_excluded']}


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN)), 'Already attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Hull synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'conservative-prefix-hull-completion-v1', 'deadline': diagnostic.parent.parent.DEADLINE_LOCAL,
            'parent': str(PARENT), 'parent_hashes': PARENT_HASHES, 'selection': 'all and only final prefix_undetermined',
            'expected_unknown_points': 1, 'all_input_files': 57, 'geometry_groups': 39, 'prefix_paths': 78,
            'all_other_prefix_arrays_exact_reuse': True, 'no_earlier_source_or_result_overwritten': True,
            'proof': 'endpoint corner convex hull plus |lh|*dtheta^2/8 + hypot(L,width/2)*dheading^2/8 chord enclosure',
            'full_original_prefix_endpoints_unchanged': True, 'spatial_error_unchanged': True,
            'time_resolution_s': 1e-8, 'tolerance_m': base.TOLERANCE, 'numerical_guard_m': 1e-12,
            'maximum_GE0S_evaluations_per_point': 131072, 'all_subdivision_nodes_preserved': True,
            'run_cap_bytes': r.RUN_CAP, 'reservation_bytes': RESERVATION, 'E_Z_cap_bytes': r.CAP,
            'Z_reserve_bytes': r.RESERVE, 'workers': 1, 'inflight': 1,
            'conditional_label_unknowns_not_resolved_by_prefix_proof': True,
            'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v6.json'),
            'version': '20261022-0000-v7-prefix-hull-completion', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'next_action': 'full required prefix hull/chord proof all and only remaining prefix unknowns; no forced clearance'}
        hashes = {p.relative_to(PARENT).as_posix(): r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'parent_files_sha256.json', r.encoded(hashes)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
                [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('HULL PREFIX PREPARED; actual input admission still pending', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        gate()
        cp = {'status': 'preflight', 'completed': {}, 'corrected_truth_revalidated_prediction_jobs': 0}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            print('HULL PREFIX PREFLIGHT: all original inputs and closed parent arrays', flush=True)
            loaded, groups, selected, validation = diagnostic.load_all()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'input_files': len(loaded),
                'geometry_groups': len(groups), 'all_original_prefix_arrays_bound': validation,
                'selection': [{'group': key, 'path': tag, 'indices': ids.tolist()} for key, tag, ids, *_ in selected],
                'execution': idle, 'mutex': mutex}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='prefix_hull_completion_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'),
                input_worker_admitted=True, input_worker_admission_pending=False)
            r.mutable(ROOT / 'active_research_run.json', active)
            print('HULL PREFIX PREFLIGHT PASSED 57 INPUTS / 39 GROUPS / 78 PATHS / ALL 1 UNKNOWN', flush=True)
            for key, tag, ids, xy, time, states, error, vehicle, labels, final in selected:
                for index in ids:
                    r.require(r.before_deadline(), 'New supplemental prefix block cutoff')
                    lower = float(labels['contact_lower_s'][index])
                    proof, summary = hull.audit_point(xy[index], time, states, lower, vehicle=vehicle,
                        spatial_error_m=error, tolerance_m=base.TOLERANCE,
                        time_resolution_s=1e-8, maximum_evaluations=131072)
                    blob = base.npz_bytes(proof)
                    name = key + '_' + tag + '_' + str(index)
                    folder = RUN / 'points' / name
                    record = {'group': key, 'path': tag, 'union_index': int(index), 'point_xy': xy[index].tolist(),
                        'original_selected_final': base.array_meta({k: v[index:index + 1] for k, v in final.items()}),
                        'parent_prefix_result_sha256': r.file_hash(diagnostic.PARENT / 'groups' / key / 'result.json'),
                        'arrays': base.array_meta(proof), 'npz_sha256': r.sha(blob), 'summary': summary}
                    r.batch([(folder / 'proof.npz', blob), (folder / 'result.json', r.encoded(record))])
                    cp['completed'][name] = {'result_sha256': r.file_hash(folder / 'result.json'), 'summary': summary}
                    r.checkpoint(cp)
                    r.require(summary['status'] != 'early_contact_witness', 'Early-contact counterexample saved; stop')
            cp['status'] = 'complete_pending_independent_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('HULL PREFIX WORKER EXITING; independent close pending', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted close or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        gate()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_close' and len(cp['completed']) == 1, 'Incomplete hull batch')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, selected, validation = diagnostic.load_all()
            checks = []
            for key, tag, ids, xy, time, states, error, vehicle, labels, final in selected:
                for index in ids:
                    name = key + '_' + tag + '_' + str(index)
                    folder = RUN / 'points' / name
                    saved = r.read(folder / 'result.json')
                    r.require(r.file_hash(folder / 'result.json') == cp['completed'][name]['result_sha256']
                              and saved['summary'] == cp['completed'][name]['summary'], 'CP/result differs')
                    blob = (folder / 'proof.npz').read_bytes()
                    r.require(r.sha(blob) == saved['npz_sha256'], 'Hull NPZ SHA differs')
                    with np.load(io.BytesIO(blob), allow_pickle=False) as decoded:
                        proof = {k: decoded[k] for k in decoded.files}
                    r.require(base.array_meta(proof) == saved['arrays'], 'Full hull proof arrays differ')
                    r.require((saved['group'], saved['path'], saved['union_index']) == (key, tag, int(index))
                              and np.array_equal(saved['point_xy'], xy[index])
                              and saved['original_selected_final'] == base.array_meta({k: v[index:index + 1] for k, v in final.items()})
                              and saved['parent_prefix_result_sha256'] == r.file_hash(diagnostic.PARENT / 'groups' / key / 'result.json'),
                              'Original coordinates, endpoints, final status or parent binding changed')
                    independent = independent_geometry(xy[index], time, states, float(labels['contact_lower_s'][index]),
                        error, vehicle, proof, saved['summary'])
                    checks.append({'group': key, 'path': tag, 'union_index': int(index), 'summary': saved['summary'],
                                   'independent_geometry': independent})
            strict = all(item['summary']['all_required_prefix_excluded'] for item in checks)
            value = {'time': r.now(), 'status': 'full_supplemental_prefix_hull_evidence_independently_checked',
                'strict_all_point_prefix_gate_passed': strict, 'original_full_prefix_acceptance_not_overwritten': True,
                'all_previously_excluded_points_exactly_reused': True, 'all_original_arrays_bound': validation,
                'all_original_input_files': len(loaded), 'geometry_groups': len(groups), 'prefix_paths': 78,
                'all_original_unknown_points': len(checks), 'remaining_prefix_unknown_points': sum(not c['summary']['all_required_prefix_excluded'] for c in checks),
                'checks': checks, 'conditional_label_unknown_point_file_records': 16464,
                'all_label_dependent_claims_withheld': True, 'corrected_truth_revalidated_prediction_jobs': 0,
                'not_formal_ODE_or_real_vehicle_certificate': True, 'source_signature': signature(),
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'execution': idle, 'mutex': mutex}
            r.freeze(RUN / 'acceptance.json', r.encoded(value))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    next_plan = {**r.read(PLAN), 'version': '20261022-0000-v8-prefix-hull-closed',
        'stage_status': 'supplemental_full_prefix_hull_closed_labels_and_scores_still_pending',
        'strict_all_point_prefix_gate_passed': strict,
        'next_action': 'all conditional label unknowns, complete expanded populations, negative controls and every affected score'}
    report = ('# Supplemental Prefix Hull Proof\n\nStrict all-point prefix gate: ' + str(strict)
        + '. Full original required prefix retained; all and only the previous unknown point audited. '
        'Endpoint hull plus original corner-chord/spatial-error bounds independently checked, including every tree node and endpoint. '
        'All earlier results retained. Conditional-label unknown point-file records remain 16464, corrected predictions 0. '
        'Not a formal ODE or vehicle certificate; S4 overall, M2, S5 and dependent claims remain withheld.\n\n'
        + '\n'.join(str(item) for item in checks) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'),
        'execution_after': after, 'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v8.json', r.encoded(next_plan)),
        (ROOT / 'reports/prefix_hull_completion_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='prefix_hull_completion_conditionally_closed', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v8.json'), next_action=next_plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('HULL PREFIX CLOSED; strict gate=' + str(strict) + '; conditional labels and scores still pending', flush=True)


def launch():
    r.require(r.before_deadline() and not SESSION.exists() and not (RUN / 'runner_lock.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        gate()
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
    print('HULL PREFIX LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
