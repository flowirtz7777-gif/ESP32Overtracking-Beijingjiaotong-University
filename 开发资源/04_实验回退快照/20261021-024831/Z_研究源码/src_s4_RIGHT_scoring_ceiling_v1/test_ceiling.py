import unittest
import analyze_ceiling as a

np = a.np


class CeilingTests(unittest.TestCase):
    def test_exact_and_off_grid_contact_have_different_strict_two_second_ceiling(self):
        common = np.arange(100, 301)*.02
        contact = np.array([4., 4.005])
        indices, earliest = a.earliest_support(contact, common)
        np.testing.assert_array_equal(indices, [0, 1])
        np.testing.assert_allclose(earliest, [2., 2.02], rtol=0, atol=1e-12)
        cap, categories = a.unattainability(contact, earliest, common, 2.)
        np.testing.assert_array_equal(cap, [True, False])
        np.testing.assert_array_equal(categories[2], [False, True])

    def test_scoring_start_is_a_separate_limitation(self):
        common = np.arange(100, 301)*.02
        contact = np.array([2.5, 4.005])
        _, earliest = a.earliest_support(contact, common)
        cap, categories = a.unattainability(contact, earliest, common, 1.)
        np.testing.assert_array_equal(cap, [False, True])
        np.testing.assert_array_equal(categories[1], [True, False])
        self.assertFalse(categories[2].any())

    def test_no_common_window_frame_is_not_zero_lead_imputation(self):
        common = np.array([2., 5.])
        contact = np.array([4.5])
        indices, earliest = a.earliest_support(contact, common)
        self.assertEqual(indices[0], -1)
        self.assertTrue(np.isnan(earliest[0]))
        cap, categories = a.unattainability(contact, earliest, common, 0.)
        self.assertFalse(cap[0])
        self.assertTrue(categories[0][0])

    def test_empty_time_axis_has_no_support(self):
        common = np.array([], dtype=float)
        c = np.array([4.])
        _, earliest = a.earliest_support(c, common)
        cap, categories = a.unattainability(c, earliest, common, 1.)
        self.assertFalse(cap[0])
        self.assertTrue(categories[0][0])

    def test_unsorted_or_duplicate_axis_rejected(self):
        for axis in (np.array([2., 2.]), np.array([3., 2.])):
            with self.assertRaises(AssertionError):
                a.earliest_support(np.array([4.]), axis)

    def test_exact_original_timestamp_membership_required(self):
        common = np.arange(100, 301)*.02
        c = np.array([4.])
        _, earliest = a.earliest_support(c, common)
        with self.assertRaises(AssertionError):
            a.verify_actual(c, np.array([2.001]), common, earliest, np.array([9], np.int32), [1.])

    def test_supported_timestamp_and_pointwise_checks(self):
        common = np.arange(100, 301)*.02
        c = np.array([4., 4.005])
        _, earliest = a.earliest_support(c, common)
        proof = a.verify_actual(c, np.array([2., np.nan]), common, earliest, np.array([8, 11], np.int32), [0., 1., 2.])
        self.assertEqual(proof['finite_valid_count'], 1)
        self.assertEqual(len(proof['threshold_pointwise_checks']), 3)
        with self.assertRaises(AssertionError):
            a.verify_actual(c, np.array([4.02, np.nan]), common, earliest, np.array([8, 11], np.int32), [1.])

    def test_equal_net_counts_cannot_hide_different_covered_points(self):
        with self.assertRaises(AssertionError):
            a.require_pointwise_subset(np.array([True, False]), np.array([False, True]))

    def test_population_rates_keep_all_points_and_exact_fixed_weights(self):
        c = np.array([4., 4.005, 4.])
        common = np.arange(100, 301)*.02
        _, earliest = a.earliest_support(c, common)
        rows = a.population_rows(c, earliest, np.array([0, 1, 1]), np.arange(3), common, [2.])
        pooled = next(row for row in rows if row['aggregation'] == 'raw_pooled')
        fixed = next(row for row in rows if row['aggregation'] == 'fixed_equal_strata')
        self.assertAlmostEqual(pooled['scoring_ceiling_pct'], 200/3)
        self.assertEqual(fixed['scoring_ceiling_pct'], 75.)
        self.assertIsNone(fixed['ceiling_covered_count'])
        self.assertEqual(fixed['grid_window_phase_limit_pct'], 25.)


if __name__ == '__main__':
    unittest.main()
