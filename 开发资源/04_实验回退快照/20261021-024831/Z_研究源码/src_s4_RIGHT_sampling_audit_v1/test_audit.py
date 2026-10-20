import unittest
import audit_sampling as a

np = a.np


class AuditTests(unittest.TestCase):
    def test_phase_partition_including_negative_cells(self):
        cells = np.array([[-3, -3], [-2, -3], [-3, -2], [-2, -2], [0, 0], [1, 1]])
        np.testing.assert_array_equal(a.phases(cells * .0125), [3, 2, 1, 0, 0, 3])
        with self.assertRaises(AssertionError):
            a.phases(np.array([[.001, 0.]]))

    def test_added_indices_empty_and_nonempty_roundtrip(self):
        for full in [np.array([], dtype=np.int32), np.arange(17, dtype=np.int32)]:
            packed, added = a.encode_omissions(full, full[::2])
            np.testing.assert_array_equal(added, full[1::2])
            np.testing.assert_array_equal(a.decode_omissions(full, packed, len(full)), added)

    def test_membership_length_checked(self):
        with self.assertRaises(AssertionError):
            a.decode_omissions(np.array([1, 3], dtype=np.int32), np.array([0], dtype=np.uint8), 1)

    def test_missing_indices_not_netted_against_other_points(self):
        full = np.array([4, 13, 21], dtype=np.int32)
        _, added = a.encode_omissions(full, np.array([0, 4, 8], dtype=np.int32))
        np.testing.assert_array_equal(added, [13, 21])

    def test_metric_names_and_undefined_lead(self):
        row = {'right_contacts': 20, 'right_miss': 2, 'right_pct': 15., 'right_no_before': 1, 'right_lead_p10_s': 1.4}
        self.assertEqual(a.metrics(row), dict(zip(a.METRICS, [10., 15., 5., 1.4])))
        p = a.base.read_json(a.PROTOCOL)
        values = dict(zip(a.METRICS, [0., 0., 0., None]))
        self.assertFalse(a.difference(values, values, p)['RIGHT_component_numeric_limits_met'])

    def test_original_index_projection_and_all_phase_coverage(self):
        n = 280004
        targets = {'xy': np.column_stack([np.arange(n) * .0125, np.zeros(n)]),
                   'contact_time': np.full(n, 3.), 'front_ignored': np.zeros(n, dtype=bool),
                   'edge': np.full(n, 2), 'main_ids': np.array([1, 3, 5], dtype=np.int32)}
        targets['front_ignored'][3] = True
        result = a.cohorts(targets, np.array([0, 3, 6], dtype=np.int32), 8.)
        np.testing.assert_array_equal(result['original_70000_RIGHT'], [1, 5])
        np.testing.assert_array_equal(result['original_140000_RIGHT'], [0, 6])
        self.assertEqual(len(result), 8)

    def test_thresholds_are_not_relaxed(self):
        p = a.base.read_json(a.PROTOCOL)
        origin = dict(zip(a.METRICS, [0., 0., 0., 1.]))
        changed = {**origin, 'RIGHT_window_miss_pct': .200001}
        self.assertFalse(a.difference(changed, origin, p)['RIGHT_component_numeric_limits_met'])
        changed = {**origin, 'RIGHT_valid_lead_P10_s': 1.050001}
        self.assertFalse(a.difference(changed, origin, p)['RIGHT_component_numeric_limits_met'])


if __name__ == '__main__':
    unittest.main()
