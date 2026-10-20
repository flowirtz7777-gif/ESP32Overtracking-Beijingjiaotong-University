import unittest
import numpy as np
from run_audit import summarize_prefix


class AuditContractTests(unittest.TestCase):
    def test_unknown_not_accepted_as_excluded(self):
        arrays={'prefix_excluded':np.array([True,False]),'early_contact_witness':np.array([False,False]),
            'prefix_undetermined':np.array([False,True]),'budget_exhausted':np.array([False,True])}
        result=summarize_prefix(arrays)
        self.assertFalse(result['strict_prefix_gate_passed'])
        self.assertEqual(result['budget_exhausted'],1)

    def test_early_witness_not_a_pass(self):
        arrays={'prefix_excluded':np.array([False]),'early_contact_witness':np.array([True]),
            'prefix_undetermined':np.array([False]),'budget_exhausted':np.array([False])}
        self.assertEqual(summarize_prefix(arrays)['early_contact_witness'],1)

    def test_contradictory_state_rejected(self):
        arrays={k:np.array([True]) for k in ('prefix_excluded','early_contact_witness','prefix_undetermined','budget_exhausted')}
        with self.assertRaises(RuntimeError):
            summarize_prefix(arrays)

    def test_empty_prefix_population(self):
        arrays={k:np.zeros(0,bool) for k in ('prefix_excluded','early_contact_witness','prefix_undetermined','budget_exhausted')}
        result=summarize_prefix(arrays)
        self.assertEqual(result['points'],0)


if __name__=='__main__':
    unittest.main()
