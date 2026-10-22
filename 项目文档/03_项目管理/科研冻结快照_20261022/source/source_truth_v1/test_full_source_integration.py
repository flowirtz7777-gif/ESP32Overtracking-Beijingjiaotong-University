from copy import deepcopy
from fractions import Fraction as F
import unittest
from . import core,worker,audit_core
from .primary import source_control_enclosure as sc,general_step_residual as p

def fixture():
    c=dict(peak=F(.3),entry_rate=F(.1),return_rate=F(.2),blend=F(.2),pre=F(6),entry_duration=F(.3/.1+.2),plateau=F(2))
    v=dict(l=F(4),l_h=F(9,5),L=F(27,2),width=F(2));speed=F(2);end=F(1,5);initial=[F(0),F(0),F(1),F(1,20)]
    points=[dict(original_index=4,union_index=9,xy=[F(100),F(100)]),dict(original_index=7,union_index=12,xy=[F(-100),F(-100)])]
    limits=dict(maximum_step=F(1,5),maximum_steps=512,degree=6,time_error=F(1,2**48),tolerance=F(1,20),geometry_evaluations_per_point=4096,maximum_geometry_depth=24)
    args=dict(control=c,vehicle=v,speed=speed,end=end,initial=initial,points=points,limits=limits)
    times=sc.partition(c,end,limits["maximum_step"]);center=list(initial);errors=[F(0)]*4;records=[];params=dict(v=speed,l=v["l"],lh=v["l_h"],L=v["L"])
    for left,right in zip(times,times[1:]):
        h=right-left;alpha,ae,trace=sc.enclose(c,left,h,limits["time_error"],6)
        P,alpha=p.build(center,alpha,6,h,**params)
        proof=p.certify(center,P,alpha,6,h,**params,initial_errors=errors,alpha_error=ae)
        records.append(dict(start=left,end=right,center=list(center),P=P,alpha=alpha,alpha_error=ae,source_branch_trace=trace,n=6))
        center,raw=p.recenter(center,P,h,proof["end_state_error_bounds"])
        errors=[worker._up(e) for e in raw]
    return args,dict(args,steps=records)

class FullSourceIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.args,cls.artifact=fixture()
    def test_full_source_binding_and_both_point_geometry(self):
        r=core.worker_geometry(self.artifact,self.args)
        self.assertTrue(r["complete_source_control_bound"])
        self.assertEqual(len(r["point_covers"]),2)
        self.assertTrue(all(x["summary"]["candidate_status"]=="noncontact" for x in r["point_covers"]))
        self.assertFalse(r["full_population_admission_allowed"])
    def test_worker_and_independent_geometry_whole_chain(self):
        worker_result=core.worker_geometry(self.artifact,self.args)
        own=core.independent_geometry(self.artifact,self.args,worker_result)
        self.assertEqual(own["existence_candidates"],2)
        self.assertTrue(all(x["candidate_status"]=="candidate_noncontact_mutual" for x in own["point_results"]))
        self.assertFalse(own["full_population_admission_allowed"])
    def test_actual_float_point_values_preserve_exact_binary_identity(self):
        args=deepcopy(self.args);artifact=deepcopy(self.artifact)
        for source in (args,artifact):
            for point in source["points"]:point["xy"]=[float(x) for x in point["xy"]]
        result=core.worker_geometry(artifact,args)
        own=core.independent_geometry(artifact,args,result)
        self.assertEqual(own["existence_candidates"],2)
    def test_codec_complete_worker_and_independent_artifacts(self):
        from .independent_math import proof_codec
        result=core.worker_geometry(self.artifact,self.args)
        own=core.independent_geometry(self.artifact,self.args,result)
        for value in (result,own):self.assertEqual(proof_codec.decode(proof_codec.encode(value)),value)
    def test_control_phase_or_whole_input_tamper_rejected(self):
        for kind in ("control","partition","missing_point"):
            bad=deepcopy(self.artifact)
            if kind=="control":bad["steps"][0]["alpha_error"]+=1
            elif kind=="partition":bad["steps"]=bad["steps"][:-1]
            else:bad["points"]=bad["points"][:1]
            with self.assertRaises(ValueError):core.bind_source(bad,self.args)
    def test_budget_order_and_step_cannot_be_increased(self):
        for key,value in (("degree",8),("maximum_step",F(1,4)),("geometry_evaluations_per_point",8192),("maximum_geometry_depth",25)):
            args=deepcopy(self.args);args["limits"][key]=value;art=deepcopy(self.artifact);art["limits"]=deepcopy(args["limits"])
            with self.assertRaises(ValueError):core.bind_source(art,args)
    def test_independent_source_own_chain_recomputed(self):
        a=self.args
        own=audit_core.audit(self.artifact,a["control"],a["vehicle"],a["speed"],a["end"],a["initial"],a["points"],a["limits"])
        self.assertTrue(own["independent_full_source_chain_verified"])
        self.assertEqual(len(own["independent_chain"]["steps"]),len(self.artifact["steps"]))
        self.assertFalse(own["scientific_label_promotion_allowed"])
if __name__=="__main__":unittest.main()
