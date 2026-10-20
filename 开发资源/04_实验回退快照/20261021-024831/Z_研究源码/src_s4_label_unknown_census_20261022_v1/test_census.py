import copy
import unittest
import numpy as np
import census as c
import census_core as core


def path(statuses):
    status = np.asarray(statuses, np.int8)
    n = len(status)
    lower, upper = np.full(n, np.nan), np.full(n, np.nan)
    lower[status != 0] = .4
    upper[status == 1] = .5
    bits = np.zeros(n, np.uint16)
    bits[status == 1] = 1
    bits[status >= 2] = 255
    return {'contact_status': status, 'contact_lower_s': lower, 'contact_upper_s': upper,
            'possible_edge_codes': bits, 'edge_certain': status == 1, 'budget_exhausted': status == 3}


class UnknownCensusContracts(unittest.TestCase):
    def fixture(self):
        a, b = path([0, 1, 1, 2, 1, 3, 0, 1]), path([0, 1, 1, 2, 2, 3, 1, 1])
        a['possible_edge_codes'][2], a['edge_certain'][2] = 255, False
        a['contact_upper_s'][5] = b['contact_upper_s'][5] = .5
        b['possible_edge_codes'][7] = 2
        return a, b, c.base.combine(a, b)

    def test_vector_scalar_classifiers_exact(self):
        a, b, combined = self.fixture()
        expected = core.independent_classify(a, b, combined)
        actual = core.classify(a, b, combined)
        for left, right in zip(actual, expected):
            np.testing.assert_array_equal(left, right)

    def test_all_and_only_scope_includes_edge_unknown(self):
        flags, scope = core.classify(*self.fixture())
        self.assertEqual(np.flatnonzero(scope).tolist(), [2, 3, 4, 5, 6, 7])
        self.assertTrue(flags[2] & 2)
        self.assertFalse(flags[2] & 1)

    def test_budget_with_witness_not_no_contact_witness(self):
        flags, _ = core.classify(*self.fixture())
        self.assertTrue(flags[5] & 1)
        self.assertTrue(flags[5] & 32)
        self.assertTrue(flags[5] & 64)
        self.assertFalse(flags[5] & 4)
        self.assertFalse(flags[5] & 8)
        self.assertFalse(flags[5] & 16)

    def test_model_conflict_retained(self):
        flags, scope = core.classify(*self.fixture())
        self.assertTrue(flags[6] & 128)
        self.assertTrue(scope[6])

    def test_edge_conflict_retained(self):
        flags, scope = core.classify(*self.fixture())
        self.assertTrue(flags[7] & 512)
        self.assertTrue(scope[7])

    def test_corner_code_is_one_code_not_two_ambiguous_faces(self):
        a, b = path([1]), path([1])
        a['possible_edge_codes'][0] = b['possible_edge_codes'][0] = 16
        flags, scope = core.classify(a, b, c.base.combine(a, b))
        self.assertEqual(flags.tolist(), [0])
        self.assertFalse(scope.any())

    def test_no_mutation_of_labels_or_times(self):
        values = self.fixture()
        before = copy.deepcopy(values)
        core.classify(*values)
        core.independent_classify(*values)
        for actual, expected in zip(values, before):
            for name in expected:
                np.testing.assert_array_equal(actual[name], expected[name])

    def test_nonexclusive_reasons_not_summed(self):
        a, b, combined = self.fixture()
        flags, scope = core.classify(a, b, combined)
        summary = core.summarize(a, b, combined, flags, scope)
        self.assertEqual(sum(summary['exclusive_reason_combinations'].values()), summary['census_points'])
        self.assertGreater(sum(summary['reason_counts_nonexclusive'].values()), summary['census_points'])

    def test_original_order_projection(self):
        a, b, combined = self.fixture()
        flags, scope = core.classify(a, b, combined)
        xy = np.column_stack((np.arange(8.), np.arange(8.) * 2))
        index = np.array([7, 1, 3, 0, 2], np.int32)
        result = core.projection_payload(index, xy, xy[index], flags, scope)
        self.assertEqual(result['original_index'].tolist(), [0, 2, 4])
        self.assertEqual(result['union_index'].tolist(), [7, 3, 2])

    def test_bad_projection_rejected(self):
        xy = np.array([[0., 0.], [1., 2.]])
        with self.assertRaises(ValueError):
            core.projection_payload(np.array([0, 1]), xy, xy[::-1], np.array([1, 1], np.uint16), np.ones(2, bool))

    def test_mask_padding_is_zero(self):
        a, b = path([0] * 9), path([0] * 9)
        a['contact_status'][8] = 2
        a['contact_lower_s'][8] = .4
        a['possible_edge_codes'][8] = 255
        combined = c.base.combine(a, b)
        flags, scope = core.classify(a, b, combined)
        payload = core.group_payload(np.zeros((9, 2)), {'oldpath': a, 'independent': b}, combined, flags, scope)
        self.assertEqual(int(payload['all_scope_packbits'][-1]), 1)

    def test_empty_population(self):
        a, b = path([]), path([])
        flags, scope = core.classify(a, b, c.base.combine(a, b))
        self.assertEqual(len(flags), 0)
        self.assertFalse(scope.any())

    def test_invalid_status_rejected(self):
        a, b, combined = self.fixture()
        a['contact_status'][0] = 9
        with self.assertRaises(ValueError):
            core.classify(a, b, combined)

    def test_invalid_contact_interval_rejected(self):
        a, b, combined = self.fixture()
        a['contact_lower_s'][1] = .6
        with self.assertRaises(ValueError):
            core.classify(a, b, combined)

    def test_point_file_multiplicity_not_new_geometry_samples(self):
        a, b, combined = self.fixture()
        flags, scope = core.classify(a, b, combined)
        summary = core.summarize(a, b, combined, flags, scope)
        accounting = c.totals([{'summary': summary}, {'summary': summary}], {'one': summary})
        self.assertEqual(accounting['complete_census_point_file_records'], 2 * summary['census_points'])
        self.assertEqual(accounting['complete_census_group_unique_points'], summary['census_points'])


if __name__ == '__main__':
    unittest.main()
