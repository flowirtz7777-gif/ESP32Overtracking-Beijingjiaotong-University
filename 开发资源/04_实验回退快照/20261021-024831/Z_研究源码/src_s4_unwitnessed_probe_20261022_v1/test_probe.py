"""Synthetic strict-witness search and full independent replay."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np
import probe_core as c

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src_s4_truth_remediation_20261019_v1"))
sys.path.insert(0, str(ROOT / "src_s4_label_observability_20261022_v1"))
from contact_primitives import finite_face_geometry
from observability_core import geos_geometry

V = SimpleNamespace(L=1., width=2., l_h=0.)


def geometry(xy, poses):
    return finite_face_geometry(xy, poses, length=V.L, width=V.width, hitch_offset=V.l_h)


def fixture():
    xy = np.array([[1.5, 0.], [10., 0.], [1.5, 0.], [25., 0.], [30., 0.], [0., 0.], [2., 0.]])
    time = np.array([0., 4.])
    states = np.array([[0., 0., 0., 0.], [4., 0., 0., 0.]])
    labels = {"contact_status": np.array([2, 2, 2, 1, 0, 2, 2], np.int8),
        "contact_lower_s": np.array([0., 0., .2, .1, np.nan, 0., 4.]),
        "contact_upper_s": np.array([np.nan, np.nan, np.nan, .4, np.nan, np.nan, np.nan]),
        "nominal_instantaneous_edge": np.array([0, 0, 0, 5, 0, 0, 0], np.int8),
        "possible_edge_codes": np.array([255, 255, 255, 16, 0, 255, 255], np.uint16),
        "edge_certain": np.array([0, 0, 0, 1, 0, 0, 0], bool),
        "budget_exhausted": np.zeros(7, bool), "interval_evaluations": np.arange(7, dtype=np.int32),
        "candidate_interval_seen": np.ones(7, bool),
        "initial_tolerance_contact_certain": np.zeros(7, bool),
        "initial_tolerance_contact_possible": np.array([1, 1, 0, 0, 0, 1, 0], bool),
        "initial_nominal_body_overlap": np.zeros(7, bool)}
    return xy, time, states, labels


class ProbeTests(unittest.TestCase):
    def run_fixture(self, error=1e-6):
        xy, time, states, labels = fixture()
        candidate, trace, variation = c.candidate(xy, time, states, labels, error, V, geometry)
        return (xy, time, states, labels, candidate, trace, variation, error)

    def check(self, f):
        xy, time, states, labels, proposed, trace, variation, error = f
        return c.independent_check(xy, time, states, labels, proposed, error, V, trace, variation, geos_geometry)

    def test_all_unwitnessed_rows_selected_both_initial_and_noninitial(self):
        *_, labels = fixture()
        self.assertEqual(c.selection(labels).tolist(), [True, True, True, False, False, True, True])

    def test_new_witnesses_all_independently_replayed(self):
        f = self.run_fixture()
        checked = self.check(f)
        self.assertEqual(checked["selected_unwitnessed_records"], 5)
        self.assertEqual(checked["new_strict_contact_witnesses"], 3)

    def test_original_scientific_lower_every_byte_exact(self):
        f = self.run_fixture()
        self.assertTrue(c.same(f[3]["contact_lower_s"], f[4]["contact_lower_s"]))

    def test_signed_zero_lower_preserved(self):
        xy, time, states, labels = fixture()
        labels["contact_lower_s"][0] = -0.
        out, trace, variation = c.candidate(xy, time, states, labels, 1e-6, V, geometry)
        self.assertEqual(out["contact_lower_s"].view(np.uint64)[0], 1 << 63)
        c.independent_check(xy, time, states, labels, out, 1e-6, V, trace, variation, geos_geometry)

    def test_all_no_witness_fields_nan_payload_exact(self):
        xy, time, states, labels = fixture()
        labels["contact_upper_s"].view(np.uint64)[1] = 0x7ff8000000000041
        before = {k: v.copy() for k, v in labels.items()}
        out, _, _ = c.candidate(xy, time, states, labels, 1e-6, V, geometry)
        for name in labels:
            self.assertTrue(c.same(out[name][1:2], before[name][1:2]), name)
            self.assertTrue(c.same(labels[name], before[name]), name)

    def test_existing_witness_and_known_noncontact_never_queried(self):
        xy, time, states, labels = fixture()
        queried = []
        def tracked(points, pose):
            queried.extend(points[:, 0].tolist())
            return geometry(points, pose)
        out, trace, _ = c.candidate(xy, time, states, labels, 1e-6, V, tracked)
        self.assertNotIn(25., queried)
        self.assertNotIn(30., queried)
        for i in (3, 4):
            self.assertEqual(trace["forward_evaluations"][i], 0)
            for k in labels:
                self.assertTrue(c.same(labels[k][i:i+1], out[k][i:i+1]))

    def test_no_pre_lower_probe_on_any_selected_row(self):
        f = self.run_fixture()
        labels, trace = f[3], f[5]
        for prefix in ("forward", "refine"):
            for i in range(len(f[0])):
                count = int(trace[prefix + "_evaluations"][i])
                self.assertTrue(np.all(trace[prefix + "_time_s"][i, :count] >= labels["contact_lower_s"][i]))

    def test_forward_schedule_fixed_doubling_and_horizon(self):
        f = self.run_fixture()
        tr = f[5]
        count = tr["forward_evaluations"][1]
        expected = [0.] + [min(4., 1e-7 * 2 ** j) for j in range(count - 1)]
        self.assertEqual(tr["forward_time_s"][1, :count].tolist(), expected)
        self.assertTrue(tr["search_reached_horizon_without_witness"][1])
        self.assertEqual(f[4]["contact_status"][1], 2)

    def test_horizon_lower_one_probe_no_negative_label(self):
        f = self.run_fixture()
        self.assertEqual(f[5]["forward_evaluations"][6], 1)
        self.assertTrue(f[5]["search_reached_horizon_without_witness"][6])
        self.assertEqual(f[4]["contact_status"][6], 2)

    def test_zero_width_strict_witness_at_lower(self):
        f = self.run_fixture()
        self.assertEqual(f[4]["contact_upper_s"][5], 0.)
        self.assertEqual(f[5]["forward_evaluations"][5], 1)
        self.assertEqual(f[5]["refine_evaluations"][5], 0)
        self.assertEqual(f[5]["motion_radius_m"][5], 0.)

    def test_refinement_failed_probe_never_changes_scientific_lower(self):
        f = self.run_fixture()
        self.assertGreater(f[5]["refine_evaluations"][0], 0)
        self.assertTrue((~f[5]["refine_witness"][0, :f[5]["refine_evaluations"][0]]).any())
        self.assertEqual(f[4]["contact_lower_s"][0], 0.)

    def test_final_witness_strict_original_error_and_guard(self):
        f = self.run_fixture()
        for i in np.flatnonzero(f[5]["found_strict_witness"]):
            q = f[4]["contact_upper_s"][i]
            body, _ = geos_geometry(f[0][i], c.poses(f[1], f[2], np.array([q]))[0], V)
            self.assertLessEqual(body + f[7] + c.GUARD, c.TOL)

    def test_refinement_internal_width_not_first_contact_claim(self):
        f = self.run_fixture()
        tr = f[5]
        found = tr["found_strict_witness"]
        self.assertTrue(np.all(tr["refine_internal_remaining_width_s"][found] <= c.RESOLUTION))
        self.assertGreater(f[4]["contact_upper_s"][0] - f[4]["contact_lower_s"][0], 1.)

    def test_nonmonotone_trajectory_is_supported_without_exclusion_claim(self):
        xy, _, _, labels = fixture()
        time = np.array([0., 1., 2., 4.])
        states = np.array([[0., 0., 0., 0.], [3., 0., 0., 0.], [0., 0., 0., 0.], [3., 0., 0., 0.]])
        out, trace, var = c.candidate(xy, time, states, labels, 1e-6, V, geometry)
        c.independent_check(xy, time, states, labels, out, 1e-6, V, trace, var, geos_geometry)
        self.assertTrue(c.same(labels["contact_lower_s"], out["contact_lower_s"]))

    def test_narrow_unsampled_contact_remains_unknown_not_negative(self):
        xy, time, states, labels = fixture()
        xy[0] = [2., 0.]
        out, trace, _ = c.candidate(xy, time, states, labels, 1e-6, V, geometry)
        body, _ = geometry(xy[:1], c.poses(time, states, np.array([2.5])))
        self.assertEqual(body[0], 0.)
        self.assertFalse(trace["found_strict_witness"][0])
        self.assertEqual(out["contact_status"][0], 2)
        self.assertTrue(np.isnan(out["contact_upper_s"][0]))

    def test_forward_budget_separate_from_original_provenance(self):
        xy, time, states, labels = fixture()
        time[-1] = 1e15
        states[-1] = states[0]
        labels["contact_lower_s"][6] = 0.
        out, trace, var = c.candidate(xy, time, states, labels, 1e-6, V, geometry)
        self.assertTrue(trace["forward_budget_exhausted"][0])
        self.assertFalse(out["budget_exhausted"][0])
        self.assertEqual(out["contact_status"][0], 2)
        c.independent_check(xy, time, states, labels, out, 1e-6, V, trace, var, geos_geometry)

    def test_refinement_budget_does_not_remove_existing_strict_witness(self):
        with patch.object(c, "REFINE_STEPS", 1):
            f = self.run_fixture()
            self.assertTrue(f[5]["refine_budget_exhausted"][0])
            self.assertEqual(f[4]["contact_status"][0], 1)
            self.assertFalse(f[4]["budget_exhausted"][0])
            self.check(f)

    def test_full_original_interval_decimal_envelope(self):
        f = self.run_fixture()
        self.check(f)
        for i in np.flatnonzero(f[5]["found_strict_witness"]):
            _, _, bound = c.motion.decimal_radius(f[1], f[2], V,
                f[3]["contact_lower_s"][i], f[4]["contact_upper_s"][i])
            self.assertGreaterEqual(f[5]["motion_radius_m"][i], float(bound))

    def test_single_finite_face_code(self):
        f = self.run_fixture()
        self.assertTrue(f[4]["edge_certain"][5])
        self.assertEqual(f[4]["possible_edge_codes"][5], 1)

    def test_corner_is_one_code_bit_not_two_faces(self):
        xy, time, states, labels = fixture()
        xy[5] = [0., -1.]
        out, trace, var = c.candidate(xy, time, states, labels, 1e-6, V, geometry)
        self.assertTrue(out["edge_certain"][5])
        self.assertEqual(out["nominal_instantaneous_edge"][5], 5)
        self.assertEqual(out["possible_edge_codes"][5], 16)
        c.independent_check(xy, time, states, labels, out, 1e-6, V, trace, var, geos_geometry)

    def test_every_immutable_label_and_provenance_field_exact(self):
        f = self.run_fixture()
        for k in f[3].keys() - c.MUTABLE:
            self.assertTrue(c.same(f[3][k], f[4][k]), k)

    def test_all_unused_probe_slots_nan_and_false(self):
        f = self.run_fixture()
        for prefix in ("forward", "refine"):
            for i in range(len(f[0])):
                count = int(f[5][prefix + "_evaluations"][i])
                self.assertTrue(np.isnan(f[5][prefix + "_time_s"][i, count:]).all())
                self.assertFalse(f[5][prefix + "_witness"][i, count:].any())

    def corrupt(self, change):
        f = self.run_fixture()
        change(f)
        with self.assertRaises((ValueError, RuntimeError)):
            self.check(f)

    def test_changed_lower_rejected(self):
        self.corrupt(lambda f: f[4]["contact_lower_s"].__setitem__(0, .1))

    def test_changed_provenance_rejected(self):
        self.corrupt(lambda f: f[4]["interval_evaluations"].__setitem__(0, 999))

    def test_no_witness_false_negative_rejected(self):
        self.corrupt(lambda f: f[4]["contact_status"].__setitem__(1, 0))

    def test_forward_padding_rejected(self):
        self.corrupt(lambda f: f[5]["forward_time_s"].__setitem__((0, 63), 3.))

    def test_refinement_padding_rejected(self):
        self.corrupt(lambda f: f[5]["refine_witness"].__setitem__((0, 63), True))

    def test_missing_scope_probe_rejected(self):
        self.corrupt(lambda f: f[5]["forward_evaluations"].__setitem__(1, 0))

    def test_premature_forward_completion_rejected(self):
        self.corrupt(lambda f: f[5]["forward_evaluations"].__setitem__(1, 1))

    def test_truncated_refinement_rejected(self):
        self.corrupt(lambda f: f[5]["refine_evaluations"].__setitem__(0, 1))

    def test_forged_body_distance_rejected(self):
        self.corrupt(lambda f: f[5]["forward_body_distance_m"].__setitem__((0, 0), 0.))

    def test_forged_contact_upper_rejected(self):
        self.corrupt(lambda f: f[4]["contact_upper_s"].__setitem__(0, 1.))

    def test_forged_edge_confidence_rejected(self):
        self.corrupt(lambda f: f[4]["edge_certain"].__setitem__(0, True))

    def test_forged_midpoint_faces_rejected(self):
        self.corrupt(lambda f: f[5]["candidate_midpoint_faces_m"].__setitem__((0, 0), 99.))

    def test_underbounding_motion_rejected(self):
        self.corrupt(lambda f: f[6].__setitem__(0, 0.))

    def test_wrong_motion_sum_rejected(self):
        self.corrupt(lambda f: f[5]["left_motion_m"].__setitem__(0, 99.))

    def test_reduced_spatial_envelope_rejected(self):
        self.corrupt(lambda f: f[5]["total_envelope_m"].__setitem__(0, 0.))

    def test_forged_scope_flag_rejected(self):
        self.corrupt(lambda f: f[5]["selected_unwitnessed"].__setitem__(3, True))

    def test_trace_dtype_rejected(self):
        f = self.run_fixture()
        f[5]["forward_evaluations"] = f[5]["forward_evaluations"].astype(float)
        with self.assertRaises(ValueError):
            self.check(f)

    def test_invalid_error_and_path_rejected(self):
        xy, time, states, labels = fixture()
        for error in (-1., np.nan):
            with self.assertRaises(ValueError):
                c.candidate(xy, time, states, labels, error, V, geometry)
        with self.assertRaises(ValueError):
            c.candidate(xy, time[::-1], states, labels, 0., V, geometry)

    def test_invalid_old_budget_and_status_rejected(self):
        xy, time, states, labels = fixture()
        labels["budget_exhausted"][0] = True
        with self.assertRaises(ValueError):
            c.candidate(xy, time, states, labels, 0., V, geometry)
        labels["budget_exhausted"][0] = False
        labels["contact_status"][0] = 0
        with self.assertRaises(ValueError):
            c.candidate(xy, time, states, labels, 0., V, geometry)

    def test_empty_population_no_geometry(self):
        xy, time, states, labels = fixture()
        labels = {k: v[:0] for k, v in labels.items()}
        def forbidden(*_):
            raise AssertionError("No geometry for empty scope")
        out, trace, var = c.candidate(xy[:0], time, states, labels, 0., V, forbidden)
        c.independent_check(xy[:0], time, states, labels, out, 0., V, trace, var, forbidden)

    def test_floating_stagnation_rejected_not_false_completion(self):
        xy, _, states, labels = fixture()
        time = np.array([1e15, 1e15 + 4])
        labels["contact_lower_s"][:] = np.nan
        labels["contact_upper_s"][:] = np.nan
        labels["contact_status"][:] = 0
        labels["edge_certain"][:] = False
        labels["contact_lower_s"][1] = time[0]
        labels["contact_status"][1] = 2
        with self.assertRaises(ValueError):
            c.candidate(xy, time, states, labels, 0., V, geometry)


if __name__ == "__main__":
    unittest.main()

