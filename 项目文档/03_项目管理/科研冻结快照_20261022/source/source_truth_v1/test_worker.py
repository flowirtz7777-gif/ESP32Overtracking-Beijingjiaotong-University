import unittest
from copy import deepcopy
from fractions import Fraction as F
from .worker import certify_chain,cover_point

def record(a,b,center=(0,0,0,0)):
    return dict(start=F(a),end=F(b),center=list(map(F,center)),P=[[F(0)]*7 for _ in range(4)],
        alpha=[F(0)]*7,n=6,alpha_error=F(0),worker_full_errors=[0]*4)
def fixture(errors=None):
    rec=[record(0,F(1,5)),record(F(1,5),F(2,5))]
    err=[F(0)]*4 if errors is None else errors
    chain=dict(steps=[dict(start=r["start"],end=r["end"],end_errors=list(err)) for r in rec])
    return rec,chain,dict(original_index=3,union_index=9,xy=(F(4),F(0))),dict(l_h=F(2),L=F(10),width=F(2))
class WorkerTests(unittest.TestCase):
    def test_full_far_geometry_and_full_trace_metering(self):
        r,c,p,v=fixture()
        out=cover_point(r,c,p,v,F(2,5),F(1,20),10)
        self.assertEqual(out["summary"]["candidate_status"],"noncontact")
        self.assertEqual(out["geometry_evaluations"],2)
        self.assertEqual(out["compiled_step_count"],2)
        self.assertEqual(out["point"]["original_index"],3)
    def test_contact_exists_does_not_invent_face_certificate(self):
        r,c,p,v=fixture();p["xy"]=(-3,0)
        out=cover_point(r,c,p,v,F(2,5),F(1,20),10)
        self.assertEqual(out["summary"]["candidate_status"],"contact_exists")
        self.assertFalse(out["summary"]["face_certification_complete"])
        self.assertFalse(out["summary"]["scientific_admission_allowed"])
    def test_uncomputed_budget_time_preserved_not_negative(self):
        r,c,p,v=fixture()
        out=cover_point(r,c,p,v,F(2,5),F(1,20),1)
        self.assertEqual(out["geometry_evaluations"],1)
        self.assertEqual(out["summary"]["candidate_status"],"unknown")
        self.assertTrue(any(x["distance_squared"] is None for s in out["steps"] for x in s["frontier"]))
    def test_unknown_parents_metered_and_depth_bounded(self):
        r,c,p,v=fixture([F(1,10)]*4);p["xy"]=(F(41,20),0)
        out=cover_point(r,c,p,v,F(2,5),F(1,20),10,2)
        self.assertLessEqual(out["geometry_evaluations"],10)
        self.assertGreater(out["geometry_evaluations"],sum(len(s["frontier"]) for s in out["steps"] if all(x["trace_index"] is not None for x in s["frontier"])))
        calls=[t["call_index"] for s in out["steps"] for t in s["evaluated_trace"]]
        self.assertEqual(calls,list(range(len(calls))))
    def test_source_gap_or_zeroed_claim_cannot_reset_chain(self):
        r,c,p,v=fixture()
        params=dict(v=F(1),l=F(4),lh=F(2),L=F(10))
        chain=certify_chain(r,[0]*4,F(2,5),params)
        self.assertGreater(chain["steps"][1]["initial_errors"][0],0)
        self.assertGreater(chain["steps"][1]["end_errors"][0],chain["steps"][0]["end_errors"][0])
        r[1]["start"]=F(1,4)
        with self.assertRaises(ValueError):certify_chain(r,[0]*4,F(2,5),params)
    def test_bad_point_and_chain_identity(self):
        r,c,p,v=fixture();p["original_index"]=True
        with self.assertRaises(ValueError):cover_point(r,c,p,v,F(2,5),F(1,20),10)
        r,c,p,v=fixture();c["steps"][1]["start"]=F(1,4)
        with self.assertRaises(ValueError):cover_point(r,c,p,v,F(2,5),F(1,20),10)
if __name__=="__main__":unittest.main()
