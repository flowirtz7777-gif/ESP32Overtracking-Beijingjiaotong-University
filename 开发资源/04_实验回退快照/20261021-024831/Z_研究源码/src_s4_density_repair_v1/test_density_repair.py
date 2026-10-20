import sys
import unittest
sys.dont_write_bytecode = True
import run_density_repair as run


class DensityRepairTests(unittest.TestCase):
    def test_target_extension_preserves_every_original_coordinate_and_order(self):
        old_xy = run.np.column_stack((run.np.arange(12), run.np.zeros(12))).astype(float)
        old_group = run.np.repeat(run.np.arange(3), 4).astype('int8')
        extra_xy = run.np.concatenate((old_xy, run.np.column_stack((100+run.np.arange(30), run.np.zeros(30))).astype(float)))
        extra_group = run.np.concatenate((old_group, run.np.repeat(run.np.arange(3), 10))).astype('int8')
        xy, group, main = run.augment_pool({'xy': old_xy, 'group': old_group}, extra_xy, extra_group, 24)
        self.assertEqual(len(run.np.unique(xy, axis=0)), 24)
        self.assertTrue(run.np.array_equal(xy[main], old_xy))
        self.assertTrue(run.np.array_equal(group[main], old_group))

    def test_target_extension_fails_without_enough_unique_near_field_points(self):
        old = {'xy': run.np.column_stack((run.np.arange(6), run.np.zeros(6))), 'group': run.np.repeat(run.np.arange(3), 2)}
        with self.assertRaises(AssertionError):
            run.augment_pool(old, old['xy'], old['group'], 12)

    def test_main_only_target_set_is_not_duplicated(self):
        old = {'xy': run.np.column_stack((run.np.arange(6), run.np.zeros(6))), 'group': run.np.repeat(run.np.arange(3), 2)}
        xy, group, main = run.augment_pool(old, old['xy'], old['group'], 6)
        self.assertTrue(run.np.array_equal(xy, old['xy']))

    def test_frozen_design_has_54_jobs_and_216_rows(self):
        jobs = run.jobs()
        self.assertEqual(len(jobs), 54)
        self.assertEqual(len({j['id'] for j in jobs}), 54)
        self.assertEqual({j['contact_tolerance_m'] for j in jobs}, {.025, .05, .1})
        self.assertEqual(sum(len(j['variants'])*len(j['density_counts']) for j in jobs), 216)

    def test_density_pairs_have_108_groups_and_correct_hold_differences(self):
        p = run.base.read_json(run.PROTOCOL)
        rows = []
        for case in p['cases']:
            for core in p['core_configs']:
                for condition in p['conditions']:
                    for tol in p['contact_tolerances_m']:
                        for v in p['variants']:
                            for count in p['density_counts']:
                                rows.append({'case_id': case, 'core_id': core['id'], 'condition': condition,
                                             'contact_tolerance_m': tol, 'margin_m': v['margin'], 'confirmation_s': v['confirmation'],
                                             'target_count': count, 'right_pct': .01, 'negative_fp_pct': 1.,
                                             'common_2s_reference_fpr_pct': .1, 'right_lead_p10_s': 1.})
        pairs = run.density_pairs(rows)
        self.assertEqual(len(pairs), 108)
        self.assertTrue(all(x['negative_fp_pct_paired_effect_change_pp'] == 0 for x in pairs))

    def test_new_target_set_does_not_change_core_causality(self):
        from prediction import rollout
        n = 24
        data = {'time': run.np.arange(n)*.02, 'state': run.np.zeros((n, 4)), 'alpha': run.np.linspace(0, .1, n), 'v_B': run.np.full(n, 3.)}
        future = {k: v.copy() for k, v in data.items()}
        future['alpha'][16:] = .3
        future['state'][16:] = 20
        for core in run.base.read_json(run.PROTOCOL)['core_configs']:
            method = run.pipeline.Method(core['mode'], gain=core['gain'], decay_s=core['decay_s'])
            self.assertTrue(run.np.array_equal(rollout(data, method, .3)[:16], rollout(future, method, .3)[:16]))


if __name__ == '__main__':
    unittest.main()
