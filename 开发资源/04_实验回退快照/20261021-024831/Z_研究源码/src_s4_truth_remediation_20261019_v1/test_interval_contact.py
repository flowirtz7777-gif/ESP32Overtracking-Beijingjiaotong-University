import unittest
import numpy as np
from interval_contact import motion_bound, point_contact_interval, original_corner_rule

P = dict(length=4., width=2., hitch_offset=0.)

class IntervalContactTests(unittest.TestCase):
    def test_analytic_entry(self):
        result = point_contact_interval([1.,0.], [0.,1.], [[0,0,0,0],[1,0,0,0]], **P)
        self.assertEqual(result['status'], 'contact')
        self.assertLessEqual(result['lower_s'], .95)
        self.assertGreaterEqual(result['upper_s'], .95)
        self.assertLess(result['upper_s']-result['lower_s'], 2e-7)

    def test_both_endpoints_outside_can_contact(self):
        result = point_contact_interval([1.,0.], [0.,1.], [[0,0,0,0],[10,0,0,0]], **P)
        self.assertEqual(result['status'], 'contact')
        self.assertAlmostEqual(result['lower_s'], .095, places=6)

    def test_endpoints_and_midpoint_outside_can_contact(self):
        result = point_contact_interval([.2,0.], [0.,1.], [[0,0,0,0],[10,0,0,0]],
                                        length=.1, width=.1, hitch_offset=0.)
        self.assertEqual(result['status'], 'contact')
        self.assertAlmostEqual(result['lower_s'], .015, places=6)

    def test_noncontact_requires_interval_exclusion(self):
        result = point_contact_interval([20.,20.], [0.,1.], [[0,0,0,0],[10,0,0,0]], **P)
        self.assertEqual(result['status'], 'noncontact')
        self.assertIsNone(result['upper_s'])

    def test_initial_overlap(self):
        result = point_contact_interval([-2.,0.], [0.,1.], [[0,0,0,0],[1,0,0,0]], **P)
        self.assertTrue(result['initial_overlap'])
        self.assertEqual(result['upper_s'], 0.)

    def test_uncertain_surface_not_declared_noncontact(self):
        result = point_contact_interval([1.,0.], [0.,1.], [[0,0,0,0],[1,0,0,0]],
                                        spatial_error_m=.1, maximum_evaluations=100, **P)
        self.assertIn(result['status'], ('possible_contact_unresolved', 'unresolved_budget'))

    def test_budget_exhaustion_explicit(self):
        result = point_contact_interval([1.,0.], [0.,1.], [[0,0,0,0],[1,0,0,0]],
                                        maximum_evaluations=3, **P)
        self.assertEqual(result['status'], 'unresolved_budget')

    def test_rotation_in_speed_bound(self):
        value = motion_bound(np.array([[0.,0.,0.,0.],[0.,0.,1.,0.]]), np.array([0.,1.]), **P)
        self.assertGreaterEqual(value[0], np.hypot(4.,1.))

    def test_reference_subdivision_same_linear_path(self):
        a = point_contact_interval([1.,0.], [0.,1.], [[0,0,0,0],[1,0,0,0]], **P)
        b = point_contact_interval([1.,0.], [0.,.5,1.], [[0,0,0,0],[.5,0,0,0],[1,0,0,0]], **P)
        self.assertEqual(a['status'], b['status'])
        self.assertLessEqual(max(a['lower_s'], b['lower_s']), min(a['upper_s'], b['upper_s']))

    def test_original_one_mm_rule_preserved(self):
        self.assertEqual(original_corner_rule([[.1,.1005,1.,2.]])[0], 5)
        self.assertEqual(original_corner_rule([[.1,.102,1.,2.]])[0], 1)

if __name__ == '__main__':
    unittest.main()
