import unittest
import review_foundation as r

np = r.np


class ReviewTests(unittest.TestCase):
    def test_exact_existing_lossless_output_reservations(self):
        self.assertEqual(r.job_quota(727343), 27494768)
        self.assertEqual(r.job_quota(736455), 27826080)
        self.assertEqual(r.job_quota(778721), 29362872)

    def test_whole_three_method_case_block_plus_headroom(self):
        needed = 3*r.job_quota(1000)+2*1024**2
        self.assertTrue(r.three_method_block_fits(1000, needed))
        self.assertFalse(r.three_method_block_fits(1000, needed-1))

    def test_output_only_maximum_respects_exact_boundary(self):
        remaining = 100*1024**2
        points = r.optimistic_output_only_max_points(remaining)
        self.assertTrue(r.three_method_block_fits(points, remaining))
        self.assertFalse(r.three_method_block_fits(points+1, remaining))

    def test_unknown_finer_grid_inventory_cannot_be_admitted(self):
        self.assertIsNone(r.job_quota(None))
        self.assertFalse(r.three_method_block_fits(None, 1<<50))

    def test_subset_pass_is_not_full_gate_pass(self):
        self.assertFalse(r.can_advance([{'required_for_simulation_stage_advance': True, 'full_gate_status': 'passed_subset_only'}]))
        self.assertTrue(r.can_advance([{'required_for_simulation_stage_advance': True, 'full_gate_status': 'passed'}]))

    def test_historical_pass_with_changed_source_is_not_current(self):
        self.assertFalse(r.source_is_current('old', 'new'))
        self.assertTrue(r.source_is_current('same', 'same'))

    def test_current_all_four_core_forecasts_are_prefix_causal(self):
        from prediction import rollout
        observed = {'time': np.arange(80)*.02, 'state': np.zeros((80, 4)),
                    'alpha': np.linspace(0, .1, 80), 'v_B': np.full(80, 3.)}
        poisoned = {key: value.copy() for key, value in observed.items()}
        poisoned['state'][40:] += 1.
        poisoned['alpha'][40:] = -.2
        poisoned['v_B'][40:] = 5.
        for mode in ('hold', 'linear', 'damped_linear', 'bounded_second_order'):
            method = r.pipeline.Method(mode)
            np.testing.assert_array_equal(rollout(observed, method, .3)[:40], rollout(poisoned, method, .3)[:40])

    def test_large_resource_headroom_does_not_override_failed_evidence(self):
        self.assertTrue(r.three_method_block_fits(1000, 1<<50))
        matrix = [{'required_for_simulation_stage_advance': True, 'full_gate_status': 'passed'},
                  {'required_for_simulation_stage_advance': True, 'full_gate_status': 'failed'}]
        self.assertFalse(r.can_advance(matrix))


if __name__ == '__main__':
    unittest.main()
