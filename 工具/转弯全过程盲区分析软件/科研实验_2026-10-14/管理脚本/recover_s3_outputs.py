from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
sys.path.insert(0, str(ROOT / 'src_v3'))

import run_night as runner
from common import array_hash, file_hash, read_json, write_json
from evaluation import Variant
from observations import observe, preprocess, conditions
from prediction import Method


def allowed_configurations(cp):
    source = runner.signature()
    assert source == cp['source_signature'], 'Frozen source changed'
    assert cp['stages'].get('S0') and cp['stages'].get('S2'), 'Foundation and S2 must be complete'
    partition = cp['stages']['S0']['partition']
    core = read_json(ROOT / 'reports' / 'S1_analysis.json')
    processing = read_json(ROOT / 'reports' / 'S2_analysis.json')['chosen_preprocessing']
    variants = [Variant(w, m, c) for w in [2, 3] for m in [0, .02, .05] for c in [0, .1]]
    cases = [(partition, spec['id']) for spec in read_json(ROOT / 'scenario_matrix.json')]
    for speed in [2.5, 3.5]:
        for rate in [3, 6]:
            for template in read_json(ROOT / 'plan.json')['driving_factors']['templates']:
                cases.append(('selection_v2', f"sel_v{speed}_r{rate}_{template['id']}"))
    stress = [condition for condition in conditions() if condition['id'] in ['clean', 'delay100']
              or condition['id'].startswith('noise100_s') or condition['id'].startswith('combined100_s')]
    expected = {}
    for part, case in cases:
        for finalist in core['finalists']:
            for condition in stress:
                config = runner.job('S3', part, case, Method(**finalist['method']), source,
                                    condition, processing, variants)
                expected[config['id']] = config
    assert len(expected) == 624
    return expected


def verify_output(folder, config):
    assert read_json(folder / 'configuration.json') == config, 'Effective configuration mismatch'
    report = read_json(folder / 'report.json')
    assert report['id'] == config['id'] and report['source_signature'] == config['source_signature']
    for name, sha in report['output_sha256'].items():
        assert file_hash(folder / name) == sha, 'Output hash mismatch: ' + name
    assert set(report['output_sha256']) == {'target_results.npz', 'frame_results.npz',
                                          'summary.json', 'configuration.json', 'timing.json'}
    data, targets, manifest = runner.load_case(config['partition'], config['case_id'])
    assert report['input_hashes'] == manifest['files']
    assert report['target_coordinates_sha256'] == manifest['target_coordinates_sha256']
    assert report['contact_label_sha256'] == manifest['contact_label_sha256']
    observed = preprocess(observe(data, config['condition']), config['preprocessing'])
    assert report['observed_state_sha256'] == array_hash(observed['state'])
    assert report['observed_alpha_sha256'] == array_hash(observed['alpha'])
    rows = read_json(folder / 'summary.json')
    assert len(rows) == 12
    effective = {(row['EXIT_W_s'], row['margin_m'], row['confirmation_s']) for row in rows}
    declared = {(variant['exit_W'], variant['margin'], variant['confirmation']) for variant in config['variants']}
    assert effective == declared and report['target_count'] == len(targets['xy'])
    for row in rows:
        assert row['job_id'] == config['id'] and row['stage'] == 'S3'
        assert row['case_id'] == config['case_id'] and row['partition'] == config['partition']
        assert row['condition'] == config['condition']['id'] and row['preprocessing'] == config['preprocessing']
        assert row['target_count'] == manifest['target_count'] >= 20000
        assert row['score_end_s'] == float(data['time'][-1]-3)
        assert row['method'] == config['method']['mode']
        assert row['config_id'] == runner.method_id(Method(**config['method']))
    return rows, file_hash(folder / 'report.json')


def recover(run, dry_run=False):
    runner.RUN = run
    kernel, mutex = runner.acquire_lock()
    try:
        assert read_json(run / 'runner_lock.json')['status'] == 'stopped', 'Runner must be stopped first'
        cp = read_json(run / 'checkpoint.json')
        expected = allowed_configurations(cp)
        recovered, rejected, incomplete = [], [], []
        for folder in sorted((run / 'jobs').iterdir()):
            if not folder.is_dir() or folder.name in cp['completed'] or not folder.name.startswith('S3__'):
                continue
            if not (folder / 'report.json').exists():
                incomplete.append(folder.name)
                continue
            try:
                assert folder.name in expected, 'Unexpected job identifier'
                rows, sha = verify_output(folder, expected[folder.name])
            except Exception as error:
                rejected.append({'id': folder.name, 'error': repr(error)})
            else:
                recovered.append((folder.name, rows, sha))
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        report = {'captured_at_utc': timestamp, 'dry_run': dry_run,
                  'source_signature': cp['source_signature'], 'script_sha256': file_hash(__file__),
                  'checkpoint_before_sha256': file_hash(run / 'checkpoint.json'),
                  'verified_recoverable_jobs': [identifier for identifier, _, _ in recovered],
                  'rejected_jobs': rejected, 'incomplete_preserved_jobs': incomplete,
                  'inputs_and_existing_outputs_changed': False}
        if not dry_run and recovered:
            backup = run / 'recovery' / (timestamp + '_checkpoint_before.json')
            backup.parent.mkdir(exist_ok=True)
            backup.write_bytes((run / 'checkpoint.json').read_bytes())
            assert file_hash(backup) == report['checkpoint_before_sha256']
            for identifier, rows, sha in recovered:
                cp['completed'][identifier] = {'report_sha256': sha}
                cp['summaries'].extend(rows)
            cp['last_output_recovery_utc'] = timestamp
            write_json(run / 'checkpoint.json', cp)
        if not dry_run:
            report['checkpoint_after_sha256'] = file_hash(run / 'checkpoint.json')
            write_json(run / 'recovery' / (timestamp + '_recovery_report.json'), report)
        print(json.dumps({key: value for key, value in report.items() if key != 'source_signature'}))
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, default=ROOT / 'runs' / 'overnight_20261014_v3')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    recover(args.run_dir, args.dry_run)
