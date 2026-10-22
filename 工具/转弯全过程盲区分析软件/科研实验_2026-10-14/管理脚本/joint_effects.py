from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEVELS = ([2.0, 3.0], [0.0, .02, .05], [0.0, .1])
METRICS = {'right_pct': 'pp', 'right_miss': 'count', 'right_late': 'count',
           'right_no_before': 'count', 'exit_right_pct': 'pp', 'exit_right_miss': 'count',
           'negative_fp_pct': 'pp', 'frame_fpr_pct': 'pp',
           'common_2s_reference_fpr_pct': 'pp', 'right_lead_p10_s': 's'}


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def csv_save(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


def weighted_difference(parts):
    result = {}
    for metric, unit in METRICS.items():
        result[metric + '_delta_' + unit] = (sum(weight * row[metric] for weight, row in parts)
                if all(row[metric] is not None for _, row in parts) else None)
    return result


def pair_tables(rows):
    groups = defaultdict(dict)
    for row in rows:
        key = tuple(row[name] for name in ['partition', 'case_id', 'config_id', 'condition', 'preprocessing'])
        variant = tuple(row[name] for name in ['EXIT_W_s', 'margin_m', 'confirmation_s'])
        assert variant not in groups[key], ('duplicate_variant', key, variant)
        groups[key][variant] = row
    windows, processing, interactions = [], [], []
    expected = set(itertools.product(*LEVELS))
    for key, block in sorted(groups.items()):
        assert set(block) == expected, ('incomplete_variant_block', key)
        assert len({row['job_id'] for row in block.values()}) == 1
        assert len({(row['target_count'], row['score_end_s'], row['right_contacts'],
                     row['exit_right_contacts']) for row in block.values()}) == 1
        meta = dict(zip(['partition', 'case_id', 'config_id', 'condition', 'preprocessing'], key))
        meta['job_id'] = next(iter(block.values()))['job_id']
        for margin in LEVELS[1]:
            for confirmation in LEVELS[2]:
                a, b = block[(2., margin, confirmation)], block[(3., margin, confirmation)]
                windows.append({**meta, 'control_EXIT_W_s': 2, 'treatment_EXIT_W_s': 3,
                    'margin_m': margin, 'confirmation_s': confirmation,
                    'exit_right_contacts': a['exit_right_contacts'],
                    **weighted_difference([(1, b), (-1, a)])})
        for window in LEVELS[0]:
            for confirmation in LEVELS[2]:
                for margin in LEVELS[1][1:]:
                    a, b = block[(window, 0., confirmation)], block[(window, margin, confirmation)]
                    processing.append({**meta, 'factor': 'margin', 'control_level': 0,
                        'treatment_level': margin, 'EXIT_W_s': window, 'confirmation_s': confirmation,
                        **weighted_difference([(1, b), (-1, a)])})
            for margin in LEVELS[1]:
                a, b = block[(window, margin, 0.)], block[(window, margin, .1)]
                processing.append({**meta, 'factor': 'confirmation', 'control_level': 0,
                    'treatment_level': .1, 'EXIT_W_s': window, 'margin_m': margin,
                    **weighted_difference([(1, b), (-1, a)])})
        specifications = []
        for confirmation in LEVELS[2]:
            for margin in LEVELS[1][1:]:
                specifications.append(('window_margin', (2., 0., confirmation), (3., margin, confirmation), (0, 1)))
        for margin in LEVELS[1]:
            specifications.append(('window_confirmation', (2., margin, 0.), (3., margin, .1), (0, 2)))
        for window in LEVELS[0]:
            for margin in LEVELS[1][1:]:
                specifications.append(('margin_confirmation', (window, 0., 0.), (window, margin, .1), (1, 2)))
        for margin in LEVELS[1][1:]:
            specifications.append(('window_margin_confirmation', (2., 0., 0.), (3., margin, .1), (0, 1, 2)))
        for name, low, high, axes in specifications:
            parts = []
            for bits in itertools.product([0, 1], repeat=len(axes)):
                point = list(low)
                for axis, bit in zip(axes, bits):
                    point[axis] = high[axis] if bit else low[axis]
                parts.append(((-1)**(len(axes)-sum(bits)), block[tuple(point)]))
            interactions.append({**meta, 'interaction': name,
                'low_EXIT_W_s': low[0], 'high_EXIT_W_s': high[0],
                'low_margin_m': low[1], 'high_margin_m': high[1],
                'low_confirmation_s': low[2], 'high_confirmation_s': high[2],
                **weighted_difference(parts)})
    return windows, processing, interactions


def analyze(run):
    cp = read(run / 'checkpoint.json')
    source = cp['source_signature']
    for name, sha in source.items():
        assert digest(run / 'source' / name) == sha
        assert digest(ROOT / 'src_v3' / name) == sha
    rows = [row for row in cp['summaries'] if row['stage'] == 'S3']
    by_job = defaultdict(list)
    for row in rows:
        by_job[row['job_id']].append(row)
    for identifier, group in by_job.items():
        folder = run / 'jobs' / identifier
        assert digest(folder / 'report.json') == cp['completed'][identifier]['report_sha256']
        report = read(folder / 'report.json')
        assert report['source_signature'] == source
        for name, sha in report['output_sha256'].items():
            assert digest(folder / name) == sha
        assert read(folder / 'summary.json') == group
    windows, processing, interactions = pair_tables(rows)
    selected_ids = {row['config_id'] for row in rows}
    complete = bool(cp['stages'].get('S3') and ('hold' in selected_ids or cp['stages'].get('S3_baseline')))
    out = run / 'reports'
    out.mkdir(exist_ok=True)
    csv_save(out / 'S3_paired_window_effects.csv', windows)
    csv_save(out / 'S3_paired_processing_effects.csv', processing)
    csv_save(out / 'S3_interaction_effects.csv', interactions)
    report = {'status': 'completed' if complete else ('partial_no_global_selection' if rows else 'not_started'),
        'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'source_signature': source,
        'checkpoint_sha256': digest(run / 'checkpoint.json'), 'analysis_script_sha256': digest(__file__),
        'S3_completed_prediction_jobs': len(by_job), 'S3_variant_scores': len(rows),
        'window_paired_rows': len(windows), 'processing_paired_rows': len(processing),
        'interaction_rows': len(interactions), 'global_comparison_complete': complete,
        'window_change': 'EXIT_3s_minus_EXIT_2s_with_same_method_margin_confirmation_observation_targets',
        'negative_rate_delta_means_improvement': True, 'positive_lead_delta_means_more_lead_time': True,
        'common_2s_reference_fpr_preserved': True,
        'interactions_are_paired_differences_not_significance_tests': True,
        'EXIT_is_control_return_phase_not_full_trailer_recovery': True,
        'physical_validation': False}
    save(out / 'S3_pairing_analysis.json', report)
    print(json.dumps({key: value for key, value in report.items() if key != 'source_signature'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, default=ROOT / 'runs' / 'overnight_20261014_v3')
    analyze(parser.parse_args().run_dir)
