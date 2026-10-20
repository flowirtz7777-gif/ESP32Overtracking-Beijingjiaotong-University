import io
import unittest
import numpy as np
import analyze_matched as m


CELLS = ['a', 'b', 'c', 'd']
PAIRS = [['confirmation_at_m20', 0, 1], ['confirmation_at_m50', 2, 3],
         ['margin_at_c0', 0, 2], ['margin_at_c100', 1, 3]]


def fixture():
    target = {'reference_ids': np.array([40, 10, 30, 20], np.int32),
              'contact_time': np.array([5., 5., 5., 5.]), 'edge': np.full(4, 2, np.int8),
              'front_ignored': np.zeros(4, bool)}
    point = {tag+'_valid': np.array([3., 3.2, 3.4, 3.6]) for tag in CELLS}
    return target, point


class MatchedTests(unittest.TestCase):
    def calculate(self, target=None, point=None, positions=None):
        t, p = fixture()
        return m.matched(t if target is None else target, p if point is None else point,
                         np.arange(4, dtype=np.int32) if positions is None else positions,
                         10., cells=CELLS, pairs=PAIRS)

    def test_five_complete_contrasts(self):
        rows, arrays = self.calculate()
        self.assertEqual(len(rows), 5)
        self.assertEqual(len(arrays), 19)

    def test_sorted_full_identity(self):
        _, arrays = self.calculate()
        np.testing.assert_array_equal(arrays['confirmation_at_m20__ids'], [10, 20, 30, 40])

    def test_pair_direction(self):
        target, point = fixture()
        point['b_valid'] += .1
        rows, arrays = self.calculate(target, point)
        np.testing.assert_allclose(arrays['confirmation_at_m20__delta_s'], -.1)
        self.assertEqual(rows[0]['paired_delta_after_minus_before']['decreased_count'], 4)

    def test_pair_intersection_not_separate_survivors(self):
        target, point = fixture()
        point['a_valid'][0] = np.nan
        point['b_valid'][1] = np.nan
        rows, _ = self.calculate(target, point)
        self.assertEqual(rows[0]['matched_points'], 2)
        self.assertEqual(rows[0]['before_only_detected'], 1)
        self.assertEqual(rows[0]['after_only_detected'], 1)

    def test_interaction_requires_all_four(self):
        target, point = fixture()
        point['a_valid'][0] = np.nan
        point['d_valid'][1] = np.nan
        rows, arrays = self.calculate(target, point)
        self.assertEqual(rows[-1]['matched_points'], 2)
        self.assertEqual(arrays['interaction__four_leads_s'].shape, (2, 4))

    def test_interaction_sign(self):
        target, point = fixture()
        point['b_valid'] += .1
        point['d_valid'] += .3
        _, arrays = self.calculate(target, point)
        np.testing.assert_allclose(arrays['interaction__delta_s'], -.2)

    def test_empty_keeps_null_and_shape(self):
        rows, arrays = self.calculate(positions=np.array([], np.int32))
        self.assertIsNone(rows[0]['paired_delta_after_minus_before']['median_s'])
        self.assertIsNone(rows[-1]['paired_difference_of_differences']['p10_s'])
        self.assertEqual(arrays['interaction__four_leads_s'].shape, (0, 4))

    def test_label_scope(self):
        target, point = fixture()
        target['front_ignored'][0] = True
        target['edge'][1] = 1
        target['contact_time'][2] = np.nan
        rows, _ = self.calculate(target, point)
        self.assertEqual(rows[0]['eligible_right_points'], 1)

    def test_score_edges(self):
        target, _ = fixture()
        target['contact_time'] = np.array([2., 10., 1.99, 10.01])
        ids = m.eligible_positions(target, np.arange(4, dtype=np.int32), 10.)
        np.testing.assert_array_equal(target['reference_ids'][ids], [10, 40])

    def test_five_percent_exact_boundary(self):
        self.assertTrue(m.exact_budget(5, 100, 20))
        self.assertFalse(m.exact_budget(5001500, 100000000, 20))

    def test_half_percent_exact_boundary(self):
        self.assertTrue(m.exact_budget(5, 1000, 200))
        self.assertFalse(m.exact_budget(6, 1000, 200))

    def test_no_denominator_not_pass(self):
        self.assertIsNone(m.exact_budget(0, 0, 20))

    def test_invalid_counts_rejected(self):
        for values in [(2, 1, 20), (-1, 3, 20), (1., 3, 20)]:
            with self.assertRaises(AssertionError):
                m.exact_budget(*values)

    def test_quantiles_independent(self):
        values = np.array([-4., -1., 0., 2., 9.])
        for q in [.1, .5]:
            self.assertAlmostEqual(m.scalar_quantile(values, q), float(np.quantile(values, q)))

    def test_pair_quantile_not_quantile_difference(self):
        left, right = np.array([0., 10., 11.]), np.array([9., 9., 20.])
        self.assertNotEqual(m.distribution(right-left)['median_s'],
                            m.distribution(right)['median_s']-m.distribution(left)['median_s'])

    def test_complete_npz_dtype_shape_sha_roundtrip(self):
        _, arrays = self.calculate()
        blob = m.q.f.coarse.npz_bytes(arrays)
        loaded = m.q.c.readback(blob, m.q.c.descriptors(arrays))
        for key in arrays:
            np.testing.assert_array_equal(arrays[key], loaded[key])
            self.assertEqual(arrays[key].dtype, loaded[key].dtype)

    def test_empty_npz_roundtrip(self):
        _, arrays = self.calculate(positions=np.array([], np.int32))
        loaded = m.q.c.readback(m.q.f.coarse.npz_bytes(arrays), m.q.c.descriptors(arrays))
        self.assertEqual(loaded['interaction__four_leads_s'].shape, (0, 4))

    def test_nonfinite_values_rejected(self):
        with self.assertRaises(AssertionError):
            m.distribution([float('nan')])


if __name__ == '__main__':
    unittest.main()
