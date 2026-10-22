import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

from . import checker as C

def fixtures(h=F(1),end_errors=(0,0,0,0)):
    center=[F(0)]*4;n=4;P=[[F(0)]*(n+1) for _ in range(4)]
    source=[dict(start=F(0),end=h,center=center,P=P,n=n)]
    own=[dict(start=F(0),end=h,initial_errors=(0,0,0,0),end_errors=end_errors)]
    point=dict(original_index=7,union_index=11,xy=(F(10),F(0)))
    return source,own,point


def cover(point, *, split=False, unknown_right=False, claimed=(1,1), total_override=None):
    h=F(1)
    if not split:
        trace=[dict(local_time=(F(0),h),depth=0,distance_squared=claimed,
                    finite_edge_distance_squared=(claimed,claimed,claimed,claimed),call_index=0)]
        frontier=[dict(local_time=(F(0),h),depth=0,trace_index=0,
                       distance_squared=claimed,evaluations=1)]
    else:
        left=(F(0),F(1,2));right=(F(1,2),h)
        trace=[
            dict(local_time=(F(0),h),depth=0,distance_squared=claimed,
                 finite_edge_distance_squared=(claimed,)*4,call_index=0),
            dict(local_time=left,depth=1,distance_squared=claimed,
                 finite_edge_distance_squared=(claimed,)*4,call_index=1),
        ]
        frontier=[dict(local_time=left,depth=1,trace_index=1,distance_squared=claimed,evaluations=1)]
        if unknown_right:
            frontier.append(dict(local_time=right,depth=1,trace_index=None,distance_squared=None,evaluations=0))
        else:
            trace.append(dict(local_time=right,depth=1,distance_squared=claimed,
                finite_edge_distance_squared=(claimed,)*4,call_index=2))
            frontier.append(dict(local_time=right,depth=1,trace_index=2,distance_squared=claimed,evaluations=1))
    worker_point=dict(original_index=point["original_index"],union_index=point["union_index"],xy=tuple(point["xy"]))
    return dict(point=worker_point,steps=[dict(step_index=0,start=F(0),end=h,
        evaluated_trace=trace,frontier=frontier)],
        geometry_evaluations=len(trace) if total_override is None else total_override,
        summary={})


class IndependentChainCheckerTests(unittest.TestCase):
    def runcheck(self,source,own,point,w,**kw):
        return C.check_point(source,own,point,w,hitch_offset=0,trailer_length=4,width=2,tolerance=F(1,20),**kw)

    def test_full_step_root_and_four_face_order_recomputed(self):
        src,own,p=fixtures()
        w=cover(p,claimed=(100,100))
        # Point x=10 is certainly outside; all own four face distances are returned.
        out=self.runcheck(src,own,p,w)
        self.assertEqual(out["candidate_status"],"candidate_noncontact_mutual")
        self.assertEqual(out["step_reports"][0]["own_trace"][0]["own_finite_edge_distance_squared"],
                         ((F(100),F(100)),(F(101),F(101)),(F(196),F(196)),(F(101),F(101))))
        self.assertEqual(out["face_candidate_mask"],255)

    def test_own_chain_error_not_zeroed_by_worker_exclusion(self):
        src,own,p=fixtures(end_errors=(F(1,10),0,0,0));p["xy"]=(F(0),F(0))
        w=cover(p,claimed=(1,1))
        out=self.runcheck(src,own,p,w)
        leaf=out["step_reports"][0]["frontier"][0]
        self.assertEqual(leaf["own_state"],"unknown")
        self.assertEqual(leaf["worker_state"],"excluded")
        self.assertEqual(leaf["conflict"],"worker_exclusion_not_reproduced_by_own_tube")
        self.assertEqual(out["candidate_status"],"unknown_or_conflict")

    def test_budget_partial_unknown_keeps_suffix_unknown(self):
        src,own,p=fixtures()
        w=cover(p,split=True,unknown_right=True,claimed=(100,100))
        out=self.runcheck(src,own,p,w)
        self.assertEqual(out["candidate_status"],"unknown_or_conflict")
        self.assertEqual(out["step_reports"][0]["frontier"][-1]["own_state"],"unknown")
        self.assertTrue(out["entire_original_horizon_covered"])

    def test_rejects_omitted_split_parent_or_child(self):
        src,own,p=fixtures()
        w=cover(p,split=True,claimed=(100,100))
        w["steps"][0]["evaluated_trace"].pop(0)
        w["geometry_evaluations"]-=1
        with self.assertRaises(ValueError):self.runcheck(src,own,p,w)
        w=cover(p,split=True,claimed=(100,100))
        w["steps"][0]["frontier"].pop()
        with self.assertRaises(ValueError):self.runcheck(src,own,p,w)

    def test_rejects_reordered_indices_wrong_identity_and_call_budget(self):
        src,own,p=fixtures()
        w=cover(p,claimed=(100,100));w["steps"][0]["evaluated_trace"][0]["call_index"]=2
        with self.assertRaises(ValueError):self.runcheck(src,own,p,w)
        w=cover(p,claimed=(100,100));w["point"]["original_index"]=99
        with self.assertRaises(ValueError):self.runcheck(src,own,p,w)
        w=cover(p,claimed=(100,100));w["geometry_evaluations"]=4097
        with self.assertRaises(ValueError):self.runcheck(src,own,p,w)

    def test_rejects_own_chain_tube_reset_at_transition(self):
        h=F(1,2);n=4;c=[F(0)]*4;P=[[F(0)]*(n+1) for _ in range(4)]
        P[0][1]=F(1)
        src=[dict(start=F(0),end=h,center=c,P=P,n=n),
             dict(start=h,end=F(1),center=[F(1),F(0),F(0),F(0)],P=[[F(0)]*(n+1) for _ in range(4)],n=n)]
        own=[dict(start=F(0),end=h,initial_errors=(0,0,0,0),end_errors=(F(1,100),0,0,0)),
             dict(start=h,end=F(1),initial_errors=(0,0,0,0),end_errors=(0,0,0,0))]
        with self.assertRaises(ValueError):C._source_chain(src,own)

    def test_check_callback_runs_per_cell_and_interrupts(self):
        src,own,p=fixtures();w=cover(p,split=True,claimed=(100,100))
        seen=[]
        out=self.runcheck(src,own,p,w,check=lambda:seen.append(len(seen)))
        self.assertEqual(out["candidate_status"],"candidate_noncontact_mutual")
        self.assertGreaterEqual(len(seen),12)
        class Interrupted(Exception):pass
        ticks=[0]
        def stop():
            ticks[0]+=1
            if ticks[0]==10:raise Interrupted
        with self.assertRaises(Interrupted):self.runcheck(src,own,p,w,check=stop)

    def test_over_budget_trace_rejected_before_any_geometry(self):
        from unittest.mock import patch
        src,own,p=fixtures();w=cover(p,claimed=(100,100))
        template=w["steps"][0]["evaluated_trace"][0]
        w["steps"][0]["evaluated_trace"]=[dict(template,call_index=i) for i in range(4097)]
        w["geometry_evaluations"]=4097
        with patch.object(C._GEOM,"project",side_effect=AssertionError("geometry must not run")) as project:
            with self.assertRaises(ValueError):self.runcheck(src,own,p,w)
            project.assert_not_called()

    def test_boolean_worker_point_identity_is_rejected(self):
        src,own,p=fixtures();w=cover(p,claimed=(100,100))
        w["point"]["original_index"]=True
        with self.assertRaises(ValueError):self.runcheck(src,own,p,w)


if __name__=="__main__":unittest.main()
