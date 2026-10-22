"""PURE rational continuous-time rectangular-body exclusion; no data I/O.
Only returns interval exclusions or unknown, never sampled negative labels.
Caller must provide valid global state/trig enclosures and original vehicle contract.
"""
from fractions import Fraction as F
from math import factorial,comb

def box(x):
 if isinstance(x,(tuple,list)):
  lo,hi=map(F,x)
  if lo>hi:raise ValueError('Ordered interval')
  return lo,hi
 q=F(x);return q,q

def add(a,b):a,b=box(a),box(b);return a[0]+b[0],a[1]+b[1]
def neg(a):a=box(a);return -a[1],-a[0]
def sub(a,b):return add(a,neg(b))
def mul(a,b):
 a,b=box(a),box(b);p=[x*y for x in a for y in b];return min(p),max(p)
def square(a):
 a=box(a)
 return (F(0) if a[0]<=0<=a[1] else min(a[0]**2,a[1]**2),max(a[0]**2,a[1]**2))
def maximum(*args):
 args=[box(a) for a in args];return max(a[0] for a in args),max(a[1] for a in args)
def inflate(a,e):
 a=box(a);e=F(e)
 if e<0:raise ValueError('Nonnegative enclosure radius')
 return a[0]-e,a[1]+e

def polynomial_range(coeff,t):
 # Exact midpoint shift is interval evaluation, NOT a truth label or sample proof.
 lo,hi=box(t);mid=(lo+hi)/2;h=(hi-lo)/2;n=len(coeff)-1
 shifted=[sum((F(coeff[k])*comb(k,j)*mid**(k-j) for k in range(j,n+1)),F(0)) for j in range(n+1)]
 out=box(shifted[-1])
 for c in reversed(shifted[:-1]):out=add(mul(out,(-h,h)),c)
 return out

def small_trig(x,cosine=False):
 x=box(x);B=max(abs(x[0]),abs(x[1]))
 if B>1:raise ValueError('Local angle contract only')
 n=16;coef=[F(0)]*(n+1)
 for k in range(0 if cosine else 1,n+1,2):coef[k]=F((-1)**(k//2),factorial(k))
 # Ordinary interval Horner is sufficient; scalar Lagrange derivatives bounded by1.
 out=box(coef[-1])
 for q in reversed(coef[:-1]):out=add(mul(out,x),q)
 out=inflate(out,B**(n+1)/factorial(n+1))
 return max(F(-1),out[0]),min(F(1),out[1])

def direction(delta,c0,s0):
 sd,cd=small_trig(delta),small_trig(delta,True)
 return sub(mul(c0,cd),mul(s0,sd)),add(mul(s0,cd),mul(c0,sd))

def local_state(P,errors,t,pre,v,c0,s0):
 if len(P)!=4 or len(errors)!=4:raise ValueError('Four-state enclosure')
 states=[inflate(polynomial_range(p,t),e) for p,e in zip(P,errors)]
 states[0]=add(states[0],F(pre)*F(v)*F(c0));states[1]=add(states[1],F(pre)*F(v)*F(s0))
 return states

def body_distance_squared(point,state,c0,s0,lh,L,width):
 if F(L)<=0 or F(width)<=0:raise ValueError('Finite positive body dimensions')
 bx,by,delta,phi=map(box,state);ct,st=direction(delta,c0,s0);c,s=direction(sub(delta,phi),c0,s0)
 dx=sub(point[0],add(bx,mul(lh,ct)));dy=sub(point[1],add(by,mul(lh,st)))
 q=add(mul(dx,c),mul(dy,s));right=sub(mul(dx,s),mul(dy,c))
 longitudinal=maximum(q,neg(add(L,q)),0);lateral=maximum(sub(right,F(width)/2),sub(neg(right),F(width)/2),0)
 return add(square(longitudinal),square(lateral))

def exclude_cover(distance_squared,start,end,tolerance,max_cells=4096,max_depth=24):
 start,end,tolerance=map(F,(start,end,tolerance))
 if not start<end or tolerance<0 or max_cells<1 or max_depth<0:raise ValueError('Finite complete coverage contract')
 pending=[(start,end,0)];leaves=[];evaluated=0
 while pending:
  lo,hi,depth=pending.pop();bound=box(distance_squared((lo,hi)));evaluated+=1
  if bound[0]>tolerance*tolerance:leaves.append(dict(start=lo,end=hi,status='strict_noncontact',bound=bound,depth=depth))
  elif depth>=max_depth or evaluated+len(pending)+2>max_cells:
   leaves.append(dict(start=lo,end=hi,status='unknown',bound=bound,depth=depth))
  else:
   mid=(lo+hi)/2;pending.extend([(mid,hi,depth+1),(lo,mid,depth+1)])
 leaves.sort(key=lambda r:r['start'])
 if leaves[0]['start']!=start or leaves[-1]['end']!=end or any(a['end']!=b['start'] for a,b in zip(leaves,leaves[1:])):raise AssertionError('Gap or overlap in full time coverage')
 return dict(leaves=leaves,evaluated_cells=evaluated,all_times_covered=True,strict_noncontact_all_times=all(r['status']=='strict_noncontact' for r in leaves),unknown_cells=sum(r['status']=='unknown' for r in leaves),scientific_admission=False)
