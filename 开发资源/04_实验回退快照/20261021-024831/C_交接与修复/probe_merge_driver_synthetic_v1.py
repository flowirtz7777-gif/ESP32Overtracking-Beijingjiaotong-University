"""Synthetic-only adapter tests; import frozen driver, never call scientific entrypoints."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14')
sys.path.insert(0,str(ROOT/'src_s4_unwitnessed_probe_merge_20261022_v1'))
import probe_merge_driver as d
from test_probe_merge import fixture
import numpy as np


class DriverTests(unittest.TestCase):
    def synthetic(self):
        old,*_=fixture()
        paths={tag:{k:v.copy() for k,v in old.items()} for tag in d.core.TAGS}
        combined=d.base.combine(paths['oldpath'],paths['independent'])
        flags,scope=d.census.core.classify(paths['oldpath'],paths['independent'],combined)
        original={'xy':np.arange(10,dtype=np.float64).reshape(5,2),'all_reason_flags':flags,
                  'all_scope_packbits':np.packbits(scope,bitorder='little'),
                  'local_motion_changed_oldpath__packbits':np.array([4],np.uint8)}
        for tag,values in (*paths.items(),('combined',combined)):
            original.update({tag+'__'+k:v for k,v in values.items()})
        ids=np.flatnonzero(scope).astype(np.int64)
        proposed={k:v[ids].copy() for k,v in old.items()}
        proposed['contact_status'][0]=1; proposed['contact_upper_s'][0]=.2
        proposed['nominal_instantaneous_edge'][0]=3; proposed['possible_edge_codes'][0]=4
        proposed['edge_certain'][0]=True
        found=np.zeros(len(ids),bool); found[0]=True
        candidates={'g/'+tag:(ids,proposed,found) for tag in d.core.TAGS}
        return (original,{},paths),candidates

    def test_driver_import_and_resource_policy(self):
        self.assertEqual(d.r.CAP,32*1024**3); self.assertEqual(d.r.RUN_CAP,1024**3)
        self.assertEqual(d.r.RESERVE,3*1024**3)

    def test_full_group_vector_scalar_equal_and_new_upper_allowed(self):
        asset,candidates=self.synthetic()
        a=d.build_group('g',asset,candidates,scalar=False)
        b=d.build_group('g',asset,candidates,scalar=True)
        self.assertEqual(a[-1],b[-1])
        self.assertTrue(all(d.core.same(a[4][k],b[4][k]) for k in a[4]))
        self.assertEqual(a[0]['oldpath']['contact_upper_s'][0],.2)
        self.assertTrue(d.core.same(a[0]['oldpath']['contact_lower_s'],asset[2]['oldpath']['contact_lower_s']))

    def test_full_census_reclassified_not_old_mask(self):
        asset,candidates=self.synthetic()
        paths,combined,flags,scope,arrays,summary=d.build_group('g',asset,candidates,scalar=False)
        self.assertTrue(asset[0]['all_reason_flags'][0]!=0)
        self.assertEqual(flags[0],0); self.assertFalse(scope[0])
        self.assertEqual(summary['combined_status_unknown'],2)

    def test_full_census_projection_scalar_exact(self):
        asset,candidates=self.synthetic()
        paths,combined,flags,scope,arrays,_=d.build_group('g',asset,candidates,scalar=False)
        a=d.census_group(arrays['xy'],paths,combined,flags,scope,scalar=False)
        b=d.census_group(arrays['xy'],paths,combined,flags,scope,scalar=True)
        self.assertTrue(all(d.core.same(a[k],b[k]) for k in a))

    def test_old_provenance_still_exact_after_new_scope(self):
        asset,candidates=self.synthetic()
        out=d.build_group('g',asset,candidates,scalar=False)[4]
        self.assertTrue(d.core.same(out['local_motion_changed_oldpath__packbits'],asset[0]['local_motion_changed_oldpath__packbits']))


if __name__=='__main__':
    import subprocess
    results=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DriverTests))
    # I/O evidence is administrative; test inputs above are entirely synthetic.
    DEV=d.AUTH/'runtime_sessions/unwitnessed_probe_merge_development_tests_v3'
    d.r.require(not DEV.exists(),'Adapter test version already used')
    d.configure()
    d.r.batch([(DEV/'adapter_tests.py',Path(__file__).read_bytes()),
        (DEV/'result.json',d.r.encoded(dict(time=d.r.now(),tests_run=results.testsRun,
            succeeded=results.wasSuccessful(),failures=[(str(t),s) for t,s in results.failures],
            errors=[(str(t),s) for t,s in results.errors],synthetic_only=True,
            frozen_driver_sha256=d.r.file_hash(Path(d.__file__)),
            frozen_core_sha256=d.r.file_hash(d.SOURCE/'probe_merge_core.py'))))])
    sys.exit(0 if results.wasSuccessful() else 1)
