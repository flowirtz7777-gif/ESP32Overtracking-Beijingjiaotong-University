"""Synthetic-only tests: no study input is opened."""
import copy
from decimal import Decimal
import math
from types import SimpleNamespace
import unittest

import numpy as np

import local_motion_core as c


V = SimpleNamespace(L=3., width=2., l_h=-.5)


def fixture(faces=None, error=1e-6):
    time = np.asarray([0., 1., 2., 3.])
    states = np.zeros((4, 4))
    states[:, 0] = [0., .0001, .0002, 100.]
    n = 5
    labels = {
        "contact_status": np.asarray([1, 2, 2, 0, 1], np.int8),
        "contact_lower_s": np.asarray([.25, 0., .75, np.nan, .25]),
        "contact_upper_s": np.asarray([1.75, np.nan, np.nan, np.nan, 1.75]),
        "nominal_instantaneous_edge": np.asarray([1, 0, 0, 0, 1], np.int8),
        "possible_edge_codes": np.asarray([255, 255, 255, 0, 1], np.uint16),
        "edge_certain": np.asarray([False, False, False, False, True]),
        "initial_tolerance_contact_certain": np.asarray([False]*n),
        "initial_tolerance_contact_possible": np.asarray([False, True, False, False, False]),
        "initial_nominal_body_overlap": np.asarray([False]*n),
        "candidate_interval_seen": np.asarray([True]*n),
        "interval_evaluations": np.arange(n, dtype=np.int32),
        "budget_exhausted": np.asarray([False]*n),
    }
    xy = np.zeros((n, 2))
    face = np.asarray([0., .003, 1., 2.] if faces is None else faces)
    calls = []
    def geometry(points, poses):
        calls.extend(points.tolist())
        return np.zeros(len(points)), np.broadcast_to(face, (len(points), 4)).copy()
    def geos(point, pose, vehicle):
        return 0., face.copy()
    return xy, time, states, labels, error, V, geometry, geos, calls


def run_fixture(f=None):
    f = fixture() if f is None else f
    out, trace, variation = c.candidate(*f[:7])
    return f, out, trace, variation


class MotionTests(unittest.TestCase):
    def test_stationary_zero(self):
        t = np.asarray([0., 1.])
        s = np.zeros((2, 4))
        np.testing.assert_array_equal(c.segment_variation(t, s, V), [0.])
        self.assertEqual(c.bracket_bound(t, np.zeros(1), 0., 1.)[3], 0.)

    def test_translation(self):
        t = np.asarray([0., 2.])
        s = np.asarray([[0., 0., 0., 0.], [3., 4., 0., 0.]])
        v = c.segment_variation(t, s, V)
        self.assertGreaterEqual(v[0], 5.)
        self.assertLess(v[0], 5.000000000001)
        self.assertGreaterEqual(c.integrated_bound(t, v, .5, 1.5), 2.5)

    def test_rotation_high_precision(self):
        t = np.asarray([0., .1, 1.])
        s = np.asarray([[0., 0., .4, -.2], [.1, -.1, -.5, .8], [.5, .6, .1, -.8]])
        v = c.segment_variation(t, s, V)
        for k in range(2):
            self.assertGreaterEqual(Decimal.from_float(float(v[k])), c.decimal_segment_variation(s[k], s[k+1], V))
        for low, high in ((0., 1.), (.05, .7), (.1, .2), (0., 0.), (1., 1.)):
            _, left, right, radius = c.bracket_bound(t, v, low, high)
            exact = c.decimal_radius(t, s, V, low, high)
            for a, b in zip((left, right, radius), exact):
                self.assertGreaterEqual(Decimal.from_float(a), b)

    def test_far_global_speed_not_used(self):
        f, _, trace, _ = run_fixture()
        self.assertLess(trace["motion_radius_m"][0], .001)
        self.assertGreater(np.max(np.diff(f[2][:, 0])) * .75, 70.)

    def test_crossing_fast_interval_included(self):
        t = np.asarray([0., 1., 2.])
        v = np.asarray([100., 1.])
        mid, left, right, radius = c.bracket_bound(t, v, .5, 1.5)
        self.assertEqual(mid, 1.)
        self.assertGreaterEqual(left, 50.)
        self.assertGreaterEqual(right, .5)
        self.assertEqual(radius, left)

    def test_boundary_interval_not_added(self):
        self.assertEqual(c.integrated_bound(np.asarray([0., 1., 2.]), np.asarray([100., 0.]), 1., 2.), 0.)

    def test_empty_bracket_endpoint(self):
        self.assertEqual(c.bracket_bound(np.asarray([0., 1.]), np.asarray([10.]), 1., 1.), (1., 0., 0., 0.))

    def test_reject_outside_full_path(self):
        for a, b in ((-.1, 1.), (0., 1.1), (1., 0.), (math.nan, 1.)):
            with self.assertRaises(ValueError):
                c.integrated_bound(np.asarray([0., 1.]), np.asarray([1.]), a, b)

    def test_invalid_vehicle_or_path(self):
        for t, s, v in ((np.asarray([0., 0.]), np.zeros((2, 4)), V),
                        (np.asarray([0., 1.]), np.zeros((2, 3)), V),
                        (np.asarray([0., 1.]), np.zeros((2, 4)), SimpleNamespace(L=0., width=2., l_h=1.))):
            with self.assertRaises(ValueError):
                c.segment_variation(t, s, v)

    def test_piecewise_reconstruction(self):
        t = np.asarray([0., .2, 1., 3.])
        v = np.asarray([2., 5., 10.])
        for a, b in ((0., 3.), (.1, 2.5), (.2, 1.), (1., 1.), (.1, .1001)):
            self.assertEqual(c.integrated_bound(t, v, a, b), c.independent_sum(t, v, a, b))


class CandidateTests(unittest.TestCase):
    def test_strict_single_certification(self):
        f, out, trace, v = run_fixture()
        self.assertTrue(out["edge_certain"][0])
        self.assertEqual(out["possible_edge_codes"][0], 1)
        result = c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])
        self.assertEqual(result["newly_certified_edge_candidates"], 1)
        self.assertEqual(result["independent_midpoint_GE0S_queries"], 1)

    def test_unwitnessed_and_noncontact_no_geometry(self):
        f, out, trace, _ = run_fixture()
        self.assertEqual(len(f[-1]), 1)
        np.testing.assert_array_equal(trace["unwitnessed_contact_unknown_retained"], [False, True, True, False, False])
        for name in out:
            self.assertEqual(out[name][1:].tobytes(), f[3][name][1:].tobytes())

    def test_all_scientific_endpoints_unchanged(self):
        f, out, _, _ = run_fixture()
        for name in f[3].keys() - {"edge_certain", "possible_edge_codes"}:
            self.assertEqual(f[3][name].tobytes(), out[name].tobytes())

    def test_uncertain_signed_margin_retained(self):
        f, out, trace, v = run_fixture(fixture([0., .00101, 1., 2.]))
        self.assertFalse(out["edge_certain"][0])
        self.assertLess(trace["confidence_margins_m"][0, 0], 0.)
        self.assertLess(trace["confidence_margins_m"][0, 1], 0.)
        for name in out:
            self.assertEqual(out[name].tobytes(), f[3][name].tobytes())
        c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_spatial_bound_not_removed(self):
        f, out, _, _ = run_fixture(fixture(error=.002))
        self.assertFalse(out["edge_certain"][0])

    def test_zero_width_keeps_spatial_error(self):
        f = fixture(error=.002)
        f[3]["contact_lower_s"][0] = f[3]["contact_upper_s"][0] = 0.
        _, out, trace, _ = run_fixture(f)
        self.assertEqual(trace["motion_radius_m"][0], 0.)
        self.assertGreater(trace["total_envelope_m"][0], .002)
        self.assertFalse(out["edge_certain"][0])

    def test_corner_is_single_code(self):
        f = fixture([0., .0001, 1., 2.])
        f[3]["nominal_instantaneous_edge"][0] = 5
        _, out, _, _ = run_fixture(f)
        self.assertTrue(out["edge_certain"][0])
        self.assertEqual(out["possible_edge_codes"][0], 16)

    def test_opposite_faces_not_corner(self):
        code, stable, _ = c.face_rule(np.asarray([0., 1., .0001, 2.]), 1e-6)
        self.assertEqual(code, 1)
        self.assertFalse(stable)

    def test_no_corner_margin_equality_promotion(self):
        _, stable, margins = c.face_rule(np.asarray([0., .001, 1., 2.]), 0.)
        self.assertFalse(stable)
        self.assertEqual(margins[0], 0.)
        self.assertEqual(margins[1], 0.)

    def test_wrong_original_nominal_rejected(self):
        f = fixture()
        f[3]["nominal_instantaneous_edge"][0] = 2
        with self.assertRaises(ValueError):
            c.candidate(*f[:7])

    def test_budget_not_silently_omitted(self):
        f = fixture()
        f[3]["budget_exhausted"][2] = True
        with self.assertRaises(ValueError):
            c.candidate(*f[:7])

    def test_invalid_spatial_error(self):
        for error in (-1., math.nan, math.inf):
            with self.assertRaises(ValueError):
                c.candidate(*fixture(error=error)[:7])

    def test_nan_and_infinite_endpoints_rejected(self):
        for field, value in (("contact_lower_s", math.nan), ("contact_upper_s", math.inf)):
            f = fixture()
            f[3][field][0] = value
            with self.assertRaises(ValueError):
                c.candidate(*f[:7])

    def test_independent_rejects_lower_change(self):
        f, out, trace, v = run_fixture()
        out["contact_lower_s"][0] += .1
        with self.assertRaises(ValueError):
            c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_independent_rejects_unwitnessed_relabel(self):
        f, out, trace, v = run_fixture()
        out["edge_certain"][1] = True
        with self.assertRaises(ValueError):
            c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_independent_rejects_omitted_motion(self):
        f, out, trace, v = run_fixture()
        trace["motion_radius_m"][0] = 0.
        with self.assertRaises(ValueError):
            c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_independent_rejects_variation_tamper(self):
        for value in (0., 1000., math.nan):
            f, out, trace, v = run_fixture()
            v[0] = value
            with self.assertRaises(ValueError):
                c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_independent_rejects_padding(self):
        f, out, trace, v = run_fixture()
        trace["midpoint_s"][1] = 0.
        with self.assertRaises(ValueError):
            c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_independent_rejects_scope_flag(self):
        f, out, trace, v = run_fixture()
        trace["unwitnessed_contact_unknown_retained"][1] = False
        with self.assertRaises(ValueError):
            c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_independent_rejects_dtype(self):
        f, out, trace, v = run_fixture()
        out["possible_edge_codes"] = out["possible_edge_codes"].astype(np.int32)
        with self.assertRaises(ValueError):
            c.independent_check(*f[:4], out, f[4], f[5], trace, v, f[7])

    def test_empty_scope(self):
        f = fixture()
        empty = {k: v[:0] for k, v in f[3].items()}
        out, trace, v = c.candidate(f[0][:0], f[1], f[2], empty, f[4], V, f[6])
        c.independent_check(f[0][:0], f[1], f[2], empty, out, f[4], V, trace, v, f[7])
        self.assertEqual(len(f[-1]), 0)



    def test_random_full_brackets_against_high_precision(self):
        rng = np.random.default_rng(20261022)
        for case in range(40):
            t = np.r_[0., np.cumsum(rng.uniform(.001, .2, size=7))]
            s = np.cumsum(rng.normal(size=(8, 4)), axis=0)
            v = c.segment_variation(t, s, V)
            for j in range(5):
                low, high = sorted(rng.uniform(t[0], t[-1], size=2))
                _, left, right, radius = c.bracket_bound(t, v, low, high)
                exact = c.decimal_radius(t, s, V, low, high)
                for actual, expected in zip((left, right, radius), exact):
                    self.assertGreaterEqual(Decimal.from_float(actual), expected)

    def test_actual_finite_faces_with_shapely(self):
        import shapely
        f = fixture()
        f[0][0] = [-2., -1.01]
        f[3]["nominal_instantaneous_edge"][0] = 2
        def geos(point, pose, vehicle):
            x, y, theta, phi = map(float, pose)
            heading = theta - phi
            hx, hy = x + vehicle.l_h * math.cos(theta), y + vehicle.l_h * math.sin(theta)
            rx, ry = hx - vehicle.L * math.cos(heading), hy - vehicle.L * math.sin(heading)
            nx, ny = vehicle.width / 2 * math.sin(heading), -vehicle.width / 2 * math.cos(heading)
            corners = [(hx+nx, hy+ny), (rx+nx, ry+ny), (rx-nx, ry-ny), (hx-nx, hy-ny)]
            p = shapely.Point(*point)
            faces = np.asarray([p.distance(shapely.LineString([corners[a], corners[b]]))
                                for a, b in ((3, 0), (0, 1), (1, 2), (2, 3))])
            return p.distance(shapely.Polygon(corners)), faces
        def geometry(xy, poses):
            answers = [geos(point, pose, V) for point, pose in zip(xy, poses)]
            return np.asarray([a[0] for a in answers]), np.asarray([a[1] for a in answers])
        out, trace, v = c.candidate(*f[:6], geometry)
        self.assertTrue(out["edge_certain"][0])
        self.assertEqual(out["possible_edge_codes"][0], 2)
        c.independent_check(*f[:4], out, f[4], f[5], trace, v, geos)

if __name__ == "__main__":
    unittest.main()

