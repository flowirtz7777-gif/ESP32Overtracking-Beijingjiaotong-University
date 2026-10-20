import unittest
import numpy as np
from analyze_full_sampling import balanced_ids, projected_summary, missed_right_ids, COUNTS


class ProjectionTests(unittest.TestCase):
    def fixture(self):
        targets = {'xy': np.array([[.0125*i, 0.] for i in range(9)]), 'group': np.repeat(np.arange(3), 3),
                   'contact_time': np.array([3., 4., 5., 3., 4., 5., np.nan, np.nan, np.nan]),
                   'edge': np.array([2, 2, 2, 2, 2, 2, 0, 0, 0]), 'front_ignored': np.zeros(9, bool)}
        data = {'time': np.arange(0, 10.01, .02), 'true_phase': np.zeros(501, np.int8)}
        points = {'v_first': np.full(9, 2.), 'v_valid': np.array([2., np.nan, 4.5, 2., 2., 2., np.nan, np.nan, np.nan])}
        for key in COUNTS:
            points['v_'+key] = np.zeros(9, np.int32)
        points['v_ref_negative_opportunities'][:] = 10
        points['v_negative_opportunities'][:] = 10
        return data, targets, points

    def test_balanced_coordinate_only_indices(self):
        _, targets, _ = self.fixture()
        ids = balanced_ids(targets, 7, .5)
        self.assertEqual(len(np.unique(ids)), 7)
        self.assertEqual(np.bincount(targets['group'][ids]).tolist(), [3, 2, 2])
        np.testing.assert_array_equal(ids, balanced_ids(targets, 7, .5))

    def test_projected_scoring_and_miss_ids(self):
        data, targets, points = self.fixture()
        ids = np.arange(9)
        row = projected_summary(data, targets, points, 'v', ids)
        self.assertEqual(row['right_contacts'], 6)
        self.assertEqual(row['right_miss'], 1)
        self.assertEqual(row['right_late'], 1)
        self.assertEqual(row['negative_fp'], 3)
        np.testing.assert_array_equal(missed_right_ids(data, targets, points, 'v', ids), [1])

    def test_duplicate_indices_rejected(self):
        data, targets, points = self.fixture()
        with self.assertRaises(AssertionError):
            projected_summary(data, targets, points, 'v', np.array([0, 0]))

    def test_subset_does_not_mutate_frozen_arrays(self):
        data, targets, points = self.fixture()
        original = points['v_valid'].copy()
        projected_summary(data, targets, points, 'v', np.array([1, 2, 6]))
        np.testing.assert_array_equal(points['v_valid'], original)


if __name__ == '__main__':
    unittest.main()
