import copy
import unittest
from unittest.mock import patch
import numpy as np
import candidate_core as c
import candidate_driver as d


class SparsePrefixTests(unittest.TestCase):
    def setUp(self):
        self.vehicle = c.hull.common.Vehicle()
        self.time = np.array([0., 1., 2.])
        self.state = np.zeros((3, 4))
        self.broad = c.boxes(self.time, self.state, self.vehicle)

    def audit(self, point=(100., 100.), lower=np.nan, error=1e-6):
        return c.audit(np.asarray(point), self.time, self.state, lower, error, self.vehicle, self.broad)

    def validate(self, arrays, summary, point=(100., 100.), lower=np.nan, error=1e-6):
        broad = c.independent_boxes(self.state, self.vehicle, self.broad)
        return c.validate(np.asarray(point), self.time, self.state, lower, error, self.vehicle, broad, arrays, summary)

    def test_full_nan_path_far_point_has_no_geos(self):
        a, s = self.audit()
        self.assertTrue(s['all_required_prefix_excluded'])
        self.assertEqual(s['audited_until_s'], 2.)
        self.assertEqual(s['GEOS_evaluations'], 0)
        self.assertTrue(self.validate(a, s)['complete'])

    def test_original_finite_endpoint_not_shortened(self):
        a, s = self.audit(lower=.25)
        self.assertEqual(s['audited_until_s'], .25)
        self.validate(a, s, lower=.25)

    def test_empty_required_prefix(self):
        a, s = self.audit(point=(0., 0.), lower=0.)
        self.assertTrue(s['all_required_prefix_excluded'])
        self.validate(a, s, point=(0., 0.), lower=0.)

    def test_early_contact_preserved(self):
        a, s = self.audit(point=(0., 0.))
        self.assertEqual(s['status'], 'early_contact_witness')
        self.assertFalse(self.validate(a, s, point=(0., 0.))['complete'])

    def test_uncertainty_not_negative_label(self):
        a, s = self.audit(point=(0., 1.05), lower=1., error=1e-5)
        self.assertEqual(s['status'], 'unknown_time_leaf')
        self.assertFalse(self.validate(a, s, point=(0., 1.05), lower=1., error=1e-5)['complete'])

    def test_selected_narrow_hull_exclusion(self):
        state = np.array([[0., 0., .7, .1], [0., 0., .7, .1], [0., 0., .7, .1]])
        broad = c.boxes(self.time, state, self.vehicle)
        point = broad['hi'][0] - .01
        a, s = c.audit(point, self.time, state, np.nan, 1e-6, self.vehicle, broad)
        self.assertGreater(s['selected_intervals'], 0)
        self.assertTrue(s['all_required_prefix_excluded'])
        c.validate(point, self.time, state, np.nan, 1e-6, self.vehicle, broad, a, s)

    def test_all_and_only_candidates_vector_scalar(self):
        random = np.random.default_rng(920)
        state = np.cumsum(random.normal(0, .1, (10, 4)), axis=0)
        time = np.arange(10, dtype=float)
        broad = c.boxes(time, state, self.vehicle)
        independent = c.independent_boxes(state, self.vehicle, broad)
        for point in random.normal(0, 10, (30, 2)):
            np.testing.assert_array_equal(c.selected(point, time, 7.2, broad, 1e-5),
                                          c.independent_selected(point, time, 7.2, independent, 1e-5))

    def test_spatial_error_not_reduced(self):
        point = np.array([0., 1.06])
        self.assertEqual(len(c.selected(point, self.time, np.nan, self.broad, .001)), 0)
        self.assertEqual(len(c.selected(point, self.time, np.nan, self.broad, .02)), 2)

    def test_corrupt_selected_interval_rejected(self):
        a, s = self.audit(point=(0., 0.))
        a['selected_original_intervals'] = np.array([], np.int32)
        with self.assertRaises(RuntimeError):
            self.validate(a, s, point=(0., 0.))

    def test_selected_dtype_rejected(self):
        a, s = self.audit()
        a['selected_original_intervals'] = a['selected_original_intervals'].astype(float)
        with self.assertRaises(RuntimeError):
            self.validate(a, s)

    def test_original_endpoint_corruption_rejected(self):
        a, s = self.audit()
        s['audited_until_s'] = 1.
        with self.assertRaises(RuntimeError):
            self.validate(a, s)

    def test_missing_tree_record_rejected(self):
        a, s = self.audit(point=(0., 0.))
        s['interval_records'] = []
        with self.assertRaises(RuntimeError):
            self.validate(a, s, point=(0., 0.))

    def test_counterexample_cannot_be_promoted(self):
        a, s = self.audit(point=(0., 0.))
        s['status'], s['all_required_prefix_excluded'] = 'excluded', True
        with self.assertRaises(RuntimeError):
            self.validate(a, s, point=(0., 0.))

    def test_tree_hole_rejected(self):
        a, s = self.audit(point=(0., 0.))
        a['a'][0] = .1
        with self.assertRaises(RuntimeError):
            self.validate(a, s, point=(0., 0.))

    def test_surplus_nodes_rejected(self):
        a, s = self.audit()
        a['a'] = np.array([0.])
        with self.assertRaises(RuntimeError):
            self.validate(a, s)

    def test_lower_outside_path_rejected(self):
        for lower in (-1., 3., np.inf, -np.inf):
            with self.assertRaises(ValueError):
                self.audit(lower=lower)

    def test_nonmonotone_path_rejected(self):
        with self.assertRaises(ValueError):
            c.boxes(np.array([0., 1., 1.]), self.state, self.vehicle)

    def test_negative_space_error_rejected(self):
        with self.assertRaises(ValueError):
            self.audit(error=-1.)

    def test_corrupt_broad_enclosure_rejected(self):
        bad = copy.deepcopy(self.broad)
        bad['lo'][0, 0] += .01
        with self.assertRaises(RuntimeError):
            c.independent_boxes(self.state, self.vehicle, bad)

    def test_per_interval_budget_and_policy_fixed(self):
        self.assertEqual(c.INTERVAL_BUDGET, 131072)
        self.assertEqual(c.RESOLUTION, 1e-8)
        self.assertEqual(c.TOLERANCE, d.base.TOLERANCE)

    def test_frozen_hull_code_object_not_modified(self):
        before = c.hull.audit_point.__code__
        self.audit()
        self.assertIs(before, c.hull.audit_point.__code__)

    def test_execution_restores_current_run_even_on_failure(self):
        with patch.object(d.parent, 'execution', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):
                d.execution()
        self.assertEqual(d.r.RUN, d.RUN)

    def test_no_synthetic_test_calls_used_entrypoints(self):
        with patch.object(d.parent, 'run', side_effect=AssertionError('old entry')), \
             patch.object(d.parent, 'close', side_effect=AssertionError('old close')):
            self.audit()

    def test_budget_unknown_preserved_before_any_more_intervals(self):
        with patch.object(c, 'INTERVAL_BUDGET', 1):
            a, s = self.audit(point=(0., 1.05), error=1e-5)
        self.assertEqual(s['status'], 'unknown_budget')
        self.assertFalse(s['all_required_prefix_excluded'])
        self.assertEqual(len(s['interval_records']), 1)
        self.assertEqual(a['status'][-1], c.hull.BUDGET)

    def test_clipped_last_interval_exact_tree_endpoint(self):
        a, s = self.audit(point=(0., 0.), lower=.25)
        self.assertEqual(a['b'][0], .25)
        self.validate(a, s, point=(0., 0.), lower=.25)

    def test_no_future_intervals_when_lower_at_boundary(self):
        a, s = self.audit(point=(0., 0.), lower=1.)
        np.testing.assert_array_equal(a['selected_original_intervals'], [0])
        self.validate(a, s, point=(0., 0.), lower=1.)

    def test_chord_aabb_contains_sampled_full_affine_corner_path(self):
        state = np.array([[0., 0., .2, -.2], [2., 1., 1., .3]])
        broad = c.boxes(np.array([0., 1.]), state, self.vehicle)
        poses = state[0] + np.linspace(0, 1, 101)[:, None] * (state[1] - state[0])
        points = c.hull.common.body_corners(poses, self.vehicle)
        self.assertTrue(np.all(points >= broad['lo'][0] - broad['curve'][0] - 1e-12))
        self.assertTrue(np.all(points <= broad['hi'][0] + broad['curve'][0] + 1e-12))


if __name__ == '__main__':
    unittest.main()
