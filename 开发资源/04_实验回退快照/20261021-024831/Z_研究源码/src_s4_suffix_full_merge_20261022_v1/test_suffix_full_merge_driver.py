"""Driver adapter tests with an entirely synthetic parent; no research I/O/imports."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import numpy as np
import suffix_merge_core as core
from test_suffix_merge import fixture


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def load_driver():
    runtime = NS(require=require, file_hash=Mock(return_value='synthetic'), read=Mock())
    base = NS(read_arrays=Mock(), common=NS(array_hash=lambda a: a.tobytes().hex()),
              combine=lambda a,b: {k:v.copy() for k,v in a.items()},
              old_discrepancies=lambda target,combined: {'contact':np.zeros(len(target['xy']),bool)})
    merged = NS(core=NS(scalar_combine=base.combine,
                       scalar_discrepancies=base.old_discrepancies), checked_output=Mock())
    def classify(a,b,c):
        flags=np.where(c['contact_status']==2,1,0).astype(np.uint16)
        return flags,flags!=0
    def summarize(a,b,c,flags,scope):
        return {'unknown':int(scope.sum()),'records':len(scope)}
    census=NS(core=NS(classify=classify,independent_classify=classify,summarize=summarize),
              summarize_projection=lambda a,b,index,flags,scope:{'records':len(index)})
    parent=ModuleType('suffix_driver')
    parent.base,parent.r,parent.AUTH=base,runtime,Path('SYNTHETIC_AUTH')
    parent.parent=NS(census=census,merged=merged)
    parent.PARENT,parent.RUN=Path('SYNTHETIC_PARENT'),Path('SYNTHETIC_CANDIDATE')
    parent.DEPENDENCIES=()
    parent.configure=Mock()
    parent.verify=Mock()
    source=Path(__file__).with_name('suffix_full_merge_driver.template.py')
    if not source.exists():
        source=Path(__file__).with_name('suffix_full_merge_driver.py')
    spec=importlib.util.spec_from_file_location('synthetic_suffix_full_merge_driver',source)
    driver=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'suffix_driver':parent}):
        spec.loader.exec_module(driver)
    return driver


def payload():
    old,index,new,scope,found=fixture()
    xy=np.arange(10,dtype=np.float64).reshape(5,2)
    original={'xy':xy,'all_reason_flags':scope.astype(np.uint16),
              'all_scope_packbits':np.packbits(scope,bitorder='little')}
    for tag in core.TAGS:
        original.update({tag+'__'+k:v for k,v in old.items()})
        for prefix in ('merge','upper_merge','local_motion','probe_merge'):
            original[prefix+'_changed_'+tag+'__packbits']=np.array([4],np.uint8)
    asset=original,{}, {tag:old for tag in core.TAGS}
    candidates={'g/'+tag:(index,new,found) for tag in core.TAGS}
    return asset,candidates


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.d=load_driver()

    def equal_arrays(self,a,b):
        self.assertEqual(set(a),set(b))
        for key in a:
            self.assertTrue(core.same(a[key],b[key]),key)

    def test_import_uses_stub_only_no_parent_io(self):
        self.d.r.read.assert_not_called()
        self.d.r.file_hash.assert_not_called()
        self.d.base.read_arrays.assert_not_called()

    def test_unbound_hashes_fail_closed_before_candidate_reads(self):
        self.d.HASHES={}
        self.assertEqual(self.d.HASHES,{})
        with self.assertRaisesRegex(RuntimeError,'hashes must be frozen'):
            self.d.gate()
        self.d.r.read.assert_not_called()
        self.d.r.file_hash.assert_not_called()

    def test_gate_rejects_wrong_hash_keys(self):
        for hashes in ({'checkpoint.json':'x'}, {'unexpected':'x'}):
            self.d.HASHES=hashes
            with self.assertRaisesRegex(RuntimeError,'hashes must be frozen'):
                self.d.gate()

    def test_strip_removes_only_expected_prefix_and_packed_duplicates(self):
        arr={'original__contact_status':np.ones(2,np.int8),
             'original__flag__packbits':np.array([3],np.uint8),
             'candidate__contact_status':np.zeros(2,np.int8)}
        self.assertEqual(set(self.d.strip(arr,'original__')),{'contact_status'})

    def test_group_adapter_scalar_vector_all_fields_and_census(self):
        asset,candidates=payload()
        a=self.d.build_group('g',asset,candidates,scalar=False)
        b=self.d.build_group('g',asset,candidates,scalar=True)
        for tag in core.TAGS:
            self.equal_arrays(a[0][tag],b[0][tag])
            self.assertTrue(core.same(a[0][tag]['contact_lower_s'],asset[2][tag]['contact_lower_s']))
        self.equal_arrays(a[1],b[1]); self.equal_arrays(a[4],b[4])
        self.assertEqual(a[5],b[5])
        for name,value in asset[0].items():
            if name.endswith('__packbits') and name!='all_scope_packbits':
                self.assertTrue(core.same(value,a[4][name]))

    def test_group_adapter_rejects_changed_immutable_lower(self):
        asset,candidates=payload()
        candidates['g/oldpath'][1]['contact_lower_s'][0]=1.
        with self.assertRaises(ValueError):
            self.d.build_group('g',asset,candidates,scalar=False)

    def test_census_group_scalar_vector_multidimensional_and_empty(self):
        for scope in (np.array([1,0,1,0,0],bool),np.zeros(5,bool)):
            old,*_=fixture()
            old['matrix']=np.arange(10).reshape(5,2)
            xy=np.arange(10,dtype=float).reshape(5,2)
            args=(xy,{tag:old for tag in core.TAGS},old,np.arange(5,dtype=np.uint16),scope)
            a=self.d.census_group(*args,scalar=False)
            b=self.d.census_group(*args,scalar=True)
            self.equal_arrays(a,b)
            self.assertEqual(a['oldpath__matrix'].shape,(int(scope.sum()),2))

    def project(self,index,scalar):
        asset,candidates=payload()
        paths,combined,flags,scope,arrays,_=self.d.build_group('g',asset,candidates,scalar=scalar)
        xy=asset[0]['xy']
        old=core.project(index,xy,xy[index],asset[2],asset[2]['oldpath'],
            asset[0]['all_reason_flags'],asset[0]['all_reason_flags']!=0,asset[0])
        self.d.base.read_arrays.return_value=old,{}
        result=self.d.projection('synthetic',{'synthetic':{'target':{'xy':xy[index]}}},
            xy,paths,combined,flags,scope,arrays,scalar=scalar)
        return result,old

    def test_projection_original_order_duplicates_int32_and_int64(self):
        for dtype in (np.int32,np.int64):
            index=np.array([4,0,1,0,2,3],dtype)
            a,old=self.project(index,False)
            b,_=self.project(index,True)
            self.equal_arrays(a[0],b[0]); self.equal_arrays(a[2],b[2]); self.assertEqual(a[1],b[1])
            self.assertTrue(core.same(a[0]['union_index'],index))
            for name,value in old.items():
                if name.startswith(('merge_','upper_merge_','local_motion_','probe_merge_')):
                    self.assertTrue(core.same(a[0][name],value))
            self.assertEqual(a[2]['original_index'].tolist(),[0,2])
            self.assertEqual(a[2]['union_index'].tolist(),[4,1])

    def test_projection_empty_and_padding(self):
        for index in (np.array([],np.int32),np.array([4,1,4],np.int64)):
            a,_=self.project(index,False); b,_=self.project(index,True)
            self.equal_arrays(a[0],b[0]); self.equal_arrays(a[2],b[2])
            for name,value in a[0].items():
                if name.endswith('__packbits') or name=='all_scope_packbits':
                    self.assertFalse(np.unpackbits(value,bitorder='little')[len(index):].any())

    def test_copy_diagnostics_counts_and_checks_both_closed_files(self):
        self.d.r.read.return_value={'completed':{'g/oldpath':{'datasets':{'id':{'result_sha256':'synthetic'}}}}}
        self.d.r.batch=Mock()
        with patch.object(Path,'read_bytes',return_value=b'full synthetic 2D diagnostic bytes'):
            entry=self.d.copy_parent_diagnostics('g','oldpath','id')
            self.d.check_parent_diagnostics('oldpath','id',entry)
        writes=self.d.r.batch.call_args.args[0]
        self.assertEqual([p.name for p,_ in writes],['arrays.npz','result.json'])
        self.assertTrue(all(blob==b'full synthetic 2D diagnostic bytes' for _,blob in writes))


if __name__=='__main__':
    unittest.main()
