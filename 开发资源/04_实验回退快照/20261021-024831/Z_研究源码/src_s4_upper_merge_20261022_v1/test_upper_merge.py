"""Synthetic exact merge/combination/projection fixtures, no real inputs."""
import inspect
import unittest
import numpy as np
import upper_merge_driver as d

c = d.core


def fixture():
    status = np.array([1, 1, 0, 2, 1], np.int8)
    n = len(status)
    a = {'contact_status': status, 'contact_lower_s': np.array([0., 0., np.nan, .2, 0.]),
        'contact_upper_s': np.array([1., 0., np.nan, np.nan, .5]),
        'nominal_instantaneous_edge': np.array([5, 7, 0, 0, 5], np.int8),
        'possible_edge_codes': np.array([255, 255, 0, 255, 16], np.uint16),
        'edge_certain': np.array([False, False, False, False, True]),
        'budget_exhausted': np.zeros(n, bool), 'interval_evaluations': np.arange(n, dtype=np.int32),
        'candidate_interval_seen': status != 0,
        'initial_tolerance_contact_certain': np.zeros(n, bool),
        'initial_tolerance_contact_possible': np.zeros(n, bool),
        'initial_nominal_body_overlap': np.zeros(n, bool)}
    index = np.array([0, 1], np.int64)
    b = {k: v[index].copy() for k, v in a.items()}
    b['contact_upper_s'][0] = .3
    b['edge_certain'][0] = True
    b['possible_edge_codes'][0] = 16
    return a, index, b


class UpperMergeTests(unittest.TestCase):
    def exact(self, a, b):
        self.assertEqual(d.base.array_meta(a), d.base.array_meta(b))

    def test_distinct_new_nonbudget_contract_module(self):
        self.assertIsNot(c.merge_path, d.merged.core.merge_path)
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            d.merged.core.merge_path(a, i, b)
        self.assertEqual(c.merge_path(a, i, b)['contact_upper_s'][0], .3)

    def test_vector_scalar_all_fields_exact(self):
        a, i, b = fixture()
        self.exact(c.merge_path(a, i, b), c.merge_path(a, i, b, scalar=True))

    def test_inputs_unchanged(self):
        a, i, b = fixture()
        before = d.base.array_meta(a)
        c.merge_path(a, i, b)
        self.assertEqual(before, d.base.array_meta(a))

    def test_all_scientific_lowers_byte_exact(self):
        a, i, b = fixture()
        self.assertEqual(c.merge_path(a, i, b)['contact_lower_s'].tobytes(), a['contact_lower_s'].tobytes())

    def test_initial_zero_width_included_not_skipped(self):
        a, i, b = fixture()
        self.assertEqual(c.selected_mask(a).tolist(), [True, True, False, False, False])
        for k, v in c.merge_path(a, i, b).items():
            self.assertEqual(v[1:2].tobytes(), a[k][1:2].tobytes())

    def test_missing_unchanged_zero_width_index_rejected(self):
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            c.merge_path(a, i[:1], {k: v[:1] for k, v in b.items()})

    def test_no_budget_mask_selection(self):
        a, i, b = fixture()
        self.assertFalse(a['budget_exhausted'].any())
        self.assertEqual(len(np.flatnonzero(c.selected_mask(a))), 2)

    def test_duplicate_index_rejected(self):
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            c.merge_path(a, np.array([0, 0]), b)

    def test_unsorted_index_rejected(self):
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            c.merge_path(a, i[::-1], {k: v[::-1] for k, v in b.items()})

    def test_extra_certain_index_rejected(self):
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            c.merge_path(a, np.array([0, 1, 4]), {k: a[k][[0, 1, 4]] for k in a})

    def test_negative_index_rejected(self):
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            c.merge_path(a, np.array([-1, 1]), b)

    def test_out_of_range_index_rejected(self):
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            c.merge_path(a, np.array([0, 5]), b)

    def test_float_index_rejected(self):
        a, i, b = fixture()
        with self.assertRaises(ValueError):
            c.merge_path(a, i.astype(float), b)

    def test_dtype_change_rejected(self):
        a, i, b = fixture()
        b['contact_status'] = b['contact_status'].astype(np.int64)
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_missing_field_rejected(self):
        a, i, b = fixture()
        b.pop('initial_nominal_body_overlap')
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_shape_change_rejected(self):
        a, i, b = fixture()
        b['contact_upper_s'] = b['contact_upper_s'].reshape(-1, 1)
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_scientific_lower_change_rejected(self):
        a, i, b = fixture()
        b['contact_lower_s'][0] = 1e-10
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_old_evaluation_provenance_change_rejected(self):
        a, i, b = fixture()
        b['interval_evaluations'][0] += 1
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_upper_increase_rejected(self):
        a, i, b = fixture()
        b['contact_upper_s'][0] = 1.1
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_upper_before_lower_rejected(self):
        a, i, b = fixture()
        b['contact_upper_s'][0] = -.1
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_nan_upper_rejected(self):
        a, i, b = fixture()
        b['contact_upper_s'][0] = np.nan
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_unchanged_upper_other_field_change_rejected(self):
        a, i, b = fixture()
        b['nominal_instantaneous_edge'][1] = 5
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_selected_budget_rejected(self):
        a, i, b = fixture()
        a['budget_exhausted'][0] = True
        b['budget_exhausted'][0] = True
        with self.assertRaises(ValueError):
            c.merge_path(a, i, b)

    def test_unselected_nan_payload_byte_exact(self):
        a, i, b = fixture()
        a['contact_lower_s'].view(np.uint64)[2] = 0x7ff8000000000041
        a['contact_upper_s'].view(np.uint64)[2] = 0x7ff8000000000022
        out = c.merge_path(a, i, b)
        for k in a:
            self.assertEqual(out[k][2:].tobytes(), a[k][2:].tobytes())

    def test_signed_zero_lower_byte_exact(self):
        a, i, b = fixture()
        a['contact_lower_s'][0] = -0.
        b['contact_lower_s'][0] = -0.
        self.assertEqual(c.merge_path(a, i, b)['contact_lower_s'].tobytes(), a['contact_lower_s'].tobytes())

    def test_empty_selection_exact(self):
        a, _, _ = fixture()
        a['edge_certain'][[0, 1]] = True
        b = {k: v[:0] for k, v in a.items()}
        self.exact(a, c.merge_path(a, np.array([], np.int64), b))

    def test_empty_population_exact(self):
        a, _, _ = fixture()
        a = {k: v[:0] for k, v in a.items()}
        self.exact(a, c.merge_path(a, np.array([], np.int64), a))

    def group(self):
        a, index, b = fixture()
        paths = {tag: c.merge_path(a, index, b) for tag in c.TAGS}
        combined = d.merged.core.scalar_combine(paths['oldpath'], paths['independent'])
        flags, scope = d.census.core.classify(paths['oldpath'], paths['independent'], combined)
        original = {'xy': np.arange(10, dtype=float).reshape(5, 2),
            'independent_time': np.array([0., 1.]), 'independent_state': np.zeros((2, 4))}
        for tag in c.TAGS:
            original.update({tag + '__' + k: v for k, v in a.items()})
            for kind in ('selected', 'changed'):
                original['merge_' + kind + '_' + tag + '__packbits'] = np.array([4], np.uint8)
        result = c.group_payload(original, paths, combined, flags, scope, {tag: index for tag in c.TAGS})
        return original, result, paths, combined, flags, scope

    def test_budget_merge_masks_preserved_new_masks_separate(self):
        original, result, *_ = self.group()
        for tag in c.TAGS:
            for kind in ('selected', 'changed'):
                key = 'merge_' + kind + '_' + tag + '__packbits'
                self.assertEqual(original[key].tobytes(), result[key].tobytes())
            self.assertEqual(result['upper_merge_selected_' + tag + '__packbits'].tolist(), [3])
            self.assertEqual(result['upper_merge_changed_' + tag + '__packbits'].tolist(), [1])

    def test_other_group_trajectory_arrays_exact(self):
        original, result, *_ = self.group()
        for key in ('xy', 'independent_time', 'independent_state'):
            self.assertEqual(original[key].tobytes(), result[key].tobytes())

    def test_new_masks_tail_padding_zero(self):
        _, result, *_ = self.group()
        for k, v in result.items():
            if k.startswith('upper_merge_'):
                self.assertFalse(np.unpackbits(v, bitorder='little')[5:].any())

    def test_all_original_order_fields_and_duplicate_projection_indices(self):
        original, arrays, paths, combined, flags, scope = self.group()
        index = np.array([4, 1, 0, 3, 0, 2], np.int64)
        xy = original['xy']
        out = d.merged.core.project(index, xy, xy[index], paths, combined, flags, scope, arrays)
        c.add_projection_masks(out, index, arrays, len(xy))
        for tag in c.TAGS:
            for k, v in paths[tag].items():
                self.assertEqual(out[tag + '__' + k].tobytes(), v[index].tobytes())
            self.assertEqual(np.unpackbits(out['upper_merge_selected_' + tag + '__packbits'], bitorder='little')[:6].tolist(),
                             [0, 1, 1, 0, 1, 0])
        self.assertEqual(out['xy'].tobytes(), xy[index].tobytes())

    def test_vector_and_scalar_combination_and_reason_flags(self):
        _, _, paths, combined, flags, scope = self.group()
        self.exact(combined, d.base.combine(paths['oldpath'], paths['independent']))
        f, s = d.census.core.independent_classify(paths['oldpath'], paths['independent'], combined)
        self.assertEqual(f.tobytes(), flags.tobytes())
        self.assertEqual(s.tobytes(), scope.tobytes())

    def test_new_model_time_and_edge_conflicts_retained(self):
        a, i, b = fixture()
        a = c.merge_path(a, i, b)
        other = {k: v.copy() for k, v in a.items()}
        other['contact_lower_s'][0] = .4
        other['contact_upper_s'][0] = .6
        other['possible_edge_codes'][0] = 32
        both = d.merged.core.scalar_combine(a, other)
        self.exact(both, d.base.combine(a, other))
        f, s = d.census.core.independent_classify(a, other, both)
        for k in ('model_conflict', 'time_interval_conflict', 'edge_set_conflict'):
            self.assertTrue(both[k][0])
        self.assertTrue(s[0] and (f[0] & 128))

    def test_unknown_not_negative_or_dropped(self):
        _, _, paths, both, flags, scope = self.group()
        self.assertEqual(both['contact_status'][3], 2)
        self.assertTrue(scope[3])
        self.assertEqual(both['possible_edge_codes'][3], 255)

    def test_single_corner_code_not_two_edge_codes(self):
        _, _, paths, both, flags, scope = self.group()
        self.assertEqual(both['possible_edge_codes'][0], 16)
        self.assertFalse(scope[0])

    def test_old_scientific_entrypoints_and_geometry_not_called(self):
        text = inspect.getsource(d)
        for forbidden in ('prior.run(', 'prior.close(', 'merged.run(', 'merged.close(',
                          'label_population(', 'independently_check(', 'geos_geometry(', 'merge.core.merge_path('):
            self.assertNotIn(forbidden, text)

    def test_row_changed_empty_population(self):
        a, _, _ = fixture()
        a = {k: v[:0] for k, v in a.items()}
        self.assertEqual(c.row_changed(a, a).shape, (0,))

    def test_old_label_discrepancy_vector_scalar(self):
        _, _, paths, combined, *_ = self.group()
        target = {'contact_time': np.array([.2, 0., np.nan, .3, .5]), 'edge': np.array([5, 7, 0, 2, 5])}
        self.exact(d.merged.core.scalar_discrepancies(target, combined), d.base.old_discrepancies(target, combined))


if __name__ == '__main__':
    unittest.main()

