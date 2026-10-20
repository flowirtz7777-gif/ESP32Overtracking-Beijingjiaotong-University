"""Synthetic complete scope/projection adapters; no real inputs, fitting or files."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
import numpy as np
import local_scope
from test_edge_cover import fixture,V,geom,geos


def require(ok,message):
    if not ok: raise RuntimeError(message)


def load_driver():
    parent=ModuleType('suffix_full_merge_driver')
    parent.base=NS(finite_face_geometry=lambda points,poses,**kwargs:geom(points,poses),
                   save_arrays=Mock(),read_arrays=Mock())
    parent.r=NS(require=require,file_hash=Mock(return_value='synthetic'))
    parent.AUTH=Path('SYNTHETIC_AUTH'); parent.RUN=Path('SYNTHETIC_PARENT')
    parent.DEPENDENCIES=(); parent.configure=Mock()
    parent.local=NS(RUN=Path('SYNTHETIC_PREVIOUS_CANDIDATE'),scope_core=local_scope,science=NS(core=NS(geos_geometry=geos)))
    parent.strip=lambda arrays,prefix:{k[len(prefix):]:v for k,v in arrays.items()
        if k.startswith(prefix) and not k.endswith('__packbits')}
    parent.core=NS(unpack=lambda mask,n:np.unpackbits(mask,bitorder='little')[:n].astype(bool))
    spec=importlib.util.spec_from_file_location('synthetic_edge_cover_driver',Path(__file__).with_name('edge_cover_driver.py'))
    d=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'suffix_full_merge_driver':parent}): spec.loader.exec_module(d)
    return d


def build(d,saved=None):
    xy,time,states,labels=fixture()
    full=dict(xy=xy,all_reason_flags=np.ones(4,np.uint16),all_scope_packbits=np.array([15],np.uint8))
    for prefix in ('merge','upper_merge','local_motion','probe_merge','suffix_merge'):
        full[prefix+'_changed_oldpath__packbits']=np.array([1],np.uint8)
    diagnostic={'union_index':np.arange(4,dtype=np.int64),'xy':xy.copy()}
    for tag in ('oldpath','independent'):
        diagnostic.update({tag+'__label__'+k:v for k,v in labels.items()})
        diagnostic[tag+'__metric__initial_origin']=np.array([0,1,0,0],bool)
        diagnostic[tag+'__metric__time_leaf_origin']=np.zeros(4,bool)
    result=d.build('synthetic','oldpath',time,states,0.,V,labels,(full,{},{}),(diagnostic,{}),saved=saved)
    return result,full


class DriverTests(unittest.TestCase):
    def setUp(self): self.d=load_driver()

    def equal(self,a,b):
        self.assertEqual(set(a),set(b))
        for key in a: self.assertTrue(local_scope.same(a[key],b[key]),key)

    def test_no_real_read_or_output_on_synthetic_build(self):
        (arrays,counts,_),_=build(self.d)
        self.d.base.read_arrays.assert_not_called(); self.d.base.save_arrays.assert_not_called()
        self.assertEqual(counts['scope_records'],4); self.assertEqual(counts['selected_uncertain_witnessed_edges'],1)
        self.assertEqual(counts['new_edge_certified_candidates'],1)
        self.assertEqual(arrays['trace__faces_m'].shape,(4,64,4))

    def test_full_independent_build_every_saved_field_exact(self):
        (arrays,counts,_),_=build(self.d)
        (other,values,checked),_=build(self.d,saved=arrays)
        self.equal(arrays,other); self.assertEqual(counts,values)
        self.assertTrue(checked['complete_interval_cover_tree_frontier_budget_padding_checked'])

    def test_all_prior_provenance_including_suffix_preserved(self):
        (arrays,_,_),full=build(self.d)
        for name,value in full.items():
            if name.endswith('__packbits'):
                if name=='all_scope_packbits': continue
                self.assertTrue(local_scope.same(arrays['parent_provenance__'+name],value))

    def test_retained_initial_unknown_and_original_status_exact(self):
        (arrays,counts,_),_=build(self.d)
        self.assertEqual(arrays['retained_unknown_union_index'].tolist(),[1])
        self.assertEqual(counts['initial_unknown_exactly_retained'],1)
        for name in ('contact_status','contact_lower_s','contact_upper_s'):
            self.assertTrue(local_scope.same(arrays['original__'+name],arrays['candidate__'+name]))

    def project(self,index,scalar):
        (arrays,_,_),full=build(self.d)
        source={'union_index':index,'xy':full['xy'][index]}
        for name,value in full.items():
            if name.endswith('__packbits') and name!='all_scope_packbits':
                source[name]=np.packbits(np.unpackbits(value,bitorder='little')[index],bitorder='little')
        self.d.base.read_arrays.return_value=source,{}
        return self.d.projection('synthetic',full,arrays,scalar=scalar)

    def test_original_order_int32_duplicates_all3d_traces(self):
        index=np.array([3,0,1,0,2],np.int32)
        a,rec=self.project(index,False); b,other=self.project(index,True)
        self.equal(a,b); self.assertEqual(rec,other)
        self.assertEqual(a['trace__faces_m'].shape,(5,64,4))
        self.assertEqual(a['source_union_index'].dtype,np.int32)
        self.assertTrue(local_scope.same(a['trace__faces_m'][1],a['trace__faces_m'][3]))

    def test_empty_original_order_3d_and_frontier_shapes(self):
        a,_=self.project(np.array([],np.int64),False); b,_=self.project(np.array([],np.int64),True)
        self.equal(a,b)
        self.assertEqual(a['trace__faces_m'].shape,(0,64,4)); self.assertEqual(a['trace__frontier_a_s'].shape,(0,65))

    def test_projection_tail_padding_and_packed_masks(self):
        a,_=self.project(np.array([0,1,0,3,2],np.int64),False)
        for key,value in a.items():
            if key.endswith('__packbits'):
                self.assertFalse(np.unpackbits(value,bitorder='little')[5:].any())

    def test_omitted_scope_row_rejected_before_any_source_read(self):
        (arrays,_,_),full=build(self.d); arrays['union_index']=arrays['union_index'][:-1]
        with self.assertRaises(RuntimeError): self.d.projection('synthetic',full,arrays)
        self.d.base.read_arrays.assert_not_called()

    def test_independent_failure_preserves_full_counterexample(self):
        (arrays,_,_),_=build(self.d); arrays['trace__kind'][0,0]=4
        with self.assertRaises(ValueError): build(self.d,saved=arrays)
        self.d.base.save_arrays.assert_called_once()
        saved=self.d.base.save_arrays.call_args.args[1]
        self.assertIn('saved__trace__faces_m',saved)
        self.assertIn('last_geometry__query_xy',saved)


if __name__=='__main__': unittest.main()
