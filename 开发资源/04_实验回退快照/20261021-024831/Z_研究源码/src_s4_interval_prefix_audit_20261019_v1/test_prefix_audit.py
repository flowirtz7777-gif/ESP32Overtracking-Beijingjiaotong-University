import unittest
import numpy as np
import shapely
from prefix_audit import audit_prefixes,common


class PrefixTests(unittest.TestCase):
    def setUp(self):
        self.vehicle=common.Vehicle(l_h=0,L=2,width=2)
        self.time=np.array([0.,1.])
        self.states=np.array([[0.,0.,0.,0.],[4.,0.,0.,0.]])

    def run_audit(self,xy,lower,**kw):
        return audit_prefixes(np.array(xy,float),self.time,self.states,np.array(lower,float),vehicle=self.vehicle,**kw)

    def test_correct_prefix_excluded(self):
        out=self.run_audit([[1.,0.]],[.2374])
        self.assertTrue(out['prefix_excluded'][0])

    def test_false_late_first_contact_has_early_witness(self):
        out=self.run_audit([[1.,0.]],[.8])
        self.assertTrue(out['early_contact_witness'][0])
        self.assertFalse(out['prefix_excluded'][0])

    def test_noncontact_claim_entire_path_checked(self):
        out=self.run_audit([[1.,0.],[1.,3.]],[np.nan,np.nan])
        np.testing.assert_array_equal(out['prefix_excluded'],[False,True])

    def test_initial_time_empty_prefix(self):
        out=self.run_audit([[0.,0.]],[0.])
        self.assertTrue(out['prefix_excluded'][0])
        self.assertEqual(out['GEOS_evaluations'][0],0)

    def test_budget_never_false_exclusion(self):
        out=self.run_audit([[1.,1.06]],[1.],spatial_error_m=.02,max_evaluations_per_point=1)
        self.assertTrue(out['prefix_undetermined'][0])
        self.assertTrue(out['budget_exhausted'][0])
        self.assertFalse(out['prefix_excluded'][0])

    def test_out_of_domain_and_infinite_lower_rejected(self):
        for value in (-1.,2.,np.inf):
            with self.assertRaises(ValueError):
                self.run_audit([[1.,0.]],[value])

    def test_empty_arrays(self):
        out=audit_prefixes(np.empty((0,2)),self.time,self.states,np.empty(0),vehicle=self.vehicle)
        self.assertEqual(len(out['prefix_excluded']),0)

    def test_rotating_hitch_body_no_dense_witness_false_exclusion(self):
        vehicle=common.Vehicle(l_h=1,L=3,width=1.2)
        state=np.array([[0.,0.,1.5,-.2],[3.,1.,.3,.6]])
        xy=np.random.default_rng(101).uniform([-5,-4],[6,5],(80,2))
        alpha=np.linspace(0,1,121)
        corners=common.body_corners(state[0]+alpha[:,None]*(state[1]-state[0]),vehicle)
        distance=shapely.distance(shapely.points(xy)[None,:],shapely.polygons(corners)[:,None])
        dense_hit=np.any(distance<=.050000001,axis=0)
        result=audit_prefixes(xy,np.array([0.,1.]),state,np.full(len(xy),np.nan),vehicle=vehicle)
        self.assertTrue(np.any(dense_hit))
        self.assertFalse(np.any(dense_hit&result['prefix_excluded']))

    def test_evaluation_cap_applies_even_to_excluded_intervals(self):
        time=np.linspace(0,1,5)
        state=np.column_stack([np.linspace(0,.04,5),np.zeros(5),np.full(5,np.pi/4),np.zeros(5)])
        result=audit_prefixes(np.array([[-1.8,.5]]),time,state,np.array([np.nan]),
                              vehicle=self.vehicle,max_evaluations_per_point=1)
        self.assertLessEqual(result['GEOS_evaluations'][0],1)


if __name__=='__main__':
    unittest.main()
