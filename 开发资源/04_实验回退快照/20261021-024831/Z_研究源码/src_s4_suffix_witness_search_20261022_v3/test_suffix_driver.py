"""Synthetic complete driver/projection contracts, with no real array I/O."""
from pathlib import Path
import inspect
import unittest
from unittest.mock import patch
import numpy as np

import suffix_driver as d
from test_probe import fixture, V


def integration_fixture():
    xy, time, states, labels = fixture()
    full_xy = np.vstack((xy, [[90., 90.], [91., 91.]]))
    all_labels = {k: np.concatenate((v, v[4:5], v[4:5])) for k, v in labels.items()}
    scope = np.arange(len(full_xy)) < len(xy)
    full = {"xy": full_xy, "all_reason_flags": scope.astype(np.uint16),
            "all_scope_packbits": np.packbits(scope, bitorder="little")}
    for tag in d.TAGS:
        for prefix, kinds in (("merge", ("selected", "changed")),
                              ("upper_merge", ("selected", "changed")),
                              ("local_motion", ("selected", "certified", "changed")),
                              ("probe_merge", ("scope", "new_witness", "changed"))):
            for kind in kinds:
                full[prefix + "_" + kind + "_" + tag + "__packbits"] = np.packbits(
                    np.arange(len(full_xy)) % 3 == 0, bitorder="little")
    diagnostic = {"union_index": np.arange(len(full_xy), dtype=np.int64), "xy": full_xy.copy()}
    for tag in d.TAGS:
        diagnostic.update({tag + "__label__" + k: v.copy() for k, v in all_labels.items()})
        diagnostic[tag + "__metric__initial_origin"] = np.isfinite(all_labels["contact_lower_s"]) & (all_labels["contact_lower_s"] == 0)
        diagnostic[tag + "__metric__time_leaf_origin"] = np.isfinite(all_labels["contact_lower_s"]) & (all_labels["contact_lower_s"] > 0)
        diagnostic[tag + "__metric__leaf_witness_margin_m"] = np.arange(len(full_xy), dtype=float) - 20
        diagnostic[tag + "__metric__midpoint_faces_m"] = np.zeros((len(full_xy), 4))
    asset = full, {}, {tag: all_labels for tag in d.TAGS}
    with patch.object(d.base, "save_arrays") as saver:
        arrays, summary, check = d.build("synthetic", "oldpath", time, states, 1e-6, V, all_labels, asset, (diagnostic, {}))
        saver.assert_not_called()
    return time, states, all_labels, asset, diagnostic, arrays, summary, check


class ProbeDriverTests(unittest.TestCase):
    def exact(self, a, b):
        self.assertEqual(set(a), set(b))
        for key in a:
            self.assertTrue(d.scope_core.same(a[key], b[key]), key)

    def test_full_scope_build_keeps_all_rows_not_only_new_witnesses(self):
        _, _, _, _, _, arrays, summary, checked = integration_fixture()
        self.assertEqual(summary["scope_records"], 7)
        self.assertEqual(summary["selected_unwitnessed"], 5)
        self.assertEqual(summary["strict_new_witnesses"], 3)
        self.assertEqual(len(arrays["union_index"]), 7)
        self.assertIsNone(checked)

    def test_build_saved_independent_every_quantity_exact(self):
        time, states, labels, asset, diag, arrays, summary, _ = integration_fixture()
        with patch.object(d.base, "save_arrays") as saver:
            independent, values, checked = d.build("synthetic", "oldpath", time, states, 1e-6, V,
                labels, asset, (diag, {}), saved=arrays)
            saver.assert_not_called()
        self.exact(arrays, independent)
        self.assertEqual(summary, values)
        self.assertEqual(checked["new_strict_contact_witnesses"], 3)

    def test_all_parent_provenance_types_bound(self):
        _, _, _, asset, _, arrays, _, _ = integration_fixture()
        for name, value in asset[0].items():
            if name.startswith(("merge_", "upper_merge_", "local_motion_", "probe_merge_")):
                self.assertTrue(d.scope_core.same(arrays["parent_provenance__" + name], value))

    def test_source_initial_and_leaf_diagnostics_kept_even_if_candidate_witnessed(self):
        _, _, _, _, _, arrays, summary, _ = integration_fixture()
        self.assertEqual(summary["source_initial_unknown"], 3)
        self.assertEqual(summary["source_time_leaf_unknown"], 2)
        self.assertEqual(len(arrays["retained_unknown_union_index"]), 5)
        self.assertEqual(arrays["retained_unknown_label__contact_status"].tolist(), [2] * 5)
        self.assertEqual(arrays["candidate__contact_status"][[0, 2, 5]].tolist(), [1, 1, 1])

    def project(self, index, *, scalar=False):
        _, _, _, asset, _, arrays, _, _ = integration_fixture()
        full = asset[0]
        source = {"union_index": index, "xy": full["xy"][index]}
        for name, value in full.items():
            if name.startswith(("merge_", "upper_merge_", "local_motion_", "probe_merge_")):
                bits = np.unpackbits(value, bitorder="little")[:len(full["xy"])]
                source[name] = np.packbits(bits[index], bitorder="little")
        with patch.object(d.base, "read_arrays", return_value=(source, {})), patch.object(d.r, "file_hash", return_value="synthetic"):
            return d.projection("synthetic", full, arrays, scalar=scalar), source, arrays

    def test_int32_duplicate_original_order_and_2d_probe_traces_exact(self):
        index = np.array([6, 0, 2, 0, 8, 4, 5], np.int32)
        (a, rec), original, _ = self.project(index)
        (b, other), _, _ = self.project(index, scalar=True)
        self.exact(a, b)
        self.assertEqual(rec, other)
        self.assertTrue(d.scope_core.same(a["source_union_index"], original["union_index"]))
        self.assertEqual(a["source_union_index"].dtype, np.int32)
        self.assertEqual(a["union_index"].dtype, np.int32)
        self.assertEqual(a["trace__forward_time_s"].shape, (6, 256))
        self.assertTrue(d.scope_core.same(a["trace__forward_time_s"][1:2], a["trace__forward_time_s"][3:4]))

    def test_int64_original_dtype_retained(self):
        (out, _), _, _ = self.project(np.array([2, 0, 2], np.int64))
        self.assertEqual(out["source_union_index"].dtype, np.int64)

    def test_empty_original_order_projection_and_matrix_shape(self):
        (out, _), _, _ = self.project(np.array([], np.int32))
        self.assertEqual(out["trace__forward_time_s"].shape, (0, 256))
        self.assertEqual(out["trace__forward_witness__packbits"].shape, (0,))
        (other, _), _, _ = self.project(np.array([], np.int32), scalar=True)
        self.exact(out, other)

    def test_bool_probe_matrix_packbits_exact_flat_row_order(self):
        (out, _), _, _ = self.project(np.array([5, 0, 2, 5], np.int32))
        for prefix in ("forward", "refine"):
            name = "trace__" + prefix + "_witness"
            width=256 if prefix=="forward" else 64
            self.assertEqual(out[name].shape, (4, width))
            packed = out[name + "__packbits"]
            self.assertEqual(packed.shape, (4*width//8,))
            self.assertEqual(np.unpackbits(packed, bitorder="little").tolist(),
                             out[name].reshape(-1).astype(np.uint8).tolist())

    def test_all_1d_masks_tail_padding_zero(self):
        (out, _), _, _ = self.project(np.array([5, 0, 2, 5, 8], np.int32))
        for name in ("full_scope_packbits", "full_unknown_packbits"):
            self.assertFalse(np.unpackbits(out[name], bitorder="little")[5:].any())
        for name, value in out.items():
            if name.startswith("parent_provenance__"):
                self.assertFalse(np.unpackbits(value, bitorder="little")[5:].any())

    def test_source_union_index_dtype_and_coordinate_rejections(self):
        _, _, _, asset, _, arrays, _, _ = integration_fixture()
        full = asset[0]
        for index in (np.array([-1], np.int32), np.array([9], np.int64),
                      np.array([0.]), np.array([0], np.uint32), np.array([False])):
            with self.assertRaises(ValueError):
                d.scope_core.project(full["xy"], index, np.zeros((1, 2)), arrays)
        with self.assertRaises(ValueError):
            d.scope_core.project(full["xy"], np.array([0], np.int32), np.zeros((1, 2)), arrays)

    def test_bad_parent_mask_padding_rejected(self):
        _, _, _, asset, _, arrays, _, _ = integration_fixture()
        arrays["parent_provenance__merge_selected_oldpath__packbits"][-1] |= np.uint8(128)
        with self.assertRaises(ValueError):
            d.scope_core.project(asset[0]["xy"], np.array([0], np.int32), asset[0]["xy"][:1], arrays)

    def test_real_original_35000_rows_and_70000_group_shape_with_sparse_scope(self):
        _, _, _, _, _, arrays, _, _ = integration_fixture()
        indices = np.array([0, 35000, 69998], np.int64)
        rr = np.array([0, 1, 2], np.int64)
        n = 70000
        full_xy = np.zeros((n, 2))
        full_xy[indices] = arrays["xy"][rr]
        selected = np.zeros(n, bool)
        selected[indices] = True
        group = {"union_index": indices, "xy": full_xy[indices],
                 "full_scope_packbits": np.packbits(selected, bitorder="little")}
        for name, value in arrays.items():
            if name.startswith(("original__", "candidate__", "trace__")) and not name.endswith("__packbits"):
                group[name] = value[rr]
        retained = np.array([0, 35000, 69998], np.int64)
        group.update(retained_unknown_union_index=retained, retained_unknown_xy=full_xy[retained],
                     retained_unknown_parent_row=np.arange(3, dtype=np.int64),
                     full_unknown_packbits=np.packbits(selected, bitorder="little"))
        for name, value in arrays.items():
            if name.startswith(("retained_unknown_label__", "retained_unknown_metric__")):
                group[name] = value[:3]
            if name.startswith("parent_provenance__"):
                group[name] = np.packbits(np.zeros(n, bool), bitorder="little")
        index = np.arange(35000, dtype=np.int32) * 2
        a = d.scope_core.project(full_xy, index, full_xy[index], group)
        b = d.scope_core.project(full_xy, index, full_xy[index], group, scalar=True)
        self.exact(a, b)
        self.assertEqual(len(a["source_union_index"]), 35000)
        self.assertEqual(a["trace__forward_time_s"].shape, (3, 256))
        self.assertEqual(a["source_union_index"].dtype, np.int32)

    def test_scope_omission_cannot_be_hidden_by_changed_only_indices(self):
        _, _, _, asset, _, arrays, _, _ = integration_fixture()
        arrays["union_index"] = arrays["union_index"][:1]
        with patch.object(d.base, "read_arrays") as reader:
            with self.assertRaises(RuntimeError):
                d.projection("synthetic", asset[0], arrays)
            reader.assert_not_called()

    def test_failure_input_context_is_saved_without_real_io_and_error_reraised(self):
        time, states, labels, asset, diag, _, _, _ = integration_fixture()
        with patch.object(d.core, "candidate", side_effect=ValueError("synthetic query failure")), \
             patch.object(d.base, "save_arrays") as saver:
            with self.assertRaisesRegex(ValueError, "synthetic query failure"):
                d.build("synthetic", "oldpath", time, states, 1e-6, V, labels, asset, (diag, {}))
            self.assertIn("failure_context", str(saver.call_args.args[0]))
            payload = saver.call_args.args[1]
            self.assertTrue(d.core.same(payload["states"], states))
            self.assertTrue(d.core.same(payload["original__contact_lower_s"], labels["contact_lower_s"][:7]))

    def test_independent_failure_preserves_full_saved_payload(self):
        time, states, labels, asset, diag, arrays, _, _ = integration_fixture()
        with patch.object(d.core, "independent_check", side_effect=ValueError("synthetic replay failure")), \
             patch.object(d.base, "save_arrays") as saver:
            with self.assertRaisesRegex(ValueError, "synthetic replay failure"):
                d.build("synthetic", "oldpath", time, states, 1e-6, V, labels, asset, (diag, {}), saved=arrays)
            payload = saver.call_args.args[1]
            for name, value in arrays.items():
                self.assertTrue(d.core.same(payload["saved__" + name], value))

    def test_missing_or_changed_unknown_source_field_rejected_without_real_io(self):
        time, states, labels, asset, diag, _, _, _ = integration_fixture()
        diag["oldpath__label__contact_lower_s"][0] = .5
        with patch.object(d.base, "save_arrays") as saver:
            with self.assertRaises(ValueError):
                d.build("synthetic", "oldpath", time, states, 1e-6, V, labels, asset, (diag, {}))
            saver.assert_called_once()

    def test_metadata_binds_current_parent_and_both_original_paths(self):
        time, states, _, _, _, _, values, _ = integration_fixture()
        with patch.object(d.r, "file_hash", return_value="synthetic"):
            rec = d.record("synthetic", "oldpath", values, time, states, 1e-6, V)
        self.assertEqual(rec["parent_hashes"], d.HASHES)
        self.assertTrue(rec["all_original_lowers_and_full_prefixes_exact_reuse"])
        self.assertTrue(rec["fixed_probes_not_exhaustive_or_global_earliest_or_noncontact_proof"])


if __name__=="__main__": unittest.main()
