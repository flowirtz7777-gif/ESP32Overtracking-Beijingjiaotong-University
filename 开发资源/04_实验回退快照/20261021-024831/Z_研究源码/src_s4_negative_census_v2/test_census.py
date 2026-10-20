import unittest
import numpy as np
import shapely
from run_census import cell_keys, extend_targets, enumerate_negative
from geometry import generate_target_pool


class CensusTests(unittest.TestCase):
    def test_exact_raster_keys_with_negative_coordinates(self):
        xy = np.array([[-.025, .025], [0., 0.], [.025, -.025], [-.0125, 0.]])
        keys = cell_keys(xy, .0125)
        self.assertEqual(len(np.unique(keys)), 4)
        np.testing.assert_array_equal(keys, cell_keys(xy.copy(), .0125))
        with self.assertRaises(AssertionError):
            cell_keys(np.array([[.003, 0.]]), .0125)

    def test_enumeration_matches_existing_geometry_population(self):
        body = shapely.box(-2, -1, 2, 1)
        right = shapely.LineString([[-2, -1], [2, -1]])
        _, _, meta = generate_target_pool(body, right, maximum=30, spacing=.025)
        census = enumerate_negative(body, .025, .05, .5, 32)
        self.assertEqual(len(census), meta['capacity'][2])
        self.assertFalse(shapely.dwithin(shapely.points(census), body, .05+1e-9).any())
        self.assertTrue(shapely.dwithin(shapely.points(census), body, .5+1e-9).all())

    def test_extend_keeps_every_original_coordinate_label_and_order(self):
        old = {'xy': np.array([[0., 0.], [.025, 0.], [.05, 0.]]), 'group': np.array([0, 1, 2], np.int8),
               'contact_time': np.array([2., 3., np.nan]), 'contact_index': np.array([400, 600, -1], np.int32),
               'edge': np.array([2, 2, 0], np.int8), 'front_ignored': np.array([False, False, False]),
               'main_ids': np.array([0, 1, 2], np.int32), 'previous_ids': np.array([0, 1, 2], np.int32)}
        census = np.array([[.05, 0.], [.0625, 0.], [.075, 0.]])
        targets = extend_targets(old, census, .0125)
        for key in ('xy', 'group', 'contact_time', 'contact_index', 'edge', 'front_ignored'):
            np.testing.assert_array_equal(targets[key][:3], old[key])
        self.assertEqual(len(targets['new_ids']), 2)
        self.assertTrue(np.isnan(targets['contact_time'][targets['new_ids']]).all())
        with self.assertRaises(AssertionError):
            extend_targets(old, census[:0], .0125)

    def test_duplicate_census_is_rejected(self):
        old = {'xy': np.array([[0., 0.]]), 'group': np.array([2]), 'contact_time': np.array([np.nan]),
               'contact_index': np.array([-1], np.int32), 'edge': np.array([0], np.int8), 'front_ignored': np.array([False]),
               'main_ids': np.array([0]), 'previous_ids': np.array([0])}
        with self.assertRaises(AssertionError):
            extend_targets(old, np.array([[0., 0.], [0., 0.]]), .0125)


if __name__ == '__main__':
    unittest.main()
