import unittest
import numpy as np
import shapely
import population as a
from interval_contact import point_contact_interval

class PopulationTests(unittest.TestCase):
    def setUp(self):
        self.v=a.common.Vehicle(l=4.,l_h=0.,L=4.,width=2.)

    def test_analytic_entry_and_noncontact(self):
        value=a.label_population(np.array([[1.,0.],[20.,20.]]),np.array([0.,1.]),
                                 np.array([[0.,0.,0.,0.],[1.,0.,0.,0.]]),vehicle=self.v,tolerance_m=.05)
        self.assertEqual(value['contact_status'].tolist(),[1,0])
        self.assertLessEqual(value['contact_lower_s'][0],.95)
        self.assertGreaterEqual(value['contact_upper_s'][0],.95)
        self.assertEqual(value['possible_edge_codes'][1],0)

    def test_endpoint_and_midpoint_outside_not_false_negative(self):
        v=a.common.Vehicle(l=4.,l_h=0.,L=.1,width=.1)
        value=a.label_population([[.2,0.]],[0.,1.],[[0.,0.,0.,0.],[10.,0.,0.,0.]],vehicle=v,tolerance_m=.05)
        self.assertNotEqual(value['contact_status'][0],0)

    def test_initial_overlap_preserved(self):
        value=a.label_population([[-2.,0.]],[0.,1.],[[0.,0.,0.,0.],[1.,0.,0.,0.]],vehicle=self.v)
        self.assertTrue(value['initial_tolerance_contact_certain'][0])
        self.assertEqual(value['contact_upper_s'][0],0.)

    def test_uncertain_not_deleted_or_negative(self):
        value=a.label_population([[1.,0.]],[0.,1.],[[0.,0.,0.,0.],[1.,0.,0.,0.]],vehicle=self.v,
                                 spatial_error_m=.1,max_evaluations_per_interval=32)
        self.assertNotEqual(value['contact_status'][0],0)
        self.assertEqual(len(value['possible_edge_codes']),1)

    def test_budget_exhaustion_explicit(self):
        value=a.label_population([[1.,0.]],[0.,1.],[[0.,0.,0.,0.],[1.,0.,0.,0.]],vehicle=self.v,
                                 max_evaluations_per_interval=3)
        self.assertTrue(value['budget_exhausted'][0])
        self.assertEqual(value['contact_status'][0],3)

    def test_scalar_reference_agrees_on_straight_cases(self):
        xy=np.array([[.3,0.],[1.,0.],[1.5,-.8],[2.,-2.],[-2.,0.]])
        time=np.array([0.,.5,1.])
        states=np.array([[0.,0.,0.,0.],[1.,0.,0.,0.],[2.,0.,0.,0.]])
        batch=a.label_population(xy,time,states,vehicle=self.v,tolerance_m=.05)
        for j,p in enumerate(xy):
            scalar=point_contact_interval(p,time,states,length=4.,width=2.,hitch_offset=0.)
            if scalar['status']=='contact':
                self.assertNotEqual(batch['contact_status'][j],0)
                self.assertLessEqual(batch['contact_lower_s'][j],scalar['upper_s'])
            if batch['contact_status'][j]==0:
                self.assertEqual(scalar['status'],'noncontact')

    def test_conservative_curved_broad_phase(self):
        states=np.array([[0.,0.,0.,0.],[0.,0.,.5,0.]])
        hull,curve=a.interval_candidates(states,self.v)
        for alpha in np.linspace(0,1,51):
            corners=a.common.body_corners((states[0]+alpha*(states[1]-states[0]))[None,:],self.v)[0]
            self.assertTrue(np.all(shapely.distance(shapely.points(corners),hull[0])<=curve[0]+1e-12))

    def test_coordinate_order_is_preserved(self):
        xy=np.array([[20.,20.],[1.,0.],[-2.,0.]])
        value=a.label_population(xy,[0.,1.],[[0.,0.,0.,0.],[1.,0.,0.,0.]],vehicle=self.v)
        self.assertEqual(value['contact_status'].tolist(),[0,1,1])

    def test_reject_invalid_reference(self):
        with self.assertRaises(ValueError):
            a.label_population([[0.,0.]],[1.,0.],np.zeros((2,4)))

    def test_piecewise_linear_subdivision_bounds_overlap(self):
        one=a.label_population([[1.,0.]],[0.,1.],[[0.,0.,0.,0.],[1.,0.,0.,0.]],vehicle=self.v)
        two=a.label_population([[1.,0.]],[0.,.5,1.],[[0.,0.,0.,0.],[.5,0.,0.,0.],[1.,0.,0.,0.]],vehicle=self.v)
        self.assertLessEqual(max(one['contact_lower_s'][0],two['contact_lower_s'][0]),
                             min(one['contact_upper_s'][0],two['contact_upper_s'][0]))

    def test_dense_independent_geos_has_no_false_negative(self):
        rng=np.random.default_rng(24)
        xy=rng.uniform([-5.,-3.],[3.,3.],size=(80,2))
        time=np.array([0.,.5,1.])
        states=np.array([[0.,0.,0.,0.],[.7,.2,.2,.05],[1.2,.3,.35,.07]])
        result=a.label_population(xy,time,states,vehicle=self.v,tolerance_m=.05)
        ever=np.zeros(len(xy),bool)
        for t in np.linspace(0,1,201):
            pose=np.array([np.interp(t,time,states[:,k]) for k in range(4)])
            body=shapely.polygons(a.common.body_corners(pose[None,:],self.v))[0]
            ever|=shapely.dwithin(shapely.points(xy),body,.05)
        self.assertTrue(np.all(result['contact_status'][ever]!=0))
        ids=np.flatnonzero(np.isfinite(result['contact_upper_s']))
        corners=a.common.body_corners(result['witness_pose'][ids],self.v)
        d=shapely.distance(shapely.points(xy[ids]),shapely.polygons(corners))
        self.assertTrue(np.all(d<=.05+1e-12))

    def test_empty_population(self):
        result=a.label_population(np.empty((0,2)),[0.,1.],np.zeros((2,4)),vehicle=self.v)
        self.assertEqual(result['contact_status'].shape,(0,))

if __name__=='__main__':
    unittest.main()
