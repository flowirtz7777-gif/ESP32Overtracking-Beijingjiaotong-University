import unittest
import numpy as np
from unittest.mock import patch
from reference import acceleration_bound,curve_bound,combine,common,independent_reference
from scenarios import Maneuver,SinusoidalManeuver


class ReferencePolicyTests(unittest.TestCase):
    def test_acceleration_bound_covers_numerical_corners(self):
        spec={'id':'unit','alpha_peak_abs_deg':10,'entry_rate_abs_deg_s':4,
              'return_rate_abs_deg_s':4,'v_B_mps':3,'turn_heading_change_deg':90}
        for cls in (Maneuver,SinusoidalManeuver):
            m=cls.from_spec(spec)
            self.assertGreater(acceleration_bound(m,common.Vehicle()),0)

    def test_curvature_translation_zero(self):
        self.assertEqual(curve_bound(np.array([[0,0,1,0],[1,2,1,0]]),common.Vehicle()),0)

    def sample(self,status,lo=1.,hi=2.,bits=2):
        return {'contact_status':np.array(status,np.int8),'contact_lower_s':np.full(len(status),lo),
                'contact_upper_s':np.full(len(status),hi),'possible_edge_codes':np.full(len(status),bits,np.uint16)}

    def test_unknown_never_hidden(self):
        out=combine(self.sample([1,0,1,3]),self.sample([2,0,1,1]))
        np.testing.assert_array_equal(out['contact_status'],[2,0,1,3])
        np.testing.assert_array_equal(out['possible_edge_codes'],[255,2,2,255])

    def test_conflicts_explicit(self):
        self.assertTrue(combine(self.sample([0]),self.sample([1]))['model_conflict'][0])
        self.assertTrue(combine(self.sample([1]),self.sample([1],lo=3,hi=4))['model_conflict'][0])
        self.assertTrue(combine(self.sample([1]),self.sample([1],bits=4))['model_conflict'][0])

    def test_union_not_false_precision(self):
        out=combine(self.sample([1],lo=1,hi=3,bits=2),self.sample([1],lo=2,hi=4,bits=6))
        self.assertEqual(out['contact_lower_s'][0],1)
        self.assertEqual(out['contact_upper_s'][0],4)
        self.assertEqual(out['possible_edge_codes'][0],6)

    def test_independent_integrations_analytic_straight_reference(self):
        class Straight:
            speed=1.
            peak=0.
            entry_rate=return_rate=0.
            end=.1
            def alpha(self,t):
                return np.zeros_like(t)
        time=np.arange(21)*.005
        states=np.column_stack([np.zeros(21),time,np.full(21,np.pi/2),np.zeros(21)])
        with patch('reference.maneuver_for',return_value=(Straight(),common.Vehicle())):
            out,meta=independent_reference({},time,states)
        self.assertEqual(len(out['time']),41)
        np.testing.assert_allclose(out['state'][:,1],out['time'],rtol=0,atol=1e-12)
        self.assertLess(meta['old_all_corner_vs_DOP853_m'],1e-12)
        self.assertGreaterEqual(meta['old_path_spatial_envelope_m'],1e-7)




if __name__=='__main__':
    unittest.main()
