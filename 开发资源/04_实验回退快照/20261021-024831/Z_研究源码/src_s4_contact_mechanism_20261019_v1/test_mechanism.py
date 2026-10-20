import unittest
import numpy as np
import run_mechanism as a

class MechanismTests(unittest.TestCase):
    def test_all_change_categories_selected(self):
        values={'coarse_edge':np.array([2,1,0,2]),'fine_edge':np.array([2,5,0,2]),
            'coarse_front_ignored':np.array([0,1,0,0],bool),'fine_front_ignored':np.array([0,1,0,1],bool),
            'coarse_contact_time':np.array([1.,1.,np.nan,1.]),'fine_contact_time':np.array([1.,1.,1.,1.])}
        np.testing.assert_array_equal(a.changed_ids(values),[1,2,3])

    def test_pose_interpolation(self):
        np.testing.assert_array_equal(a.pose_at([0.,1.],np.array([[0.,0.,0.,0.],[2.,0.,0.,0.]]),[.5]),[[1.,0.,0.,0.]])

    def test_noncontact_swept_code(self):
        self.assertEqual(a.swept_code(np.array([0.,0.]),np.zeros((2,4)),-1),0)

    def test_no_historical_truth_recertification_from_diagnostic(self):
        self.assertNotEqual(a.RUN,a.DEP)
        self.assertEqual(a.PARAMS['width'],a.VEHICLE.width)

    def test_finite_faces_independent_geos(self):
        import shapely
        rng=np.random.default_rng(19)
        poses=rng.normal(size=(100,4))
        xy=rng.normal(size=(100,2))*10
        body,face=a.finite_face_geometry(xy,poses,**a.PARAMS)
        corners=a.labels.dep.common.body_corners(poses,a.VEHICLE)
        points=shapely.points(xy)
        expected=np.column_stack([shapely.distance(points,shapely.linestrings(corners[:,pair,:]))
                                  for pair in ([3,0],[0,1],[1,2],[2,3])])
        np.testing.assert_allclose(face,expected,rtol=0,atol=1e-12)
        np.testing.assert_allclose(body,shapely.distance(points,shapely.polygons(corners)),rtol=0,atol=1e-12)

    def test_motion_bound_contains_sampled_distance_changes(self):
        from interval_contact import motion_bound
        start=np.array([0.,0.,.3,.1])
        end=np.array([1.,-.5,.6,.2])
        t=np.linspace(0,1,101)
        poses=start+t[:,None]*(end-start)
        point=np.broadcast_to([2.,-3.],(101,2))
        d,_=a.finite_face_geometry(point,poses,**a.PARAMS)
        bound=motion_bound(np.stack((start,end)),np.array([0.,1.]),**a.PARAMS)[0]
        self.assertTrue(np.all(np.abs(np.diff(d))/np.diff(t)<=bound+1e-12))

if __name__=='__main__':
    unittest.main()
