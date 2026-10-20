import datetime as dt
import unittest
from unittest.mock import Mock, patch
import numpy as np
import prefix as p


def seed():
    return {'prefix_excluded': np.array([True, False]), 'early_contact_witness': np.array([False, False]),
            'prefix_undetermined': np.array([False, True]), 'budget_exhausted': np.array([False, True]),
            'GEOS_evaluations': np.array([1, 8192], dtype=np.int32),
            'candidate_interval_pairs': np.array([1, 2], dtype=np.int32), 'audited_until_s': np.array([.1, .2])}


class PrefixTests(unittest.TestCase):
    def test_complete_partition_original_order(self):
        groups = {str(i): [str(i)] for i in range(39)}
        reused = {str(i): {} for i in range(12)}
        old, new = p.partition(groups, reused)
        self.assertEqual(old, list(groups)[:12])
        self.assertEqual(new, list(groups)[12:])

    def test_incomplete_population_rejected(self):
        with self.assertRaises(RuntimeError):
            p.partition({str(i): [] for i in range(38)}, {str(i): {} for i in range(12)})

    def test_missing_accepted_group_rejected(self):
        with self.assertRaises(RuntimeError):
            p.partition({str(i): [] for i in range(39)}, {str(i): {} for i in range(11)})

    def test_foreign_accepted_group_rejected(self):
        with self.assertRaises(RuntimeError):
            p.partition({str(i): [] for i in range(39)}, {str(i + 50): {} for i in range(12)})

    def test_exact_same_computation_code_object(self):
        f = p.bound_audit()
        self.assertIs(f.__code__, p.follow.audit_group.__code__)
        self.assertEqual(f.__globals__['RUN'], p.RUN)
        self.assertEqual(f.__globals__['old'].OLD, p.POPULATION)

    def test_frozen_original_namespace_not_mutated(self):
        original_run, original_population = p.follow.RUN, p.follow.old.OLD
        p.bound_audit()
        self.assertEqual(p.follow.RUN, original_run)
        self.assertEqual(p.follow.old.OLD, original_population)

    def test_no_excluded_point_recomputation_selection(self):
        original = seed()
        with self.assertRaises(RuntimeError):
            p.follow.merge_refinement(original, {k: v[:1] for k, v in original.items()}, np.array([0]))

    def test_no_undetermined_point_can_be_omitted(self):
        original = seed()
        with self.assertRaises(RuntimeError):
            p.follow.merge_refinement(original, {k: v[:0] for k, v in original.items()}, np.array([], dtype=np.int64))

    def test_refinement_preserves_every_unselected_array(self):
        original = seed()
        refined = {k: v[1:].copy() for k, v in original.items()}
        final = p.follow.merge_refinement(original, refined, np.array([1]))
        for name in original:
            np.testing.assert_array_equal(final[name][:1], original[name][:1])

    def test_unknown_is_not_noncontact_or_pass(self):
        original = seed()
        final = p.follow.merge_refinement(original, {k: v[1:] for k, v in original.items()}, np.array([1]))
        self.assertFalse(p.follow.old.summarize_prefix(final)['strict_prefix_gate_passed'])

    def test_early_witness_survives_refinement(self):
        original = seed()
        refined = {k: v[1:].copy() for k, v in original.items()}
        refined['early_contact_witness'][:] = True
        refined['prefix_undetermined'][:] = False
        refined['budget_exhausted'][:] = False
        final = p.follow.merge_refinement(original, refined, np.array([1]))
        self.assertEqual(p.follow.old.summarize_prefix(final)['early_contact_witness'], 1)

    def test_original_endpoints_cannot_be_shortened(self):
        with self.assertRaises(RuntimeError):
            p.follow.validate_prefix(seed(), np.array([.1, .15]))

    def test_refinement_budget_unchanged(self):
        self.assertEqual(p.follow.REFINE_BUDGET, 131072)

    def test_resource_and_deadline_binding(self):
        p.configure()
        self.assertEqual(p.r.RUN, p.RUN)
        self.assertEqual(p.r.AUTH, p.AUTH)
        self.assertEqual(p.r.CAP, 32 * 1024**3)
        self.assertEqual(p.r.RUN_CAP, 512 * 1024**2)
        self.assertEqual(p.r.RESERVE, 3 * 1024**3)
        self.assertEqual(p.r.DEADLINE, dt.datetime(2026, 10, 21, 16, tzinfo=dt.timezone.utc))

    def test_execution_restores_binding_after_failure(self):
        with patch.object(p.parent, 'execution', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):
                p.execution()
        self.assertEqual(p.r.RUN, p.RUN)
        self.assertEqual(p.r.AUTH, p.AUTH)

    def test_running_foreign_runner_rejected(self):
        folder = Mock()
        path = Mock()
        folder.glob.return_value = [path]
        with patch.object(p.parent, 'execution', return_value=(object(), {})), \
             patch.object(p, 'POPULATION', folder), \
             patch.object(p.r, 'read', return_value={'status': 'running', 'pid': -99}):
            with self.assertRaises(RuntimeError):
                p.execution()

    def test_refinement_wrong_dtype_rejected(self):
        original = seed()
        refined = {k: v[1:].copy() for k, v in original.items()}
        refined['GEOS_evaluations'] = refined['GEOS_evaluations'].astype(np.float64)
        with self.assertRaises(RuntimeError):
            p.follow.merge_refinement(original, refined, np.array([1]))

    def test_refinement_duplicate_indices_rejected(self):
        original = seed()
        with self.assertRaises(RuntimeError):
            p.follow.merge_refinement(original, original, np.array([1, 1]))

    def test_accepted_proof_identity_is_fixed(self):
        self.assertEqual(p.ACCEPTED_CP, '44396f02a4f2b1a6015b41d8697d4c02849daa6e18a9ba42a223bd17e6df81bb')
        self.assertEqual(p.ACCEPTED_SHA, 'aa25b6c22232e37173af5e051ebd1ab1a871225410ed6fa8d4a07eccfbf68f99')


if __name__ == '__main__':
    unittest.main()
