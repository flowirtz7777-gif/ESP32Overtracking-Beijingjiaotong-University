import unittest
import numpy as np
from diagnose_sampling import shared_indices, nested_fp_decomposition, metrics


class SamplingTests(unittest.TestCase):
    def test_shared_unique_stratified_reproducible(self):
        group = np.repeat(np.arange(3), 20)
        a = shared_indices(group, 31, 17)
        np.testing.assert_array_equal(a, shared_indices(group, 31, 17))
        self.assertEqual(len(np.unique(a)), 31)
        self.assertEqual(np.bincount(group[a]).tolist(), [11, 10, 10])
        self.assertFalse(np.array_equal(a, shared_indices(group, 31, 18)))

    def test_nested_sample_prefix(self):
        group = np.repeat(np.arange(3), 20)
        a, b = shared_indices(group, 12, 1), shared_indices(group, 30, 1)
        for layer in range(3):
            np.testing.assert_array_equal(a[group[a] == layer], b[group[b] == layer][:4])

    def test_no_replacement_overflow(self):
        with self.assertRaises(ValueError):
            shared_indices(np.array([0, 1, 2]), 4, 1)

    def test_fp_decomposition(self):
        def row(n, f):
            return dict(negative_count=n, negative_fp=f, negative_fp_pct=100*f/n)
        r = nested_fp_decomposition(row(100, 10), row(200, 30), row(300, 40))
        self.assertAlmostEqual(r['full_minus_previous_negative_fp_pp'], 10/3)
        with self.assertRaises(AssertionError):
            nested_fp_decomposition(row(100, 10), row(200, 30), row(300, 41))

    def test_scoring_boundaries_and_missing(self):
        t = dict(contact_time=np.array([3., 3., np.nan, np.nan, 1.]), front_ignored=np.zeros(5, bool), edge=np.array([2, 2, 0, 0, 2]))
        p = {'v_first': np.array([2., 2., 1., 2., 2.]), 'v_valid': np.array([2., np.nan, np.nan, np.nan, np.nan]),
             'v_ref_FP': np.array([0, 0, 0, 1, 0]), 'v_ref_negative_opportunities': np.ones(5, dtype=int)}
        r = metrics(t, p, 'v', np.arange(5), 4.)
        self.assertEqual(r['right_contacts'], 2)
        self.assertEqual(r['right_miss'], 1)
        self.assertEqual(r['right_pct'], 50)
        self.assertEqual(r['negative_fp_pct'], 50)


if __name__ == '__main__':
    unittest.main()
