import unittest
import numpy as np
from packing import pack_points, unpack_points, array_hash


class PackingTests(unittest.TestCase):
    def test_roundtrip_exact_timestamp_and_count_bytes(self):
        time = np.arange(4000)*.02
        original = {'w_first': np.array([np.nan, time[100], time[-1]]),
                    'w_raw': np.array([time[0], np.nan, time[101]]),
                    'w_valid': np.full(3, np.nan), 'w_TP': np.array([0, 44, 2000], np.int32)}
        packed, meta = pack_points(original, time)
        restored = unpack_points(packed, meta, time)
        self.assertTrue(all(value.dtype == np.uint16 for value in packed.values()))
        for key in original:
            self.assertEqual(array_hash(original[key]), array_hash(restored[key]))

    def test_not_an_observation_time_is_rejected_not_rounded(self):
        with self.assertRaises(ValueError):
            pack_points({'x_raw': np.array([.02000000001])}, np.arange(10)*.02)

    def test_negative_count_rejected(self):
        with self.assertRaises(ValueError):
            pack_points({'x_FP': np.array([-1], np.int32)}, np.arange(10)*.02)

    def test_uint32_used_without_overflow(self):
        time = np.arange(70000)*.02
        values, meta = pack_points({'x_first': np.array([time[-1], np.nan]), 'x_FP': np.array([70000, 0], np.int32)}, time)
        self.assertEqual(values['x_first'].dtype, np.uint32)
        self.assertEqual(values['x_FP'].dtype, np.uint32)
        unpack_points(values, meta, time)

    def test_changed_time_reference_rejected(self):
        time = np.arange(20)*.02
        values, meta = pack_points({'x_raw': np.array([time[3]])}, time)
        with self.assertRaises(AssertionError):
            unpack_points(values, meta, time+.001)

    def test_tampered_payload_rejected(self):
        time = np.arange(20)*.02
        values, meta = pack_points({'x_raw': np.array([time[3]])}, time)
        values['x_raw'][0] += 1
        with self.assertRaises(AssertionError):
            unpack_points(values, meta, time)

    def test_noncanonical_nan_payload_is_not_silently_changed(self):
        value = np.array([0x7ff8000000000001], np.uint64).view(np.float64)
        with self.assertRaises(AssertionError):
            pack_points({'x_valid': value}, np.arange(20)*.02)


if __name__ == '__main__':
    unittest.main()
