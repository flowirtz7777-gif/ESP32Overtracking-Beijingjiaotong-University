import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_trace as r

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
        self.assertEqual(sum(r.quotas(case)['input']+3*r.quotas(case)['job'] for case in cases)+16*1024**2, 156531876)
        self.assertEqual([r.quotas(case)['job'] for case in cases], [12245432, 20144327, 7847937])

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
        self.assertEqual(p['ledger_before_run']['accepted_numeric'], 2268)
        self.assertEqual(p['execution']['deadline_local'], '2026-10-17T14:00:00+08:00')
        self.assertTrue(p['no_algorithm_optimization_same_path_speed_replay_or_S5'])


if __name__ == '__main__':
    unittest.main()
