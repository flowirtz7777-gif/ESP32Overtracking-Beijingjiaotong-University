import unittest
from fractions import Fraction as F
from .frontier import summarize,source_distance_decision

def cell(a,b,bounds,index=0,calls=1):
    return dict(time=(a,b),distance_squared=bounds,step_index=index,evaluations=calls)

class FrontierTests(unittest.TestCase):
    def run_frontier(self,rows,steps=((0,1),(1,2)),budget=10):
        return summarize(steps,rows,2,F(1,20),budget)
    def test_full_horizon_exclusion(self):
        r=self.run_frontier([cell(0,1,(1,2)),cell(1,2,(1,2),1)])
        self.assertEqual(r["candidate_status"],"noncontact")
        self.assertFalse(r["scientific_admission_allowed"])
        self.assertEqual(r["face_candidate_mask"],255)
    def test_unknown_prefix_not_erased_by_later_contact(self):
        r=self.run_frontier([cell(0,1,None,calls=0),cell(1,2,(0,0),1)])
        self.assertEqual(r["candidate_status"],"contact_exists")
        self.assertEqual(r["first_contact_interval"],(F(0),F(1)))
        self.assertFalse(r["face_certification_complete"])
    def test_complete_exclusion_before_contact(self):
        r=self.run_frontier([cell(0,1,(1,2)),cell(1,2,(0,0),1)])
        self.assertEqual(r["first_contact_interval"],(F(1),F(1)))
    def test_uncomputed_suffix_blocks_noncontact(self):
        r=self.run_frontier([cell(0,1,(1,2)),cell(1,2,None,1,0)])
        self.assertEqual(r["candidate_status"],"unknown")
    def test_no_midpoint_truth_and_closed_tolerance(self):
        self.assertEqual(source_distance_decision((0,F(1,400)),F(1,20)),"contact_all_times_in_cell")
        self.assertEqual(source_distance_decision((0,F(1,399)),F(1,20)),"unknown")
    def test_gap_overlap_cross_step_or_missing_step_rejected(self):
        for rows in ([cell(0,F(1,2),(1,2)),cell(1,2,(1,2),1)],
                     [cell(0,1,(1,2)),cell(F(1,2),2,(1,2),1)],
                     [cell(0,2,(1,2))],
                     [cell(0,1,(1,2)),cell(1,2,(1,2))]):
            with self.assertRaises(ValueError):self.run_frontier(rows)
    def test_budget_or_unmetered_computation_rejected(self):
        for rows,budget in (([cell(0,1,(1,2)),cell(1,2,(1,2),1)],1),
                            ([cell(0,1,(1,2),calls=0),cell(1,2,(1,2),1)],10)):
            with self.assertRaises(ValueError):self.run_frontier(rows,budget=budget)
    def test_invalid_scalar_indices_and_horizon(self):
        for bad in (True,float("nan"),float("inf")):
            with self.assertRaises(ValueError):source_distance_decision((0,1),bad)
        for bad in (True,0.0,-1):
            with self.assertRaises(ValueError):self.run_frontier([cell(0,1,(1,2),bad),cell(1,2,(1,2),1)])
        with self.assertRaises(ValueError):self.run_frontier([cell(0,1,(1,2)),cell(1,2,(1,2),1)],steps=((0,1),(F(3,2),2)))
if __name__=="__main__":unittest.main()
