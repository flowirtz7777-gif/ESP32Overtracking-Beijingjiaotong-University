import copy
import unittest
import numpy as np
import budget as b
import budget_core as core


class BudgetCandidateTests(unittest.TestCase):
    def fixture(self):
        xy = np.array([[0., 0.]])
        time = np.array([0., 1.])
        state = np.array([[-20., 0., 0., 0.], [20., 0., 0., 0.]])
        return xy, time, state, .001, b.base.common.Vehicle()

    def test_all_and_only_budget_selection(self):
        path = {'budget_exhausted': np.array([False, True, False, True])}
        self.assertEqual(core.selected_indices(path, np.array([0, 32, 2, 32], np.uint16), 32).tolist(), [1, 3])

    def test_missing_census_budget_rejected(self):
        with self.assertRaises(ValueError):
            core.selected_indices({'budget_exhausted': np.array([True])}, np.array([0], np.uint16), 32)

    def test_extra_census_budget_rejected(self):
        with self.assertRaises(ValueError):
            core.selected_indices({'budget_exhausted': np.array([False])}, np.array([64], np.uint16), 64)

    def test_budget_dtype_rejected(self):
        with self.assertRaises(ValueError):
            core.selected_indices({'budget_exhausted': np.array([1], np.int8)}, np.array([32], np.uint16), 32)

    def test_fixed_policy_matches_original(self):
        self.assertEqual(core.SEED_BUDGET, b.base.EVALUATIONS)
        self.assertEqual(core.TIME_RESOLUTION, b.base.TIME_RESOLUTION)
        self.assertEqual(core.TOLERANCE, b.base.TOLERANCE)
        self.assertEqual(core.REFINE_BUDGET, 131072)

    def test_original_kernel_code_object_unchanged(self):
        code = b.base.label_population.__code__
        core.compute(b.base.label_population, *self.fixture(), core.SEED_BUDGET)
        self.assertIs(b.base.label_population.__code__, code)

    def test_repeated_original_seed_exact(self):
        args = self.fixture()
        first = core.compute(b.base.label_population, *args, core.SEED_BUDGET)
        second = core.compute(b.base.label_population, *args, core.SEED_BUDGET)
        self.assertEqual(b.base.array_meta(first), b.base.array_meta(second))

    def test_budget_cleared_is_not_edge_certification(self):
        args = self.fixture()
        args[0][0, 1] = 1.049
        seed = core.compute(b.base.label_population, *args, 3)
        refined = core.compute(b.base.label_population, *args, core.REFINE_BUDGET)
        self.assertTrue(seed['budget_exhausted'][0])
        self.assertFalse(refined['budget_exhausted'][0])
        self.assertFalse(refined['edge_certain'][0])
        self.assertEqual(int(refined['possible_edge_codes'][0]), 255)
        self.assertTrue(np.isfinite(refined['contact_upper_s'][0]))

    def test_candidates_do_not_mutate_original_arrays(self):
        args = self.fixture()
        seed = core.compute(b.base.label_population, *args, 3)
        snapshot = copy.deepcopy(seed)
        refined = core.compute(b.base.label_population, *args, core.REFINE_BUDGET)
        core.summarize(seed, refined)
        self.assertEqual(b.base.array_meta(seed), b.base.array_meta(snapshot))

    def test_equal_nans_are_not_changes(self):
        value = {'a': np.array([np.nan, 1.])}
        self.assertFalse(core.changed_points(value, copy.deepcopy(value)).any())

    def test_unequal_nan_is_change(self):
        self.assertEqual(core.changed_points({'a': np.array([np.nan])}, {'a': np.array([1.])}).tolist(), [True])

    def test_schema_change_rejected(self):
        with self.assertRaises(ValueError):
            core.changed_points({'a': np.zeros(1)}, {'b': np.zeros(1)})

    def test_dtype_change_rejected(self):
        with self.assertRaises(ValueError):
            core.changed_points({'a': np.zeros(1, np.int32)}, {'a': np.zeros(1, np.int64)})

    def test_shape_change_rejected(self):
        with self.assertRaises(ValueError):
            core.changed_points({'a': np.zeros(1)}, {'a': np.zeros(2)})

    def test_changed_packbits_padding(self):
        changed = core.changed_points({'a': np.zeros(9)}, {'a': np.array([0.] * 8 + [1.])})
        self.assertEqual(np.packbits(changed, bitorder='little').tolist(), [0, 1])

    def test_seed_and_candidate_have_full_same_schema(self):
        args = self.fixture()
        seed = core.compute(b.base.label_population, *args, core.SEED_BUDGET)
        refined = core.compute(b.base.label_population, *args, core.REFINE_BUDGET)
        self.assertEqual(set(seed), set(refined))
        self.assertNotIn('witness_pose', refined)
        for name in seed:
            self.assertEqual(seed[name].dtype, refined[name].dtype)
            self.assertEqual(seed[name].shape, refined[name].shape)


if __name__ == '__main__':
    unittest.main()
