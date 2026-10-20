import unittest
import numpy as np
from completion import merge_refinement, validate_prefix, old, REFINE_BUDGET


def example():
    return {'prefix_excluded': np.array([True, False]), 'early_contact_witness': np.array([False, False]),
        'prefix_undetermined': np.array([False, True]), 'budget_exhausted': np.array([False, True]),
        'GEOS_evaluations': np.array([1, 8192], dtype=np.int32),
        'candidate_interval_pairs': np.array([1, 2], dtype=np.int32), 'audited_until_s': np.array([.1, .2])}


class CompletionTests(unittest.TestCase):
    def test_fixed_refinement_budget_not_acceptance_relaxation(self):
        self.assertEqual(REFINE_BUDGET, 131072)

    def test_no_unresolved_point_may_be_dropped(self):
        seed = example()
        with self.assertRaises(RuntimeError):
            merge_refinement(seed, {k: v[:0] for k, v in seed.items()}, np.array([], dtype=np.int64))

    def test_previously_excluded_cannot_be_selected(self):
        seed = example()
        with self.assertRaises(RuntimeError):
            merge_refinement(seed, {k: v[:1] for k, v in seed.items()}, np.array([0]))

    def test_unchanged_excluded_point_reused_exactly(self):
        seed = example()
        refined = {k: v[1:].copy() for k, v in seed.items()}
        final = merge_refinement(seed, refined, np.array([1]))
        for k in seed:
            np.testing.assert_array_equal(final[k][:1], seed[k][:1])

    def test_unknown_stays_unknown_not_negative(self):
        seed = example()
        final = merge_refinement(seed, {k: v[1:] for k, v in seed.items()}, np.array([1]))
        self.assertFalse(old.summarize_prefix(final)['strict_prefix_gate_passed'])

    def test_early_witness_not_hidden(self):
        seed = example()
        refined = {k: v[1:].copy() for k, v in seed.items()}
        refined['early_contact_witness'][:] = True
        refined['prefix_undetermined'][:] = False
        refined['budget_exhausted'][:] = False
        self.assertEqual(old.summarize_prefix(merge_refinement(seed, refined, np.array([1])))['early_contact_witness'], 1)

    def test_endpoints_cannot_be_shortened(self):
        with self.assertRaises(RuntimeError):
            validate_prefix(example(), np.array([.1, .15]))

    def test_new_success_resolves_only_unresolved(self):
        seed = example()
        refined = {k: v[1:].copy() for k, v in seed.items()}
        refined['prefix_excluded'][:] = True
        refined['prefix_undetermined'][:] = False
        refined['budget_exhausted'][:] = False
        self.assertTrue(old.summarize_prefix(merge_refinement(seed, refined, np.array([1])))['strict_prefix_gate_passed'])


if __name__ == '__main__':
    unittest.main()
