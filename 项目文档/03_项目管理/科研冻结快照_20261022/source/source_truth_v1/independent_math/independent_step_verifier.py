"""Independent sparse-polynomial rational residual verifier, no primary imports.
Saved polynomials are candidate expressions, not trusted solutions or trusted error bounds.
Own step errors must be propagated; compare own geometry proofs, never reset tubes.
"""
from fractions import Fraction as Q
from math import factorial
from functools import lru_cache

def polynomial(row):return {k:Q(v) for k,v in enumerate(row) if v}
def plus(a,b):
 out=dict(a)
 for k,v in b.items():out[k]=out.get(k,Q(0))+v
 return {k:v for k,v in out.items() if v}
def scaled(a,v):return {k:x*v for k,x in a.items() if x*v}
def minus(a,b):return plus(a,scaled(b,-1))
def product(a,b):
 out={}
 for j,x in a.items():
  for k,y in b.items():out[j+k]=out.get(j+k,Q(0))+x*y
 return {k:v for k,v in out.items() if v}
def weight(a,h):return sum((abs(v)*h**k for k,v in a.items()),Q(0))
def truncated(a,n):return {k:v for k,v in a.items() if k<=n}
def differentiated(a):return {k-1:k*v for k,v in a.items() if k}
def at(a,t):return sum((v*t**k for k,v in a.items()),Q(0))

@lru_cache(maxsize=256)
def scalar_trig(x,cosine=False):
 x=Q(x)
 if abs(x)>4:raise ValueError('Independent center range')
 k=0 if cosine else 1;term=Q(1) if cosine else x;total=term
 while k+2<=80:
  term=-term*x*x/((k+1)*(k+2));total+=term;k+=2
 return total,abs(x)**81/factorial(81)

def trig_zero(P,n,h,cosine=False):
 if P.get(0,0)!=0:raise ValueError('Independent zero-deviation contract')
 B=weight(P,h);power={0:Q(1)};lost=Q(0);out={};error=Q(0)
 for k in range(n+2):
  if k%2==(0 if cosine else 1):
   c=Q((-1)**(k//2),factorial(k));out=plus(out,scaled(power,c));error+=abs(c)*lost
  full=product(power,P);lost=lost*B+weight({j:v for j,v in full.items() if j>n},h);power=truncated(full,n)
 return out,error+B**(n+2)/factorial(n+2)

def trig_offset(center,P,n,h,cosine=False):
 S,es=trig_zero(P,n,h);C,ec=trig_zero(P,n,h,True);s,e0s=scalar_trig(center);c,e0c=scalar_trig(center,True)
 if cosine:return minus(scaled(C,c),scaled(S,s)),abs(c)*ec+abs(s)*es+e0c+e0s
 return plus(scaled(C,s),scaled(S,c)),abs(s)*ec+abs(c)*es+e0s+e0c

def quotient_series(A,B,n):
 constant=B.get(0,0)
 if not constant:raise ValueError('Independent formal divisor')
 out={}
 for k in range(n+1):
  q=(A.get(k,Q(0))-sum((v*out.get(k-j,Q(0)) for j,v in B.items() if 1<=j<=k),Q(0)))/constant
  if q:out[k]=q
 return out

def verify_step(center,rows,alpha,n,h,v,l,lh,L,initial_errors,alpha_error):
 center=list(map(Q,center));initial_errors=list(map(Q,initial_errors));h,v,l,lh,L,alpha_error=map(Q,(h,v,l,lh,L,alpha_error))
 if len(center)!=4 or len(rows)!=4 or len(initial_errors)!=4 or any(len(r)!=n+1 or Q(r[0])!=0 for r in rows) or len(alpha)!=n+1 or n<4 or min(h,v,l,L)<=0 or any(e<0 for e in initial_errors) or alpha_error<0:raise ValueError('Independent complete step/tube contract')
 P=list(map(polynomial,rows));A=polynomial(alpha);a0=A.pop(0,Q(0));S,es=trig_offset(a0,A,n,h);C,ec=trig_offset(a0,A,n,h,True);ratio=quotient_series(S,C,n)
 lower=1-(abs(a0)+weight(A,h)+alpha_error)**2/2
 if lower<=0:raise ValueError('Independent positive cosine proof')
 err=(weight(minus(S,product(C,ratio)),h)+es+ec*weight(ratio,h))/lower+alpha_error/lower**2
 yaw=scaled(ratio,v/l);eyaw=err*v/l
 ST,est=trig_offset(center[2],P[2],n,h);CT,ect=trig_offset(center[2],P[2],n,h,True);SP,esp=trig_offset(center[3],P[3],n,h);CP,ecp=trig_offset(center[3],P[3],n,h,True)
 full=product(yaw,CP);tail=weight({k:x for k,x in full.items() if k>n},h)
 FP=minus(yaw,scaled(plus(scaled(SP,v),scaled(truncated(full,n),lh)),1/L))
 rx=weight(minus(scaled(CT,v),differentiated(P[0])),h)+v*ect
 ry=weight(minus(scaled(ST,v),differentiated(P[1])),h)+v*est
 rt=weight(minus(yaw,differentiated(P[2])),h)+eyaw
 rp=weight(minus(FP,differentiated(P[3])),h)+(1+abs(lh)/L)*eyaw+v/L*esp+abs(lh)/L*(weight(yaw,h)*ecp+tail)
 K=(v+abs(lh)*(weight(yaw,h)+eyaw))/L
 if K*h>=1:raise ValueError('Independent rational step majorant')
 x,y,t,p=initial_errors;errors=[x+h*rx+v*h*t+v*h*h*rt/2,y+h*ry+v*h*t+v*h*h*rt/2,t+h*rt,(p+h*rp)/(1-K*h)]
 return dict(residual_bounds=[rx,ry,rt,rp],state_error_bounds=errors,lipschitz_phi=K,source_or_scientific_admission=False)

def verify_transition(center,rows,h,own_end_errors,next_center,next_initial_errors):
 if len(center)!=4 or len(rows)!=4 or any(not r or Q(r[0])!=0 for r in rows) or len(next_center)!=4 or len(next_initial_errors)!=4 or len(own_end_errors)!=4:raise ValueError('Independent four-state transition')
 exact=[Q(c)+at(polynomial(r),Q(h)) for c,r in zip(center,rows)]
 if any(Q(e)<Q(old)+abs(Q(c)-x) for e,old,c,x in zip(next_initial_errors,own_end_errors,next_center,exact)):raise ValueError('Transition discards independently certified initial tube or recenter error')
 return True


def verify_chain(steps,exact_initial_state,start,end,v,l,lh,L,check=lambda:None):
 """Own tube chain; ignores any worker-supplied error vectors. No label admission."""
 if not steps or len(exact_initial_state)!=4:raise ValueError('Complete independently initialized chain')
 clock=Q(start);errors=[Q(0)]*4;current=list(map(Q,exact_initial_state));last_rows=None;last_h=None;records=[]
 for index,record in enumerate(steps):
  check()
  left,right=Q(record['start']),Q(record['end']);center=list(map(Q,record['center']))
  if left!=clock or right<=left or len(center)!=4:raise ValueError('Gap or invalid interval in independent chain')
  if index==0:
   if center!=current:raise ValueError('Exact shared initial state required')
  else:
   exact=[c+at_value for c,at_value in zip(current,[at(polynomial(r),last_h) for r in last_rows])]
   errors=[e+abs(c-x) for e,c,x in zip(errors,center,exact)]
   errors=[Q(-((-e.numerator*(1<<100))//e.denominator),1<<100) for e in errors]
   verify_transition(current,last_rows,last_h,records[-1]['end_errors'],center,errors)
  initial=list(errors)
  proof=verify_step(center,record['P'],record['alpha'],record['n'],right-left,v,l,lh,L,initial,record['alpha_error'])
  errors=[Q(-((-e.numerator*(1<<100))//e.denominator),1<<100) for e in proof['state_error_bounds']];records.append(dict(start=left,end=right,initial_errors=initial,end_errors=list(errors)))
  current=center;last_rows=record['P'];last_h=right-left;clock=right
 if clock!=Q(end):raise ValueError('Incomplete independent source horizon')
 return dict(steps=records,all_time_partitions_contiguous=True,end_errors=errors,scientific_admission=False)
