import unittest
import numpy as np
import run_fine_RIGHT as f


class FineRIGHTTests(unittest.TestCase):
    def targets(self):
        return {'xy': np.array([[5.8, -1], [6, -1], [100, 100], [6.2, -1], [6.4, -1]], float),
            'group': np.array([0, 1, 2, 0, 1], np.int8),
            'contact_time': np.array([4, 4.2, np.nan, 4.4, 4.6]),
            'contact_index': np.array([800, 840, -1, 880, 920], np.int32),
            'edge': np.array([2, 2, 0, 2, 2], np.int8), 'front_ignored': np.zeros(5, bool)}

    def data(self):
        time = np.arange(401)*.02
        fine = np.arange(1601)*.005
        return {'time': time, 'state': np.column_stack((time, np.zeros((len(time), 3)))),
            'alpha': np.zeros(len(time)), 'v_B': np.ones(len(time)), 'fine_time': fine,
            'fine_state': np.column_stack((fine, np.zeros((len(fine), 3)))), 'true_phase': np.ones(len(time), np.int8)}

    def test_exact_integer_quota_matches_frozen_reservations(self):
        for n, expected in [(2453007, 272816885), (2497935, 277717631), (2584003, 287105930)]:
            self.assertEqual(3*f.quotas(n)['job']+2*1024**2, expected)
            self.assertGreater(f.quotas(n)['input'], 48*n)

    def test_quota_rejects_unknown_or_noninteger_population(self):
        for invalid in (-1, 1.1, None, True):
            with self.assertRaises(ValueError):
                f.quotas(invalid)

    def test_quota_requires_whole_and_run_and_physical_headroom(self):
        p = f.protocol()['execution']
        resource = {'experiment_bytes': p['experiment_budget_bytes']-100, 'run_bytes': p['new_run_budget_bytes']-100,
                    'free_bytes': p['reserve_bytes']+100}
        self.assertTrue(f.fits(resource, 100))
        self.assertFalse(f.fits(resource, 101))
        for key in ('experiment_bytes', 'run_bytes'):
            changed = {**resource, key: resource[key]+1}
            self.assertFalse(f.fits(changed, 100))
        self.assertFalse(f.fits({**resource, 'free_bytes': resource['free_bytes']-1}, 100))

    def test_target_prefix_and_main_order_byte_exact(self):
        target = self.targets()
        old = {k:v[:3] for k,v in target.items()}
        old['main_ids'] = np.array([1, 0])
        full = f.append_targets(old, {k:v[3:] for k,v in target.items()})
        for key in f.FIELDS:
            self.assertEqual(f.base.array_hash(full[key][:3]), f.base.array_hash(old[key]))
        np.testing.assert_array_equal(full['main_ids'], old['main_ids'])

    def test_target_missing_field_or_dtype_change_rejected(self):
        old = self.targets()
        old['main_ids'] = np.array([0])
        with self.assertRaises(AssertionError):
            f.append_targets(old, {'xy': old['xy']})
        delta = {k: old[k].copy() for k in f.FIELDS}
        delta['edge'] = delta['edge'].astype(np.int64)
        with self.assertRaises(AssertionError):
            f.append_targets(old, delta)

    def test_new_point_selection_uses_only_geometry_and_complete_phase(self):
        target = self.targets()
        target['front_ignored'][3] = True
        selected = f.geometry_delta_mask(target, np.array([True, False, False, False, False]), 5.)
        np.testing.assert_array_equal(selected, [False, True, False, False, True])
        with self.assertRaises(AssertionError):
            f.geometry_delta_mask(target, np.array([True]), 5.)

    def test_full_output_reconstruction_rejects_gaps(self):
        with self.assertRaises(AssertionError):
            f.merge_outputs({'v_TP': np.zeros(3, np.int32)}, {'v_TP': np.ones(2, np.int32)}, 6)

    def test_output_dtype_shape_nan_bytes_are_lossless(self):
        old = {'v_first': np.array([np.nan, 2., 2.02]), 'v_TP': np.array([0, 3, 5], np.int32)}
        delta = {'v_first': np.array([2.04, np.nan]), 'v_TP': np.array([9, 0], np.int32)}
        time = np.arange(300)*.02
        packed, metadata = f.coarse.pack_points(delta, time)
        decoded = f.coarse.unpack_points(packed, metadata, time)
        full = f.merge_outputs(old, decoded, 5)
        for key in old:
            self.assertEqual(f.base.array_hash(full[key]), f.base.array_hash(np.concatenate((old[key], delta[key]))))

    def test_actual_pipeline_all_methods_prefix_packing_summary_integration(self):
        data, targets = self.data(), self.targets()
        prefix = {k:v[:3] for k,v in targets.items()}
        variants = [f.pipeline.Variant(**v) for v in f.protocol()['variants']]
        for method in [f.pipeline.Method('hold'), f.pipeline.Method('linear', gain=.625), f.pipeline.Method('damped_linear', gain=1.25, decay_s=1)]:
            old = f.pipeline.evaluate(data, prefix, method, variants)
            full = f.pipeline.evaluate(data, targets, method, variants)
            for key, value in old['point_output'].items():
                self.assertEqual(f.base.array_hash(value), f.base.array_hash(full['point_output'][key][:3]))
            packed, metadata = f.coarse.pack_points({k:v[3:] for k,v in full['point_output'].items()}, data['time'])
            decoded = f.coarse.unpack_points(packed, metadata, data['time'])
            merged = f.merge_outputs(old['point_output'], decoded, 5)
            for key, value in full['point_output'].items():
                self.assertEqual(f.base.array_hash(value), f.base.array_hash(merged[key]))
            for before, after in zip(old['states'], full['states']):
                self.assertEqual(f.coarse.projected_summary(data, targets, after, np.arange(3)), f.pipeline.summarize(data, prefix, before))

    def test_fixed_prediction_prefix_is_causal_all_methods(self):
        raw = {'time': np.arange(80)*.02, 'state': np.zeros((80, 4)), 'alpha': np.linspace(0, .1, 80), 'v_B': np.ones(80)*3}
        changed = {k:v.copy() for k,v in raw.items()}
        for key in ('state', 'alpha', 'v_B'):
            changed[key][40:] += .3
        for method in [f.pipeline.Method('hold'), f.pipeline.Method('linear', gain=.625), f.pipeline.Method('damped_linear', gain=1.25, decay_s=1)]:
            np.testing.assert_array_equal(f.coarse.rollout(raw, method, .3)[:40], f.coarse.rollout(changed, method, .3)[:40])

    def test_cohorts_do_not_mix_negative_controls_or_new_points_into_main(self):
        target = self.targets()
        target['main_ids'] = np.array([0, 1, 2])
        selected = f.cohorts(target, 3, 5.)
        np.testing.assert_array_equal(selected['original_70000'], [0, 1, 2])
        np.testing.assert_array_equal(selected['complete_coarse_RIGHT'], [0, 1])
        np.testing.assert_array_equal(selected['complete_fine_RIGHT'], [0, 1, 3, 4])
        np.testing.assert_array_equal(selected['old_280000_near_negative_controls'], [2])

    def test_frozen_design_and_execution_boundaries(self):
        p = f.protocol()
        self.assertEqual(p['execution']['deadline_local'], '2026-10-17T14:00:00+08:00')
        self.assertEqual(p['execution']['experiment_budget_bytes'], 16*1024**3)
        self.assertEqual(p['execution']['workers'], p['execution']['max_inflight'])
        self.assertEqual(p['baseline_numeric'], p['baseline_formal']+p['baseline_diagnostic'])
        self.assertFalse(p['algorithm_search_allowed'])
        self.assertFalse(p['old_density_failure_overridden'])


if __name__ == '__main__':
    unittest.main()
