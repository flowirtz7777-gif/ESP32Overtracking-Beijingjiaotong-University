"""Synthetic full-scope merge contracts; no real input arrays are opened."""
import inspect
import unittest
from unittest.mock import patch
import numpy as np
import motion_merge_driver as d

c = d.core


def fixture():
    status = np.array([1, 1, 2, 0, 1, 2, 1, 1, 0], np.int8)
    a = {"contact_status": status, "contact_lower_s": np.array([0., 0., 0., np.nan, .2, .3, .1, .1, np.nan]),
         "contact_upper_s": np.array([.8, 0., np.nan, np.nan, .5, np.nan, .4, .3, np.nan]),
         "nominal_instantaneous_edge": np.array([5, 7, 0, 0, 5, 0, 2, 1, 0], np.int8),
         "edge_certain": np.array([0, 0, 0, 0, 1, 0, 0, 1, 0], bool),
         "possible_edge_codes": np.array([255, 255, 255, 0, 16, 255, 255, 1, 0], np.uint16),
         "budget_exhausted": np.zeros(9, bool), "interval_evaluations": np.arange(9, dtype=np.int32),
         "candidate_interval_seen": status != 0,
         "initial_tolerance_contact_certain": np.zeros(9, bool),
         "initial_tolerance_contact_possible": np.array([0, 0, 1, 0, 0, 0, 0, 0, 0], bool),
         "initial_nominal_body_overlap": np.zeros(9, bool)}
    scope = np.array([1, 1, 1, 1, 1, 1, 1, 0, 0], bool)
    index = np.flatnonzero(scope)
    b = {k: v[index].copy() for k, v in a.items()}
    proof = np.array([1, 0, 0, 0, 0, 0, 0], bool)
    b["edge_certain"][0] = True
    b["possible_edge_codes"][0] = 16
    return a, index, b, scope, proof


def group():
    a, index, candidate, scope, proof = fixture()
    paths = {tag: c.merge_path(a, index, candidate, scope, proof) for tag in c.TAGS}
    combined = d.base.combine(paths["oldpath"], paths["independent"])
    flags, new_scope = d.census.core.classify(paths["oldpath"], paths["independent"], combined)
    original = {"xy": np.arange(18, dtype=float).reshape(9, 2), "trajectory_state": np.zeros((3, 4)),
                "all_reason_flags": scope.astype(np.uint16), "all_scope_packbits": np.packbits(scope, bitorder="little")}
    for tag in c.TAGS:
        original.update({tag + "__" + k: v for k, v in a.items()})
        for prefix in ("merge", "upper_merge"):
            for kind in ("selected", "changed"):
                original[prefix + "_" + kind + "_" + tag + "__packbits"] = np.array([4, 0], np.uint8)
    arrays = c.group_payload(original, paths, combined, flags, new_scope,
                            {tag: index for tag in c.TAGS}, {tag: proof for tag in c.TAGS})
    return original, arrays, paths, combined, flags, new_scope


class MotionMergeTests(unittest.TestCase):
    def exact(self, a, b):
        self.assertEqual(set(a), set(b))
        for k in a:
            self.assertTrue(c.same(a[k], b[k]), k)

    def reject(self, mutate):
        a, i, b, s, p = fixture()
        args = [a, i, b, s, p]
        mutate(args)
        with self.assertRaises((ValueError, RuntimeError)):
            c.merge_path(*args)

    def test_new_contract_not_budget_or_upper_contract(self):
        self.assertIsNot(c.merge_path, d.merged.core.merge_path)
        self.assertIsNot(c.merge_path, d.parent.core.merge_path)
        a, i, b, s, p = fixture()
        for old in (d.merged.core.merge_path, d.parent.core.merge_path):
            with self.assertRaises(ValueError):
                old(a, i, b)
        c.merge_path(a, i, b, s, p)

    def test_vector_scalar_every_field_byte_exact(self):
        args = fixture()
        self.exact(c.merge_path(*args), c.merge_path(*args, scalar=True))

    def test_inputs_not_mutated(self):
        a, i, b, s, p = fixture()
        before = {k: v.copy() for k, v in a.items()}
        proposed = {k: v.copy() for k, v in b.items()}
        c.merge_path(a, i, b, s, p)
        self.exact(a, before)
        self.exact(b, proposed)

    def test_initial_zero_width_unchanged_included(self):
        args = fixture()
        out = c.merge_path(*args)
        for k, v in args[0].items():
            self.assertTrue(c.same(out[k][1:2], v[1:2]))

    def test_all_unknown_initial_leaf_noncontact_and_already_certain_rows_exact(self):
        args = fixture()
        out = c.merge_path(*args)
        for k, v in args[0].items():
            self.assertTrue(c.same(out[k][1:], v[1:]))

    def test_missing_unchanged_scope_row_rejected(self):
        self.reject(lambda x: x.__setitem__(1, x[1][:-1]))

    def test_changed_only_selection_rejected(self):
        self.reject(lambda x: x.__setitem__(1, x[1][:1]))

    def test_extra_nonscope_row_rejected(self):
        self.reject(lambda x: x.__setitem__(1, np.r_[x[1], 8]))

    def test_unsorted_selection_rejected(self):
        self.reject(lambda x: x.__setitem__(1, x[1][::-1]))

    def test_duplicate_selection_rejected(self):
        self.reject(lambda x: x[1].__setitem__(1, 0))

    def test_unsigned_selection_rejected(self):
        self.reject(lambda x: x.__setitem__(1, x[1].astype(np.uint32)))

    def test_float_selection_rejected(self):
        self.reject(lambda x: x.__setitem__(1, x[1].astype(float)))

    def test_negative_selection_rejected(self):
        self.reject(lambda x: x[1].__setitem__(0, -1))

    def test_oob_selection_rejected(self):
        self.reject(lambda x: x[1].__setitem__(-1, 9))

    def test_scope_dtype_rejected(self):
        self.reject(lambda x: x.__setitem__(3, x[3].astype(np.int8)))

    def test_proof_dtype_rejected(self):
        self.reject(lambda x: x.__setitem__(4, x[4].astype(np.uint8)))

    def test_proof_shape_rejected(self):
        self.reject(lambda x: x.__setitem__(4, x[4][:-1]))

    def test_missing_field_rejected(self):
        self.reject(lambda x: x[2].pop("interval_evaluations"))

    def test_field_dtype_rejected(self):
        self.reject(lambda x: x[2].__setitem__("contact_status", x[2]["contact_status"].astype(np.int64)))

    def test_field_shape_rejected(self):
        self.reject(lambda x: x[2].__setitem__("contact_upper_s", x[2]["contact_upper_s"].reshape(-1, 1)))

    def test_science_lower_change_rejected(self):
        self.reject(lambda x: x[2]["contact_lower_s"].__setitem__(0, 1e-12))

    def test_science_upper_change_rejected(self):
        self.reject(lambda x: x[2]["contact_upper_s"].__setitem__(0, .7))

    def test_nominal_code_change_rejected(self):
        self.reject(lambda x: x[2]["nominal_instantaneous_edge"].__setitem__(0, 1))

    def test_contact_status_change_rejected(self):
        self.reject(lambda x: x[2]["contact_status"].__setitem__(0, 2))

    def test_budget_provenance_change_rejected(self):
        self.reject(lambda x: x[2]["budget_exhausted"].__setitem__(0, True))

    def test_evaluation_provenance_change_rejected(self):
        self.reject(lambda x: x[2]["interval_evaluations"].__setitem__(0, 999))

    def test_uncertified_edge_set_change_rejected(self):
        self.reject(lambda x: x[2]["possible_edge_codes"].__setitem__(1, 64))

    def test_uncertified_confidence_change_rejected(self):
        self.reject(lambda x: x[2]["edge_certain"].__setitem__(1, True))

    def test_wrong_certified_singleton_rejected(self):
        self.reject(lambda x: x[2]["possible_edge_codes"].__setitem__(0, 32))

    def test_certified_not_certain_rejected(self):
        self.reject(lambda x: x[2]["edge_certain"].__setitem__(0, False))

    def test_unknown_cannot_be_certified(self):
        self.reject(lambda x: x[4].__setitem__(2, True))

    def test_noncontact_cannot_be_certified(self):
        self.reject(lambda x: x[4].__setitem__(3, True))

    def test_already_certain_cannot_be_newly_certified(self):
        self.reject(lambda x: x[4].__setitem__(4, True))

    def test_signed_zero_endpoint_and_nan_payload_exact(self):
        a, i, b, s, p = fixture()
        a["contact_lower_s"][0] = b["contact_lower_s"][0] = -0.
        a["contact_upper_s"].view(np.uint64)[8] = 0x7ff8000000000041
        self.assertEqual(c.merge_path(a, i, b, s, p)["contact_upper_s"].tobytes(), a["contact_upper_s"].tobytes())
        self.assertEqual(c.merge_path(a, i, b, s, p)["contact_lower_s"].tobytes(), a["contact_lower_s"].tobytes())

    def test_empty_scope(self):
        a, _, _, s, _ = fixture()
        self.exact(a, c.merge_path(a, np.array([], np.int32), {k: v[:0] for k, v in a.items()},
                                   np.zeros(len(s), bool), np.zeros(0, bool)))

    def test_empty_population(self):
        a, *_ = fixture()
        a = {k: v[:0] for k, v in a.items()}
        self.exact(a, c.merge_path(a, np.array([], np.int64), a, np.zeros(0, bool), np.zeros(0, bool)))
        self.assertEqual(c.changed(a, a).shape, (0,))

    def test_full_scope_int32_accepted_without_coercion(self):
        a, i, b, s, p = fixture()
        self.exact(c.merge_path(a, i, b, s, p), c.merge_path(a, i.astype(np.int32), b, s, p))

    def test_prior_masks_and_trajectory_retained(self):
        original, arrays, *_ = group()
        for k, v in original.items():
            if k.startswith(("merge_", "upper_merge_")) or k in ("xy", "trajectory_state"):
                self.assertTrue(c.same(v, arrays[k]))

    def test_new_masks_separate_and_padding_zero(self):
        _, arrays, *_ = group()
        for tag in c.TAGS:
            self.assertEqual(c.unpack(arrays["local_motion_selected_" + tag + "__packbits"], 9).sum(), 7)
            self.assertEqual(c.unpack(arrays["local_motion_certified_" + tag + "__packbits"], 9).sum(), 1)
            self.assertTrue(c.same(arrays["local_motion_certified_" + tag + "__packbits"],
                                   arrays["local_motion_changed_" + tag + "__packbits"]))

    def test_corner_is_one_code_bit_not_two_faces(self):
        _, _, _, both, _, scope = group()
        self.assertEqual(both["possible_edge_codes"][0], 16)
        self.assertFalse(scope[0])

    def test_unknown_stays_unknown_not_negative(self):
        _, _, _, both, _, scope = group()
        for i in (2, 5):
            self.assertEqual(both["contact_status"][i], 2)
            self.assertTrue(scope[i])

    def test_vector_scalar_combination_and_classification(self):
        _, _, paths, combined, flags, scope = group()
        self.exact(combined, d.merged.core.scalar_combine(paths["oldpath"], paths["independent"]))
        f, s = d.census.core.independent_classify(paths["oldpath"], paths["independent"], combined)
        self.assertTrue(c.same(flags, f) and c.same(scope, s))

    def test_all_new_conflicts_retained(self):
        _, _, paths, _, _, _ = group()
        other = {k: v.copy() for k, v in paths["independent"].items()}
        other["contact_lower_s"][0] = 1.
        other["contact_upper_s"][0] = 2.
        other["possible_edge_codes"][0] = 32
        both = d.merged.core.scalar_combine(paths["oldpath"], other)
        self.exact(both, d.base.combine(paths["oldpath"], other))
        for name in ("model_conflict", "time_interval_conflict", "edge_set_conflict"):
            self.assertTrue(both[name][0])
        _, scope = d.census.core.independent_classify(paths["oldpath"], other, both)
        self.assertTrue(scope[0])

    def project(self, index, *, scalar=False):
        original, arrays, paths, both, flags, scope = group()
        xy = original["xy"]
        return c.project(index, xy, xy[index], paths, both, flags, scope, arrays, scalar=scalar)

    def test_int32_original_order_duplicate_indices_preserved(self):
        index = np.array([6, 0, 2, 0, 4, 8, 1], np.int32)
        out = self.project(index)
        self.assertTrue(c.same(out["union_index"], index))
        self.exact(out, self.project(index, scalar=True))

    def test_int64_original_order_indices_preserved(self):
        index = np.array([8, 2, 0, 2], np.int64)
        self.assertTrue(c.same(self.project(index)["union_index"], index))

    def test_empty_projection_scalar_vector_exact(self):
        i = np.array([], np.int32)
        self.exact(self.project(i), self.project(i, scalar=True))

    def test_projection_rejects_unsigned_float_bool_negative_oob(self):
        for i in (np.array([0.]), np.array([0], np.uint32), np.array([True]),
                  np.array([-1], np.int32), np.array([9], np.int64)):
            original, arrays, paths, both, flags, scope = group()
            with self.assertRaises(ValueError):
                c.project(i, original["xy"], np.zeros((len(i), 2)), paths, both, flags, scope, arrays)

    def test_projection_coordinate_signed_zero_mismatch_rejected(self):
        original, arrays, paths, both, flags, scope = group()
        target = original["xy"][:1].copy()
        target[0, 0] = -0.
        with self.assertRaises(ValueError):
            c.project(np.array([0], np.int32), original["xy"], target, paths, both, flags, scope, arrays)

    def test_nonzero_tail_padding_rejected(self):
        with self.assertRaises(ValueError):
            c.unpack(np.array([0, 128], np.uint8), 9)

    def test_mask_shape_and_dtype_rejected(self):
        for a in (np.array([0], np.uint8), np.array([0, 0], np.int32)):
            with self.assertRaises(ValueError):
                c.unpack(a, 9)

    def test_real_shape_35000_original_rows_and70000_group_rows(self):
        n = 70000
        index = (np.arange(35000, dtype=np.int32) * 2)[::-1].copy()
        xy = np.arange(n * 2, dtype=float).reshape(n, 2)
        paths = {tag: {"contact_status": np.zeros(n, np.int8)} for tag in c.TAGS}
        flags, scope = np.zeros(n, np.uint16), np.zeros(n, bool)
        masks = {"local_motion_selected_oldpath__packbits": np.packbits(np.arange(n) % 3 == 0, bitorder="little")}
        out = c.project(index, xy, xy[index], paths, paths["oldpath"], flags, scope, masks)
        self.assertTrue(c.same(out["union_index"], index))
        self.assertEqual(len(out["local_motion_selected_oldpath__packbits"]), 4375)
        self.exact(out, c.project(index, xy, xy[index], paths, paths["oldpath"], flags, scope, masks, scalar=True))

    def test_driver_full_projection_and_census_scalar_vector_int32(self):
        original, arrays, paths, both, flags, scope = group()
        index = np.array([6, 0, 2, 0, 4, 8, 1], np.int32)
        xy = original["xy"]
        old = c.project(index, xy, xy[index], {t: {k.split("__", 1)[1]: v for k, v in original.items()
                        if k.startswith(t + "__")} for t in c.TAGS}, both, flags, scope, arrays)
        target = {"xy": xy[index], "contact_time": np.array([.2, .2, np.nan, .2, .3, np.nan, 0.]),
                  "edge": np.array([2, 5, 0, 5, 5, 0, 7], np.int8)}
        loaded = {"synthetic": {"target": target}}
        with patch.object(d.base, "read_arrays", return_value=(old, {})), patch.object(d.r, "file_hash", return_value="synthetic"):
            vec = d.projection("synthetic", loaded, xy, paths, both, flags, scope, arrays, scalar=False)
            independent = d.projection("synthetic", loaded, xy, paths, both, flags, scope, arrays, scalar=True)
        self.exact(vec[0], independent[0])
        self.assertEqual(vec[1], independent[1])
        self.exact(vec[2], independent[2])
        self.assertEqual(vec[0]["union_index"].dtype, np.int32)

    def test_driver_census_group_scalar_vector(self):
        original, _, paths, both, flags, scope = group()
        self.exact(d.census_group(original["xy"], paths, both, flags, scope, scalar=False),
                   d.census_group(original["xy"], paths, both, flags, scope, scalar=True))

    def test_driver_build_group_scalar_vector(self):
        a, i, b, s, p = fixture()
        original, _, *_ = group()
        asset = (original, {}, {tag: a for tag in c.TAGS})
        candidates = {"fixture/" + tag: (i, b, p) for tag in c.TAGS}
        vector = d.build_group("fixture", asset, candidates, scalar=False)
        scalar = d.build_group("fixture", asset, candidates, scalar=True)
        for tag in c.TAGS:
            self.exact(vector[0][tag], scalar[0][tag])
        for j in (1, 4):
            self.exact(vector[j], scalar[j])
        self.assertTrue(c.same(vector[2], scalar[2]) and c.same(vector[3], scalar[3]))
        self.assertEqual(vector[5], scalar[5])

    def test_no_old_entrypoints_or_new_geometry(self):
        text = inspect.getsource(d)
        for forbidden in ("local.run(", "local.close(", "parent.run(", "parent.close(", "local.core.candidate(",
                          "geos_geometry(", "label_population(", "core.independent_check("):
            self.assertNotIn(forbidden, text)
        self.assertIn("independent=False", text)
        self.assertIn("scalar=True", text)

    def test_fresh_plan_not_inherited_stale_parent_metadata(self):
        text = inspect.getsource(d.prepare)
        self.assertNotIn("**r.read", text)
        self.assertIn('"parent_merged_assets": str(PARENT)', text)


if __name__ == "__main__":
    unittest.main()

