import sys
import unittest
sys.dont_write_bytecode = True
import run_density_repair_v2 as run


class DensityRepairV2Tests(unittest.TestCase):
    def test_design_has_54_new_jobs_and_216_score_rows(self):
        jobs = run.jobs()
        self.assertEqual(len(jobs), 54)
        self.assertEqual(len({j['id'] for j in jobs}), 54)
        self.assertTrue(all(j['density_counts'] == [140000, 280000] for j in jobs))
        self.assertEqual(sum(len(j['variants'])*len(j['density_counts']) for j in jobs), 216)

    def test_full_design_has_108_density_pairs(self):
        p = run.base.read_json(run.PROTOCOL)
        rows = []
        for case in p['cases']:
            for core in p['core_configs']:
                for condition in p['conditions']:
                    for tolerance in p['contact_tolerances_m']:
                        for v in p['variants']:
                            for count in p['density_counts']:
                                rows.append({'case_id': case, 'core_id': core['id'], 'condition': condition,
                                             'contact_tolerance_m': tolerance, 'margin_m': v['margin'], 'confirmation_s': v['confirmation'],
                                             'target_count': count, 'right_pct': 1., 'negative_fp_pct': 1.,
                                             'common_2s_reference_fpr_pct': .1, 'right_lead_p10_s': 1.})
        self.assertEqual(len(run.density_pairs(rows)), 108)

    def test_nested_extension_preserves_both_old_coordinate_sets(self):
        main = {'xy': run.np.column_stack((run.np.arange(12), run.np.zeros(12))).astype(float),
                'group': run.np.repeat(run.np.arange(3), 4).astype('int8')}
        pool = run.np.column_stack((100+run.np.arange(120), run.np.zeros(120))).astype(float)
        groups = run.np.repeat(run.np.arange(3), 40).astype('int8')
        old_xy, old_groups, _ = run.augment_pool(main, pool, groups, 24)
        full, full_groups, old_ids = run.augment_pool({'xy': old_xy, 'group': old_groups}, pool, groups, 48)
        self.assertTrue(run.np.array_equal(full[old_ids], old_xy))
        self.assertTrue(run.np.array_equal(full[run.subset_indices(full_groups, 12)], main['xy']))
        self.assertEqual(len(run.np.unique(full, axis=0)), 48)

    def test_delta_reconstruction_is_byte_exact_including_nan_and_integer_counts(self):
        old_ids = run.np.array([0, 2, 4], dtype='int32')
        new_ids = run.np.array([1, 3, 5], dtype='int32')
        values = {'valid': run.np.array([run.np.nan, 1.1, 2.2, run.np.nan, 3.3, 4.4]),
                  'FP': run.np.array([0, 10, 20, 30, 0, 50], dtype='int32')}
        old = {key: value[old_ids] for key, value in values.items()}
        delta = {key: value[new_ids] for key, value in values.items()}
        restored = run.reconstruct_delta(old, delta, old_ids, new_ids, 6)
        for key in values:
            self.assertEqual(run.base.array_hash(restored[key]), run.base.array_hash(values[key]))

    def test_delta_rejects_overlapping_or_missing_indices(self):
        with self.assertRaises(AssertionError):
            run.reconstruct_delta({'x': run.np.array([1, 2])}, {'x': run.np.array([3, 4])},
                                  run.np.array([0, 1]), run.np.array([1, 3]), 4)

    def test_delta_rejects_changed_dtype(self):
        with self.assertRaises(AssertionError):
            run.reconstruct_delta({'x': run.np.array([1], dtype='int32')}, {'x': run.np.array([2], dtype='int64')},
                                  run.np.array([0]), run.np.array([1]), 2)

    def test_unchanged_methods_are_causal(self):
        from prediction import rollout
        n = 24
        data = {'time': run.np.arange(n)*.02, 'state': run.np.zeros((n, 4)), 'alpha': run.np.linspace(0, .1, n), 'v_B': run.np.full(n, 3.)}
        future = {k: v.copy() for k, v in data.items()}
        future['alpha'][16:] = .3
        future['state'][16:] = 20
        for core in run.base.read_json(run.PROTOCOL)['core_configs']:
            m = run.pipeline.Method(core['mode'], gain=core['gain'], decay_s=core['decay_s'])
            self.assertTrue(run.np.array_equal(rollout(data, m, .3)[:16], rollout(future, m, .3)[:16]))


if __name__ == '__main__':
    unittest.main()
