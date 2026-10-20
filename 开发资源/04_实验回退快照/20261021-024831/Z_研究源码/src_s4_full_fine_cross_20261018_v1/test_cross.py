import copy
import io
import unittest
import numpy as np
import run_cross as r


def point_fixture(n=11):
    time = np.arange(0, 37.08, .02)
    arrays = {}
    for tag in ('w2000_m20_c0', 'w2000_m50_c100'):
        for field in ('first', 'raw', 'valid'):
            value = np.full(n, np.nan, np.float64)
            value[::2] = time[np.arange(len(value[::2])) % len(time)]
            arrays[tag+'_'+field] = value
        for field in r.f.COUNT_FIELDS:
            arrays[tag+'_'+field] = (np.arange(n) % len(time)).astype(np.int32)
    return arrays, time


class CrossTests(unittest.TestCase):
    def test_all_eighteen_arrays_roundtrip(self):
        arrays, times = point_fixture()
        packed, metadata = r.f.coarse.pack_points(arrays, times)
        restored = r.independent_decode(packed, metadata, times)
        self.assertEqual(len(restored), 18)
        for k in arrays:
            self.assertEqual(r.base.array_hash(arrays[k]), r.base.array_hash(restored[k]))

    def test_actual_observation_frame_bound(self):
        arrays, times = point_fixture()
        self.assertEqual(len(times), 1854)
        packed, metadata = r.f.coarse.pack_points(arrays, times)
        self.assertTrue(all(v.dtype == np.uint16 for v in packed.values()))

    def test_complete_npz_integration(self):
        arrays, times = point_fixture(100001)
        packed, meta = r.f.coarse.pack_points(arrays, times)
        blob = r.f.coarse.npz_bytes(packed)
        with np.load(io.BytesIO(blob)) as saved:
            result = r.independent_decode({k:saved[k] for k in saved.files}, meta, times)
        self.assertEqual(r.q.c.descriptors(result), r.q.c.descriptors(arrays))

    def test_empty_eighteen_arrays(self):
        arrays, times = point_fixture(0)
        packed, meta = r.f.coarse.pack_points(arrays, times)
        result = r.independent_decode(packed, meta, times)
        self.assertTrue(all(x.shape == (0,) for x in result.values()))

    def test_timestamp_range_rejected(self):
        arrays, times = point_fixture()
        packed, meta = r.f.coarse.pack_points(arrays, times)
        packed['w2000_m20_c0_valid'][0] = len(times)
        with self.assertRaises(AssertionError):
            r.independent_decode(packed, meta, times)

    def test_count_range_rejected(self):
        arrays, times = point_fixture()
        packed, meta = r.f.coarse.pack_points(arrays, times)
        packed['w2000_m20_c0_TP'][0] = len(times)+1
        with self.assertRaises(AssertionError):
            r.independent_decode(packed, meta, times)

    def test_nonexact_timestamp_rejected(self):
        arrays, times = point_fixture()
        arrays['w2000_m20_c0_first'][0] = .013
        with self.assertRaises(ValueError):
            r.f.coarse.pack_points(arrays, times)

    def test_missing_array_rejected(self):
        arrays, times = point_fixture()
        packed, meta = r.f.coarse.pack_points(arrays, times)
        packed.pop('w2000_m20_c0_FP')
        with self.assertRaises(AssertionError):
            r.independent_decode(packed, meta, times)

    def test_dtype_corruption_rejected(self):
        arrays, times = point_fixture()
        packed, meta = r.f.coarse.pack_points(arrays, times)
        packed['w2000_m20_c0_FP'] = packed['w2000_m20_c0_FP'].astype(np.uint32)
        with self.assertRaises(AssertionError):
            r.independent_decode(packed, meta, times)

    def test_sha_corruption_rejected(self):
        arrays, times = point_fixture()
        packed, meta = r.f.coarse.pack_points(arrays, times)
        packed['w2000_m20_c0_FP'][0] += 1
        with self.assertRaises(AssertionError):
            r.independent_decode(packed, meta, times)

    def test_packbits_identity(self):
        ids = np.array([0, 7, 8, 100, 1000000], np.int32)
        packed, meta = r.mask_encode(ids, 1000001)
        np.testing.assert_array_equal(r.mask_decode(packed, meta), ids)

    def test_empty_packbits(self):
        for n in (0, 1, 9, 100):
            packed, meta = r.mask_encode(np.array([], np.int32), n)
            self.assertEqual(r.mask_decode(packed, meta).shape, (0,))

    def test_duplicate_and_unsorted_ids_rejected(self):
        for ids in ([1, 1], [2, 1], [-1], [10]):
            with self.assertRaises(AssertionError):
                r.mask_encode(np.array(ids, np.int32), 10)

    def test_mask_corruption_rejected(self):
        packed, meta = r.mask_encode(np.array([0], np.int32), 10)
        packed[0] ^= 1
        with self.assertRaises(AssertionError):
            r.mask_decode(packed, meta)

    def test_mask_padding_rejected(self):
        packed, meta = r.mask_encode(np.array([0], np.int32), 9)
        packed[-1] |= 128
        meta['packed_sha256'] = r.base.array_hash(packed)
        with self.assertRaises(AssertionError):
            r.mask_decode(packed, meta)

    def test_quota_actual_dimensions(self):
        for n in (3460350, 3514390, 3642724):
            self.assertGreater(r.quota(n), 36*n)

    def test_quota_invalid_dimension(self):
        for n in (-1, 1.5):
            with self.assertRaises(AssertionError):
                r.quota(n)

    def test_all_four_contrasts_and_interaction_with_null(self):
        rows = [{**{k: None for k in r.factors.METRICS}, 'variant': tag, 'right_miss': 0}
                for tag in r.factors.CELLS.values()]
        misses = {tag: np.array([], np.int32) for tag in r.factors.CELLS.values()}
        result, indices = r.factors.contrasts(rows, misses, case='empty', method='hold', cohort='negative', prefix='test')
        self.assertEqual(len(result), 5)
        self.assertEqual(len(indices), 8)
        self.assertIsNone(result[-1]['metric_difference_of_differences']['right_lead_p10_s'])


if __name__ == '__main__':
    unittest.main()
