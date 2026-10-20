import sys
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
for folder in ('src_s4_unwitnessed_probe_20261022_v1','src_s4_suffix_witness_search_20261022_v1',
               'src_s4_local_motion_20261022_v2','src_s4_label_observability_20261022_v1'):
    sys.path.insert(0,str(ROOT/folder))
from test_probe import fixture,V,geometry
from observability_core import geos_geometry
import search_core as c


class AdapterTests(unittest.TestCase):
    def candidate(self):
        xy,time,states,labels=fixture()
        proposed,trace,variation=c.candidate(xy,time,states,labels,1e-6,V,geometry)
        return xy,time,states,labels,proposed,trace,variation

    def check(self,f):
        xy,time,states,labels,proposed,trace,variation=f
        return c.independent_check(xy,time,states,labels,proposed,1e-6,V,trace,variation,geos_geometry)

    def test_full_scope_search_refinement_face_and_decimal_independent_check(self):
        f=self.candidate(); checked=self.check(f)
        self.assertEqual(checked['scope_records'],7); self.assertEqual(checked['selected_unwitnessed_records'],5)
        self.assertEqual(checked['new_strict_contact_witnesses'],3)

    def test_every_lower_and_provenance_byte_exact(self):
        f=self.candidate()
        for key in set(f[3])-c.MUTABLE: self.assertTrue(c.same(f[3][key],f[4][key]))

    def test_no_witness_exact_unknown_existing_witness_and_noncontact_reused(self):
        f=self.candidate(); found=f[5]['found_strict_witness']
        for key in f[3]: self.assertTrue(c.same(f[3][key][~found],f[4][key][~found]))

    def test_boolean_budget_tampering_rejected(self):
        f=self.candidate(); f[5]['forward_budget_exhausted'][0]=~f[5]['forward_budget_exhausted'][0]
        with self.assertRaises(ValueError): self.check(f)

    def test_query_parent_tampering_rejected(self):
        f=self.candidate(); f[5]['search__parent_index'][0,1]=100
        with self.assertRaises(ValueError): self.check(f)

    def test_2D_integer_padding_tampering_rejected(self):
        f=self.candidate(); count=int(f[5]['forward_evaluations'][0]); f[5]['search__parent_index'][0,count]=1
        with self.assertRaises(ValueError): self.check(f)

    def test_2D_float_padding_tampering_rejected(self):
        f=self.candidate(); count=int(f[5]['forward_evaluations'][0]); f[5]['search__start_s'][0,count]=0.
        with self.assertRaises(ValueError): self.check(f)

    def test_proposed_lower_tampering_rejected(self):
        f=self.candidate(); f[4]['contact_lower_s'][0]=.1
        with self.assertRaises(ValueError): self.check(f)

    def test_no_witness_cannot_turn_negative(self):
        f=self.candidate(); f[4]['contact_status'][1]=0
        with self.assertRaises(ValueError): self.check(f)

    def test_trace_shape_dtype_and_schema_tampering_rejected(self):
        for kind in range(3):
            f=self.candidate()
            if kind==0: f[5]['search__node_status']=f[5]['search__node_status'].astype(np.int64)
            elif kind==1: f[5]['search__node_status']=f[5]['search__node_status'][:,:10]
            else: del f[5]['search__node_status']
            with self.subTest(kind=kind),self.assertRaises(ValueError): self.check(f)


if __name__=='__main__': unittest.main()
