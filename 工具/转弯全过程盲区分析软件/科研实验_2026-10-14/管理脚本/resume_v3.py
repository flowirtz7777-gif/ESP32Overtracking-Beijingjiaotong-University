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
from common import file_hash, read_json, write_json, utc_now
from audit_and_factors import audit


def without_status(value):
    if isinstance(value, dict):
        return {key: without_status(item) for key, item in value.items() if key != 'status'}
    if isinstance(value, list):
        return [without_status(item) for item in value]
    return value


def inspect_checkpoint():
    cp = read_json(runner.RUN / 'checkpoint.json')
    source = runner.signature()
    if cp['source_signature'] != source:
        raise RuntimeError('Frozen v3 source changed; do not reuse its checkpoint.')
    for name, sha in source.items():
        if file_hash(runner.RUN / 'source' / name) != sha:
            raise RuntimeError('Frozen snapshot mismatch: ' + name)
    original_plan = read_json(runner.RUN / 'plan_snapshot.json')
    current_plan = read_json(ROOT / 'plan.json')
    if without_status(original_plan) != without_status(current_plan):
        raise RuntimeError('Experiment plan changed beyond progress status; create a new research version.')
    foundation = cp['stages'].get('S0')
    if foundation:
        for spec in read_json(ROOT / 'scenario_matrix.json'):
            profile = read_json(ROOT / 'datasets' / foundation['partition'] / spec['id'] / 'profile.json')
            if profile['design'] != spec:
                raise RuntimeError('Frozen scenario design mismatch: ' + spec['id'])
    return cp


def main():
    parser = argparse.ArgumentParser(description='Resume unchanged v3 experiments with an explicit execution deadline.')
    parser.add_argument('--until', help='Timezone-aware ISO datetime, for example 2026-10-14T12:00:00+08:00.')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error('workers must be between 1 and 8')
    cp = inspect_checkpoint()
    if args.check_only:
        print(json.dumps({'status': 'frozen_source_matches_checkpoint', 'run': runner.RUN.name,
                          'completed_jobs': len(cp['completed']), 'stages': list(cp['stages']),
                          'checkpoint_status': cp.get('status', 'running'),
                          'jobs_started_by_this_check': 0}))
        return
    if not args.until:
        parser.error('A new --until deadline is required; the original night deadline is never silently extended.')
    try:
        until = datetime.fromisoformat(args.until)
    except ValueError:
        parser.error('--until must be a valid ISO datetime')
    if until.tzinfo is None:
        parser.error('--until must include a timezone')
    deadline = until.astimezone(timezone.utc)
    if deadline <= datetime.now(timezone.utc):
        parser.error('--until must be in the future')
    audit(runner.RUN)
    session_path = runner.RUN / 'runtime_sessions' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    record = {'status': 'requested', 'started_at_utc': utc_now(),
              'deadline_utc': deadline.isoformat(), 'workers': args.workers,
              'wrapper_sha256': file_hash(__file__), 'source_signature': cp['source_signature'],
              'starting_checkpoint_sha256': file_hash(runner.RUN / 'checkpoint.json'),
              'execution_plan_sha256': file_hash(ROOT / 'plan.json'),
              'previous_plan_snapshot_sha256': file_hash(runner.RUN / 'plan_snapshot.json'),
              'scenario_matrix_sha256': file_hash(ROOT / 'scenario_matrix.json'),
              'numeric_source_changed': False, 'completed_outputs_reused_after_hash_verification': True}
    write_json(session_path.with_name(session_path.stem + '_prior_plan.json'), read_json(runner.RUN / 'plan_snapshot.json'))
    write_json(session_path, record)
    runner.DEADLINE = deadline.timestamp()
    try:
        runner.main(args.workers)
    except Exception as error:
        record.update(status='failed', error=repr(error))
        raise
    else:
        record['status'] = read_json(runner.RUN / 'checkpoint.json').get('status', 'stopped')
    finally:
        record['ended_at_utc'] = utc_now()
        write_json(session_path, record)


if __name__ == '__main__':
    main()
