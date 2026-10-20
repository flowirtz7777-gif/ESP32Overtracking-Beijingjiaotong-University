import unittest
import numpy as np
from audit_sampling import geometric_order, systematic_ids


class GeometrySamplingTests(unittest.TestCase):
    def test_small_morton_order(self):
        xy = np.array([[0., 0.], [.0125, 0.], [0., .0125], [.0125, .0125]])
        np.testing.assert_array_equal(geometric_order(xy), np.arange(4))

    def test_translation_and_input_order(self):
        xy = np.array([[-.025, -.025], [-.0125, -.025], [-.025, -.0125], [-.0125, -.0125]])
        order = np.array([3, 1, 0, 2])
        np.testing.assert_array_equal(order[geometric_order(xy[order])], np.arange(4))
        np.testing.assert_array_equal(geometric_order(xy+.1), np.arange(4))

    def test_sample_counts_uniqueness_and_offsets(self):
        order = np.arange(1000)[::-1]
        for n in (20, 100, 1000):
            for offset in (.25, .5, .75):
                ids = systematic_ids(order, n, offset)
                self.assertEqual(len(np.unique(ids)), n)
                self.assertTrue(np.isin(ids, order).all())
                np.testing.assert_array_equal(ids, systematic_ids(order, n, offset))

    def test_invalid_design_and_duplicate_raster(self):
        with self.assertRaises(ValueError):
            systematic_ids(np.arange(10), 11, .5)
        with self.assertRaises(ValueError):
            systematic_ids(np.arange(10), 5, 0.)
        with self.assertRaises(AssertionError):
            geometric_order(np.array([[0., 0.], [0., 0.]]))


if __name__ == '__main__':
    unittest.main()
