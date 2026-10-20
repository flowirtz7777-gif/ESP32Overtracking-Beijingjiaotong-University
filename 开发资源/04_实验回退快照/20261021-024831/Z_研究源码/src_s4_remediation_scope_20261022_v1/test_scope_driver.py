import importlib.util
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
from test_scope import registered,report,H


def require(ok,message):
    if not ok: raise RuntimeError(message)


def driver():
    parent=ModuleType('edge_cover_merge_driver')
    parent.r=NS(require=require); parent.configure=Mock()
    parent.RUN=Path('SYNTHETIC_PARENT'); parent.AUTH=Path('SYNTHETIC_AUTH')
    spec=importlib.util.spec_from_file_location('synthetic_scope_driver',Path(__file__).with_name('scope_driver.py'))
    d=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'edge_cover_merge_driver':parent}): spec.loader.exec_module(d)
    return d


class DriverTests(unittest.TestCase):
    def setUp(self): self.d=driver()

    def test_exact_new_plan_paths(self):
        self.assertEqual(self.d.PLAN.name,'resume_plan_20261022_0000_v42.json')
        self.assertEqual(self.d.CLOSED_PLAN.name,'resume_plan_20261022_0000_v43.json')
        self.assertEqual(self.d.RUN.name,'resume_20261022_0000_remediation_scope_v1')

    def test_no_io_or_scientific_entrypoint_on_import(self):
        self.assertFalse(hasattr(self.d.r,'read'))

    def block(self,bad=False):
        self.d.BLOCK=2
        entries=[]
        for i in range(2):
            value=registered(); value['report']=str(Path('synthetic')/str(i)/'report.json')
            if bad: value['point_outputs']={'../escape.npz':H}
            entries.append(value)
        checked=Mock(); read=Mock(return_value=(H,report()))
        with patch.object(Path,'exists',return_value=False):
            rows=self.d.block_rows(0,{'prediction_output_records':entries},({},{},{}),checked,read)
        return rows,checked

    def test_block_preserves_every_registry_row_and_unknown_link(self):
        rows,checked=self.block()
        self.assertEqual([v['registry_index'] for v in rows],[0,1])
        self.assertTrue(all(v['input_reconstruction_still_required'] for v in rows))
        self.assertTrue(all(v['expanded_full_coordinate_descriptor_link_resolved'] is False for v in rows))
        self.assertTrue(all(v['configuration_present'] is False for v in rows))
        self.assertEqual(checked.call_count,2)

    def test_output_parent_escape_rejected_before_hash(self):
        with self.assertRaises(RuntimeError): self.block(bad=True)

    def test_every_nonmapping_descriptor_preserved_without_claim(self):
        for value in ([],['point','report'],None,3,'text'):
            row=self.d.core.descriptor('synthetic',H,value)
            self.assertEqual(row['json_kind'],type(value).__name__)
            self.assertFalse(row['scientific_truth_accepted'])


if __name__=='__main__': unittest.main()
