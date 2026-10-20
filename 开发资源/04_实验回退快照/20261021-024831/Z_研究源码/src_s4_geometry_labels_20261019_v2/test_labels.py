import math
import unittest
import numpy as np
import run_labels as a

class LabelTests(unittest.TestCase):
    def labels(self):
        return {"contact_time": np.array([1., 2., np.nan]),
                "edge": np.array([1, 2, 0], dtype=np.int8),
                "front_ignored": np.array([True, False, False])}

    def test_exact(self):
        x = self.labels()
        result, masks = a.compare_labels(x, x)
        self.assertTrue(result["label_step_gate_passed"])
        self.assertTrue(all(not x.any() for x in masks.values()))

    def test_contact_existence_change(self):
        x, y = self.labels(), self.labels()
        y["contact_time"][2] = 3.
        result, _ = a.compare_labels(x, y)
        self.assertFalse(result["label_step_gate_passed"])
        self.assertEqual(result["contact_existence_changed"], 1)

    def test_right_to_corner_is_failure_not_hidden(self):
        x, y = self.labels(), self.labels()
        y["edge"][1] = 6
        result, _ = a.compare_labels(x, y)
        self.assertFalse(result["label_step_gate_passed"])
        self.assertEqual(result["RIGHT_membership_changed"], 1)

    def test_front_exclusion_change(self):
        x, y = self.labels(), self.labels()
        y["front_ignored"][0] = False
        result, _ = a.compare_labels(x, y)
        self.assertFalse(result["label_step_gate_passed"])

    def test_time_gate(self):
        x, y = self.labels(), self.labels()
        y["contact_time"][0] += .01
        result, _ = a.compare_labels(x, y)
        self.assertFalse(result["label_step_gate_passed"])

    def test_empty_null_not_zero(self):
        x = {"contact_time": np.array([np.nan]), "edge": np.array([0]), "front_ignored": np.array([False])}
        result, _ = a.compare_labels(x, x)
        self.assertIsNone(result["max_common_contact_time_change_s"])
        self.assertTrue(result["label_step_gate_passed"])

    def test_nested_target_ids(self):
        groups = np.repeat(np.arange(3, dtype=np.int8), [46667, 46667, 46666])
        ids = a.dep.geometry.subset_indices(groups, 70000)
        self.assertEqual(len(ids), 70000)
        self.assertEqual(len(np.unique(ids)), 70000)

    def test_fresh_scandir_size_matches_stat(self):
        root = a.SOURCE
        expected = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        self.assertEqual(a.scan_size(root), expected)

    def test_union_membership_is_recomputed(self):
        import shapely
        xy = np.array([[.5, .5], [2., 2.]])
        body = shapely.box(0., 0., 1., 1.)
        self.assertTrue(a.union_membership_exact(xy, body, np.array([1., np.nan])))
        self.assertFalse(a.union_membership_exact(xy, body, np.array([np.nan, np.nan])))

    def test_recovery_dependency_not_interrupted_run(self):
        self.assertEqual(a.DEPENDENCY.name, 'resume_20261019_geometry_delay_recovery_v1')


    def test_capacity_rule_uses_geometry_not_labels(self):
        attempts = []
        def generator(body, right, count, spacing):
            attempts.append(spacing)
            if spacing == .02:
                raise ValueError("Insufficient unique near-field target pool: group=0 capacity=10 needed=46667")
            return np.zeros((1, 2)), np.array([0]), {"spacing_m": spacing}
        _, _, sampling = a.capacity_admitted_pool(None, None, generator)
        self.assertEqual(attempts, [.02, .01])
        self.assertTrue(sampling["selection_uses_geometry_capacity_only"])
        self.assertEqual(len(sampling["previous_capacity_rejections"]), 1)

    def test_capacity_rule_never_catches_unrelated_failure(self):
        def generator(*args):
            raise ValueError("Unrelated geometry error")
        with self.assertRaisesRegex(ValueError, "Unrelated"):
            a.capacity_admitted_pool(None, None, generator)

    def test_capacity_rule_does_not_refine_after_success(self):
        attempts = []
        def generator(body, right, count, spacing):
            attempts.append(spacing)
            return np.zeros((1, 2)), np.array([0]), {"spacing_m": spacing}
        a.capacity_admitted_pool(None, None, generator)
        self.assertEqual(attempts, [.02])

if __name__ == "__main__":
    unittest.main()
