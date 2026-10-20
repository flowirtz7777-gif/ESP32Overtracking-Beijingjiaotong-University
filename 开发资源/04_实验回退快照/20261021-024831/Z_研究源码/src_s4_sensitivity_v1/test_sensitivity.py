from __future__ import annotations

from datetime import datetime, timezone
import sys
import unittest
sys.dont_write_bytecode = True
import run_sensitivity as run


class SensitivityTests(unittest.TestCase):
    def test_only_36_new_predictions_and_shared_groups(self):
        jobs = run.jobs()
        self.assertEqual(len(jobs), 36)
        self.assertEqual({j['contact_tolerance_m'] for j in jobs}, {.025, .1})
        self.assertEqual(len({j['id'] for j in jobs}), 36)
        self.assertTrue(all(j['density_counts'] == [35000, 70000] for j in jobs))

    def test_density_subset_is_unique_frozen_stratified_prefix(self):
        group = run.np.repeat(run.np.arange(3), [23334, 23333, 23333])
        indices = run.subset_indices(group, 35000)
        self.assertEqual(len(run.np.unique(indices)), 35000)
        self.assertEqual(run.np.bincount(group[indices]).tolist(), [11667, 11667, 11666])
        self.assertTrue(run.np.all(indices >= 0) and run.np.all(indices < 70000))

    def test_saved_state_keeps_all_scoring_counts(self):
        v = run.pipeline.Variant(2, .05, 0)
        keys = ('first', 'raw', 'valid', *run.COUNTS)
        points = {v.tag+'_'+key: run.np.array([1, 2]) for key in keys}
        state = run.state_from_saved(points, v)
        self.assertEqual(set(state['point_counts']), set(run.COUNTS))
        self.assertTrue(run.np.array_equal(state['valid'], points[v.tag+'_valid']))

    def test_failure_partition_distinguishes_never_contact_and_early(self):
        targets = {'contact_time': run.np.array([5., run.np.nan, 8.]), 'front_ignored': run.np.zeros(3, dtype=bool),
                   'edge': run.np.array([2, 0, 2]), 'group': run.np.array([0, 2, 1])}
        state = {'valid': run.np.array([4.5, run.np.nan, run.np.nan]), 'point_counts': {'FP': run.np.array([2, 3, 4])}}
        result = run.diagnostic_counts(targets, state, 10)
        self.assertEqual(result['fp_frames_total'], 9)
        self.assertEqual(result['fp_never_contact_frames'], 3)
        self.assertEqual(result['fp_before_own_window_frames'], 6)
        self.assertEqual(result['right_late'], 1)
        self.assertEqual(result['right_window_miss'], 1)

    def test_density_pairs_include_method_minus_hold_effect_changes(self):
        rows = []
        for core, values in [('hold', [1., 2.]), ('linear_g0625', [3., 5.])]:
            for count, value in zip([35000, 70000], values):
                rows.append({'case_id': 'case', 'condition': 'clean', 'core_id': core,
                             'contact_tolerance_m': .05, 'margin_m': .05, 'confirmation_s': 0,
                             'target_count': count, 'right_pct': value, 'negative_fp_pct': value,
                             'common_2s_reference_fpr_pct': value, 'right_lead_p10_s': 1.})
        result = next(r for r in run.density_pairs(rows) if r['core_id'] == 'linear_g0625')
        self.assertEqual(result['right_pct_delta_pp'], 2.)
        self.assertEqual(result['right_pct_paired_effect_change_pp'], 1.)

    def test_tolerance_geometry_is_nested_and_contact_does_not_move_later(self):
        reference = {'time': run.np.array([0., .005, .01]), 'state': run.np.array([[0., 0, 0, 0], [.01, 0, 0, 0], [.02, 0, 0, 0]])}
        points = run.np.array([[0., -1.02], [0., -1.04], [0., -1.08], [0., -1.2]])
        segments, _, _ = run.complete_geometry(reference['state'])
        labels = [run.label_contacts(points, reference, segments, tolerance=t) for t in [.025, .05, .1]]
        self.assertEqual([run.np.isfinite(x['contact_time']).sum() for x in labels], [1, 2, 3])

    def test_future_poison_does_not_change_any_core_past_predictions(self):
        n = 24
        data = {'time': run.np.arange(n)*.02, 'state': run.np.zeros((n, 4)),
                'alpha': run.np.linspace(0, .1, n), 'v_B': run.np.full(n, 3.)}
        poisoned = {k: v.copy() for k, v in data.items()}
        poisoned['alpha'][16:] = -.2
        poisoned['state'][16:] = 10.
        from prediction import rollout
        for core in run.read_json(run.PROTOCOL)['core_configs']:
            method = run.pipeline.Method(core['mode'], gain=core['gain'], decay_s=core['decay_s'])
            a, b = rollout(data, method, .3), rollout(poisoned, method, .3)
            self.assertTrue(run.np.array_equal(a[:16], b[:16]))

    def test_deadline_is_today_noon_with_fixed_zone(self):
        deadline = datetime.fromisoformat(run.read_json(run.PROTOCOL)['execution']['deadline_local'])
        self.assertEqual(deadline.astimezone(timezone.utc).isoformat(), '2026-10-15T04:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
