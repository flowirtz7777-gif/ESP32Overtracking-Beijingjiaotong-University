"""Fixed-policy observation of every remaining accepted-prefix unknown, not repair."""
from __future__ import annotations
import argparse
import ctypes
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
sys.path.insert(0, str(ROOT / 'src_s4_population_prefix_20261022_v1'))
import prefix as parent
import leaf
import numpy as np
import shapely

base, r, follow = parent.base, parent.r, parent.follow
PARENT = parent.RUN
AUTH = parent.AUTH
RUN = ROOT / 'runs/resume_20261022_0000_prefix_leaf_diagnostic_v1'
PROTOCOL = ROOT / 'protocol_prefix_leaf_diagnostic_20261022_0000_v1.json'
PLAN = ROOT / 'resume_plan_20261022_0000_v5.json'
SESSION = AUTH / 'runtime_sessions/prefix_leaf_diagnostic_launch_v1'
RESERVATION = 96 * 1024**2
PARENT_HASHES = {
    'checkpoint.json': '13b8e8b7b8cc76dd7381c595cd7799130f199152e8d274692c0927083e8f5857',
    'acceptance.json': '9694aa33d907e292e5ab24a66cc705feb6061ec68e9fcdac3462de87c763b0ae',
    'close_receipt.json': '8947cf0551db908829cee074d1e350240cb24d982a4dd353cd24990c8c3d7d5f'}
EXPECTED_GROUP = '6ce88a849bf12790b6cf3cbe2bf0e52d1c8c7cf1a7f5c58a2eb19c191cdb15b9'


def configure():
    parent.configure()
    r.RUN, r.RUN_CAP = RUN, 128 * 1024**2


configure()


def execution():
    try:
        h, evidence = parent.execution()
    finally:
        configure()
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
    found = []
    for process in parent.parent.admin.command_evidence():
        if process['ProcessId'] == os.getpid() or not process.get('CommandLine'):
            continue
        count = ctypes.c_int()
        pointer = parse(process['CommandLine'], ctypes.byref(count))
        r.require(bool(pointer), 'Cannot decode actual process command line')
        try:
            argv = [pointer[i] for i in range(count.value)]
        finally:
            ctypes.windll.kernel32.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))
        if (len(argv) >= 3 and argv[-1] in ('prepare', 'launch', 'run', 'close')
                and str(ROOT).casefold() in argv[-2].casefold() and argv[-2].endswith('.py')):
            found.append(process)
    r.require(not found, 'Actual research worker remains active')
    evidence['actual_versioned_scientific_processes'] = found
    return h, evidence


def gate():
    parent.verify()
    for name, digest in PARENT_HASHES.items():
        r.require(r.file_hash(PARENT / name) == digest, 'Closed full-prefix evidence changed')
    cp, accepted = (r.read(PARENT / name) for name in ('checkpoint.json', 'acceptance.json'))
    r.require(cp['status'] == 'complete_pending_independent_close' and len(cp['completed']) == 39
              and len(cp['exact_reused_groups']) == 12 and len(cp['new_audited_groups']) == 27,
              'Whole stopped prefix population required')
    r.require(accepted['strict_all_point_prefix_gate_passed'] is False and len(accepted['rows']) == 39,
              'Diagnostic is conditional, never a strict acceptance')
    paths = [value['prefix'] for row in accepted['rows'] for value in row['summary'].values()]
    r.require(len(paths) == 78 and sum(p['prefix_undetermined'] for p in paths) == 1
              and sum(p['early_contact_witness'] for p in paths) == 0
              and sum(p['budget_exhausted'] for p in paths) == 0, 'Original unresolved population differs')
    return cp


def signature():
    paths = {ROOT / rel for rel in r.read(PARENT / 'source_manifest.json')}
    paths.update(PARENT / name for name in (*PARENT_HASHES, 'source_manifest.json'))
    paths.update(SOURCE.glob('*.py'))
    paths.update((PROTOCOL, PLAN, AUTH / 'authorization.json'))
    return {p.relative_to(ROOT).as_posix(): r.file_hash(p) for p in sorted(paths)}


def verify():
    expected = r.read(RUN / 'source_manifest.json')
    r.require(signature() == expected, 'Diagnostic frozen dependencies changed')
    for rel, digest in expected.items():
        r.require(r.file_hash(RUN / 'source' / rel) == digest, 'Diagnostic source snapshot differs')
    for rel, digest in r.read(RUN / 'parent_files_sha256.json').items():
        r.require(r.file_hash(PARENT / rel) == digest, 'Closed parent asset changed')


def selected_indices(final):
    follow.old.summarize_prefix(final)
    return np.flatnonzero(final['prefix_undetermined'])


def exact_arrays(actual, expected):
    r.require(base.array_meta(actual) == base.array_meta(expected), 'Diagnostic differs from original final arrays')


def load_all():
    cp = gate()
    loaded, groups, assets, _, _, _ = parent.load_all()
    selected, validation = [], {}
    for key, entry in cp['completed'].items():
        arrays, saved = parent.validate_prefix_group(key, entry, assets[key], loaded, groups, PARENT)
        validation[key] = {'result_sha256': entry['result_sha256'], 'arrays': saved['arrays']}
        for tag, time, states, error, vehicle, labels in follow.paths_for(key, loaded, groups, assets[key]):
            final = follow.path_arrays(arrays, tag)
            final.pop('refined_indices')
            indices = selected_indices(final)
            if len(indices):
                selected.append((key, tag, indices, assets[key][0]['xy'], time, states, error, vehicle, labels, final))
    r.require(sum(len(row[2]) for row in selected) == 1 and len(selected) == 1
              and selected[0][0:2] == (EXPECTED_GROUP, 'independent'), 'All-and-only unknown population changed')
    return loaded, groups, selected, validation


def policy(error, vehicle):
    return {'vehicle': vehicle, 'spatial_error_m': error, 'tolerance_m': base.TOLERANCE,
            'time_resolution_s': 1e-8, 'max_evaluations_per_point': follow.REFINE_BUDGET}


def analytic_body_distance(point, pose, vehicle):
    # Work in the trailer rectangle frame, independent of polygon corner ordering.
    theta, phi = pose[2:4]
    hitch = pose[:2] + vehicle.l_h * np.array([np.cos(theta), np.sin(theta)])
    angle = theta - phi
    forward = np.array([np.cos(angle), np.sin(angle)])
    left = np.array([-np.sin(angle), np.cos(angle)])
    local = np.array([np.dot(point - hitch, forward), np.dot(point - hitch, left)])
    outside = np.array([max(-vehicle.L - local[0], 0., local[0]), max(abs(local[1]) - vehicle.width / 2, 0.)])
    return float(np.hypot(*outside))


def check_leaf(row, xy, time, states, lower, error, vehicle):
    index, k = row['point_index'], row['interval_index']
    r.require(0 <= index < len(xy) and 0 <= k < len(time) - 1, 'Leaf indices out of range')
    a, b = row['fraction_a'], row['fraction_b']
    r.require(0 <= a < b <= 1, 'Invalid leaf fractions')
    delta, duration = states[k + 1] - states[k], time[k + 1] - time[k]
    middle = (a + b) / 2
    pose = states[k] + middle * delta
    radius = np.hypot(vehicle.L, vehicle.width / 2)
    motion = (np.hypot(delta[0], delta[1]) + abs(vehicle.l_h * delta[2])
              + radius * abs(delta[2] - delta[3])) * (b - a) / 2
    corners = leaf.common.body_corners(pose[None], vehicle)[0]
    point = shapely.Point(xy[index])
    distance = float(shapely.distance(point, shapely.Polygon(corners)))
    analytic = analytic_body_distance(xy[index], pose, vehicle)
    _, face_analytic = base.finite_face_geometry(xy[index:index + 1], pose[None],
        length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
    faces = np.array([shapely.distance(point, shapely.LineString(corners[pair]))
                      for pair in ([3, 0], [0, 1], [1, 2], [2, 3])])
    r.require(abs(distance - analytic) <= 1e-10 and np.allclose(faces, face_analytic[0], rtol=0, atol=1e-10),
              'Independent analytic/GEOS body or finite-face mismatch')
    until = float(time[-1] if np.isnan(lower[index]) else lower[index])
    expected = {'time_a_s': float(time[k] + a * duration), 'time_b_s': float(time[k] + b * duration),
        'time_mid_s': float(time[k] + middle * duration), 'leaf_width_s': float((b - a) * duration),
        'audited_until_s': until, 'time_resolution_s': 1e-8, 'spatial_error_m': float(error),
        'tolerance_m': base.TOLERANCE, 'motion_half_enclosure_m': float(motion),
        'midpoint_distance_GE0S_m': distance,
        'exclusion_margin_m': distance - error - motion - 1e-12 - base.TOLERANCE,
        'contact_witness_margin_m': base.TOLERANCE - distance - error}
    for name, value in expected.items():
        r.require(row[name] == value, 'Independent leaf scalar mismatch: ' + name)
    r.require(np.array_equal(row['point_xy'], xy[index]) and np.array_equal(row['midpoint_pose'], pose),
              'Leaf original coordinate or interpolated pose differs')
    time_leaf = expected['leaf_width_s'] <= 1e-8
    budget = row['GEOS_evaluations'] >= follow.REFINE_BUDGET
    r.require(row['time_leaf'] == time_leaf and row['evaluation_budget'] == budget and (time_leaf or budget),
              'Unknown reason mismatch')
    r.require(expected['time_b_s'] <= until + 1e-12 and expected['exclusion_margin_m'] <= 0
              and expected['contact_witness_margin_m'] < 0, 'Unknown cannot be relabelled as excluded/contact')
    return {'analytic_body_distance_m': analytic, 'GEOS_body_distance_m': distance,
            'analytic_finite_face_distances_m': face_analytic[0].tolist(), 'GEOS_finite_face_distances_m': faces.tolist(),
            'time_leaf': time_leaf, 'budget_exhausted': budget, 'still_undetermined': True}


def prepare():
    r.require(r.before_deadline() and not any(p.exists() for p in (RUN, PROTOCOL, PLAN)), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        gate()
        tests = subprocess.run([str(r.PYTHON), '-X', 'utf8', '-B', '-m', 'unittest', 'discover',
            '-s', str(SOURCE), '-p', 'test_*.py', '-v'], cwd=r'C:\Users\Admin', capture_output=True,
            encoding='utf-8', timeout=180)
        r.require(tests.returncode == 0, 'Synthetic tests failed: ' + tests.stderr)
        protocol = {'version': 'prefix-leaf-diagnostic-v1', 'deadline': parent.parent.DEADLINE_LOCAL,
            'parent': str(PARENT), 'parent_hashes': PARENT_HASHES, 'selection': 'all and only final prefix_undetermined',
            'expected_points': 1, 'input_files': 57, 'geometry_groups': 39, 'prefix_paths': 78,
            'evaluation_budget': follow.REFINE_BUDGET, 'time_resolution_s': 1e-8,
            'tolerance_m': base.TOLERANCE, 'all_empirical_envelopes_unchanged': True,
            'original_kernel_code_object_unchanged': True, 'all_original_final_arrays_exact': True,
            'does_not_repair_or_clear_unknown': True, 'run_cap_bytes': r.RUN_CAP,
            'reservation_bytes': RESERVATION, 'E_Z_cap_bytes': r.CAP, 'Z_reserve_bytes': r.RESERVE,
            'workers': 1, 'inflight': 1, 'corrected_truth_revalidated_prediction_jobs': 0}
        plan = {**r.read(ROOT / 'resume_plan_20261022_0000_v4.json'),
            'version': '20261022-0000-v5-prefix-leaf-diagnostic', 'stage_status': 'prepared_not_admitted',
            'run_directory': str(RUN), 'protocol': str(PROTOCOL), 'entrypoint': str(Path(__file__)),
            'next_action': 'observe every remaining prefix unknown without changing frozen policy or output'}
        hashes = {p.relative_to(PARENT).as_posix(): r.file_hash(p) for p in sorted(PARENT.rglob('*')) if p.is_file()}
        r.batch([(PROTOCOL, r.encoded(protocol)), (PLAN, r.encoded(plan)),
            (RUN / 'parent_files_sha256.json', r.encoded(hashes)),
            (RUN / 'prelaunch.json', r.encoded({'time': r.now(), 'execution': idle, 'mutex': mutex,
                'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'resources': r.guard(RESERVATION, RESERVATION)}))])
        signed = signature()
        r.batch([(RUN / 'source_manifest.json', r.encoded(signed))] +
                [(RUN / 'source' / rel, (ROOT / rel).read_bytes()) for rel in signed])
    print('LEAF DIAGNOSTIC PREPARED; no real-data admission yet', flush=True)


def run():
    r.require(r.before_deadline() and not (RUN / 'checkpoint.json').exists(), 'Attempted or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = {'status': 'preflight', 'completed': {}, 'corrected_truth_revalidated_prediction_jobs': 0}
        r.mutable(RUN / 'runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            print('LEAF PREFLIGHT: full original inputs, conditional assets and closed prefix decoding', flush=True)
            loaded, groups, selected, validation = load_all()
            r.freeze(RUN / 'preflight.json', r.encoded({'time': r.now(), 'input_files': len(loaded),
                'geometry_groups': len(groups), 'all_39_prefix_arrays_bound': validation,
                'selection': [{'group': key, 'path': tag, 'union_indices': ids.tolist()}
                              for key, tag, ids, *_ in selected], 'execution': idle, 'mutex': mutex}))
            active = r.read(ROOT / 'active_research_run.json')
            active.update(status='prefix_leaf_diagnostic_running', run_directory=str(RUN), protocol=str(PROTOCOL),
                plan=str(PLAN), entrypoint=str(Path(__file__)), pid=os.getpid(), running_analysis=True,
                stdout=str(SESSION / 'stdout.log'), stderr=str(SESSION / 'stderr.log'),
                input_worker_admitted=True, input_worker_admission_pending=False)
            r.mutable(ROOT / 'active_research_run.json', active)
            print('LEAF PREFLIGHT PASSED ALL 57 INPUTS / 39 GROUPS / 78 PREFIX PATHS / ALL 1 UNDETERMINED POINT', flush=True)
            for key, tag, indices, xy, time, states, error, vehicle, labels, final in selected:
                r.require(r.before_deadline(), 'New diagnostic block cutoff')
                original = {name: value[indices] for name, value in final.items()}
                lower = labels['contact_lower_s'][indices]
                actual, evidence = leaf.audit_with_leaf_evidence(xy[indices], time, states, lower, **policy(error, vehicle))
                arrays = {'union_indices': indices, 'xy': xy[indices], 'contact_lower_s': lower}
                arrays.update({'original__' + name: value for name, value in original.items()})
                arrays.update({'diagnostic__' + name: value for name, value in actual.items()})
                blob = base.npz_bytes(arrays)
                record = {'time': r.now(), 'group': key, 'path': tag, 'union_indices': indices.tolist(),
                    'arrays': base.array_meta(arrays), 'npz_sha256': r.sha(blob), 'leaves': evidence,
                    'all_original_final_arrays_exact': base.array_meta(actual) == base.array_meta(original),
                    'parent_result_sha256': r.file_hash(PARENT / 'groups' / key / 'result.json')}
                name = key + '_' + tag
                folder = RUN / 'selected' / name
                r.batch([(folder / 'arrays.npz', blob), (folder / 'result.json', r.encoded(record))])
                cp['completed'][name] = {'result_sha256': r.file_hash(folder / 'result.json'), 'points': len(indices)}
                r.checkpoint(cp)
                exact_arrays(actual, original)
                r.require(len(evidence) == len(indices), 'Unobserved uncertainty saved; stop')
            cp['status'] = 'complete_pending_independent_close'
            r.checkpoint(cp)
        except Exception:
            cp.update(status='stopped_failure_or_deadline', failure=traceback.format_exc())
            r.checkpoint(cp)
            raise
        finally:
            r.mutable(RUN / 'runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    print('LEAF WORKER EXITING; independent close pending, strict prefix gate remains false', flush=True)


def close():
    r.require(r.before_deadline() and not (RUN / 'acceptance.json').exists(), 'Attempted close or cutoff')
    h, _ = execution()
    with h.exclusive() as mutex:
        _, idle = execution()
        verify()
        cp = r.read(RUN / 'checkpoint.json')
        r.require(cp['status'] == 'complete_pending_independent_close' and len(cp['completed']) == 1,
                  'Incomplete diagnostic')
        r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'running', 'pid': os.getpid(), 'time': r.now()})
        try:
            loaded, groups, selected, _ = load_all()
            checks = []
            for key, tag, ids, xy, time, states, error, vehicle, labels, final in selected:
                name = key + '_' + tag
                folder = RUN / 'selected' / name
                entry, saved = cp['completed'][name], r.read(folder / 'result.json')
                r.require(r.file_hash(folder / 'result.json') == entry['result_sha256'] and entry['points'] == len(ids),
                          'Diagnostic CP/report mismatch')
                blob = (folder / 'arrays.npz').read_bytes()
                r.require(r.sha(blob) == saved['npz_sha256'], 'Diagnostic NPZ differs')
                with np.load(io.BytesIO(blob), allow_pickle=False) as decoded:
                    arrays = {k: decoded[k] for k in decoded.files}
                r.require(base.array_meta(arrays) == saved['arrays'], 'Full diagnostic decode differs')
                original = {name: value[ids] for name, value in final.items()}
                expected = {'union_indices': ids, 'xy': xy[ids], 'contact_lower_s': labels['contact_lower_s'][ids]}
                expected.update({'original__' + name: value for name, value in original.items()})
                expected.update({'diagnostic__' + name: value for name, value in original.items()})
                exact_arrays(arrays, expected)
                r.require(saved['all_original_final_arrays_exact'] is True and saved['union_indices'] == ids.tolist()
                          and saved['group'] == key and saved['path'] == tag
                          and saved['parent_result_sha256'] == r.file_hash(PARENT / 'groups' / key / 'result.json'),
                          'Original order, source or exact result binding differs')
                r.require(sorted(row['point_index'] for row in saved['leaves']) == list(range(len(ids))),
                          'Every and only unknown must have exactly one leaf')
                for row in saved['leaves']:
                    j = row['point_index']
                    r.require(row['GEOS_evaluations'] == int(original['GEOS_evaluations'][j])
                              and row['evaluation_budget'] == bool(original['budget_exhausted'][j]), 'Leaf counts differ')
                    checks.append({'group': key, 'path': tag, 'union_index': int(ids[j]), 'leaf': row,
                        'independent_geometry': check_leaf(row, xy[ids], time, states,
                            labels['contact_lower_s'][ids], error, vehicle)})
            value = {'time': r.now(), 'status': 'all_remaining_prefix_unknown_leaf_evidence_independently_checked',
                'input_files': len(loaded), 'geometry_groups': len(groups), 'checks': checks,
                'observed_unknown_points': len(checks), 'strict_all_point_prefix_gate_passed': False,
                'remaining_prefix_unknown_points': 1, 'conditional_label_unknown_point_file_records': 16464,
                'all_original_final_arrays_exact': True, 'all_label_dependent_claims_withheld': True,
                'corrected_truth_revalidated_prediction_jobs': 0, 'not_formal_ODE_or_real_vehicle_certificate': True,
                'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'), 'source_signature': signature(),
                'execution': idle, 'mutex': mutex}
            r.freeze(RUN / 'acceptance.json', r.encoded(value))
        finally:
            r.mutable(RUN / 'analysis_runner_lock.json', {'status': 'stopped', 'pid': os.getpid(), 'time': r.now()})
    with h.exclusive() as released:
        _, after = execution()
    next_plan = {**r.read(PLAN), 'version': '20261022-0000-v6-prefix-leaf-diagnostic-closed',
        'stage_status': 'all_remaining_prefix_unknown_leaf_evidence_closed_not_repaired',
        'next_action': 'review leaf evidence; any conservative improvement needs a separately frozen version and affected-quantity validation'}
    report = ('# Prefix Leaf Diagnostic\n\nAll 57 inputs, 39 conditional groups and 78 prefix paths decoded and bound. '
        'Every and only the one remaining prefix unknown observed. Original final arrays exactly unchanged. '
        'Independent analytic/GEOS body and finite-face checks completed. Strict prefix gate remains false; '
        'one prefix unknown and 16464 conditional-label unknown point-file records remain. '
        'No prediction recertification, score repair, formal ODE or vehicle certificate.\n\n'
        + '\n'.join(str(item) for item in checks) + '\n').encode('utf-8')
    r.batch([(RUN / 'close_receipt.json', r.encoded({'time': r.now(),
        'checkpoint_sha256': r.file_hash(RUN / 'checkpoint.json'),
        'acceptance_sha256': r.file_hash(RUN / 'acceptance.json'), 'execution_after': after,
        'mutex_reacquired_and_released': released})),
        (ROOT / 'resume_plan_20261022_0000_v6.json', r.encoded(next_plan)),
        (ROOT / 'reports/prefix_leaf_diagnostic_20261022_0000_v1.md', report)])
    active = r.read(ROOT / 'active_research_run.json')
    active.update(status='prefix_leaf_diagnostic_closed_unknown_retained', pid=None, running_analysis=False,
        plan=str(ROOT / 'resume_plan_20261022_0000_v6.json'), next_action=next_plan['next_action'])
    r.mutable(ROOT / 'active_research_run.json', active)
    print('LEAF DIAGNOSTIC CLOSED; one unknown retained; strict gate false', flush=True)


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
    print('LEAF DIAGNOSTIC LAUNCHED identity PID ' + str(child.pid), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'launch', 'run', 'close'))
    globals()[parser.parse_args().action]()
