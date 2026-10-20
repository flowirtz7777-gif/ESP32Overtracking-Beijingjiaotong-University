import unittest
import numpy as np
from run_RIGHT_census import (append_targets, block_fits, projected_summary, merge_outputs,
                              pack_points, unpack_points, pipeline, rollout, base, census)


class RIGHTCensusTests(unittest.TestCase):
    def old_targets(self):
        n = 280000
        return {'xy': np.column_stack((np.arange(n), np.zeros(n))), 'group': np.zeros(n, np.int8),
                'contact_time': np.full(n, np.nan), 'contact_index': np.full(n, -1, np.int32),
                'edge': np.zeros(n, np.int8), 'front_ignored': np.zeros(n, bool), 'main_ids': np.arange(70000)}

    def test_reserves_all_three_outputs_and_fixed_headroom(self):
        self.assertTrue(block_fits(100, 100, [30, 30, 30], 10))
        self.assertFalse(block_fits(99, 100, [30, 30, 30], 10))
        self.assertFalse(block_fits(1000, 89, [30, 30, 30], 10))

    def test_prefix_targets_and_main_order_exact(self):
        old = self.old_targets()
        delta = {key: value[:3].copy() for key, value in old.items() if key != 'main_ids'}
        delta['xy'][:, 0] += 300000
        target = append_targets(old, delta)
        self.assertEqual(len(target['xy']), 280003)
        for key in delta:
            np.testing.assert_array_equal(target[key][:280000], old[key])
        np.testing.assert_array_equal(target['main_ids'], old['main_ids'])

    def test_missing_target_field_is_rejected(self):
        with self.assertRaises(AssertionError):
            append_targets(self.old_targets(), {'xy': np.zeros((3, 2))})

    def test_full_prefix_delta_reconstruction_dtype_shape_and_bytes(self):
        old = {'x_first': np.full(280000, np.nan), 'x_TP': np.zeros(280000, np.int32)}
        delta = {'x_first': np.array([2., 2.02]), 'x_TP': np.array([3, 4], np.int32)}
        restored = merge_outputs(old, delta, 280002)
        for key in old:
            self.assertEqual(base.array_hash(restored[key]), base.array_hash(np.concatenate((old[key], delta[key]))))

    def test_reconstruction_rejects_incomplete_indices(self):
        with self.assertRaises(AssertionError):
            merge_outputs({'x_TP': np.zeros(280000, np.int32)}, {'x_TP': np.ones(2, np.int32)}, 280003)

    def test_frozen_prediction_prefix_is_causal_for_all_three_methods(self):
        observed = {'time': np.arange(80)*.02, 'state': np.zeros((80, 4)),
                    'alpha': np.linspace(0, .1, 80), 'v_B': np.full(80, 3.)}
        changed = {key: value.copy() for key, value in observed.items()}
        changed['state'][40:] += 1
        changed['alpha'][40:] = -.2
        changed['v_B'][40:] = 5.
        for method in (pipeline.Method('hold'), pipeline.Method('linear', gain=.625), pipeline.Method('damped_linear', gain=1.25, decay_s=1)):
            np.testing.assert_array_equal(rollout(observed, method, .3)[:40], rollout(changed, method, .3)[:40])

    def test_evaluation_prefix_packing_and_cohort_summary_integration(self):
        time = np.arange(401)*.02
        fine = np.arange(1601)*.005
        data = {'time': time, 'state': np.column_stack((time, np.zeros((len(time), 3)))),
                'alpha': np.zeros(len(time)), 'v_B': np.ones(len(time)),
                'fine_time': fine, 'fine_state': np.column_stack((fine, np.zeros((len(fine), 3)))),
                'true_phase': np.ones(len(time), dtype=np.int8)}
        targets = {'xy': np.array([[5.8, -1], [6., -1], [100., 100.], [6.2, -1], [6.4, -1]]),
                   'group': np.array([0, 1, 2, 0, 1]), 'contact_time': np.array([4., 4.2, np.nan, 4.4, 4.6]),
                   'contact_index': np.array([800, 840, -1, 880, 920], np.int32),
                   'edge': np.array([2, 2, 0, 2, 2]), 'front_ignored': np.zeros(5, bool)}
        variants = [pipeline.Variant(2, .05, 0), pipeline.Variant(2, .02, .1)]
        small = {key: value[:3] for key, value in targets.items()}
        reference = pipeline.evaluate(data, small, pipeline.Method('hold'), variants)
        full = pipeline.evaluate(data, targets, pipeline.Method('hold'), variants)
        for key, value in full['point_output'].items():
            np.testing.assert_array_equal(value[:3], reference['point_output'][key])
        packed, meta = pack_points({key: value[3:] for key, value in full['point_output'].items()}, time)
        delta = unpack_points(packed, meta, time)
        restored = census.dep.reconstruct_delta(reference['point_output'], delta, np.arange(3), np.arange(3, 5), 5)
        for key, value in full['point_output'].items():
            self.assertEqual(base.array_hash(value), base.array_hash(restored[key]))
        for original_state, full_state in zip(reference['states'], full['states']):
            self.assertEqual(projected_summary(data, targets, full_state, np.arange(3)), pipeline.summarize(data, small, original_state))


if __name__ == '__main__':
    unittest.main()
