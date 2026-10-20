import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect_counterexamples as c

np = c.np


class CounterexampleTests(unittest.TestCase):
    def test_all_six_union_sorted_and_deduplicated(self):
        parts = [np.array(v, np.int32) for v in ([1, 5], [2, 5], [], [7], [], [1, 9])]
        np.testing.assert_array_equal(c.sorted_union(parts, 9), np.array([1, 2, 5, 7, 9], np.int32))

    def test_no_method_or_variant_omission(self):
        with self.assertRaises(AssertionError):
            c.sorted_union([np.empty(0, np.int32)]*5, 10)

    def test_upper_bound_stops_without_truncation(self):
        with self.assertRaises(AssertionError):
            c.sorted_union([np.array([1, 2], np.int32)]+[np.empty(0, np.int32)]*5, 1)

    def test_duplicate_or_wrong_dtype_rejected(self):
        for bad in (np.array([1, 1], np.int32), np.array([1], np.int64), np.array([-1], np.int32)):
            with self.assertRaises(AssertionError):
                c.sorted_union([bad]+[np.empty(0, np.int32)]*5, 9)

    def test_empty_case_explicit_typed_union(self):
        ids = c.sorted_union([np.empty(0, np.int32)]*6, 0)
        self.assertEqual(ids.dtype, np.int32)
        self.assertEqual(ids.shape, (0,))

    def test_nonprefix_previous_ids_membership(self):
        flags = c.member_flags(np.array([0, 2, 4, 5, 8, 10], np.int32),
            np.array([0, 4], np.int32), np.array([0, 4, 5, 8], np.int32), 11, 10, (2, 4))
        np.testing.assert_array_equal(flags['in_original_140000'], [1, 0, 1, 1, 1, 0])
        np.testing.assert_array_equal(flags['in_original_280000'], [1, 1, 1, 1, 1, 0])

    def test_member_validation_rejects_wrong_nesting(self):
        with self.assertRaises(AssertionError):
            c.member_flags(np.array([0], np.int32), np.array([2], np.int32),
                           np.array([0, 1], np.int32), 4, 4, (1, 2))

    def test_npz_nan_dtype_shape_roundtrip(self):
        arrays = {'ids': np.array([1, 4], np.int32), 'valid': np.array([np.nan, 1.2], np.float64),
                  'group': np.array([0, 1], np.int8), 'empty': np.empty((0, 3, 2), np.int32)}
        desc = c.descriptors(arrays)
        c.readback(c.f.coarse.npz_bytes(arrays), desc)
        bad = {**desc, 'ids': {**desc['ids'], 'dtype': '<i8'}}
        with self.assertRaises(AssertionError):
            c.readback(c.f.coarse.npz_bytes(arrays), bad)

    def test_all_six_outcomes_common_order_including_empty(self):
        variants = ['A', 'B']
        full = {tag+'_'+field: np.arange(10, dtype=np.float64 if field in ('first', 'raw', 'valid') else np.int32)
                for tag in variants for field in c.RESULT_FIELDS}
        for ids in (np.array([2, 7], np.int32), np.empty(0, np.int32)):
            six = np.stack([c.select_outcomes(full, ids, variants)['valid']]*3, axis=1)
            self.assertEqual(six.shape, (len(ids), 3, 2))
            for core in range(3):
                for variant in range(2):
                    np.testing.assert_array_equal(six[:, core, variant], ids.astype(np.float64))

    def test_full_and_phase_miss_index_integration(self):
        ids = np.arange(8, dtype=np.int32)
        cohorts = {'full_fine_RIGHT': ids, **{'phase'+str(k)+'_RIGHT': ids[ids % 4 == k] for k in range(4)}}
        valid = np.ones(8, np.float64)
        valid[[1, 4]] = np.nan
        misses = np.array([1, 4], np.int32)
        _, meta = c.a.encode_miss_mask(~np.isfinite(valid))
        record = {'mask_metadata': {'v': meta}, 'rows': [], 'pairs': []}
        for name, chosen in cohorts.items():
            record['rows'].append({'variant': 'v', 'cohort': name, 'right_miss': int(np.isin(chosen, misses).sum()), 'right_contacts': len(chosen)})
            if name != 'full_fine_RIGHT':
                record['pairs'].append({'variant': 'v', 'cohort': name, **c.a.miss_pair(misses, chosen, 4)})
        actual, proofs = c.check_misses({'v_valid': valid}, {}, cohorts, record, 'v', 4)
        np.testing.assert_array_equal(actual, misses)
        self.assertEqual(len(proofs), 5)
        record['pairs'][0]['added_index_sha256'] = 'broken'
        with self.assertRaises(AssertionError):
            c.check_misses({'v_valid': valid}, {}, cohorts, record, 'v', 4)

    def test_checkpoint_gzip_and_resource_preflight(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(c, 'RUN', Path(directory)), patch.object(c, 'resources', return_value={}) as guard:
            c.save_cp({'status': 'fixture', 'completed': {}, 'new_predictions': 0})
            cp = (c.RUN/'checkpoint.json').read_bytes()
            packed = list((c.RUN/'checkpoint_snapshots').glob('*.gz'))
            self.assertEqual(len(packed), 1)
            self.assertEqual(gzip.decompress(packed[0].read_bytes()), cp)
            self.assertEqual(packed[0].name.split('.')[0], hashlib.sha256(cp).hexdigest())
            self.assertTrue(guard.called)

    def test_frozen_lost_five_and_protocol_integration(self):
        self.assertEqual(c.base.file_hash(c.PROTOCOL), c.EXPECTED_PROTOCOL)
        job = next(j for j in c.f.jobs() if j['case']['id'] == c.protocol()['cases'][0] and j['core_id'] == 'linear_g0625')
        self.assertEqual(c.base.read_json(c.a.RUN/'runner_lock.json')['status'], 'stopped')
        record = c.base.read_json(c.a.RUN/'jobs'/(job['id']+'.json'))
        with np.load(c.a.RUN/'miss_masks'/(job['id']+'.npz'), allow_pickle=False) as masks:
            lost = c.a.decode_miss_mask(masks['w2000_m20_c100'], record['mask_metadata']['w2000_m20_c100'])
        self.assertEqual(len(lost), 5)
        self.assertEqual(c.base.array_hash(lost), c.LOST_FIVE_SHA)


if __name__ == '__main__':
    unittest.main()
