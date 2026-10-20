import unittest
import numpy as np
from run_trace import confirmation_trace, trace_point_outputs, rollout, pipeline


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


if __name__ == '__main__':
    unittest.main()
