import unittest
import analyze_coverage as a

np = a.np


def find(rows, aggregation, threshold):
    return next(row for row in rows if row['aggregation'] == aggregation and row['threshold_s'] == threshold)


class CoverageTests(unittest.TestCase):
    def test_miss_retained_even_at_zero_lead_threshold(self):
        rows = a.coverage(np.full(4, 4.), np.array([np.nan, 3., 2., 3.5]), np.array([0, 0, 1, 1]), np.arange(4))
        self.assertEqual(find(rows, 'raw_pooled', 0.)['coverage_pct'], 75.)
        self.assertEqual(find(rows, 'raw_pooled', 1.)['coverage_pct'], 50.)
        self.assertEqual(find(rows, 'raw_pooled', 0.)['window_miss_count'], 1)

    def test_fixed_layer_weights_are_not_pooled_success_only_counts(self):
        groups = np.array([0, 1, 1, 1])
        rows = a.coverage(np.full(4, 4.), np.array([np.nan, 3., 3., 3.]), groups, np.arange(4))
        fixed = find(rows, 'fixed_equal_strata', 1.)
        self.assertEqual(find(rows, 'raw_pooled', 1.)['coverage_pct'], 75.)
        self.assertEqual(fixed['coverage_pct'], 50.)
        self.assertIsNone(fixed['numerator_count'])
        self.assertIsNone(fixed['denominator_count'])

    def test_empty_fixed_weight_layer_rejected(self):
        with self.assertRaises(AssertionError):
            a.coverage(np.full(3, 4.), np.full(3, 3.), np.zeros(3), np.arange(3))

    def test_after_contact_or_infinite_valid_timestamp_rejected(self):
        for valid in [np.array([4.1, 3.]), np.array([np.inf, 3.])]:
            with self.assertRaises(AssertionError):
                a.coverage(np.full(2, 4.), valid, np.array([0, 1]), np.arange(2))

    def test_frozen_float_boundary_and_monotonicity(self):
        rows = a.coverage(np.full(4, 4.), np.array([3. + .5*a.EPS, 3. + 2*a.EPS, 2., 2.5]), np.array([0, 0, 1, 1]), np.arange(4))
        self.assertEqual(find(rows, 'raw_pooled', 1.)['numerator_count'], 3)
        self.assertEqual(find(rows, 'raw_pooled', 2.)['numerator_count'], 1)
        self.assertEqual(len(rows), 20)

    def test_global_cohort_indices_not_reindexed_or_duplicated(self):
        rows = a.coverage(np.full(5, 4.), np.array([np.nan, 3., 2., np.nan, 2.5]), np.array([0, 0, 1, 1, 0]), np.array([1, 2]))
        self.assertEqual(find(rows, 'raw_pooled', 1.)['coverage_pct'], 100.)
        with self.assertRaises(AssertionError):
            a.coverage(np.full(2, 4.), np.full(2, 3.), np.array([0, 1]), np.array([0, 0, 1]))

    def test_integration_with_frozen_summarizer_includes_misses_and_late(self):
        time = np.arange(501)*.02
        target = {'xy': np.zeros((4, 2)), 'contact_time': np.full(4, 4.), 'group': np.array([0, 0, 1, 1]),
                  'front_ignored': np.zeros(4, bool), 'edge': np.full(4, 2)}
        valid = np.array([np.nan, 3., 3.5, 2.])
        state = {'valid': valid, 'first': valid.copy(), 'point_counts': {key: np.zeros(4, np.int32) for key in a.audit.COUNT_KEYS}}
        summary = a.pipeline.summarize({'time': time, 'true_phase': np.ones(len(time), np.int8)}, target, state)
        rows = a.coverage(target['contact_time'], valid, target['group'], np.arange(4))
        a.verify_summary(rows, summary)
        bad = {**summary, 'right_miss': 0}
        with self.assertRaises(AssertionError):
            a.verify_summary(rows, bad)

    def test_all_misses_are_not_imputed_to_zero_lead(self):
        rows = a.coverage(np.full(2, 4.), np.full(2, np.nan), np.array([0, 1]), np.arange(2))
        self.assertTrue(all(row['coverage_pct'] == 0 for row in rows))
        self.assertTrue(all(row['window_miss_pct'] == 100 for row in rows))

    def test_frozen_matrix_size(self):
        p = a.base.read_json(a.PROTOCOL)
        self.assertEqual(9*2*8*4*5, p['expected_coverage_rows'])
        self.assertEqual(3*2*2*8*4*5, p['expected_method_minus_hold_rows'])
        self.assertEqual(9*2*7*4*5, p['expected_subset_minus_full_reference_rows'])


if __name__ == '__main__':
    unittest.main()
