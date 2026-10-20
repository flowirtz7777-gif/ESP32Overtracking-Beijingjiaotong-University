import unittest
import numpy as np
import run_inventory as a


class InventoryTests(unittest.TestCase):
    def test_stream_hash_matches_full_array(self):
        data = np.arange(90, dtype=np.float64).reshape(45, 2)
        stream = a.array_stream(data.dtype, data.shape)
        for chunk in np.array_split(data, 7):
            stream.update(np.ascontiguousarray(chunk).tobytes())
        self.assertEqual(stream.hexdigest(), a.base.array_hash(data))

    def test_nested_phase_includes_negative_integer_coordinates(self):
        x = np.array([-4, -3, -2, -1, 0, 1, 2])
        np.testing.assert_array_equal(a.coarse_phase(x, x), [1, 0, 1, 0, 1, 0, 1])

    def test_quota_reserves_three_methods_and_headroom(self):
        self.assertEqual(a.quota(727343), 84581456)
        self.assertGreater(a.quota(2500000), 104*1024**2)

    def test_unknown_count_not_resource_admitted(self):
        for value in (None, -1, 2.5):
            with self.assertRaises(ValueError):
                a.quota(value)

    def test_chunk_raster_coarse_phase_reconstructs_coarse_enumerator(self):
        body = a.shapely.box(-.1, -.1, .2, .1)
        right = a.shapely.linestrings(np.array([[-.1, -.1], [.2, -.1]]))
        p = {'grid_spacing_m': .00625, 'contact_tolerance_m': .05, 'buffer_quad_segs': 32, 'chunk_point_budget': 2000}
        fine = list(a.chunks(body, right, p))
        coarse_xy = np.concatenate([c['xy'][c['coarse_positive']] for c in fine])
        coarse_group = np.concatenate([c['group'][c['coarse_positive']] for c in fine])
        expected_xy, expected_group, capacity = a.dep.enumerate_positive(body, right, {**p, 'grid_spacing_m': .0125})
        np.testing.assert_array_equal(coarse_xy, expected_xy)
        np.testing.assert_array_equal(coarse_group, expected_group)
        np.testing.assert_array_equal(np.sum([c['coarse_capacity'] for c in fine], axis=0), capacity)

    def test_chunk_labels_equal_original_labeler_on_curved_fixture(self):
        time = np.arange(81)*.02
        state = np.column_stack((time, .2*np.sin(time), .1*np.sin(time), .03*np.cos(time)))
        reference = {'time': time, 'state': state}
        segments, _, _ = a.dep.complete_geometry(state)
        xy = np.random.default_rng(20261016).uniform([-14, -4], [5, 4], (800, 2))
        tree = a.dep.build_temporal_tree(segments, 16)
        expected = a.dep.label_contacts(xy, reference, segments)
        parts = [a.dep.label_from_tree(part, reference, segments, tree) for part in np.array_split(xy, 5)]
        for k in expected:
            np.testing.assert_array_equal(np.concatenate([p[k] for p in parts]), expected[k])


if __name__ == '__main__':
    unittest.main()
