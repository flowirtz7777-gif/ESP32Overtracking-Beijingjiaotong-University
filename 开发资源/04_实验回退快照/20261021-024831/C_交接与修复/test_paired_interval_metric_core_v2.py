import unittest
from fractions import Fraction as F
import paired_interval_metric_core_v2 as c
from client_execution_contract_v2 import decode_edge_mask

class Tests(unittest.TestCase):
    def test_scored_and_legacy_valid_start_are_explicitly_different(self):
        alarms=[c.Alarm(1,2)]
        self.assertEqual(c.insufficiency(3,alarms,valid_alarm_start=None),0)
        self.assertEqual(c.insufficiency(3,alarms,valid_alarm_start=2),1)

    def test_missing_valid_gate_rejected_before_any_result(self):
        with self.assertRaises(TypeError): c.insufficiency(3,[])
        with self.assertRaises(TypeError): c.point_domain((3,3),[],[],timelines_complete=True)

    def test_raw_mask255_cannot_be_used_as_single_atomic_edge(self):
        with self.assertRaises(ValueError): c.point_domain((3,3),[],[],edge_codes=(255,),valid_alarm_start=2,timelines_complete=True)
        state=c.point_domain((3,3),[],[c.Alarm(2,2)],edge_codes=decode_edge_mask(255),valid_alarm_start=2,timelines_complete=True)
        self.assertEqual(state,{(0,0),(1,1)})

    def test_alarm_iterators_not_exhausted_by_boundary_partition(self):
        state=c.point_domain((3,3),iter([]),iter([c.Alarm(2,2)]),valid_alarm_start=2,timelines_complete=True)
        self.assertEqual(state,{(1,1)})

    def test_invalid_base_and_boolean_certificate_rejected(self):
        with self.assertRaises(ValueError): c.ratio_bounds([],base_numerator=2,base_denominator=1)
        with self.assertRaises(ValueError): c.point_domain((3,3),[],[],valid_alarm_start=2,timelines_complete=1)

    def test_v2_keeps_negative_numerator_joint_ratio_and_sign(self):
        result=c.ratio_bounds([{(0,0),(0,1)}],base_numerator=-1,base_denominator=1)
        self.assertEqual((result['lower'],result['upper']),(F(-1),F(-1,2)))
        self.assertEqual(result['verdict'],'A_strictly_better')

    def test_later_supported_alarm_selected_after_contact_change(self):
        events=[c.Alarm(1,2),c.Alarm(2.5,2)]
        self.assertEqual(c.insufficiency(3,events,valid_alarm_start=2),1)
        self.assertEqual(c.insufficiency(4,events,valid_alarm_start=2),0)

if __name__=='__main__': unittest.main()
