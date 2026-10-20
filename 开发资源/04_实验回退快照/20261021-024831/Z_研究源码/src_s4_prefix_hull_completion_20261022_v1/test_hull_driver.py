import copy
import unittest
import numpy as np
import hull_driver as c


class IndependentHullProofTests(unittest.TestCase):
    def fixture(self, point=(100., 100.), error=0.):
        xy = np.asarray(point)
        time = np.array([0., .5, 1.])
        states = np.zeros((3, 4))
        vehicle = c.hull.common.Vehicle()
        proof, summary = c.hull.audit_point(xy, time, states, np.nan, vehicle=vehicle, spatial_error_m=error)
        return xy, time, states, np.nan, error, vehicle, proof, summary

    def test_excluded_full_prefix_independently_checked(self):
        check = c.independent_geometry(*self.fixture())
        self.assertTrue(check['full_required_prefix_coverage_checked'])
        self.assertEqual(check['all_recorded_hulls_checked'], 2)

    def test_uncertainty_independently_preserved(self):
        check = c.independent_geometry(*self.fixture((1.85, 0.), .01))
        self.assertTrue(check['unknown_preserved'])
        self.assertFalse(check['full_required_prefix_coverage_checked'])

    def test_forged_distance_rejected(self):
        args = list(self.fixture())
        args[-2]['hull_distance_m'][0] += 1
        with self.assertRaises(RuntimeError):
            c.independent_geometry(*args)

    def test_forged_bound_rejected(self):
        args = list(self.fixture())
        args[-2]['curvature_m'][0] = -1e-9
        with self.assertRaises(RuntimeError):
            c.independent_geometry(*args)

    def test_reduced_space_error_rejected_by_margin(self):
        args = list(self.fixture(error=.001))
        args[4] = 0.
        with self.assertRaises(RuntimeError):
            c.independent_geometry(*args)

    def test_forged_count_rejected(self):
        args = list(self.fixture())
        args[-1]['GEOS_evaluations'] += 1
        with self.assertRaises(RuntimeError):
            c.independent_geometry(*args)

    def test_shortened_endpoint_rejected(self):
        args = list(self.fixture())
        args[-1]['audited_until_s'] -= 1e-9
        with self.assertRaises(RuntimeError):
            c.independent_geometry(*args)

    def test_wrong_dtype_rejected(self):
        args = list(self.fixture())
        args[-2]['interval'] = args[-2]['interval'].astype(np.int64)
        with self.assertRaises(RuntimeError):
            c.independent_geometry(*args)

    def test_no_nan_lower_reinterpretation(self):
        args = list(self.fixture())
        args[-1]['original_lower_is_nan'] = False
        with self.assertRaises(RuntimeError):
            c.independent_geometry(*args)

    def test_witness_remains_witness(self):
        check = c.independent_geometry(*self.fixture((0., 0.)))
        self.assertFalse(check['full_required_prefix_coverage_checked'])
        self.assertGreater(check['midpoint_analytic_GE0S_checks'], 0)

    def test_rotating_enclosure_independently_checked(self):
        args = list(self.fixture())
        args[2] = np.array([[0., 0., .3, -.1], [2., -1., .6, .2], [3., 2., -.7, .4]])
        args[-2], args[-1] = c.hull.audit_point(args[0], args[1], args[2], args[3],
            vehicle=args[5], spatial_error_m=args[4])
        self.assertTrue(c.independent_geometry(*args)['full_required_prefix_coverage_checked'])


if __name__ == '__main__':
    unittest.main()
