"""Synthetic paths and deliberately corrupted traces only; no real inputs."""
import inspect
import unittest
from unittest.mock import patch
import numpy as np
import upper_driver as d
import upper_core as c


class UpperTests(unittest.TestCase):
    def fixture(self, *, zero=False, empty=False):
        vehicle = d.base.common.Vehicle(L=2., width=1., l_h=0.)
        time = np.array([0., 1.])
        states = np.array([[0., 0., 0., 0.], [2., 0., 0., 0.]])
        xy = np.array([[.5, .1], [.5, -.2], [0., .5]])
        n = len(xy)
        labels = {'contact_status': np.ones(n, np.int8), 'contact_lower_s': np.zeros(n),
            'contact_upper_s': np.ones(n), 'nominal_instantaneous_edge': np.ones(n, np.int8),
            'possible_edge_codes': np.full(n, 255, np.uint16), 'edge_certain': np.zeros(n, bool),
            'initial_tolerance_contact_certain': np.zeros(n, bool),
            'initial_tolerance_contact_possible': np.zeros(n, bool), 'initial_nominal_body_overlap': np.zeros(n, bool),
            'candidate_interval_seen': np.ones(n, bool), 'interval_evaluations': np.arange(n, dtype=np.int32),
            'budget_exhausted': np.zeros(n, bool)}
        if zero:
            xy[:] = [0., .5]
            labels['contact_upper_s'][:] = 0.
        if empty:
            xy = xy[:0]
            labels = {k: v[:0] for k, v in labels.items()}
        params = dict(length=vehicle.L, width=vehicle.width, hitch_offset=vehicle.l_h)
        geometry = lambda x, pose: d.base.finite_face_geometry(x, pose, **params)
        speed = d.base.motion_bound(states, time, **params)
        return xy, time, states, labels, .001, vehicle, geometry, speed

    def run_fixture(self, **kwargs):
        xy, time, states, original, error, vehicle, geom, speed = self.fixture(**kwargs)
        proposed, trace = c.candidate(xy, time, states, original, error, geom, speed,
            d.base.original_corner_rule, d.science.core.confidence)
        return xy, time, states, original, proposed, error, vehicle, trace

    def check(self, values):
        xy, time, states, original, proposed, error, vehicle, trace = values
        return c.independently_check(xy, time, states, original, proposed, error, vehicle, trace,
            d.science.core.geos_geometry, d.scalar_max_speed(time, states, vehicle))

    def test_all_probes_and_candidates_independent_geos(self):
        values = self.run_fixture()
        result = self.check(values)
        self.assertEqual(result['all_selected_records'], 3)
        self.assertGreater(result['all_probe_GE0S_queries'], 0)
        self.assertEqual(result['strict_new_upper_witnesses'], 3)

    def test_all_lowers_byte_exact(self):
        *_, original, proposed, error, vehicle, trace = self.run_fixture()
        self.assertTrue(c.identical(original['contact_lower_s'], proposed['contact_lower_s']))

    def test_initial_zero_width_no_probes_full_exact_reuse(self):
        values = self.run_fixture(zero=True)
        self.check(values)
        for k in values[3]:
            self.assertTrue(c.identical(values[3][k], values[4][k]))
        self.assertEqual(values[-1]['evaluations'].sum(), 0)

    def test_empty_block_supported(self):
        result = self.check(self.run_fixture(empty=True))
        self.assertEqual(result['all_selected_records'], 0)
        self.assertEqual(result['all_probe_GE0S_queries'], 0)

    def test_inputs_unchanged(self):
        xy, t, s, original, error, v, geom, speed = self.fixture()
        before = d.base.array_meta(original)
        c.candidate(xy, t, s, original, error, geom, speed, d.base.original_corner_rule, d.science.core.confidence)
        self.assertEqual(before, d.base.array_meta(original))

    def test_nonmonotonic_search_never_promotes_internal_low(self):
        xy, t, s, original, error, v, geom, speed = self.fixture()
        def nonmonotonic(x, pose):
            q = pose[:, 0] / 2
            distance = np.where(((q > .1) & (q < .2)) | ((q > .8) & (q < .9)), 0., 1.)
            return distance, np.broadcast_to([0., 1., 2., 3.], (len(x), 4)).copy()
        out, trace = c.candidate(xy, t, s, original, error, nonmonotonic, speed,
            d.base.original_corner_rule, d.science.core.confidence)
        self.assertTrue(c.identical(out['contact_lower_s'], original['contact_lower_s']))
        self.assertTrue((out['contact_upper_s'] > .8).all())
        self.assertTrue((trace['time_s'][:, 0] == .5).all())
        self.assertFalse(trace['witness'][:, 0].any())

    def test_no_earlier_witness_all_fields_exact(self):
        xy, t, s, original, error, v, geom, speed = self.fixture()
        def no_hit(x, pose):
            return np.ones(len(x)), np.ones((len(x), 4))
        out, trace = c.candidate(xy, t, s, original, error, no_hit, speed,
            d.base.original_corner_rule, d.science.core.confidence)
        for k in original:
            self.assertTrue(c.identical(out[k], original[k]))
        self.assertFalse(trace['witness'].any())

    def test_signed_zero_lower_exact(self):
        xy, t, s, original, error, v, geom, speed = self.fixture()
        original['contact_lower_s'][0] = -0.
        out, trace = c.candidate(xy, t, s, original, error, geom, speed,
            d.base.original_corner_rule, d.science.core.confidence)
        self.assertEqual(original['contact_lower_s'].tobytes(), out['contact_lower_s'].tobytes())

    def test_original_evaluation_provenance_retained(self):
        values = self.run_fixture()
        self.assertTrue(c.identical(values[3]['interval_evaluations'], values[4]['interval_evaluations']))
        self.assertGreater(values[-1]['evaluations'].sum(), 0)

    def test_already_certain_excluded(self):
        labels = self.fixture()[3]
        labels['edge_certain'][1] = True
        self.assertEqual(c.selection(labels).tolist(), [True, False, True])

    def test_unwitnessed_excluded(self):
        labels = self.fixture()[3]
        labels['contact_upper_s'][1] = np.nan
        labels['contact_status'][1] = 2
        self.assertEqual(c.selection(labels).tolist(), [True, False, True])

    def test_budget_selected_rejected(self):
        labels = self.fixture()[3]
        labels['budget_exhausted'][1] = True
        with self.assertRaises(ValueError):
            c.selection(labels)

    def test_invalid_bracket_rejected(self):
        xy, t, s, labels, error, *_ = self.fixture()
        labels['contact_lower_s'][0] = 2.
        with self.assertRaises(ValueError):
            c.validate_inputs(xy, t, s, labels, error)

    def corruption(self, key, change):
        values = self.run_fixture()
        change(values[-1][key])
        with self.assertRaises(ValueError):
            self.check(values)

    def test_probe_time_corruption(self):
        self.corruption('time_s', lambda x: x.__setitem__((0, 0), .25))

    def test_probe_distance_corruption(self):
        self.corruption('body_distance_m', lambda x: x.__setitem__((0, 0), 10.))

    def test_witness_decision_corruption(self):
        self.corruption('witness', lambda x: x.__setitem__((0, 0), not x[0, 0]))

    def test_padding_time_corruption(self):
        self.corruption('time_s', lambda x: x.__setitem__((0, -1), 0.))

    def test_padding_witness_corruption(self):
        self.corruption('witness', lambda x: x.__setitem__((0, -1), True))

    def test_padding_distance_corruption(self):
        self.corruption('body_distance_m', lambda x: x.__setitem__((0, -1), 0.))

    def test_premature_trace_stop_rejected(self):
        self.corruption('evaluations', lambda x: x.__setitem__(0, 1))

    def test_internal_width_corruption(self):
        self.corruption('internal_remaining_width_s', lambda x: x.__setitem__(0, 1.))

    def test_probe_budget_corruption(self):
        self.corruption('probe_budget_exhausted', lambda x: x.__setitem__(0, True))

    def test_lower_corruption_rejected(self):
        values = self.run_fixture()
        values[4]['contact_lower_s'][0] = 1e-10
        with self.assertRaises(ValueError):
            self.check(values)

    def test_upper_corruption_rejected(self):
        values = self.run_fixture()
        values[4]['contact_upper_s'][0] += 1e-5
        with self.assertRaises(ValueError):
            self.check(values)

    def test_confidence_corruption_rejected(self):
        values = self.run_fixture()
        values[4]['edge_certain'][0] = not values[4]['edge_certain'][0]
        with self.assertRaises(ValueError):
            self.check(values)

    def test_nominal_code_corruption_rejected(self):
        values = self.run_fixture()
        values[4]['nominal_instantaneous_edge'][0] = 8
        with self.assertRaises(ValueError):
            self.check(values)

    def test_possible_edge_set_corruption_rejected(self):
        values = self.run_fixture()
        values[4]['possible_edge_codes'][0] = 0
        with self.assertRaises(ValueError):
            self.check(values)

    def test_dtype_corruption_rejected(self):
        values = self.run_fixture()
        values[4]['contact_status'] = values[4]['contact_status'].astype(np.int64)
        with self.assertRaises(ValueError):
            self.check(values)

    def test_fixed_budget_exhaustion_not_silent(self):
        xy, t, s, original, error, v, geom, speed = self.fixture()
        with patch.object(c, 'STEPS', 1):
            out, trace = c.candidate(xy, t, s, original, error, geom, speed,
                d.base.original_corner_rule, d.science.core.confidence)
        self.assertTrue(trace['probe_budget_exhausted'].all())

    def test_guard_is_stricter_not_tol_relaxation(self):
        self.assertEqual(c.TOL, .050000001)
        self.assertEqual(c.RESOLUTION, 1e-7)
        self.assertGreater(c.GUARD, 0.)

    def test_scalar_motion_bound_matches_original(self):
        xy, t, s, original, error, v, geom, speed = self.fixture()
        self.assertEqual(d.scalar_max_speed(t, s, v), float(speed.max()))

    def test_old_scientific_entrypoints_not_called(self):
        text = inspect.getsource(d)
        for name in ('science.run(', 'science.close(', 'admin.finalize(', 'merge.run(', 'merge.close('):
            self.assertNotIn(name, text)


if __name__ == '__main__':
    unittest.main()
