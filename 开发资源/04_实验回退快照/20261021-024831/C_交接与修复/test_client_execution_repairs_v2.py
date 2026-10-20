"""Pure synthetic regression: original trace mismatch and independent scalar oracle."""
import ast
from datetime import datetime,timedelta,timezone
from pathlib import Path
import random
import unittest
import numpy as np
import scored_trace_adapter_core_v1 as adapter
import client_execution_contract_v2 as contract

def old_trace():
    path=Path(r'Z:\大创内轮差项目_实验结果\科研实验_2026-10-14\src_s4_temporal_trace_v2\run_trace.py')
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    nodes=[v for v in tree.body if isinstance(v,ast.FunctionDef) and v.name in ('confirmation_trace','trace_point_outputs')]
    namespace={'np':np,'EPS':1e-9}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace['trace_point_outputs']

def scalar_oracle(times,hits,contacts,fronts,confirmation,horizons,start,end):
    n=len(contacts); eps=1e-9
    result={k:np.zeros(n,dtype=np.int32) for k in adapter.FIELDS}
    for k in ('raw','first','valid'): result[k]=np.full(n,np.nan)
    frames=np.zeros((len(times),4),dtype=np.int32)
    for point,c in enumerate(contacts):
        negative=bool(np.isnan(c)); eligible=not fronts[point] and not negative and start-eps<=c<=end+eps
        since=None; last=-2
        for k,t in enumerate(times):
            hit=bool(hits[k,point]); confirmed=False
            if hit:
                if last!=k-1: since=t
                last=k; confirmed=t-since>=confirmation-eps
                if np.isnan(result['raw'][point]): result['raw'][point]=t
            supported=not negative and t-eps<=c<=t+horizons[k]+eps
            reference=not negative and t-eps<=c<=t+2+eps
            before=not negative and c>=t-eps
            if confirmed and t>=start-eps:
                if np.isnan(result['first'][point]): result['first'][point]=t
                if supported and np.isnan(result['valid'][point]): result['valid'][point]=t
            if not start-eps<=t<=end+eps: continue
            if eligible:
                result['support'][point]+=supported
                result['negative_opportunities'][point]+=before and not supported
                result['ref_negative_opportunities'][point]+=before and not reference
            if negative:
                result['negative_opportunities'][point]+=1; result['ref_negative_opportunities'][point]+=1
            if confirmed and (eligible or negative) and (before or negative):
                result['TP'][point]+=supported; result['FP'][point]+=not supported
                result['ref_FP'][point]+=not reference
                frames[k,0]+=supported; frames[k,1]+=not supported
            if eligible and supported: frames[k,3]+=1
            if negative or eligible and c>t+horizons[k]+eps: frames[k,2]+=1
    frames[:,2]-=frames[:,1]; frames[:,3]-=frames[:,0]
    return result,frames

class TraceTests(unittest.TestCase):
    def test_original_trace_drops_negative_false_alarm(self):
        time=np.array([2.]); hits=np.ones((1,1),dtype=bool); contact=np.array([np.nan])
        original=old_trace()(time,hits,contact,0,2)[0]
        corrected=adapter.scored_trace(time,hits,contact,np.array([False]),0,np.array([2.]),2,2)[0]
        self.assertEqual(original['FP'].tolist(),[0]); self.assertEqual(corrected['FP'].tolist(),[1])
        self.assertEqual(original['negative_opportunities'].tolist(),[0]); self.assertEqual(corrected['negative_opportunities'].tolist(),[1])

    def test_original_trace_counts_ineligible_front_contacts(self):
        time=np.array([2.]); hits=np.ones((1,1),dtype=bool); contact=np.array([3.])
        original=old_trace()(time,hits,contact,0,5)[0]
        corrected=adapter.scored_trace(time,hits,contact,np.array([True]),0,np.array([2.]),2,5)[0]
        self.assertEqual(original['TP'].tolist(),[1]); self.assertEqual(corrected['TP'].tolist(),[0])

    def test_warmup_confirmation_preserved_but_scored_first_starts_at_two(self):
        t=np.array([1.,1.5,2.,2.5]); hit=np.ones((4,1),bool)
        out,confirmed,_,_=adapter.scored_trace(t,hit,np.array([3.]),np.array([False]),1.,np.full(4,2.),2.,5.)
        self.assertEqual(out['raw'][0],1.); self.assertEqual(out['first'][0],2.); self.assertEqual(out['valid'][0],2.)
        self.assertEqual(confirmed[:,0].tolist(),[False,False,True,True])

    def test_variable_horizon_and_reference_false_alarm_differ(self):
        out,_,_,_=adapter.scored_trace(np.array([2.]),np.ones((1,1),bool),np.array([5.]),np.array([False]),0,np.array([3.]),2,5)
        self.assertEqual(out['TP'][0],1); self.assertEqual(out['FP'][0],0); self.assertEqual(out['ref_FP'][0],1)

    def test_new_contact_reconstructs_valid_from_later_event(self):
        t=np.array([2.,3.5]); hit=np.ones((2,1),bool)
        old=adapter.scored_trace(t,hit,np.array([3.]),np.array([False]),0,np.array([2.,2.]),2,8)[0]
        new=adapter.scored_trace(t,hit,np.array([5.]),np.array([False]),0,np.array([2.,2.]),2,8)[0]
        self.assertEqual(old['valid'][0],2.); self.assertEqual(new['valid'][0],3.5)

    def test_adapter_matches_independent_scalar_oracle_100_populations(self):
        rng=np.random.default_rng(1021)
        for _ in range(100):
            t=np.arange(0,5.25,.25); hits=rng.random((len(t),7))>.4
            contact=rng.choice(np.array([np.nan,.5,2.,2.-1e-9,2.+1e-9,3.,4.,5.,5.+1e-9,7.]),size=7)
            front=rng.random(7)<.25; horizon=rng.choice([2.,3.],size=len(t)); confirmation=float(rng.choice([0.,.25,.5]))
            actual,_,_,frames=adapter.scored_trace(t,hits,contact,front,confirmation,horizon,2.,5.)
            expected,ef=scalar_oracle(t,hits,contact,front,confirmation,horizon,2.,5.)
            for key in actual: np.testing.assert_array_equal(actual[key],expected[key],err_msg=key)
            np.testing.assert_array_equal(frames,ef)

    def test_short_horizon_outside_contract_rejected(self):
        with self.assertRaises(ValueError): adapter.scored_trace(np.array([2.]),np.ones((1,1),bool),np.array([3.]),np.array([False]),0,np.array([1.]),2,5)

class ContractTests(unittest.TestCase):
    def p0(self): return {**dict.fromkeys(contract.P0_REQUIRED,True),'live_scientific_processes':0,'unresolved_conflicts':0}
    def p1(self): return dict(kind='complete_coordinate_reconstruction',source_output_records=6609,packed_records=27,
        full_array_reconstruction_verified=True,all_original_orders_groups_tolerances_controls_preserved=True,
        independent_close_actual_wait_exit_code=0,complete_frozen_inventory_rehashed=True,valid_close_receipt_binding=True)

    def test_missing_argv_or_mutex_cannot_be_substituted(self):
        for key in ('system_wide_exact_argv','named_mutex_exclusive_and_release'):
            evidence=self.p0(); evidence[key]=False; evidence['zero_recent_writes']=True
            with self.assertRaises(contract.NotAdmitted): contract.check_p0(evidence)

    def test_path_and_metadata_linkage_does_not_close_p1(self):
        e=self.p1(); e.update(kind='metadata_lineage',full_array_reconstruction_verified=False)
        with self.assertRaises(contract.NotAdmitted): contract.check_p1(e)

    def test_cannot_skip_p1_for_real_scoring(self):
        with self.assertRaises(contract.NotAdmitted): contract.permit_next('P3-real',self.p0(),{})
        self.assertTrue(contract.permit_next('P2-synthetic-prep',{},{}))

    def test_permissions_stop_on_first_denial(self):
        now=datetime.now(timezone.utc)
        self.assertEqual(contract.continuation(now,now+timedelta(hours=1),permission_error='No permission client configured'),'STOP_AND_REPORT_PERMISSION_CHANNEL')

    def test_time_limit_not_wave_count_and_no_forced_scientific_kill(self):
        now=datetime.now(timezone.utc)
        self.assertEqual(contract.continuation(now,now+timedelta(minutes=1)),'CONTINUE_FIXED_PLAN')
        self.assertEqual(contract.continuation(now,now,scientific_inflight=True),'MONITOR_NATURAL_FINISH_ONLY')
        self.assertEqual(contract.continuation(now,now),'STOP_NEW_SUBMISSIONS')

    def test_edge_255_is_mask_not_atomic_face(self):
        self.assertEqual(contract.decode_edge_mask(255),tuple(range(1,9)))
        self.assertEqual(contract.decode_edge_mask(2),(2,))
        with self.assertRaises(ValueError): contract.decode_edge_mask(256)

if __name__=='__main__': unittest.main()
