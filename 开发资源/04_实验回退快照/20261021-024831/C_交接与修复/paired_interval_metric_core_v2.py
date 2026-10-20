"""Version2 synthetic-only candidate for conservative paired RIGHT insufficiency bounds.

Explicit valid_alarm_start must match the exact frozen evaluator: 2 for scored
evaluator, None only for the unscored legacy semantics. Atomic edge codes must
be1..8: decode original uint8 masks externally;255 is not one face. Rational
comparisons are not automatically a bitwise floating-point equivalence proof.

No filesystem access, geometry, real-data adapter, score promotion or training.
Independent per-point domains are a relaxation of any extra cross-point geometry
constraints: resulting bounds enclose that constrained set, not certify truth.
Complete confirmed-alarm timelines and a certified truth-domain superset must be
supplied by a separately accepted adapter before any future real-data use.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import math

def q(value):
    if isinstance(value,bool): raise ValueError('Numeric time required')
    if isinstance(value,float) and not math.isfinite(value): raise ValueError('Finite value required')
    return F(str(value)) if isinstance(value,float) else F(value)

@dataclass(frozen=True)
class Alarm:
    time: F
    horizon: F

    def __post_init__(self):
        object.__setattr__(self,'time',q(self.time))
        object.__setattr__(self,'horizon',q(self.horizon))
        if self.horizon<0: raise ValueError('Nonnegative horizon required')

def insufficiency(contact,alarms,eps=F(1,10**9),lead=F(1),*,valid_alarm_start):
    """Reconstruct earliest *supported* confirmed alarm for this contact time."""
    contact,eps,lead=q(contact),q(eps),q(lead)
    if eps<0 or lead<0: raise ValueError('Nonnegative thresholds required')
    supported=[a.time for a in alarms if (valid_alarm_start is None or a.time>=q(valid_alarm_start)-eps)
        and a.time-eps<=contact<=a.time+a.horizon+eps]
    valid=min(supported) if supported else None
    return int(valid is None or contact-valid<lead-eps)

def point_domain(interval,alarms_a,alarms_b,*,edge_codes=(2,),front_states=(False,),
                 can_be_noncontact=False,score_start=2,score_end=20,
                 eps=F(1,10**9),lead=1,timelines_complete=False,valid_alarm_start):
    """Return all paired (late_or_miss_A - late_or_miss_B, eligible) states.

    A/B always share the same contact time, edge and front state. Enumerating
    independent edge/front choices intentionally keeps a conservative superset.
    Boundary singleton values and every intervening open cell are both checked.
    """
    if timelines_complete is not True: raise ValueError('Complete confirmed timelines required; first/raw/valid alone insufficient')
    if type(can_be_noncontact) is not bool: raise ValueError('Explicit contact-domain boolean required')
    alarms_a,alarms_b=tuple(alarms_a),tuple(alarms_b)
    eps,lead=q(eps),q(lead); lo_eligible,hi_eligible=q(score_start)-eps,q(score_end)+eps
    if eps<0 or lead<0 or lo_eligible>hi_eligible: raise ValueError('Invalid score thresholds')
    edge_codes=tuple(edge_codes); front_states=tuple(front_states)
    if not edge_codes or any(isinstance(e,bool) or not isinstance(e,int) or not 1<=e<=8 for e in edge_codes): raise ValueError('Explicit nonempty edge code superset required')
    if not front_states or any(type(f) is not bool for f in front_states): raise ValueError('Explicit front states required')
    states={(0,0)} if can_be_noncontact else set()
    if interval is None:
        if not can_be_noncontact: raise ValueError('Empty contact/noncontact domain')
        return frozenset(states)
    lower,upper=map(q,interval)
    if lower>upper: raise ValueError('Reversed contact interval')
    boundaries={lower,upper,lo_eligible,hi_eligible}
    for alarm in (*alarms_a,*alarms_b):
        boundaries.update((alarm.time-eps,alarm.time+alarm.horizon+eps,alarm.time+lead-eps))
    points=sorted(t for t in boundaries if lower<=t<=upper)
    representatives=points+[(a+b)/2 for a,b in zip(points,points[1:]) if a<b]
    for contact in representatives:
        for edge in edge_codes:
            for front in front_states:
                eligible=(edge==2 and not front and lo_eligible<=contact<=hi_eligible)
                states.add((insufficiency(contact,alarms_a,eps,lead,valid_alarm_start=valid_alarm_start)-insufficiency(contact,alarms_b,eps,lead,valid_alarm_start=valid_alarm_start),1)
                    if eligible else (0,0))
    return frozenset(states)

def ratio_bounds(domains,*,base_numerator=0,base_denominator=0):
    """Exact fraction extrema on the independent point-domain relaxation.

    A domain's positive denominator must be one fixed positive integer (a shared
    point multiplicity); exclusion is (0,0). For a fixed included subset choose
    each point's lowest/highest numerator. The fractional optimum consists of a
    prefix ordered by these numerator/denominator slopes. Zero-denominator
    completions remain explicitly undefined and prohibit strict ranking claims.
    """
    if isinstance(base_denominator,bool) or not isinstance(base_denominator,int) or base_denominator<0: raise ValueError('Nonnegative base denominator required')
    if isinstance(base_numerator,bool) or not isinstance(base_numerator,int): raise ValueError('Integer base numerator required')
    if abs(base_numerator)>base_denominator: raise ValueError('Paired base numerator must be within eligible denominator')
    nmin=nmax=base_numerator; fixed_d=base_denominator
    optional_min=[]; optional_max=[]
    for domain in domains:
        options=set(domain)
        if not options: raise ValueError('Empty point domain')
        if any(type(n) is not int or type(d) is not int or d<0 or (d==0 and n!=0) or abs(n)>d for n,d in options):
            raise ValueError('Invalid paired numerator/denominator contribution')
        positive=[(n,d) for n,d in options if d]
        if not positive: continue
        ds={d for n,d in positive}
        if len(ds)!=1: raise ValueError('One shared positive multiplicity per domain required')
        d=ds.pop(); low=min(n for n,_ in positive); high=max(n for n,_ in positive)
        if (0,0) in options:
            optional_min.append((low,d)); optional_max.append((high,d))
        else:
            nmin+=low; nmax+=high; fixed_d+=d
    undefined_possible=(fixed_d==0)
    def extreme(numerator,items,largest):
        denominator=fixed_d
        values=[F(numerator,denominator)] if denominator else []
        for n,d in sorted(items,key=lambda pair:F(*pair),reverse=largest):
            numerator+=n; denominator+=d; values.append(F(numerator,denominator))
        return (max(values) if largest else min(values)) if values else None
    lower=extreme(nmin,optional_min,False); upper=extreme(nmax,optional_max,True)
    if lower is None: verdict='undefined'
    elif undefined_possible: verdict='unresolved_zero_denominator_possible'
    elif lower>0: verdict='B_strictly_better'
    elif upper<0: verdict='A_strictly_better'
    elif lower==upper==0: verdict='equal_on_domain_relaxation'
    else: verdict='unresolved'
    return dict(lower=lower,upper=upper,undefined_possible=undefined_possible,verdict=verdict,
        sign_definition='insufficient_A/eligible - insufficient_B/eligible; positive favors B',
        scope='independent-point-domain relaxation; no corrected truth certification')
