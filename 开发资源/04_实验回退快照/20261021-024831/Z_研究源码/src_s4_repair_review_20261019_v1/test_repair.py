import dataclasses
import math
import unittest
import numpy as np
import runtime as r
import run_repair as a

class RepairTests(unittest.TestCase):
    def test_ledger(self):
        self.assertEqual(2238 + 57 + 9, 2304)

    def test_geometry_count_and_no_old_peak_rerun(self):
        specs = a.geometry_matrix()
        self.assertEqual(len(specs), 12)
        self.assertEqual(len({x["id"] for x in specs}), 12)
        self.assertNotIn(10., {x["alpha_peak_abs_deg"] for x in specs})

    def test_phi_limit_unchanged(self):
        self.assertEqual(a.common.Vehicle().mapping(), {"l": 4., "l_h": 1.8, "L": 13.5, "width": 2.})

    def test_independent_edge_formula(self):
        states = np.array([[0., 0., 0., 0.], [3., 4., .8, -.9], [2., -3., -1.3, .7]])
        np.testing.assert_array_equal(a.independent_right_edge(states), a.common.right_edge(states, a.common.Vehicle()))

    def test_straight_reference(self):
        spec = {"id": "test", "alpha_peak_abs_deg": 5., "entry_rate_abs_deg_s": 4.,
                "return_rate_abs_deg_s": 4., "v_B_mps": 3., "turn_heading_change_deg": 90.}
        maneuver = a.scenarios.Maneuver.from_spec(spec)
        np.testing.assert_allclose(a.independent_rhs(0., np.array([0., 0., 0., 0.]), maneuver), [3., 0., 0., 0.])

    def test_quota_boundaries(self):
        state = {"combined_research_bytes": r.CAP-100, "physical_free_Z_bytes": r.RESERVE+100,
                 "run_bytes": r.RUN_CAP-100}
        self.assertTrue(r.fits(state, 100, 100))
        self.assertFalse(r.fits(state, 101, 100))
        self.assertFalse(r.fits(state, 100, 101))

    def test_physical_reserve_boundary(self):
        state = {"combined_research_bytes": 0, "physical_free_Z_bytes": r.RESERVE+99, "run_bytes": 0}
        self.assertFalse(r.fits(state, 100, 0))

    def test_actual_old_matrix_is_fixed(self):
        jobs = a.old_matrix()
        self.assertEqual(len(jobs), 9)
        self.assertEqual({x["processor"] for x in jobs}, {"raw", "alpha_lp", "age_hold"})
        self.assertEqual({x["method"]["mode"] for x in jobs}, {"hold", "linear", "damped_linear"})
        self.assertTrue(all(x["condition"]["noise_level"] == 0 for x in jobs))

    def test_control_shape_changes_spatial_ramp_length(self):
        specs = a.geometry_matrix()
        low = a.scenarios.Maneuver.from_spec(specs[0])
        high = a.scenarios.Maneuver.from_spec(specs[3])
        self.assertNotEqual(low.speed*low.entry_duration, high.speed*high.entry_duration)

    def test_delay_source_never_future(self):
        time = np.arange(30)*.02
        truth = {"time": time, "alpha": time*.01, "state": np.zeros((30, 4)), "v_B": np.full(30, 3.)}
        observed = a.observations.observe(truth, {"delay_s": .2, "noise_level": 0})
        self.assertTrue(np.all(observed["source_index"] <= np.arange(30)))
        self.assertTrue(np.all(observed["measurement_time"] <= time))

    def test_npz_empty_nan_uint16(self):
        arrays = {"empty": np.array([], dtype=np.uint16), "float": np.array([0., np.nan, np.inf]),
                  "integer": np.arange(12, dtype=np.uint16).reshape(3, 4)}
        self.assertGreater(len(a.npz_blob(arrays)), 0)

    def test_packbits_complete_length(self):
        x = np.zeros(70000, dtype=bool)
        x[[0, 69999]] = True
        np.testing.assert_array_equal(np.unpackbits(np.packbits(x, bitorder="little"), bitorder="little").astype(bool), x)

    def test_future_poison_all_methods(self):
        n = 40
        obs = {"time": np.arange(n)*.02, "alpha": np.arange(n)*.0001,
               "state": np.zeros((n, 4)), "v_B": np.full(n, 3.)}
        poison = {k: v.copy() for k, v in obs.items()}
        poison["alpha"][20:] += .5
        poison["state"][20:] += 100
        for mode in ("hold", "linear", "damped_linear", "bounded_second_order"):
            method = a.prediction.Method(mode)
            np.testing.assert_array_equal(a.prediction.rollout(obs, method, 2)[:20],
                                          a.prediction.rollout(poison, method, 2)[:20])

    def test_geometry_45_is_not_small_angle(self):
        vehicle = a.common.Vehicle()
        state = np.array([0., 0., .4, math.pi/4])
        expected = 3*math.tan(.1)/vehicle.l - (3*math.sin(math.pi/4)
                   + vehicle.l_h*3*math.tan(.1)/vehicle.l*math.cos(math.pi/4))/vehicle.L
        self.assertAlmostEqual(a.common.derivative(state, .1, 3., vehicle)[3], expected, places=14)

if __name__ == "__main__":
    unittest.main()
