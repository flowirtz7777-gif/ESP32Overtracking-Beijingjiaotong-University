import copy
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import edge_cover_core as c
from contact_primitives import finite_face_geometry
import shapely

V=SimpleNamespace(L=2.,width=1.,l_h=.3)


def fixture(speed=2.):
    time=np.array([0.,.5,1.])
    states=np.zeros((3,4)); states[:,0]=time*speed
    labels=dict(contact_status=np.array([1,2,0,1],np.int8),
        contact_lower_s=np.array([0.,0.,np.nan,0.]),
        contact_upper_s=np.array([1.,np.nan,np.nan,0.]),
        nominal_instantaneous_edge=np.array([1,0,0,1],np.int8),
        possible_edge_codes=np.array([255,255,0,1],np.uint16),
        edge_certain=np.array([0,0,0,1],bool),budget_exhausted=np.zeros(4,bool))
    xy=np.zeros((4,2))
    return xy,time,states,labels


def geom(points,poses):
    return np.zeros(len(points)),np.tile([0.,1.,2.,3.],(len(points),1))


def geos(point,pose,v):
    return 0.,np.array([0.,1.,2.,3.])


class CoverTests(unittest.TestCase):
    def run_case(self,speed=2.,error=0.,geometry=geom):
        args=fixture(speed)
        out,t,variation=c.candidate(*args,error,V,geometry)
        return args,out,t,variation

    def check(self,args,out,t,v,error=0.,geometry=geos):
        return c.independent_check(*args,out,error,V,t,v,geometry)

    def test_subdivision_certifies_when_single_full_bracket_envelope_fails(self):
        args,out,t,v=self.run_case()
        self.assertFalse(c.motion.face_rule(np.array([0.,1.,2.,3.]),t['envelope_m'][0,0])[1])
        self.assertTrue(out['edge_certain'][0]); self.assertEqual(out['possible_edge_codes'][0],1)
        self.assertGreater(t['query_count'][0],1)
        self.assertTrue(self.check(args,out,t,v)['complete_interval_cover_tree_frontier_budget_padding_checked'])

    def test_all_science_endpoints_signedzero_and_unknowns_exact(self):
        args,out,t,v=self.run_case()
        for key,value in args[3].items():
            if key not in ('edge_certain','possible_edge_codes'):
                self.assertTrue(c.same(value,out[key]))
            self.assertTrue(c.same(value[1:],out[key][1:]))

    def test_static_complete_root_cover(self):
        args,out,t,v=self.run_case(speed=0.)
        self.assertEqual(t['query_count'][0],1)
        self.assertTrue(out['edge_certain'][0]); self.check(args,out,t,v)

    def test_complete_motion_crosses_original_intervals(self):
        args=fixture(); args[2][1,0]=3.; args[2][2,0]=0.
        out,t,v=c.candidate(*args,0.,V,geom)
        self.assertTrue(out['edge_certain'][0]); self.check(args,out,t,v)
        self.assertGreater(t['left_motion_m'][0,0],2.9)
        self.assertGreater(t['right_motion_m'][0,0],2.9)

    def test_budget_preserves_open_frontier_and_unknown(self):
        with patch.object(c,'BUDGET',3):
            args,out,t,v=self.run_case()
            self.assertTrue(t['cover_budget_exhausted'][0]); self.assertFalse(out['edge_certain'][0])
            self.assertGreater(t['frontier_count'][0],0); self.check(args,out,t,v)

    def test_spatial_error_never_removed_to_certify(self):
        args,out,t,v=self.run_case(error=.6)
        self.assertFalse(out['edge_certain'][0]); self.assertEqual(out['possible_edge_codes'][0],255)
        self.check(args,out,t,v,error=.6)

    def test_zero_width_unstable_bracket_stays_unknown(self):
        args=fixture(); args[3]['contact_upper_s'][0]=0.
        out,t,v=c.candidate(*args,.6,V,geom)
        self.assertTrue(t['cover_resolution_unresolved'][0]); self.assertFalse(out['edge_certain'][0])
        self.check(args,out,t,v,error=.6)

    def test_different_stable_code_does_not_change_original_code_set(self):
        def g(points,poses): return np.zeros(len(points)),np.tile([1.,0.,2.,3.],(len(points),1))
        def h(point,pose,v): return 0.,np.array([1.,0.,2.,3.])
        args,out,t,v=self.run_case(speed=0.,geometry=g)
        self.assertTrue(t['cover_different_stable_code'][0]); self.assertFalse(out['edge_certain'][0])
        self.assertEqual(out['nominal_instantaneous_edge'][0],1)
        self.check(args,out,t,v,geometry=h)

    def test_finite_face_corner_rule_certifies_same_corner_only(self):
        args=fixture(0.); args[3]['nominal_instantaneous_edge'][0]=5
        def g(points,poses): return np.zeros(len(points)),np.tile([0.,0.,2.,3.],(len(points),1))
        def h(point,pose,v): return 0.,np.array([0.,0.,2.,3.])
        out,t,v=c.candidate(*args,0.,V,g)
        self.assertTrue(out['edge_certain'][0]); self.assertEqual(out['possible_edge_codes'][0],16)
        self.check(args,out,t,v,geometry=h)

    def test_unselected_no_query_and_complete_nan_padding(self):
        args,out,t,v=self.run_case()
        self.assertTrue(np.isnan(t['faces_m'][1:]).all()); self.assertEqual(int(t['query_count'][1:].sum()),0)
        self.check(args,out,t,v)

    def test_empty_full_scope(self):
        args=list(fixture()); args[0]=args[0][:0]; args[3]={k:v[:0] for k,v in args[3].items()}
        out,t,v=c.candidate(*args,0.,V,geom)
        self.assertEqual(t['faces_m'].shape,(0,64,4)); self.check(args,out,t,v)

    def test_invalid_error_and_path_rejected(self):
        for error in (-1.,np.nan,np.inf):
            with self.subTest(error=error),self.assertRaises(ValueError): self.run_case(error=error)
        args=list(fixture()); args[1]=np.array([0.,0.,1.])
        with self.assertRaises(ValueError): c.candidate(*args,0.,V,geom)

    def test_mutated_each_node_contract_rejected(self):
        args,out,t,v=self.run_case()
        for key in (*c.FLOATS,*c.INTS,'faces_m','margins_m'):
            bad=copy.deepcopy(t)
            bad[key].reshape(len(t[key]),-1)[0,0]+=1
            with self.subTest(key=key),self.assertRaises(ValueError): self.check(args,out,bad,v)

    def test_missing_and_extra_fields_rejected(self):
        args,out,t,v=self.run_case()
        for extra in (True,False):
            bad=copy.deepcopy(t)
            if extra: bad['extra']=np.zeros(4)
            else: del bad['frontier_parent']
            with self.subTest(extra=extra),self.assertRaises(ValueError): self.check(args,out,bad,v)

    def test_query_truncation_cannot_forge_completed_cover(self):
        args,out,t,v=self.run_case(); t['query_count'][0]-=1
        with self.assertRaises(ValueError): self.check(args,out,t,v)

    def test_complete_open_frontier_byte_contract(self):
        with patch.object(c,'BUDGET',3):
            args,out,t,v=self.run_case()
            for key in ('frontier_a_s','frontier_b_s','frontier_parent','frontier_count'):
                bad=copy.deepcopy(t); bad[key].reshape(4,-1)[0,0]+=1
                with self.subTest(key=key),self.assertRaises(ValueError): self.check(args,out,bad,v)

    def test_padding_and_unselected_flag_cannot_hide_geometry(self):
        args,out,t,v=self.run_case()
        for key in ('faces_m','a_s','kind','edge_newly_certified'):
            bad=copy.deepcopy(t); bad[key].reshape(4,-1)[1,0]=1
            with self.subTest(key=key),self.assertRaises(ValueError): self.check(args,out,bad,v)

    def test_no_scientific_lower_or_upper_changes(self):
        args,out,t,v=self.run_case()
        for field in ('contact_lower_s','contact_upper_s','nominal_instantaneous_edge','contact_status'):
            bad=copy.deepcopy(out); bad[field][0]+=1
            with self.subTest(field=field),self.assertRaises(ValueError): self.check(args,bad,t,v)

    def test_unselected_row_cannot_be_relabeled(self):
        args,out,t,v=self.run_case(); out['edge_certain'][1]=True
        with self.assertRaises(ValueError): self.check(args,out,t,v)

    def test_independent_geometry_mismatch_stops(self):
        args,out,t,v=self.run_case()
        with self.assertRaises(ValueError): self.check(args,out,t,v,geometry=lambda a,b,v:(0.,np.ones(4)))

    def test_underbound_or_missing_segment_variation_rejected(self):
        args,out,t,v=self.run_case()
        for bad in (v[:-1],v*.5,v.astype(np.float32)):
            with self.assertRaises(ValueError): self.check(args,out,t,bad)

    def physical(self,rotate=False):
        args=list(fixture(1.2)); args[0][0]=[-.1,-.5]
        args[3]['nominal_instantaneous_edge'][0]=2
        if rotate:
            args[2][:,2]=args[1]*.1
            args[2][:,3]=args[1]*.05
        def g(points,poses):
            return finite_face_geometry(points,poses,length=V.L,width=V.width,hitch_offset=V.l_h)
        def h(point,pose,v):
            x,y,theta,phi=map(float,pose); heading=theta-phi
            hx,hy=x+v.l_h*math.cos(theta),y+v.l_h*math.sin(theta)
            rx,ry=hx-v.L*math.cos(heading),hy-v.L*math.sin(heading)
            nx,ny=v.width/2*math.sin(heading),-v.width/2*math.cos(heading)
            corners=[(hx+nx,hy+ny),(rx+nx,ry+ny),(rx-nx,ry-ny),(hx-nx,hy-ny)]
            p=shapely.Point(*point)
            distances=[p.distance(shapely.LineString([corners[a],corners[b]])) for a,b in ((3,0),(0,1),(1,2),(2,3))]
            return p.distance(shapely.Polygon(corners)),np.array(distances)
        out,t,v=c.candidate(*args,1e-6,V,g)
        self.check(args,out,t,v,error=1e-6,geometry=h)
        return out,t

    def test_actual_translating_rectangle_GE0S_cover(self):
        out,t=self.physical()
        self.assertTrue(out['edge_certain'][0]); self.assertEqual(out['possible_edge_codes'][0],2)
        self.assertGreater(t['query_count'][0],1)

    def test_actual_hitch_and_distinct_trailer_heading_GE0S(self):
        out,t=self.physical(rotate=True)
        self.assertGreater(t['query_count'][0],0)


if __name__=='__main__': unittest.main()
