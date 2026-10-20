import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import importlib.util

import run_factorial as r
import factorial_analysis as analysis

np = r.np


def fixture():
    axis = np.arange(401)*.02
    fine = np.arange(1601)*.005
    data = {'time': axis, 'state': np.column_stack((axis, np.zeros((len(axis), 3)))),
        'alpha': np.zeros(len(axis)), 'v_B': np.ones(len(axis)), 'fine_time': fine,
        'fine_state': np.column_stack((fine, np.zeros((len(fine), 3)))), 'true_phase': np.ones(len(axis), np.int8)}
    targets = {'xy': np.array([[5.8, -1], [6, -1], [100, 100], [6.2, -1]], np.float64),
        'group': np.array([0, 1, 2, 0], np.int8), 'contact_time': np.array([4, 4.2, np.nan, 4.4], np.float64),
        'contact_index': np.array([800, 840, -1, 880], np.int32), 'edge': np.array([2, 2, 0, 2], np.int8),
        'front_ignored': np.zeros(4, bool), 'main_ids': np.array([2, 0], np.int32)}
    return data, targets


class FineTraceTests(unittest.TestCase):
    def test_exact_actual_dimension_quota(self):
        cases = r.protocol()['cases']
        self.assertEqual(sum(r.quotas(case)['input']+3*r.quotas(case)['job'] for case in cases)+32*1024**2, 271970377)
        self.assertEqual(len(r.protocol()['variants']), 4)

    def test_unknown_dimension_cannot_enter(self):
        for bad in (None, -1, 1.2, True):
            with self.assertRaises(ValueError):
                r.quotas({'diagnostic_target_count': bad, 'catalog_points': 1, 'observation_frames': 10})

    def test_three_resource_limits_at_boundary(self):
        p = r.protocol()['execution']
        resources = {'experiment_bytes': p['experiment_budget_bytes']-100, 'run_bytes': p['new_run_budget_bytes']-100,
                     'free_bytes': p['reserve_bytes']+100}
        self.assertTrue(r.fits(resources, 100))
        self.assertFalse(r.fits(resources, 101))
        self.assertFalse(r.fits({**resources, 'free_bytes': resources['free_bytes']-1}, 100))

    def test_original_nonprefix_main_order_and_catalog_dedup(self):
        _, full = fixture()
        target = r.select_targets(full, np.array([0, 1, 3], np.int32), 2)
        np.testing.assert_array_equal(target['reference_ids'], [2, 0, 1, 3])
        np.testing.assert_array_equal(target['catalog_positions'], [1, 2, 3])
        np.testing.assert_array_equal(target['main_ids'], [0, 1])

    def test_empty_catalog_preserves_control(self):
        _, full = fixture()
        target = r.select_targets(full, np.empty(0, np.int32), 2)
        self.assertEqual(target['xy'].shape, (2, 2))
        self.assertEqual(target['catalog_positions'].shape, (0,))
        self.assertEqual(target['catalog_positions'].dtype, np.int32)

    def test_bad_catalog_range_dtype_or_duplicates_rejected(self):
        _, full = fixture()
        for bad in (np.array([9], np.int32), np.array([0, 0], np.int32), np.array([1], np.int64)):
            with self.assertRaises(AssertionError):
                r.select_targets(full, bad, 2)

    def test_confirmation_elapsed_time_and_gap_reset(self):
        axis = np.arange(12)*.02
        hits = np.ones((12, 1), bool)
        hits[6] = False
        confirmed, age = r.confirmation_trace(axis, hits, .1)
        self.assertFalse(confirmed[4, 0])
        self.assertTrue(confirmed[5, 0])
        self.assertFalse(confirmed[11, 0])
        self.assertEqual(age[7, 0], 0)

    def test_confirmation_prefix_causality(self):
        axis = np.arange(100)*.02
        hits = np.random.default_rng(42).random((100, 3)) > .2
        changed = hits.copy()
        changed[50:] = ~changed[50:]
        before = r.confirmation_trace(axis, hits, .1)
        after = r.confirmation_trace(axis, changed, .1)
        for left, right in zip(before, after):
            np.testing.assert_array_equal(left[:50], right[:50])

    def test_current_all_four_prediction_cores_prefix_causal(self):
        raw = {'time': np.arange(80)*.02, 'state': np.zeros((80, 4)), 'alpha': np.linspace(0, .1, 80), 'v_B': np.full(80, 3.)}
        changed = {key: value.copy() for key, value in raw.items()}
        for key in ('state', 'alpha', 'v_B'):
            changed[key][40:] += .2
        for mode in ('hold', 'linear', 'damped_linear', 'bounded_second_order'):
            method = r.pipeline.Method(mode)
            np.testing.assert_array_equal(r.f.coarse.rollout(raw, method, .3)[:40], r.f.coarse.rollout(changed, method, .3)[:40])

    def test_warmup_confirmation_not_scored_before_two(self):
        axis = np.arange(1.9, 2.141, .02)
        out, _, _, _ = r.trace_point_outputs(axis, np.ones((len(axis), 1), bool), np.array([2.1]), .1, 3.)
        self.assertAlmostEqual(out['first'][0], 2.)
        self.assertAlmostEqual(out['valid'][0], 2.)

    def test_earlier_confirmation_does_not_imply_window_hit(self):
        axis = np.arange(0, 5.001, .02)
        hits = ((axis >= 1.8) & (axis <= 2.02))[:, None]
        out, _, _, _ = r.trace_point_outputs(axis, hits, np.array([4.05]), .1, 5.)
        self.assertTrue(np.isfinite(out['first'][0]))
        self.assertTrue(np.isnan(out['valid'][0]))
        self.assertEqual(out['TP'][0], 0)

    def test_short_raw_pulse_not_confirmed(self):
        axis = np.arange(0, 5.001, .02)
        hits = ((axis >= 2.1) & (axis <= 2.16))[:, None]
        out, _, _, _ = r.trace_point_outputs(axis, hits, np.array([4.]), .1, 5.)
        self.assertTrue(np.isnan(out['valid'][0]))

    def test_actual_evaluator_trace_and_main_projection_integration(self):
        data, full = fixture()
        targets = r.select_targets(full, np.array([0, 3], np.int32), 2)
        variants = [r.pipeline.Variant(**v) for v in r.protocol()['variants']]
        for method in (r.pipeline.Method('hold'), r.pipeline.Method('linear', gain=.625), r.pipeline.Method('damped_linear', gain=1.25, decay_s=1)):
            result = r.pipeline.evaluate(data, targets, method, variants, vehicle=r.Vehicle(), retain_sequence=True)
            positions = targets['catalog_positions']
            distance = r.witness_geometry_distance(result['sequence'], targets['xy'][positions], method.dt, r.Vehicle())
            trace = {'time': data['time'], 'score_frame': (data['time'] >= 2-r.EPS) & (data['time'] <= 5+r.EPS),
                'catalog_reference_ids': targets['catalog_reference_ids'], 'catalog_xy': targets['xy'][positions],
                'contact_time': targets['contact_time'][positions], 'distance_m': distance}
            for v in variants:
                hit = distance <= .05+v.margin+r.GEOMETRY_EPS
                _, confirmed, age, support = r.trace_point_outputs(data['time'], hit, trace['contact_time'], v.confirmation, 5.)
                trace.update({v.tag+'_raw_hit': hit, v.tag+'_confirmed': confirmed, v.tag+'_continuous_age_s': age, v.tag+'_support': support})
            r.validate_trace(trace, result['point_output'], targets, variants, 5.)
            scores = r.main_scores(data, targets, result['point_output'], variants)
            only_main = {k: v[:2] for k, v in targets.items() if k in r.c.TARGET_FIELDS}
            original = r.pipeline.evaluate(data, only_main, method, variants)
            for row, state in zip(scores, original['states']):
                self.assertEqual(r.a.numeric_summary(row), r.pipeline.summarize(data, only_main, state))

    def test_empty_geometry_trace_original_dtypes_roundtrip(self):
        data, full = fixture()
        targets = r.select_targets(full, np.empty(0, np.int32), 2)
        result = r.pipeline.evaluate(data, targets, r.pipeline.Method('hold'), retain_sequence=True)
        distance = r.witness_geometry_distance(result['sequence'], np.empty((0, 2), np.float64), .02, r.Vehicle())
        self.assertEqual(distance.shape, (401, 0))
        out, confirmed, age, support = r.trace_point_outputs(data['time'], distance < .1, np.empty(0), .1, 5.)
        arrays = {'distance': distance, 'confirmed': confirmed, 'age': age, 'support': support, **out}
        r.c.readback(r.f.coarse.npz_bytes(arrays), r.c.descriptors(arrays))

    def test_checkpoint_snapshot_and_prewrite_resource_call(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(r, 'RUN', Path(directory)), patch.object(r, 'resources', return_value={}) as guard:
            r.save_cp({'status': 'fixture', 'new_formal_predictions': 0, 'completed': {}})
            blob = (r.RUN/'checkpoint.json').read_bytes()
            snapshots = list((r.RUN/'checkpoint_snapshots').glob('*.gz'))
            self.assertEqual(gzip.decompress(snapshots[0].read_bytes()), blob)
            self.assertTrue(guard.called)

    def test_fixed_matrix_protocol_and_baselines(self):
        p = r.protocol()
        self.assertEqual(r.base.file_hash(r.PROTOCOL), r.EXPECTED_PROTOCOL)
        self.assertEqual(len(r.jobs()), 9)
        self.assertEqual(p['ledger_before_run']['accepted_numeric'], 2277)
        self.assertEqual(p['execution']['deadline_local'], '2026-10-17T19:00:00+08:00')
        self.assertTrue(p['no_algorithm_optimization_same_path_speed_replay_or_S5'])

    def test_factorial_grid_exact_no_extra_parameters(self):
        self.assertEqual({(x['margin'], x['confirmation']) for x in r.protocol()['variants']},
                         {(.02, 0.), (.02, .1), (.05, 0.), (.05, .1)})
        self.assertEqual({x['exit_W'] for x in r.protocol()['variants']}, {2.})

    def test_factorial_evaluator_count_and_detection_monotonicity(self):
        data, full = fixture()
        targets = r.select_targets(full, np.array([0, 3], np.int32), 2)
        variants = [r.pipeline.Variant(**v) for v in r.protocol()['variants']]
        result = r.pipeline.evaluate(data, targets, r.pipeline.Method('hold'), variants)
        self.assertEqual(len(result['point_output']), 36)
        r.validate_factorial(result['point_output'])

    def test_single_cell_batching_does_not_change_any_point_output(self):
        data, full = fixture()
        targets = r.select_targets(full, np.array([0, 3], np.int32), 2)
        variants = [r.pipeline.Variant(**v) for v in r.protocol()['variants']]
        all_cells = r.pipeline.evaluate(data, targets, r.pipeline.Method('linear', gain=.625), variants)
        for variant in variants:
            single = r.pipeline.evaluate(data, targets, r.pipeline.Method('linear', gain=.625), [variant])
            for key, value in single['point_output'].items():
                np.testing.assert_array_equal(value, all_cells['point_output'][key])

    def test_wider_margin_can_join_short_pulses_without_using_future(self):
        axis = np.arange(21)*.02
        distance = np.full((21, 1), .071)
        distance[1:5] = .069
        distance[6:10] = .069
        narrow = distance <= .07+r.GEOMETRY_EPS
        wide = distance <= .1+r.GEOMETRY_EPS
        low, _ = r.confirmation_trace(axis, narrow, .1)
        high, _ = r.confirmation_trace(axis, wide, .1)
        self.assertFalse(low.any())
        self.assertTrue(high.any())

    def test_factorial_rejects_reversed_monotonicity(self):
        data, full = fixture()
        targets = r.select_targets(full, np.array([0, 3], np.int32), 2)
        result = r.pipeline.evaluate(data, targets, r.pipeline.Method('hold'),
                                    [r.pipeline.Variant(**v) for v in r.protocol()['variants']])
        outputs = {k: v.copy() for k, v in result['point_output'].items()}
        outputs['w2000_m20_c100_FP'] = outputs['w2000_m20_c0_FP']+1
        with self.assertRaises(AssertionError):
            r.validate_factorial(outputs)

    def test_undefined_difference_not_imputed_zero(self):
        self.assertIsNone(analysis.difference(None, 3))
        self.assertIsNone(analysis.difference(None, None))
        self.assertEqual(analysis.difference(5, 2), 3)

    def test_registered_factorial_pairs_are_all_four_simple_effects(self):
        self.assertEqual(len(analysis.PAIRS), 4)
        for _, before, after in analysis.PAIRS:
            self.assertEqual(sum(x != y for x, y in zip(before.split('c'), after.split('c'))), 1)

    def test_contrast_indices_and_empty_undefined_cells_lossless(self):
        scores = [{'variant': tag, **{key: (None if 'pct' in key or 'lead' in key else 0)
                                     for key in analysis.METRICS}} for tag in analysis.CELLS.values()]
        misses = {tag: np.empty(0, np.int32) for tag in analysis.CELLS.values()}
        rows, arrays = analysis.contrasts(scores, misses, case='empty', method='hold', cohort='catalog', prefix='test')
        self.assertEqual(len(rows), 5)
        self.assertEqual(len(arrays), 8)
        for value in arrays.values():
            self.assertEqual(value.dtype, np.int32)
            self.assertEqual(value.shape, (0,))
        self.assertIsNone(rows[-1]['metric_difference_of_differences']['negative_fp_pct'])
        r.c.readback(r.f.coarse.npz_bytes(arrays), r.c.descriptors(arrays))

    def test_miss_indices_use_reference_ids_and_eligibility_not_position(self):
        _, full = fixture()
        targets = r.select_targets(full, np.array([0, 1, 3], np.int32), 2)
        valid = np.full(len(targets['xy']), np.nan)
        result = analysis.miss_indices({'tag_valid': valid}, targets, np.arange(len(valid)), 'tag', 4.3)
        np.testing.assert_array_equal(result, [0, 1])

    def test_independent_per_point_rebuilder_four_cells_and_empty(self):
        path = r.ROOT/'管理脚本/close_fine_factorial_20261017_1900_v1.py'
        spec = importlib.util.spec_from_file_location('new_factorial_closure_test', path)
        closer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(closer)
        rebuild, _ = closer.load_independent_functions()
        axis = np.arange(401)*.02
        for points in (0, 3):
            distances = np.random.default_rng(123).uniform(.02, .12, (len(axis), points))
            contact = np.linspace(3.4, 5.8, points)
            for cell in r.protocol()['variants']:
                hits = distances <= .05+cell['margin']+r.GEOMETRY_EPS
                expected = r.trace_point_outputs(axis, hits, contact, cell['confirmation'], 5.)
                actual = rebuild(axis, hits, contact, cell['confirmation'], 5.)
                for key in expected[0]:
                    np.testing.assert_array_equal(expected[0][key], actual[0][key])
                for a0, a1 in zip(expected[1:], actual[1:]):
                    np.testing.assert_array_equal(a0, a1)


if __name__ == '__main__':
    unittest.main()
