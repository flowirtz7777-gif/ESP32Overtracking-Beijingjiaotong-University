import unittest
import numpy as np
from contact_primitives import finite_face_geometry, edge_candidates, refine_isolated_entry

PARAMS = dict(length=4., width=2., hitch_offset=0.)

class ContactPrimitiveTests(unittest.TestCase):
    def test_right_face(self):
        body, face = finite_face_geometry([[-2., -1.1]], [0., 0., 0., 0.], **PARAMS)
        self.assertAlmostEqual(body[0], .1)
        self.assertEqual(edge_candidates(face, 0.)['edge_candidate_bits'][0], 2)

    def test_finite_corner_has_both_adjacent_faces(self):
        body, face = finite_face_geometry([[.1, -1.1]], [0., 0., 0., 0.], **PARAMS)
        self.assertAlmostEqual(body[0], np.sqrt(.02))
        self.assertEqual(edge_candidates(face, 1e-15)['edge_candidate_bits'][0], 3)

    def test_no_implicit_one_mm_corner_band(self):
        _, face = finite_face_geometry([[-.1, -.8995]], [0., 0., 0., 0.], **PARAMS)
        self.assertEqual(edge_candidates(face, 0.)['edge_candidate_bits'][0], 1)
        self.assertEqual(edge_candidates(face, .001)['edge_candidate_bits'][0], 3)

    def test_inside_body_is_contact_not_zero_edge_distance(self):
        body, face = finite_face_geometry([[-2., 0.]], [0., 0., 0., 0.], **PARAMS)
        self.assertEqual(body[0], 0.)
        self.assertEqual(face.min(), 1.)

    def test_rigid_rotation_equivariance(self):
        point = np.array([[-2., -1.1]])
        angle = .7
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        expected = finite_face_geometry(point, [0., 0., 0., 0.], **PARAMS)
        actual = finite_face_geometry(point@rotation.T, [0., 0., angle, 0.], **PARAMS)
        np.testing.assert_allclose(expected[0], actual[0], atol=1e-14)
        np.testing.assert_allclose(expected[1], actual[1], atol=1e-14)

    def test_analytic_straight_entry_bracket(self):
        result = refine_isolated_entry([[1., 0.]], [0.,0.,0.,0.], [1.,0.,0.,0.], 0., 1.,
                                       isolated_entry_proven=True, **PARAMS)
        self.assertLessEqual(result['contact_lower_s'][0], .95)
        self.assertGreaterEqual(result['contact_upper_s'][0], .95)
        self.assertLessEqual(result['contact_upper_s'][0]-result['contact_lower_s'][0], 1e-7)

    def test_no_endpoint_only_global_first_entry_claim(self):
        with self.assertRaisesRegex(ValueError, 'isolation'):
            refine_isolated_entry([[1.,0.]], [0.,0.,0.,0.], [1.,0.,0.,0.], 0., 1., **PARAMS)

    def test_outside_endpoints_stay_unresolved_not_noncontact(self):
        result = refine_isolated_entry([[20.,0.]], [0.,0.,0.,0.], [1.,0.,0.,0.], 0., 1.,
                                       isolated_entry_proven=True, **PARAMS)
        self.assertTrue(result['unresolved'][0])
        self.assertTrue(np.isnan(result['contact_upper_s'][0]))

    def test_no_negative_uncertainty(self):
        with self.assertRaises(ValueError):
            edge_candidates(np.zeros((1,4)), -.01)

if __name__ == '__main__':
    unittest.main()
