import unittest
import numpy as np
from analyze_trace import intervals, classify


class AnalysisTests(unittest.TestCase):
    def test_disjoint_sample_runs_preserved_without_bridging(self):
        time = np.arange(8)*.02
        result = intervals(time, np.array([0, 1, 1, 0, 1, 0, 0, 1], bool))
        self.assertEqual([row['frames'] for row in result], [2, 1, 1])
        self.assertAlmostEqual(result[0]['elapsed_s'], .02)
        self.assertEqual(result[1]['elapsed_s'], 0.)

    def test_empty_intervals(self):
        self.assertEqual(intervals(np.arange(4), np.zeros(4, bool)), [])

    def test_earlier_confirmation_cannot_hide_missing_window_geometry(self):
        raw = np.array([1, 1, 0, 0], bool)
        confirmed = np.array([0, 1, 0, 0], bool)
        support = np.array([0, 0, 1, 1], bool)
        self.assertEqual(classify(raw, confirmed, support), 'no_geometry_hit_within_effective_window')

    def test_raw_hit_and_confirmed_hit_mechanisms_separate(self):
        raw = np.ones(4, bool)
        support = np.ones(4, bool)
        self.assertEqual(classify(raw, np.zeros(4, bool), support), 'geometry_hit_but_continuous_confirmation_not_met_in_window')
        self.assertEqual(classify(raw, raw, support), 'window_detected')


if __name__ == '__main__':
    unittest.main()
