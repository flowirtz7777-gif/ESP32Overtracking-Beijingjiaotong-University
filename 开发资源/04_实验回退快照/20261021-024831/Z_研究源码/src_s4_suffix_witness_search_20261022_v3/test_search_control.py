import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_suffix_witness_search_20261022_v1'))
sys.path.insert(0,str(ROOT/'src_s4_local_motion_20261022_v2'))
sys.path.insert(0,str(ROOT/'src_s4_label_observability_20261022_v1'))
from observability_core import geos_geometry
import search_control as c

V=SimpleNamespace(L=.001,width=.002,l_h=0.)
TIME=np.array([0.,4.])
STATES=np.array([[0.,0.,0.,0.],[4.,0.,0.,0.]])


class SuffixTests(unittest.TestCase):
    def search(self,point=(1.2345,0.),lower=0.,error=1e-8,budget=256):
        return c.search(np.array(point),TIME,STATES,lower,error,V,geos_geometry,budget=budget)

    def check(self,saved,point=(1.2345,0.),lower=0.,error=1e-8):
        return c.independently_check(np.array(point),TIME,STATES,lower,error,V,saved,geos_geometry)

    def test_narrow_contact_missed_by_exponential_schedule_found(self):
        point=np.array([1.2345,0.])
        old=[]
        for j in range(32):
            q=0. if j==0 else min(4.,1e-7*2**(j-1))
            pose=np.array([q,0.,0.,0.])
            old.append(geos_geometry(point,pose,V)[0]+1e-8+c.GUARD<=c.TOL)
            if q==4: break
        self.assertFalse(any(old))
        result=self.search(); self.assertTrue(np.isfinite(result['candidate_upper_s'][0])); self.check(result)

    def test_all_successful_and_failed_queries_independently_checked(self):
        result=self.search(); checked=self.check(result)
        self.assertEqual(checked['query_records'],len(result['query_s']))

    def test_no_query_before_scientific_lower(self):
        result=self.search(lower=1.2)
        self.assertTrue(np.all(result['query_s']>=1.2)); self.check(result,lower=1.2)

    def test_signed_zero_lower_exact(self):
        result=self.search(lower=-0.)
        self.assertEqual(int(result['scientific_lower_s'].view(np.uint64)[0]),1<<63); self.check(result,lower=-0.)

    def test_no_result_fields_claim_noncontact_or_raise_lower(self):
        result=self.search(point=(20.,0.))
        self.assertTrue(np.isnan(result['candidate_upper_s'][0]))
        self.assertTrue(result['not_a_noncontact_or_global_earliest_proof'][0]); self.check(result,point=(20.,0.))

    def test_budget_retains_open_root_and_unknown(self):
        result=self.search(budget=2)
        self.assertTrue(result['independent_budget_exhausted'][0]); self.assertFalse(result['strict_predicate_suffix_pruned'][0])
        self.assertTrue(np.isnan(result['candidate_upper_s'][0])); self.assertTrue(np.any(result['node_status']==c.OPEN))
        self.check(result)

    def test_full_children_partition_no_silent_dropped_branch(self):
        result=self.search(point=(1.2345,.051),error=1e-8,budget=32)
        for j in np.flatnonzero(result['node_status']==c.EXPANDED):
            children=np.flatnonzero(result['parent_index']==j)
            self.assertEqual(len(children),2)
        self.check(result,point=(1.2345,.051))

    def test_lower_itself_strict_witness(self):
        result=self.search(point=(0.,0.))
        self.assertEqual(len(result['query_s']),1); self.assertEqual(result['candidate_upper_s'][0],0.)
        self.check(result,point=(0.,0.))

    def test_horizon_equals_lower_stays_single_point(self):
        result=self.search(lower=4.,point=(20.,0.))
        self.assertEqual(len(result['query_s']),1); self.check(result,lower=4.,point=(20.,0.))

    def test_resolution_stop_is_unknown_not_pruned_or_noncontact(self):
        t=np.array([0.,5e-8]); s=np.zeros((2,4)); point=np.array([0.,c.TOL+V.width/2])
        result=c.search(point,t,s,0.,0.,V,geos_geometry)
        self.assertTrue(result['resolution_unresolved'][0]); self.assertFalse(result['strict_predicate_suffix_pruned'][0])
        c.independently_check(point,t,s,0.,0.,V,result,geos_geometry)

    def test_fixed_error_band_only_prunes_strict_sufficiency(self):
        t=np.array([0.,4.]); s=np.zeros((2,4)); point=np.array([0.,.051])
        result=c.search(point,t,s,0.,1e-4,V,geos_geometry)
        self.assertTrue(result['strict_predicate_suffix_pruned'][0])
        self.assertTrue(result['not_a_noncontact_or_global_earliest_proof'][0])
        c.independently_check(point,t,s,0.,1e-4,V,result,geos_geometry)

    def test_nonmonotone_distance_path(self):
        t=np.array([0.,1.,2.,3.]); s=np.array([[0.,0.,0.,0.],[4.,0.,0.,0.],[0.,0.,0.,0.],[4.,0.,0.,0.]])
        point=np.array([1.2345,0.]); result=c.search(point,t,s,0.,1e-8,V,geos_geometry)
        self.assertTrue(np.isfinite(result['candidate_upper_s'][0]))
        c.independently_check(point,t,s,0.,1e-8,V,result,geos_geometry)

    def test_deterministic_queries_and_all_trace_bytes(self):
        a,b=self.search(),self.search()
        self.assertTrue(all(a[k].dtype==b[k].dtype and a[k].shape==b[k].shape and a[k].tobytes()==b[k].tobytes() for k in a))

    def test_invalid_input_budget_and_error(self):
        for kwargs in ({'budget':1},{'budget':257},{'error':-1.},{'lower':-1.},{'lower':5.}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError): self.search(**kwargs)

    def test_bad_variation_rejected(self):
        for values in (np.zeros(2),np.array([-1.]),np.zeros(1,np.float32)):
            with self.subTest(values=values),self.assertRaises(ValueError):
                c.search(np.zeros(2),TIME,STATES,0.,0.,V,geos_geometry,variation=values)

    def test_tampered_scientific_lower_rejected(self):
        result=self.search(); result['scientific_lower_s'][0]=1.
        with self.assertRaises(ValueError): self.check(result)

    def test_missing_trace_rejected(self):
        result=self.search(); del result['body_distance_m']
        with self.assertRaises(ValueError): self.check(result)

    def test_failed_query_tampering_rejected(self):
        result=self.search(); result['body_distance_m'][0]+=1.
        with self.assertRaises(ValueError): self.check(result)

    def test_witness_tampering_rejected(self):
        result=self.search(); result['candidate_upper_s'][0]=4.
        with self.assertRaises(ValueError): self.check(result)

    def test_pruned_suffix_cannot_hide_open_or_resolution(self):
        result=self.search(budget=2); result['strict_predicate_suffix_pruned'][0]=True
        with self.assertRaises(ValueError): self.check(result)


if __name__=='__main__': unittest.main()
