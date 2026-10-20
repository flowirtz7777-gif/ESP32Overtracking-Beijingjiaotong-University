"""Synthetic paths only; no frozen real input is loaded by this suite."""
import inspect
import unittest
import numpy as np
import observability as d
import observability_core as core


class ObservabilityTests(unittest.TestCase):
    def fixture(self, *, error=.001):
        vehicle = d.base.common.Vehicle(L=2., width=1., l_h=0.)
        time = np.array([0., 1.])
        states = np.array([[0., 0., 0., 0.], [1., 0., .03, .01]])
        xy = np.array([[-1., .5495], [.2, .5495], [.2, 0.], [.5, .2],
                       [-3., 0.], [-1., .1], [-1., 0.], [0., .5]])
        params = dict(length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
        labels = d.base.label_population(xy, time, states, vehicle=vehicle, spatial_error_m=error,
            tolerance_m=core.TOLERANCE, time_resolution_s=core.RESOLUTION, max_evaluations_per_interval=2048)
        labels.pop('witness_pose')
        speed = d.base.motion_bound(states, time, **params)
        geom = lambda xy, pose: d.base.finite_face_geometry(xy, pose, **params)
        metrics = core.diagnose(xy, time, states, labels, error, vehicle, geom, speed, d.base.original_corner_rule)
        return xy, time, states, labels, error, vehicle, metrics

    def test_complete_frozen_rule_reproduction(self):
        *_, labels, error, vehicle, metrics = self.fixture()
        summary = core.summary(labels, metrics)
        self.assertEqual(summary['budget_flags'], 0)
        self.assertTrue(summary['all_saved_initial_and_edge_rules_exact'])
        self.assertTrue(summary['all_reconstructed_leaf_lowers_exact'])
        self.assertTrue(summary['all_retained_leaf_predicates_reproduced'])

    def test_independent_scalar_geos_all_records(self):
        result = core.independently_check(*self.fixture())
        self.assertEqual(result['all_records'], 8)
        self.assertGreater(result['independent_GE0S_pose_queries'], 0)

    def test_actual_noninitial_leaf_source_exists(self):
        xy, time, states, labels, _, _, metrics = self.fixture()
        ids = np.flatnonzero(metrics['time_leaf_origin'])
        self.assertGreater(len(ids), 0)
        for i in ids:
            self.assertEqual(metrics['leaf_start_s'][i], labels['contact_lower_s'][i])
            self.assertLessEqual(metrics['leaf_width_s'][i], core.RESOLUTION)
            self.assertGreater(2 * metrics['leaf_width_s'][i], core.RESOLUTION)

    def test_initial_uncertain_not_called_budget_or_noncontact(self):
        *_, labels, _, _, metrics = self.fixture()
        self.assertEqual(labels['contact_status'][0], 2)
        self.assertTrue(metrics['initial_origin'][0])
        self.assertFalse(metrics['time_leaf_origin'][0])
        self.assertLess(metrics['initial_exclusion_margin_m'][0], 0)
        self.assertLess(metrics['initial_witness_margin_m'][0], 0)

    def test_known_noncontact_has_no_new_geometry(self):
        xy, time, states, labels, error, vehicle, _ = self.fixture()
        ids = np.flatnonzero(labels['contact_status'] == 0)
        self.assertGreater(len(ids), 0)
        selected = {k: v[ids] for k, v in labels.items()}
        def forbidden(*args):
            raise AssertionError('No geometry may be queried on an already proved noncontact point')
        metrics = core.diagnose(xy[ids], time, states, selected, error, vehicle, forbidden,
                               np.array([2.]), d.base.original_corner_rule)
        self.assertTrue(np.isnan(metrics['leaf_mid_body_distance_m']).all())
        self.assertTrue(np.isnan(metrics['witness_body_distance_m']).all())

    def test_independent_noncontact_has_no_geos_pose_queries(self):
        xy, time, states, labels, error, vehicle, metrics = self.fixture()
        ids = np.flatnonzero(labels['contact_status'] == 0)
        result = core.independently_check(xy[ids], time, states, {k: v[ids] for k, v in labels.items()},
            error, vehicle, {k: v[ids] for k, v in metrics.items()})
        self.assertEqual(result['independent_GE0S_pose_queries'], 0)

    def test_original_labels_exact_before_after(self):
        xy, time, states, labels, error, vehicle, _ = self.fixture()
        before = d.base.array_meta(labels)
        params = dict(length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
        core.diagnose(xy, time, states, labels, error, vehicle,
            lambda xy, pose: d.base.finite_face_geometry(xy, pose, **params),
            d.base.motion_bound(states, time, **params), d.base.original_corner_rule)
        self.assertEqual(before, d.base.array_meta(labels))

    def test_unknowns_partitioned_without_double_counting(self):
        *_, labels, _, _, metrics = self.fixture()
        s = core.summary(labels, metrics)
        self.assertEqual(s['possible_without_witness'],
            s['possible_without_witness_initial_origin'] + s['possible_without_witness_time_leaf_origin'])
        self.assertEqual(s['witnessed_edge_uncertain'], s['uncertain_edge_spatial_only_midpoint_rule_passes']
                         + s['uncertain_edge_spatial_only_midpoint_rule_fails'])

    def test_negative_margin_not_cleared_as_float_noise(self):
        _, _, margins = core.confidence(np.array([[0., .001 - 5e-10, 1., 2.]]), np.array([0.]))
        self.assertLess(margins['single_margin_m'][0], 0.)
        self.assertAlmostEqual(margins['single_margin_m'][0], -5e-10, places=16)

    def test_spatial_only_rule_is_not_a_label_update(self):
        *_, labels, _, _, metrics = self.fixture()
        before = labels['edge_certain'].copy()
        _ = core.summary(labels, metrics)
        np.testing.assert_array_equal(before, labels['edge_certain'])

    def test_original_corner_code_kept(self):
        *_, labels, _, _, metrics = self.fixture(error=0.)
        self.assertEqual(int(labels['nominal_instantaneous_edge'][-1]), 7)
        self.assertTrue(metrics['source_edge_rule_exact'][-1])

    def test_scalar_geometry_corruption_rejected(self):
        xy, time, states, labels, error, vehicle, metrics = self.fixture()
        metrics['midpoint_faces_m'][2, 0] += .01
        with self.assertRaises(RuntimeError):
            core.independently_check(xy, time, states, labels, error, vehicle, metrics)

    def test_scalar_hypothetical_flag_corruption_rejected(self):
        xy, time, states, labels, error, vehicle, metrics = self.fixture()
        metrics['spatial_only_midpoint_rule_passes'][2] ^= True
        with self.assertRaises(RuntimeError):
            core.independently_check(xy, time, states, labels, error, vehicle, metrics)

    def test_original_endpoint_corruption_rejected(self):
        xy, time, states, labels, error, vehicle, metrics = self.fixture()
        i = np.flatnonzero(metrics['time_leaf_origin'])[0]
        metrics['leaf_a'][i] += 2.**-24
        with self.assertRaises(RuntimeError):
            core.independently_check(xy, time, states, labels, error, vehicle, metrics)

    def test_remaining_budget_rejected(self):
        xy, time, states, labels, error, vehicle, metrics = self.fixture()
        labels['budget_exhausted'][0] = True
        with self.assertRaises(RuntimeError):
            core.independently_check(xy, time, states, labels, error, vehicle, metrics)

    def test_outside_original_leaf_rejected(self):
        with self.assertRaises(ValueError):
            core.leaf(np.array([0., 1.]), 1.)

    def test_no_label_or_prefix_kernel_call_in_diagnostic_core(self):
        source = inspect.getsource(core)
        self.assertNotIn('label_population(', source)
        self.assertNotIn('audit_point(', source)
        self.assertNotIn('search_first_possible(', source)

    def test_original_scientific_constants_unchanged(self):
        self.assertEqual(core.RESOLUTION, d.base.TIME_RESOLUTION)
        self.assertEqual(core.TOLERANCE, d.base.TOLERANCE)
        self.assertEqual(core.CORNER, .001)


if __name__ == '__main__':
    unittest.main()
