import unittest
import numpy as np
from run_feasibility import build_temporal_tree, label_from_tree, complete_geometry, label_contacts, eligible_right


class FeasibilityTests(unittest.TestCase):
    def fixture(self):
        t = np.arange(161)*.02
        state = np.column_stack((2*t, .4*np.sin(t), .3*np.sin(t), .05*np.cos(t)))
        return {'time': t, 'state': state}

    def test_exact_against_frozen_labeler_on_curved_geometry(self):
        ref = self.fixture()
        segments, _, _ = complete_geometry(ref['state'])
        xy = np.random.default_rng(8142).uniform([-14, -5], [10, 5], (4000, 2))
        expected = label_contacts(xy, ref, segments)
        for leaf in (1, 7, 16, 160):
            result = label_from_tree(xy, ref, segments, build_temporal_tree(segments, leaf))
            for key in expected:
                np.testing.assert_array_equal(result[key], expected[key])

    def test_initial_and_far_points(self):
        ref = self.fixture()
        segments, _, _ = complete_geometry(ref['state'])
        result = label_from_tree(np.array([[0, 0], [100, 100]]), ref, segments, build_temporal_tree(segments, 16))
        self.assertEqual(result['contact_index'][0], 0)
        self.assertEqual(result['contact_index'][1], -1)
        self.assertTrue(np.isnan(result['contact_time'][1]))

    def test_empty_target_array(self):
        ref = self.fixture()
        segments, _, _ = complete_geometry(ref['state'])
        result = label_from_tree(np.empty((0, 2)), ref, segments, build_temporal_tree(segments, 16))
        self.assertEqual(len(result['edge']), 0)

    def test_invalid_leaf_or_empty_segments(self):
        with self.assertRaises(ValueError):
            build_temporal_tree([], 16)
        with self.assertRaises(ValueError):
            build_temporal_tree([None], 0)

    def test_eligible_RIGHT_uses_frozen_scoring_bounds_and_front_exclusion(self):
        labels = {'edge': np.array([2, 2, 2, 2, 2, 1]), 'front_ignored': np.array([0, 0, 0, 0, 1, 0], bool),
                  'contact_time': np.array([1.99, 2, 5, 5.01, 4, 4])}
        np.testing.assert_array_equal(eligible_right(labels, 5), [0, 1, 1, 0, 0, 0])


if __name__ == '__main__':
    unittest.main()
