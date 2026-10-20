import sys
import unittest
sys.dont_write_bytecode = True
import analyze_density as analysis


class AcceptanceTests(unittest.TestCase):
    def test_only_new_eligible_right_points_count_as_new_misses(self):
        n = analysis.run.np
        targets = {'contact_time': n.array([5., 5., 5., 1., 20., n.nan]), 'edge': n.array([2, 2, 1, 2, 2, 0]),
                   'front_ignored': n.array([False, False, True, False, False, False]), 'new_ids': n.array([1, 2, 3, 4, 5])}
        valid = n.full(6, n.nan)
        self.assertEqual(analysis.new_point_misses(targets, valid, 10).tolist(), [1])

    def test_finite_new_window_alarm_does_not_become_a_miss(self):
        n = analysis.run.np
        targets = {'contact_time': n.array([5., 5.]), 'edge': n.array([2, 2]), 'front_ignored': n.array([False, False]),
                   'new_ids': n.array([1])}
        self.assertEqual(analysis.new_point_misses(targets, n.array([n.nan, 4.]), 10).tolist(), [])


if __name__ == '__main__':
    unittest.main()
