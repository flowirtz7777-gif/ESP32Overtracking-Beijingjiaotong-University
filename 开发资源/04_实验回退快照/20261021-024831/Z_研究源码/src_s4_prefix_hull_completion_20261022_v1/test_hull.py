import copy
import unittest
import numpy as np
import shapely
import hull as h


class HullContracts(unittest.TestCase):
    def audit(self, point=(100., 100.), lower=np.nan, **options):
        time = np.array([0., .5, 1.])
        states = np.zeros((3, 4))
        policy = dict(vehicle=h.common.Vehicle(), spatial_error_m=0.)
        policy.update(options)
        proof, summary = h.audit_point(point, time, states, lower, **policy)
        h.validate_tree(proof, time, summary['audited_until_s'], summary['all_required_prefix_excluded'])
        return proof, summary

    def test_full_path_excluded(self):
        proof, summary = self.audit()
        self.assertTrue(summary['all_required_prefix_excluded'])
        self.assertEqual(proof['interval'].tolist(), [0, 1])
        self.assertEqual(summary['GEOS_evaluations'], 2)

    def test_original_endpoint_not_shortened(self):
        proof, summary = self.audit(lower=.75)
        self.assertEqual(proof['b'].tolist(), [1., .5])
        self.assertEqual(summary['audited_until_s'], .75)

    def test_unknown_not_noncontact(self):
        _, summary = self.audit(point=(1.85, 0.), spatial_error_m=.01)
        self.assertEqual(summary['status'], 'unknown_time_leaf')
        self.assertFalse(summary['all_required_prefix_excluded'])

    def test_budget_not_noncontact(self):
        _, summary = self.audit(point=(1.85, 0.), spatial_error_m=.01, maximum_evaluations=1)
        self.assertEqual(summary['status'], 'unknown_budget')
        self.assertEqual(summary['GEOS_evaluations'], 1)

    def test_contact_witness_retained(self):
        _, summary = self.audit(point=(0., 0.))
        self.assertEqual(summary['status'], 'early_contact_witness')

    def test_interior_contact_not_missed(self):
        time = np.array([0., 1.])
        states = np.array([[0., 0., 0., 0.], [40., 0., 0., 0.]])
        _, summary = h.audit_point([20., 0.], time, states, np.nan,
                                  vehicle=h.common.Vehicle(), spatial_error_m=0.)
        self.assertEqual(summary['status'], 'early_contact_witness')

    def test_empty_prefix_follows_original_endpoint(self):
        proof, summary = self.audit(lower=0.)
        self.assertEqual(len(proof['interval']), 0)
        self.assertTrue(summary['all_required_prefix_excluded'])

    def test_missing_interval_rejected(self):
        proof, _ = self.audit()
        proof = {k: v[:-1] for k, v in proof.items()}
        with self.assertRaises(RuntimeError):
            h.validate_tree(proof, [0., .5, 1.], 1., True)

    def test_changed_endpoint_rejected(self):
        proof, _ = self.audit()
        proof['b'][-1] = .999
        with self.assertRaises(RuntimeError):
            h.validate_tree(proof, [0., .5, 1.], 1., True)

    def test_unknown_cannot_certify_full_prefix(self):
        proof, _ = self.audit(point=(1.85, 0.), spatial_error_m=.01)
        with self.assertRaises(RuntimeError):
            h.validate_tree(proof, [0., .5, 1.], 1., True)

    def test_extra_node_rejected(self):
        proof, _ = self.audit()
        proof = {k: np.concatenate((v, v[-1:])) for k, v in proof.items()}
        with self.assertRaises(RuntimeError):
            h.validate_tree(proof, [0., .5, 1.], 1., True)

    def test_invalid_path_rejected(self):
        with self.assertRaises(ValueError):
            h.audit_point([0., 0.], [1., 0.], np.zeros((2, 4)), np.nan,
                          vehicle=h.common.Vehicle(), spatial_error_m=0.)

    def test_rotation_chord_bound_sample_check(self):
        vehicle = h.common.Vehicle()
        for delta in (np.array([3., -2., .8, -.3]), np.array([-1., 4., -1.2, .7])):
            start = np.array([1., 2., .4, -.2])
            for a, b in ((0., 1.), (.31, .47), (.8, .8001)):
                enclosure, bound = h.enclosure(start, delta, a, b, vehicle)
                for u in np.linspace(a, b, 31):
                    corners = h.common.body_corners((start + u * delta)[None], vehicle)[0]
                    for point in corners:
                        self.assertLessEqual(shapely.distance(shapely.Point(point), enclosure), bound + 1e-12)

    def test_positive_space_error_is_not_discarded(self):
        _, nominal = self.audit(point=(1.86, 0.))
        _, uncertain = self.audit(point=(1.86, 0.), spatial_error_m=.02)
        self.assertTrue(nominal['all_required_prefix_excluded'])
        self.assertFalse(uncertain['all_required_prefix_excluded'])


if __name__ == '__main__':
    unittest.main()
