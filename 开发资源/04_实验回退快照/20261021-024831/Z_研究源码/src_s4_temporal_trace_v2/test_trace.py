import unittest
import numpy as np
from run_trace import confirmation_trace, trace_point_outputs, witness_geometry_distance, Vehicle, GEOMETRY_EPS, rollout, pipeline


class TraceTests(unittest.TestCase):
    def test_confirmation_needs_elapsed_time_and_resets_on_gap(self):
        time = np.arange(12)*.02
        hits = np.ones((12, 1), bool)
        hits[6] = False
        confirmed, age = confirmation_trace(time, hits, .1)
        self.assertFalse(confirmed[4, 0])
        self.assertTrue(confirmed[5, 0])
        self.assertFalse(confirmed[11, 0])
        self.assertAlmostEqual(age[7, 0], 0.)

    def test_warmup_history_confirmed_at_scoring_start(self):
        time = np.arange(1.9, 2.141, .02)
        hits = np.ones((len(time), 1), bool)
        out, _, _, _ = trace_point_outputs(time, hits, np.array([2.1]), .1, 3.)
        self.assertAlmostEqual(out['first'][0], 2.)
        self.assertAlmostEqual(out['valid'][0], 2.)

    def test_early_confirmation_does_not_imply_window_detection(self):
        time = np.arange(0, 5.001, .02)
        hits = ((time >= 1.8) & (time <= 2.02))[:, None]
        out, _, _, support = trace_point_outputs(time, hits, np.array([4.05]), .1, 5.)
        self.assertTrue(np.isfinite(out['first'][0]))
        self.assertTrue(np.isnan(out['valid'][0]))
        self.assertEqual(out['TP'][0], 0)
        self.assertFalse((hits & support).any())

    def test_short_window_pulses_do_not_pass_confirmation(self):
        time = np.arange(0, 5.001, .02)
        hits = ((time >= 2.1) & (time <= 2.16))[:, None]
        out, _, _, _ = trace_point_outputs(time, hits, np.array([4.]), .1, 5.)
        self.assertTrue(np.isnan(out['first'][0]))
        self.assertTrue(np.isnan(out['valid'][0]))

    def test_confirmation_prefix_causality(self):
        time = np.arange(100)*.02
        hits = np.random.default_rng(42).random((100, 3)) > .2
        a, age = confirmation_trace(time, hits, .1)
        changed = hits.copy()
        changed[50:] = ~changed[50:]
        b, changed_age = confirmation_trace(time, changed, .1)
        np.testing.assert_array_equal(a[:50], b[:50])
        np.testing.assert_array_equal(age[:50], changed_age[:50])

    def test_frozen_rollout_prefix_does_not_use_future_observations(self):
        observed = {'time': np.arange(80)*.02, 'state': np.zeros((80, 4)),
                    'alpha': np.linspace(0, .1, 80), 'v_B': np.full(80, 3.)}
        changed = {key: value.copy() for key, value in observed.items()}
        changed['state'][40:] += 1
        changed['alpha'][40:] = -.2
        changed['v_B'][40:] = 5.
        for method in (pipeline.Method('hold'), pipeline.Method('linear', gain=.625), pipeline.Method('damped_linear', gain=1.25, decay_s=1)):
            np.testing.assert_array_equal(rollout(observed, method, .3)[:40], rollout(changed, method, .3)[:40])

    def test_retained_sequence_geometry_and_confirmation_match_evaluator(self):
        time = np.arange(401)*.02
        fine = np.arange(1601)*.005
        data = {'time': time, 'state': np.column_stack((time, np.zeros((len(time), 3)))),
                'alpha': np.zeros(len(time)), 'v_B': np.ones(len(time)),
                'fine_time': fine, 'fine_state': np.column_stack((fine, np.zeros((len(fine), 3)))),
                'true_phase': np.ones(len(time), dtype=np.int8)}
        targets = {'xy': np.array([[5.8, -1.]]), 'group': np.array([0]),
                   'contact_time': np.array([4.]), 'front_ignored': np.array([False]),
                   'edge': np.array([2])}
        variants = [pipeline.Variant(2, .05, 0), pipeline.Variant(2, .02, .1)]
        vehicle, method = Vehicle(), pipeline.Method('hold')
        result = pipeline.evaluate(data, targets, method, variants, vehicle=vehicle, retain_sequence=True)
        distance = witness_geometry_distance(result['sequence'], targets['xy'], method.dt, vehicle)
        self.assertEqual(distance.shape, (len(time), 1))
        for v in variants:
            hits = distance <= .05+v.margin+GEOMETRY_EPS
            output, _, _, _ = trace_point_outputs(time, hits, targets['contact_time'], v.confirmation, 5.)
            for key, array in output.items():
                np.testing.assert_array_equal(array, result['point_output'][v.tag+'_'+key])


if __name__ == '__main__':
    unittest.main()
