import sys
import unittest
from unittest.mock import patch
import numpy as np
import leaf


class LeafObserverTests(unittest.TestCase):
    def setUp(self):
        self.time = np.array([0., 1.])
        self.state = np.zeros((2, 4))
        vehicle = leaf.common.Vehicle()
        self.point = leaf.common.body_corners(self.state[:1], vehicle).mean(axis=1)
        self.lower = np.array([np.nan])

    def compare_kernel(self, points=None, **policy):
        points = self.point if points is None else points
        expected = leaf.audit_prefixes(points, self.time, self.state, self.lower, **policy)
        observed, records = leaf.audit_with_leaf_evidence(points, self.time, self.state, self.lower, **policy)
        self.assertEqual(set(expected), set(observed))
        for name in expected:
            self.assertEqual(expected[name].dtype, observed[name].dtype)
            np.testing.assert_array_equal(expected[name], observed[name])
        self.assertIsNone(sys.gettrace())
        return observed, records

    def test_time_resolution_unknown_is_observed(self):
        arrays, records = self.compare_kernel(spatial_error_m=.1, tolerance_m=.05)
        self.assertTrue(arrays['prefix_undetermined'][0])
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]['time_leaf'])
        self.assertFalse(records[0]['evaluation_budget'])
        self.assertLessEqual(records[0]['leaf_width_s'], 1e-8)
        self.assertLessEqual(records[0]['exclusion_margin_m'], 0)
        self.assertLess(records[0]['contact_witness_margin_m'], 0)

    def test_budget_unknown_is_distinct(self):
        arrays, records = self.compare_kernel(spatial_error_m=.1, tolerance_m=.05, max_evaluations_per_point=1)
        self.assertTrue(arrays['budget_exhausted'][0])
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]['evaluation_budget'])
        self.assertFalse(records[0]['time_leaf'])

    def test_early_contact_remains_an_early_contact(self):
        arrays, records = self.compare_kernel(spatial_error_m=0., tolerance_m=.05)
        self.assertTrue(arrays['early_contact_witness'][0])
        self.assertEqual(records, [])

    def test_excluded_point_has_no_leaf_evidence(self):
        arrays, records = self.compare_kernel(points=np.array([[100., 100.]]))
        self.assertTrue(arrays['prefix_excluded'][0])
        self.assertEqual(records, [])

    def test_empty_population(self):
        self.lower = np.array([])
        arrays, records = self.compare_kernel(points=np.empty((0, 2)))
        self.assertEqual(len(arrays['prefix_undetermined']), 0)
        self.assertEqual(records, [])

    def test_existing_tracer_is_preserved(self):
        def existing(frame, event, argument):
            return existing
        sys.settrace(existing)
        try:
            with self.assertRaises(RuntimeError):
                leaf.audit_with_leaf_evidence(self.point, self.time, self.state, self.lower)
            self.assertIs(sys.gettrace(), existing)
        finally:
            sys.settrace(None)

    def test_invalid_kernel_input_restores_trace(self):
        with self.assertRaises(ValueError):
            leaf.audit_with_leaf_evidence(self.point, np.array([0., 0.]), self.state, self.lower)
        self.assertIsNone(sys.gettrace())

    def test_observer_ambiguity_is_rejected(self):
        with patch.object(leaf, 'observation_line', side_effect=RuntimeError('synthetic ambiguous site')):
            with self.assertRaises(RuntimeError):
                leaf.audit_with_leaf_evidence(self.point, self.time, self.state, self.lower)
        self.assertIsNone(sys.gettrace())

    def test_multiple_unknowns_have_original_indices(self):
        self.lower = np.array([np.nan, np.nan])
        points = np.repeat(self.point, 2, axis=0)
        arrays, records = self.compare_kernel(points=points, spatial_error_m=.1, tolerance_m=.05)
        self.assertEqual(sorted(row['point_index'] for row in records), [0, 1])
        self.assertTrue(arrays['prefix_undetermined'].all())


if __name__ == '__main__':
    unittest.main()
