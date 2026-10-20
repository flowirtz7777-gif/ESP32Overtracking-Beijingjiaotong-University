"""Pure synthetic independent enumeration and original valid-window counterexamples."""
from fractions import Fraction as F
from itertools import product
import random
import unittest
import paired_interval_metric_core_v1 as c

class Tests(unittest.TestCase):
    def domain(self,interval,a,b,**kw):
        return c.point_domain(interval,a,b,timelines_complete=True,score_start=0,**kw)

    def test_negative_numerator_variable_denominator(self):
        actual=c.ratio_bounds([{(0,0),(0,1)}],base_numerator=-1,base_denominator=1)
        self.assertEqual((actual['lower'],actual['upper']),(F(-1),F(-1,2)))
        self.assertEqual(actual['verdict'],'A_strictly_better')

    def test_positive_sign_favors_B(self):
        self.assertEqual(c.ratio_bounds([{(1,1)}])['verdict'],'B_strictly_better')

    def test_contact_repair_must_reconstruct_valid(self):
        alarms=[c.Alarm(0,2)]
        self.assertEqual(c.insufficiency(1,alarms),0)
        self.assertEqual(c.insufficiency(3,alarms),1)

    def test_shared_time_identical_methods_never_independently_plus_minus_one(self):
        events=[c.Alarm(0,2),c.Alarm(4,2)]
        self.assertEqual(self.domain((0,8),events,events),{(0,1)})

    def test_same_time_distinct_horizons(self):
        self.assertEqual(self.domain((F(5,2),F(5,2)),[c.Alarm(0,2)],[c.Alarm(0,3)]),{(1,1)})

    def test_first_raw_or_saved_valid_alone_rejected(self):
        with self.assertRaises(ValueError): c.point_domain((2,3),[],[])

    def test_undefined_denominator_preserved_and_ranking_withheld(self):
        actual=c.ratio_bounds([{(0,0),(1,1)}])
        self.assertTrue(actual['undefined_possible'])
        self.assertEqual(actual['verdict'],'unresolved_zero_denominator_possible')
        self.assertEqual(c.ratio_bounds([{(0,0)}])['verdict'],'undefined')

    def test_edge_and_front_superset_preserves_exclusion(self):
        states=self.domain((3,3),[],[c.Alarm(1,3)],edge_codes=(1,2,5,255),front_states=(True,False))
        self.assertEqual(states,{(0,0),(1,1)})

    def test_closed_eps_support_and_late_boundary(self):
        eps=F(1,10**9); event=[c.Alarm(0,2)]
        self.assertEqual(c.insufficiency(2+eps,event),0)
        self.assertEqual(c.insufficiency(2+2*eps,event),1)
        self.assertEqual(c.insufficiency(1-eps,event),0)
        self.assertEqual(c.insufficiency(1-2*eps,event),1)

    def test_complete_boundary_partition_matches_dense_independent_samples(self):
        eps=F(1,10); a=[c.Alarm(0,2),c.Alarm(3,1)]; b=[c.Alarm(1,3)]
        actual=self.domain((0,5),a,b,eps=eps,score_end=4)
        expected=set()
        for t in [F(i,100) for i in range(501)]:
            # Independent direct implementation; no candidate insufficiency helper.
            if not -eps<=t<=4+eps: expected.add((0,0)); continue
            def flag(events):
                candidates=[e.time for e in events if e.time-eps<=t<=e.time+e.horizon+eps]
                return int(not candidates or t-min(candidates)<1-eps)
            expected.add((flag(a)-flag(b),1))
        self.assertEqual(actual,expected)

    def test_weighted_correlated_duplicate_point(self):
        actual=c.ratio_bounds([{(0,0),(-3,3),(3,3)},{(0,2)}])
        self.assertEqual((actual['lower'],actual['upper']),(F(-3,5),F(3,5)))

    def test_ratio_matches_full_cartesian_exhaustion_300_small_populations(self):
        rng=random.Random(121021)
        for _ in range(300):
            domains=[]
            for i in range(rng.randint(1,7)):
                d=rng.randint(1,4)
                domain={(rng.randint(-d,d),d) for j in range(rng.randint(1,3))}
                if rng.choice((True,False)): domain.add((0,0))
                domains.append(domain)
            numerator=rng.randint(-2,2); denominator=2
            values=[]; undefined=False
            for states in product(*domains):
                n=numerator+sum(v[0] for v in states); d=denominator+sum(v[1] for v in states)
                if d: values.append(F(n,d))
                else: undefined=True
            actual=c.ratio_bounds(domains,base_numerator=numerator,base_denominator=denominator)
            self.assertEqual((actual['lower'],actual['upper']),(min(values),max(values)))
            self.assertEqual(actual['undefined_possible'],undefined)

    def test_invalid_domains_and_nonfinite_times_rejected(self):
        for values in ([{(1,0)}],[{(0,1),(0,2)}],[set()]):
            with self.assertRaises(ValueError): c.ratio_bounds(values)
        with self.assertRaises(ValueError): c.Alarm(float('nan'),2)
        with self.assertRaises(ValueError): self.domain((3,2),[],[])

if __name__=='__main__': unittest.main()
