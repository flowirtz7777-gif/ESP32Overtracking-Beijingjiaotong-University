"""Synthetic diagnostic contracts only; never open actual scientific inputs."""
import copy
import unittest
import numpy as np
import shapely
import driver as d


class DiagnosticContracts(unittest.TestCase):
    def fixture(self):
        vehicle = d.leaf.common.Vehicle()
        xy = np.array([[-vehicle.L / 2 + vehicle.l_h, 0.]])
        time, states, lower = np.array([0., 1.]), np.zeros((2, 4)), np.array([np.nan])
        arrays, rows = d.leaf.audit_with_leaf_evidence(xy, time, states, lower, **d.policy(.1, vehicle))
        self.assertEqual(len(rows), 1)
        return xy, time, states, lower, vehicle, arrays, rows[0]

    def test_all_and_only_unknown_selection(self):
        arrays = self.fixture()[5]
        self.assertEqual(d.selected_indices(arrays).tolist(), [0])
        excluded = {k: v.copy() for k, v in arrays.items()}
        excluded['prefix_undetermined'][:] = False
        excluded['prefix_excluded'][:] = True
        self.assertEqual(d.selected_indices(excluded).tolist(), [])

    def test_exact_contract_rejects_dtype(self):
        arrays = self.fixture()[5]
        changed = {**arrays, 'GEOS_evaluations': arrays['GEOS_evaluations'].astype(np.int64)}
        with self.assertRaises(RuntimeError):
            d.exact_arrays(changed, arrays)

    def test_exact_contract_rejects_value(self):
        arrays = self.fixture()[5]
        changed = {k: v.copy() for k, v in arrays.items()}
        changed['audited_until_s'][0] += 1
        with self.assertRaises(RuntimeError):
            d.exact_arrays(changed, arrays)

    def test_exact_contract_accepts(self):
        arrays = self.fixture()[5]
        d.exact_arrays(copy.deepcopy(arrays), arrays)

    def test_independent_stationary_leaf(self):
        xy, time, states, lower, vehicle, _, row = self.fixture()
        check = d.check_leaf(row, xy, time, states, lower, .1, vehicle)
        self.assertTrue(check['still_undetermined'])
        self.assertTrue(check['time_leaf'])
        self.assertFalse(check['budget_exhausted'])

    def test_independent_rejects_false_scalar(self):
        xy, time, states, lower, vehicle, _, row = self.fixture()
        row['exclusion_margin_m'] += 1e-6
        with self.assertRaises(RuntimeError):
            d.check_leaf(row, xy, time, states, lower, .1, vehicle)

    def test_independent_rejects_false_budget_reason(self):
        xy, time, states, lower, vehicle, _, row = self.fixture()
        row['evaluation_budget'] = True
        with self.assertRaises(RuntimeError):
            d.check_leaf(row, xy, time, states, lower, .1, vehicle)

    def test_independent_rejects_wrong_coordinates(self):
        xy, time, states, lower, vehicle, _, row = self.fixture()
        row['point_xy'][0] += 1e-6
        with self.assertRaises(RuntimeError):
            d.check_leaf(row, xy, time, states, lower, .1, vehicle)

    def test_analytic_body_against_rotated_geos(self):
        vehicle = d.leaf.common.Vehicle()
        for theta, phi in ((0., 0.), (.7, .3), (-2., -.1), (3.1, -.8)):
            pose = np.array([2., -3., theta, phi])
            corners = d.leaf.common.body_corners(pose[None], vehicle)[0]
            for point in (np.array([0., 0.]), corners.mean(axis=0), corners[0], np.array([-20., 15.])):
                distance = shapely.distance(shapely.Point(point), shapely.Polygon(corners))
                self.assertAlmostEqual(d.analytic_body_distance(point, pose, vehicle), distance, places=10)

    def test_fixed_policy_not_adjusted_for_unknown(self):
        vehicle = d.leaf.common.Vehicle()
        policy = d.policy(.123, vehicle)
        self.assertIs(policy['vehicle'], vehicle)
        self.assertEqual(policy['max_evaluations_per_point'], 131072)
        self.assertEqual(policy['time_resolution_s'], 1e-8)
        self.assertEqual(policy['tolerance_m'], .050000001)
        self.assertEqual(policy['spatial_error_m'], .123)


if __name__ == '__main__':
    unittest.main()
