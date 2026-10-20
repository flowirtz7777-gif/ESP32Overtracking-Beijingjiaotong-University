import unittest
import explain_composition as e


def row(n0, n1, r0, r1):
    return {'right_contacts': n0 + n1, 'right_pct': (n0*r0 + n1*r1)/(n0+n1),
            'stratum_right_rows': [{'group': 0, 'right_contacts': n0, 'right_insufficient_pct': r0},
                                   {'group': 1, 'right_contacts': n1, 'right_insufficient_pct': r1}]}


class ExplanationTests(unittest.TestCase):
    def test_phase_is_not_automatically_identical_composition(self):
        self.assertFalse(e.same_composition(row(3, 7, 0, 0), row(30, 71, 0, 0)))
        self.assertTrue(e.same_composition(row(3, 7, 0, 0), row(30, 70, 0, 0)))

    def test_pure_composition_difference(self):
        result = e.decompose(row(5, 5, 2, 0), row(1, 9, 2, 0))
        self.assertAlmostEqual(result['raw_insufficient_difference_pp'], .8)
        self.assertAlmostEqual(result['within_layer_component_using_subset_weights_pp'], 0.)
        self.assertAlmostEqual(result['composition_component_using_reference_layer_rates_pp'], .8)
        self.assertAlmostEqual(result['fixed_equal_layer_standardized_difference_pp'], 0.)

    def test_both_components(self):
        result = e.decompose(row(5, 5, 3, 1), row(1, 9, 2, 0))
        self.assertAlmostEqual(result['within_layer_component_using_subset_weights_pp'], 1.)
        self.assertAlmostEqual(result['composition_component_using_reference_layer_rates_pp'], .8)
        self.assertAlmostEqual(result['fixed_equal_layer_standardized_difference_pp'], 1.)

    def test_missing_stratum_rejected(self):
        invalid = row(1, 9, 2, 0)
        invalid['stratum_right_rows'].pop()
        with self.assertRaises(AssertionError):
            e.layers(invalid)


if __name__ == '__main__':
    unittest.main()
