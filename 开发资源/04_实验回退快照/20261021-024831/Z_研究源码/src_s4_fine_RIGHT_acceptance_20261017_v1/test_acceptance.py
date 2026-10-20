import unittest
import numpy as np
import analyze_fine_RIGHT as a


class AcceptanceTests(unittest.TestCase):
    def targets(self):
        return {'xy': np.array([[0, 0], [.0125, 0], [.00625, 0], [0, .00625], [.00625, .00625]]),
            'group': np.array([0, 2, 1, 0, 1], np.int8), 'contact_time': np.array([4, np.nan, 4.2, 4.4, 4.6]),
            'contact_index': np.array([800, -1, 840, 880, 920], np.int32),
            'edge': np.array([2, 0, 2, 2, 2], np.int8), 'front_ignored': np.zeros(5, bool)}

    def metric(self, value=0):
        p = a.protocol()
        return {k: value for k in p['absolute_rate_fields']+p['lead_quantile_fields']}

    def test_integer_phase_rule_including_negative_coordinates(self):
        xy = np.array([[0, 0], [.00625, 0], [0, .00625], [.00625, .00625], [-.00625, -.00625]])
        np.testing.assert_array_equal(a.phases(xy), [0, 1, 2, 3, 3])

    def test_off_grid_coordinates_rejected(self):
        with self.assertRaises(AssertionError):
            a.phases(np.array([[.001, 0]]))

    def test_phase_partition_and_coarse_prefix_identity(self):
        result, phase = a.cohorts(self.targets(), 5, 2)
        np.testing.assert_array_equal(result['full_fine_RIGHT'], [0, 2, 3, 4])
        for k, expected in enumerate(([0], [2], [3], [4])):
            np.testing.assert_array_equal(result['phase'+str(k)+'_RIGHT'], expected)
        target = self.targets()
        target['xy'][4] = [.025, 0]
        with self.assertRaises(AssertionError):
            a.cohorts(target, 5, 2)

    def test_packbits_preserves_complete_sorted_indices_and_dtype(self):
        mask = np.zeros(19, bool)
        mask[[0, 3, 18]] = True
        packed, metadata = a.encode_miss_mask(mask)
        restored = a.decode_miss_mask(packed, metadata)
        np.testing.assert_array_equal(restored, np.array([0, 3, 18], np.int32))
        self.assertEqual(a.base.array_hash(restored), metadata['sorted_index_array_sha256'])
        empty, meta = a.encode_miss_mask(np.zeros(0, bool))
        self.assertEqual(len(a.decode_miss_mask(empty, meta)), 0)

    def test_mask_tampering_length_and_padding_rejected(self):
        packed, metadata = a.encode_miss_mask(np.zeros(9, bool))
        changed = packed.copy()
        changed[0] = 1
        with self.assertRaises(AssertionError):
            a.decode_miss_mask(changed, metadata)
        with self.assertRaises(AssertionError):
            a.decode_miss_mask(packed[:-1], metadata)
        changed = packed.copy()
        changed[-1] = 128
        forged = {**metadata, 'packed_array_sha256': a.base.array_hash(changed)}
        with self.assertRaises(AssertionError):
            a.decode_miss_mask(changed, forged)

    def test_added_removed_indices_and_zero_claim_not_netted(self):
        result = a.miss_pair(np.array([0, 4], np.int32), np.array([1, 2, 3], np.int32), 3)
        self.assertEqual(result['added_count'], 2)
        self.assertEqual(result['removed_count'], 0)
        self.assertEqual(result['added_indices_in_new_target_suffix_count'], 1)
        self.assertTrue(result['zero_miss_claim_lost'])
        self.assertEqual(result['added_index_sha256'], a.base.array_hash(np.array([0, 4], np.int32)))

    def test_undefined_metric_is_not_zero_or_pass(self):
        reference = self.metric()
        candidate = {**reference, 'exit_right_pct': None}
        result = a.difference(candidate, reference, a.protocol())
        self.assertFalse(result['numeric_limits_met'])
        self.assertIn('exit_right_pct', result['undefined_metrics'])
        self.assertIsNone(result['metrics']['exit_right_pct']['difference'])

    def test_absolute_and_effect_limits_are_not_relaxed_or_netted(self):
        p, zero = a.protocol(), self.metric()
        boundary = {**zero, 'right_pct': .2, 'right_lead_p10_s': -.05}
        self.assertTrue(a.difference(boundary, zero, p)['numeric_limits_met'])
        failed = {**zero, 'right_pct': .200001, 'exit_right_pct': -.200001}
        self.assertFalse(a.difference(failed, zero, p)['numeric_limits_met'])
        self.assertFalse(a.difference(failed, zero, p, effect=True)['numeric_limits_met'])
        self.assertFalse(a.difference({**zero, 'right_lead_p10_s': .050001}, zero, p)['numeric_limits_met'])

    def test_method_minus_hold_effect_compares_same_cohort(self):
        p = a.protocol()
        full = a.method_effect(self.metric(2), self.metric(1), p)
        phase = a.method_effect(self.metric(3), self.metric(2), p)
        self.assertTrue(a.difference(phase, full, p, effect=True)['numeric_limits_met'])
        unknown = a.method_effect({**self.metric(3), 'right_pct': None}, self.metric(2), p)
        self.assertFalse(a.difference(unknown, full, p, effect=True)['numeric_limits_met'])

    def test_stratum_composition_is_integer_checked_and_decomposed(self):
        subset = {'right_contacts':100, 'right_pct':15, 'stratum_right_rows':[
            {'group':0, 'right_contacts':50, 'right_insufficient_pct':20},
            {'group':1, 'right_contacts':50, 'right_insufficient_pct':10}]}
        full = {'right_contacts':100, 'right_pct':3, 'stratum_right_rows':[
            {'group':0, 'right_contacts':10, 'right_insufficient_pct':30},
            {'group':1, 'right_contacts':90, 'right_insufficient_pct':0}]}
        result = a.composition(subset, full)
        self.assertFalse(result['integer_stratum_proportions_exactly_equal'])
        self.assertAlmostEqual(result['within_stratum_term_pp'], 0)
        self.assertAlmostEqual(result['composition_term_pp'], 12)
        self.assertAlmostEqual(result['reconstruction_residual_pp'], 0)

    def test_layer_descriptions_keep_misses_and_half_weights_descriptive(self):
        target = self.targets()
        state = {'valid':np.array([np.nan, np.nan, 3., 4., 3.]), 'first':np.array([2., np.nan, 3., 4., 3.])}
        layers, weighted = a.describe_layers(target, state, np.array([0, 2, 3, 4]))
        self.assertEqual(sum(row['miss_count'] for row in layers), 1)
        self.assertIsNotNone(weighted)
        _, absent = a.describe_layers(target, state, np.array([0, 3]))
        self.assertIsNone(absent)

    def test_frozen_evaluator_summary_and_miss_index_integration(self):
        t, fine = np.arange(401)*.02, np.arange(1601)*.005
        data = {'time':t, 'state':np.column_stack((t,np.zeros((len(t),3)))), 'alpha':np.zeros(len(t)),
            'v_B':np.ones(len(t)), 'fine_time':fine, 'fine_state':np.column_stack((fine,np.zeros((len(fine),3)))),
            'true_phase':np.ones(len(t),np.int8)}
        targets = self.targets()
        targets['xy'] = np.array([[5.8,-1],[100,100],[6.00625,-1],[6.2,-.99375],[6.40625,-.99375]])
        target_ids, phase = a.cohorts(targets, 5., 2)
        result = a.pipeline.evaluate(data,targets,a.pipeline.Method('hold'),[a.pipeline.Variant(2,.02,.1)])
        state = result['states'][0]
        ids = target_ids['full_fine_RIGHT']
        row = a.f.coarse.projected_summary(data,targets,state,ids)
        mask = np.zeros(len(targets['xy']),bool)
        mask[ids] = ~np.isfinite(state['valid'][ids])
        packed, metadata = a.encode_miss_mask(mask)
        restored = a.decode_miss_mask(packed,metadata)
        self.assertEqual(row['right_miss'],len(restored))
        for name, chosen in target_ids.items():
            sub = a.f.coarse.projected_summary(data,targets,state,chosen)
            pair = a.miss_pair(restored,chosen,2)
            self.assertEqual(pair['subset_misses'],sub['right_miss'])
            self.assertEqual(pair['removed_count'],0)


if __name__ == '__main__':
    unittest.main()
