"""Synthetic fixtures only; no original research data are loaded."""
import unittest
from unittest.mock import patch
import numpy as np
import merge_core as core
import merge_driver as driver


def path(status=(3, 1, 0, 2, 1), budget=(True, False, False, False, False)):
    status = np.asarray(status, np.int8)
    n = len(status)
    lower = np.where(status == 0, np.nan, 1.).astype(np.float64)
    upper = np.where(status == 1, 1.01, np.nan).astype(np.float64)
    return {'contact_status': status, 'contact_lower_s': lower, 'contact_upper_s': upper,
        'possible_edge_codes': np.where(status == 0, 0, np.where(status == 1, 16, 255)).astype(np.uint16),
        'edge_certain': status == 1, 'budget_exhausted': np.asarray(budget, bool),
        'nominal_instantaneous_edge': np.where(status == 1, 5, 0).astype(np.int8),
        'interval_evaluations': np.arange(n, dtype=np.int64),
        'candidate_interval_seen': status != 0}


def subset(a, ids):
    return {k: v[ids].copy() for k, v in a.items()}


class MergeTests(unittest.TestCase):
    def assert_exact(self, a, b):
        self.assertEqual(driver.base.array_meta(a), driver.base.array_meta(b))

    def test_exact_vector_scalar_replacement(self):
        a = path()
        original = {k: v.copy() for k, v in a.items()}
        b = subset(a, [0])
        b['budget_exhausted'][:] = False
        b['contact_status'][:] = 2
        vector = core.merge_path(a, np.array([0], np.int64), b)
        scalar = core.merge_path(a, np.array([0], np.int64), b, scalar=True)
        self.assert_exact(vector, scalar)
        self.assert_exact(a, original)
        for k in a:
            self.assertEqual(vector[k][1:].tobytes(), a[k][1:].tobytes())

    def test_nan_payload_and_signed_zero_unselected_exact(self):
        a = path()
        a['contact_lower_s'].view(np.uint64)[2] = 0x7ff8000000000021
        a['contact_lower_s'][3] = -0.
        b = subset(a, [0])
        c = core.merge_path(a, np.array([0]), b)
        self.assertEqual(c['contact_lower_s'].tobytes(), a['contact_lower_s'].tobytes())

    def test_missing_exhausted_index_rejected(self):
        a = path()
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([], np.int64), subset(a, []))

    def test_duplicate_rejected(self):
        a = path()
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([0, 0]), subset(a, [0, 0]))

    def test_extra_unselected_rejected(self):
        a = path()
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([0, 1]), subset(a, [0, 1]))

    def test_negative_rejected(self):
        a = path()
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([-1]), subset(a, [0]))

    def test_out_of_range_rejected(self):
        a = path()
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([5]), subset(a, [0]))

    def test_float_indices_rejected(self):
        a = path()
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([0.]), subset(a, [0]))

    def test_missing_field_rejected(self):
        a = path(); b = subset(a, [0]); b.pop('edge_certain')
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([0]), b)

    def test_dtype_rejected(self):
        a = path(); b = subset(a, [0]); b['contact_status'] = b['contact_status'].astype(np.int64)
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([0]), b)

    def test_shape_rejected(self):
        a = path(); b = subset(a, [0]); b['contact_status'] = b['contact_status'].reshape(1, 1)
        with self.assertRaises(ValueError):
            core.merge_path(a, np.array([0]), b)

    def test_no_exhausted_points_exact(self):
        a = path(budget=(False,) * 5)
        self.assert_exact(a, core.merge_path(a, np.array([], np.int64), subset(a, [])))

    def test_all_status_pairs_combination(self):
        for sa in range(4):
            for sb in range(4):
                a, b = path((sa,), (sa == 3,)), path((sb,), (sb == 3,))
                self.assert_exact(driver.base.combine(a, b), core.scalar_combine(a, b))

    def test_disjoint_time_and_edge_conflicts_retained(self):
        a, b = path((1,), (False,)), path((1,), (False,))
        b['contact_lower_s'][:] = 2.; b['contact_upper_s'][:] = 2.01
        b['possible_edge_codes'][:] = 32
        c = core.scalar_combine(a, b)
        self.assertTrue(c['model_conflict'][0] and c['time_interval_conflict'][0] and c['edge_set_conflict'][0])
        self.assert_exact(c, driver.base.combine(a, b))

    def test_corner_single_code_is_singleton(self):
        a, b = path((1,), (False,)), path((1,), (False,))
        c = core.scalar_combine(a, b)
        flags, scope = driver.census.core.classify(a, b, c)
        self.assertFalse(scope[0])
        self.assertEqual(flags[0], 0)

    def test_multicode_and_unknown_not_negative(self):
        a, b = path(), path()
        a['possible_edge_codes'][1] = 255; a['edge_certain'][1] = False
        c = core.scalar_combine(a, b)
        f, s = driver.census.core.classify(a, b, c)
        ff, ss = driver.census.core.independent_classify(a, b, c)
        self.assert_exact({'f': f, 's': s}, {'f': ff, 's': ss})
        self.assertTrue(s[0] and s[1] and s[3])
        self.assertEqual(c['contact_status'][3], 2)

    def fixture(self):
        a, b = path(), path()
        c = core.scalar_combine(a, b)
        flags, scope = driver.census.core.classify(a, b, c)
        xy = np.arange(10., dtype=np.float64).reshape(5, 2)
        original = {'xy': xy, 'independent_time': np.array([0., 1.]), 'secondary_state': np.zeros((2, 4))}
        for tag, value in (('oldpath', a), ('independent', b), ('combined', c)):
            original.update({tag + '__' + k: v for k, v in value.items()})
        selected = {tag: np.array([0], np.int64) for tag in core.TAGS}
        full = core.group_payload(original, {'oldpath': a, 'independent': b}, c, flags, scope, selected)
        return original, {'oldpath': a, 'independent': b}, c, flags, scope, full

    def test_other_group_arrays_exact(self):
        original, _, _, _, _, full = self.fixture()
        self.assertEqual(original['secondary_state'].tobytes(), full['secondary_state'].tobytes())
        self.assertEqual(original['independent_time'].tobytes(), full['independent_time'].tobytes())

    def test_full_mask_padding_zero(self):
        _, _, _, _, scope, full = self.fixture()
        self.assertTrue((full['all_scope_packbits'][-1] & 0xe0) == 0)
        np.testing.assert_array_equal(np.unpackbits(full['all_scope_packbits'], bitorder='little', count=5), scope)
        self.assertEqual(int(full['merge_selected_oldpath__packbits'][0]), 1)

    def test_original_order_repeated_projection_full_fields(self):
        original, paths, c, flags, scope, full = self.fixture()
        index = np.array([4, 0, 3, 0, 2], np.int32)
        out = core.project(index, original['xy'], original['xy'][index], paths, c, flags, scope, full)
        self.assertEqual(out['union_index'].dtype, np.dtype('int32'))
        for tag, values in (*paths.items(), ('combined', c)):
            for k, v in values.items():
                self.assertEqual(out[tag + '__' + k].tobytes(), v[index].tobytes())
        self.assertEqual(int(out['merge_selected_oldpath__packbits'][0]), 10)
        self.assertTrue((out['all_scope_packbits'][-1] & 0xe0) == 0)

    def test_wrong_coordinate_rejected(self):
        original, paths, c, flags, scope, full = self.fixture()
        with self.assertRaises(ValueError):
            core.project(np.arange(5), original['xy'], original['xy'] + 1, paths, c, flags, scope, full)

    def test_wrong_projection_index_rejected(self):
        original, paths, c, flags, scope, full = self.fixture()
        with self.assertRaises(ValueError):
            core.project(np.array([-1, 1, 2, 3, 4]), original['xy'], original['xy'], paths, c, flags, scope, full)

    def test_scalar_old_discrepancies_match_full_vector(self):
        a, b = path(), path()
        c = core.scalar_combine(a, b)
        target = {'contact_time': np.array([np.nan, .2, 2., 5., 1.005]), 'edge': np.array([1, 2, 3, 4, 5], np.int8)}
        self.assert_exact(core.scalar_discrepancies(target, c), driver.base.old_discrepancies(target, c))

    def test_new_run_budget_does_not_change_any_parent(self):
        self.assertNotEqual(driver.RUN, driver.prior.RUN)
        self.assertEqual(driver.r.RUN_CAP, 1024**3)
        self.assertEqual(driver.r.RUN, driver.RUN)
        self.assertEqual(driver.RESERVATION, 896 * 1024**2)

    def test_no_scientific_kernel_called_by_merge(self):
        import inspect
        source = inspect.getsource(core)
        self.assertNotIn('label_population(', source)
        self.assertNotIn('audit_point(', source)
        self.assertNotIn('solve_ivp(', source)

    def merge_fixture(self):
        original, paths, _, _, _, _ = self.fixture()
        selection, candidates = {}, {}
        for tag in core.TAGS:
            refined = subset(paths[tag], [0])
            refined['budget_exhausted'][:] = False
            refined['contact_status'][:] = 2
            spec = {'group': 'synthetic', 'path': tag, 'union_indices': [0]}
            name = 'synthetic__' + tag
            selection[name] = spec
            candidates[name] = (original['xy'][[0]], np.array([0], np.int64), None, None, None, None, refined)
        return (original, {}, paths), selection, candidates

    def test_full_group_driver_vector_scalar_exact(self):
        asset, selection, candidates = self.merge_fixture()
        a = driver.build_group('synthetic', asset, selection, candidates, scalar=False)
        b = driver.build_group('synthetic', asset, selection, candidates, scalar=True)
        self.assert_exact(a[5], b[5])
        self.assertEqual(a[6], b[6])
        self.assertEqual(a[6]['reason_counts_nonexclusive']['oldpath_budget'], 0)
        self.assertTrue(a[3][0])

    def test_candidate_coordinate_corruption_rejected(self):
        asset, selection, candidates = self.merge_fixture()
        value = list(candidates['synthetic__oldpath']); value[0] = value[0] + 1
        candidates['synthetic__oldpath'] = tuple(value)
        with self.assertRaises(RuntimeError):
            driver.build_group('synthetic', asset, selection, candidates, scalar=False)

    def test_candidate_original_index_corruption_rejected(self):
        asset, selection, candidates = self.merge_fixture()
        value = list(candidates['synthetic__oldpath']); value[1] = np.array([1])
        candidates['synthetic__oldpath'] = tuple(value)
        with self.assertRaises(RuntimeError):
            driver.build_group('synthetic', asset, selection, candidates, scalar=False)

    def test_full_driver_projection_and_census_exact(self):
        asset, selection, candidates = self.merge_fixture()
        paths, combined, flags, scope, _, full, _ = driver.build_group(
            'synthetic', asset, selection, candidates, scalar=False)
        index = np.array([4, 0, 3, 0, 2], np.int32)
        target = {'xy': asset[0]['xy'][index], 'contact_time': np.array([1.005, np.nan, .5, 2., np.nan]),
                  'edge': np.array([5, 0, 2, 3, 0], np.int8)}
        loaded = {'fixture': {'target': target}}
        with patch.object(driver.base, 'read_arrays', return_value=({'union_index': index}, {})), \
                patch.object(driver.r, 'file_hash', return_value='synthetic-only'):
            a = driver.projection('fixture', loaded, asset[0]['xy'], paths, combined, flags, scope, full, scalar=False)
            b = driver.projection('fixture', loaded, asset[0]['xy'], paths, combined, flags, scope, full, scalar=True)
        self.assert_exact(a[0], b[0]); self.assertEqual(a[1], b[1]); self.assert_exact(a[2], b[2])
        self.assertEqual(a[1]['summary']['points'], 5)


if __name__ == '__main__':
    unittest.main()
