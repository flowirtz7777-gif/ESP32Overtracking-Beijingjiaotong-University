"""Synthetic scope, provenance, padding and driver-contract checks."""
import copy
import unittest
import numpy as np

import local_scope as s
import local_motion_driver as driver


def payload():
    labels = {"contact_lower_s": np.asarray([0., .5, np.nan]),
              "contact_upper_s": np.asarray([np.nan, 1., np.nan]),
              "contact_status": np.asarray([2, 1, 0], np.int8),
              "edge_certain": np.asarray([False, False, False])}
    full_xy = np.column_stack((np.arange(9.), np.arange(9.) / 2))
    index = np.asarray([1, 4, 8], np.int64)
    old = {"union_index": np.asarray([0, 1, 2, 4, 8], np.int64),
           "xy": full_xy[[0, 1, 2, 4, 8]],
           "oldpath__metric__initial_origin": np.asarray([False, True, False, False, False]),
           "oldpath__metric__time_leaf_origin": np.asarray([False]*5),
           "oldpath__metric__initial_witness_margin_m": np.asarray([np.nan, -.00001, np.nan, np.nan, np.nan])}
    for k, v in labels.items():
        a = np.empty((5,), dtype=v.dtype)
        if np.issubdtype(v.dtype, np.floating):
            a.fill(np.nan)
        else:
            a.fill(0)
        a[[1, 3, 4]] = v
        old["oldpath__label__" + k] = a
    retained = s.retained_unknown(index, full_xy[index], labels, old, "oldpath")
    group = {"union_index": index, "xy": full_xy[index],
             "trace__flag": np.asarray([False, True, False]),
             "trace__faces": np.arange(12.).reshape(3, 4),
             "parent_provenance__merge_selected_oldpath__packbits": np.packbits(
                 np.asarray([False, True, False, False, True, False, False, False, True]), bitorder="little")}
    group.update({"original__" + k: v for k, v in labels.items()})
    group.update({"candidate__" + k: v.copy() for k, v in labels.items()})
    group.update(retained)
    return full_xy, index, labels, old, group


class ScopeTests(unittest.TestCase):
    def test_arbitrary_source_order_both_paths(self):
        source = np.asarray([7, 1, 5, 0], np.int64)
        requested = np.asarray([0, 7, 1, 1], np.int64)
        np.testing.assert_array_equal(s.rows(source, requested), [3, 0, 1, 1])
        np.testing.assert_array_equal(s.rows(source, requested, scalar=True), [3, 0, 1, 1])

    def test_empty_scope(self):
        empty = np.asarray([], np.int64)
        self.assertEqual(s.rows(empty, empty).shape, (0,))
        self.assertEqual(s.rows(empty, empty, scalar=True).shape, (0,))

    def test_missing_source_point_rejected(self):
        for scalar in (False, True):
            with self.assertRaises(ValueError):
                s.rows(np.asarray([1, 3], np.int64), np.asarray([2], np.int64), scalar=scalar)

    def test_duplicate_or_negative_source_rejected(self):
        for source in (np.asarray([1, 1], np.int64), np.asarray([-1, 2], np.int64)):
            with self.assertRaises(ValueError):
                s.rows(source, np.asarray([1], np.int64))

    def test_retained_unknown_complete_fields(self):
        xy, index, labels, old, group = payload()
        other = s.retained_unknown(index, xy[index], labels, old, "oldpath", scalar=True)
        for k, v in other.items():
            self.assertTrue(s.same(v, group[k]), k)
        self.assertEqual(other["retained_unknown_metric__initial_witness_margin_m"][0], -.00001)

    def test_unknown_provenance_change_rejected(self):
        xy, index, labels, old, _ = payload()
        labels["contact_lower_s"][0] = .1
        with self.assertRaises(ValueError):
            s.retained_unknown(index, xy[index], labels, old, "oldpath")

    def test_unknown_coordinate_change_rejected(self):
        xy, index, labels, old, _ = payload()
        xy[1, 0] += .01
        with self.assertRaises(ValueError):
            s.retained_unknown(index, xy[index], labels, old, "oldpath")

    def test_all_original_order_arrays_and_padding(self):
        xy, _, _, _, group = payload()
        index = np.asarray([8, 3, 1, 4, 1, 0, 2, 7, 6], np.int64)
        a = s.project(xy, index, xy[index], group)
        b = s.project(xy, index, xy[index], group, scalar=True)
        self.assertEqual(set(a), set(b))
        for k in a:
            self.assertTrue(s.same(a[k], b[k]), k)
        np.testing.assert_array_equal(a["original_index"], [0, 2, 3, 4])
        np.testing.assert_array_equal(a["original_unknown_index"], [2, 4])
        np.testing.assert_array_equal(a["retained_unknown_union_index"], [1, 1])
        self.assertFalse(np.unpackbits(a["full_unknown_packbits"], bitorder="little")[9:].any())
        self.assertFalse(np.unpackbits(a["original__edge_certain__packbits"], bitorder="little")[4:].any())

    def test_parent_padding_tamper_rejected(self):
        xy, _, _, _, group = payload()
        group["parent_provenance__merge_selected_oldpath__packbits"][-1] |= 128
        with self.assertRaises(ValueError):
            s.project(xy, np.arange(9, dtype=np.int64), xy, group)

    def test_original_coordinate_projection_mismatch_rejected(self):
        xy, _, _, _, group = payload()
        with self.assertRaises(ValueError):
            s.project(xy, np.arange(9, dtype=np.int64), xy + .001, group)

    def test_integer_dtype_lookup_accepts_parent_int32(self):
        out = s.rows(np.asarray([1, 2], np.int32), np.asarray([1], np.int64))
        np.testing.assert_array_equal(out, [0])
        self.assertEqual(out.dtype, np.int64)


class DriverContractTests(unittest.TestCase):
    def test_fixed_parent_hashes_and_candidate_stage(self):
        self.assertEqual(driver.HASHES["checkpoint.json"],
            "033ad57e679af3f93643e5997b358c814f776cc686c9fce3ac31b7b58cc439f8")
        self.assertEqual(driver.RUN.name, "resume_20261022_0000_local_motion_v2")
        self.assertEqual(driver.PLAN.name, "resume_plan_20261022_0000_v26.json")
        self.assertEqual(driver.CLOSED_PLAN.name, "resume_plan_20261022_0000_v27.json")

    def test_run_resource_bounds(self):
        driver.configure()
        self.assertEqual(driver.r.RUN_CAP, 512 * 1024**2)
        self.assertEqual(driver.RESERVATION, 448 * 1024**2)

    def test_full_unknown_and_edge_scope_contract(self):
        counts = {"path_blocks": 78, "projected_path_files": 114,
            "scope_group_unique_points": 22985, "scope_point_file_records": 27025,
            "weighted_path_diagnostics": {}}
        for tag, unknown, edge in (("oldpath", 13956, 13069), ("independent", 13710, 12669)):
            counts["weighted_path_diagnostics"][tag] = {
                "unwitnessed_contact_unknown_exactly_retained": unknown,
                "selected_uncertain_witnessed_edges": edge, "any_contact_endpoint_changes": 0,
                "initial_unknown_exactly_retained": 0, "noninitial_time_leaf_unknown_exactly_retained": unknown}
        driver.whole_counts(counts)
        counts["weighted_path_diagnostics"]["independent"]["unwitnessed_contact_unknown_exactly_retained"] -= 1
        with self.assertRaises(RuntimeError):
            driver.whole_counts(counts)

    def test_incomplete_original_projection_contract(self):
        with self.assertRaises(RuntimeError):
            driver.whole_counts({"path_blocks": 78, "projected_path_files": 113,
                "scope_group_unique_points": 22985, "scope_point_file_records": 27025})



    def test_synthetic_path_build_and_independent_close_assembly(self):
        from unittest.mock import patch
        from test_local_motion import fixture
        f = fixture()
        xy, time, states, labels, error, vehicle = f[:6]
        original = {"union_index": np.arange(len(xy), dtype=np.int64), "xy": xy.copy(),
            "oldpath__metric__initial_origin": np.asarray([False, True, False, False, False]),
            "oldpath__metric__time_leaf_origin": np.asarray([False, False, True, False, False])}
        original.update({"oldpath__label__" + k: v.copy() for k, v in labels.items()})
        full = {"xy": xy, "all_reason_flags": np.ones(len(xy), np.uint16),
            "merge_selected_oldpath__packbits": np.packbits(np.asarray([True, False, False, False, False]), bitorder="little")}
        asset, diagnostic = (full, {}, {"oldpath": labels}), (original, {})
        with patch.object(driver.base, "finite_face_geometry", side_effect=lambda x, p, **kw: f[6](x, p)), \
             patch.object(driver.science.core, "geos_geometry", side_effect=f[7]):
            out, values, _ = driver.build("synthetic", "oldpath", time, states, error, vehicle, labels, asset, diagnostic)
            checked, independent_values, proof = driver.build("synthetic", "oldpath", time, states, error, vehicle,
                labels, asset, diagnostic, saved=out)
        self.assertEqual(values, independent_values)
        self.assertEqual(values["unwitnessed_contact_unknown_exactly_retained"], 2)
        self.assertEqual(values["new_edge_certified_candidates"], 1)
        self.assertEqual(proof["independent_midpoint_GE0S_queries"], 1)
        self.assertEqual(set(out), set(checked))
        for name in out:
            self.assertTrue(s.same(out[name], checked[name]), name)
        dataset_index = np.asarray([4, 1, 0, 2, 1, 3], np.int32)
        source = {"xy": xy[dataset_index], "union_index": dataset_index,
            "merge_selected_oldpath__packbits": np.packbits(
                np.asarray([False, False, True, False, False, False]), bitorder="little")}
        with patch.object(driver.base, "read_arrays", return_value=(source, {})), \
             patch.object(driver.r, "file_hash", return_value="synthetic-only-parent-digest"):
            a, ar = driver.projection("synthetic", full, out)
            b, br = driver.projection("synthetic", full, out, scalar=True)
        self.assertEqual(ar, br)
        self.assertEqual(ar["summary"]["unwitnessed_contact_unknown_exactly_retained"], 3)
        for name in a:
            self.assertTrue(s.same(a[name], b[name]), name)


class TypedOriginalIndexTests(unittest.TestCase):
    def test_accepted_parent_int32_actual_35000_shape(self):
        _, _, _, _, group = payload()
        full = np.column_stack((np.arange(70000.), np.arange(70000.) / 2))
        index = np.arange(35000, dtype=np.int32)
        parent_mask = np.zeros(len(full), bool)
        parent_mask[[1, 4, 8]] = True
        group["parent_provenance__merge_selected_oldpath__packbits"] = np.packbits(parent_mask, bitorder="little")
        a = s.project(full, index, full[index], group)
        b = s.project(full, index, full[index], group, scalar=True)
        self.assertEqual(a["source_union_index"].shape, (35000,))
        self.assertEqual(a["source_union_index"].dtype, np.int32)
        self.assertEqual(a["source_union_index"].tobytes(), index.tobytes())
        self.assertEqual(a["union_index"].dtype, np.int32)
        self.assertEqual(a["retained_unknown_union_index"].dtype, np.int32)
        for name in a:
            self.assertTrue(s.same(a[name], b[name]), name)

    def test_int32_duplicates_original_order_and_tail_padding(self):
        full, _, _, _, group = payload()
        index = np.asarray([8, 1, 4, 1, 0, 7, 2, 3, 6], dtype=np.int32)
        out = s.project(full, index, full[index], group)
        self.assertEqual(out["source_union_index"].tobytes(), index.tobytes())
        np.testing.assert_array_equal(out["union_index"], np.asarray([8, 1, 4, 1], np.int32))
        self.assertFalse(np.unpackbits(out["full_scope_packbits"], bitorder="little")[9:].any())

    def test_int32_empty_original_dataset_retains_shape_dtype(self):
        full, _, _, _, group = payload()
        index = np.asarray([], np.int32)
        out = s.project(full, index, full[index], group)
        self.assertEqual(out["source_union_index"].dtype, np.int32)
        self.assertEqual(out["union_index"].dtype, np.int32)
        self.assertEqual(out["xy"].shape, (0, 2))

    def test_out_of_bounds_parent_index_is_not_silently_coerced(self):
        full, _, _, _, group = payload()
        for index in (np.asarray([-1], np.int32), np.asarray([9], np.int32)):
            with self.assertRaises(ValueError):
                s.project(full, index, np.zeros((1, 2)), group)

    def test_float_boolean_unsigned_indices_rejected(self):
        full, _, _, _, group = payload()
        for dtype in (np.float64, np.bool_, np.uint32):
            index = np.asarray([1], dtype=dtype)
            with self.assertRaises(ValueError):
                s.project(full, index, full[[1]], group)

    def test_mixed_signed_lookup_no_parent_mutation(self):
        source = np.asarray([7, 1, 4], np.int64)
        requested = np.asarray([4, 7, 1, 1], np.int32)
        before = requested.tobytes()
        np.testing.assert_array_equal(s.rows(source, requested), [2, 0, 1, 1])
        np.testing.assert_array_equal(s.rows(source, requested, scalar=True), [2, 0, 1, 1])
        self.assertEqual(requested.tobytes(), before)
        self.assertEqual(requested.dtype, np.int32)

    def test_all_original_int64_indices_remain_int64(self):
        full, _, _, _, group = payload()
        index = np.arange(9, dtype=np.int64)
        out = s.project(full, index, full[index], group)
        self.assertTrue(s.same(out["source_union_index"], index))
        self.assertEqual(out["union_index"].dtype, np.int64)

if __name__ == "__main__":
    unittest.main()


