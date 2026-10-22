"""PURE source-control branch enclosure candidate for original quadratic Maneuver.
No source/environment admission, no truth/label updates. Explicit real-to-float time error.
Assumes audited NumPy ndarray square and RN binary64 basic operations, no overflow.
"""
from fractions import Fraction as F
from . import validated_entry_core as p
from . import entry_interval_geometry as i
U=F(1,2**53);ETA=F(1,2**1075)

def magnitude(poly,lo,hi):
 b=i.polynomial_range(poly,(lo,hi));return max(abs(b[0]),abs(b[1]))
def constant(x):return [F(x)],F(0)
def rounding(poly,error,h):
 B=p.norm(poly,h)+error
 if B>=2**1023:raise ValueError('No source arithmetic overflow admitted')
 return poly,error+U*B+ETA

def add(a,b,h):return rounding(p.add(a[0],b[0]),a[1]+b[1],h)
def neg(a):return p.scale(a[0],-1),a[1]
def sub(a,b,h):return add(a,neg(b),h)
def mul(a,b,h):
 poly=p.mul(a[0],b[0]);error=p.norm(a[0],h)*b[1]+p.norm(b[0],h)*a[1]+a[1]*b[1]
 return rounding(poly,error,h)
def divide_constant(a,b,h):
 if len(b[0])!=1 or abs(b[0][0])<=b[1]:raise ValueError('Nonzero constant source denominator')
 poly=p.scale(a[0],1/b[0][0]);error=(a[1]+p.norm(poly,h)*b[1])/(abs(b[0][0])-b[1])
 return rounding(poly,error,h)

def constants(control):
 peak,rate,ret,b,pre,de,plateau=map(lambda k:F(control[k]),('peak','entry_rate','return_rate','blend','pre','entry_duration','plateau'))
 if any(F(float(x))!=x for x in (peak,rate,ret,b,pre,de,plateau)):raise ValueError('Every source parameter must be its exact binary64 value')
 if b!=F(.2):raise ValueError('Pinned original ramp_value default blend=.2')
 if min(peak,rate,ret,b)<=0 or pre<0 or plateau<0:raise ValueError('Original positive quadratic-control domain')
 # Exact float values of source-computed branch constants, not decimal-intended values.
 duration=F(float(float(peak)/float(rate)+float(b)));dr=F(float(float(peak)/float(ret)+float(b)))
 if de!=duration:raise ValueError('Original entry duration must match source float expression')
 rs=F(float(float(float(pre)+float(de))+float(plateau)))
 if min(duration,dr)<=2*b:raise ValueError('Ordered ramp branches required')
 return dict(peak=peak,rate=rate,ret=ret,b=b,pre=pre,de=duration,dr=dr,rs=rs,dmb=F(float(float(duration)-float(b))),drmb=F(float(float(dr)-float(b))))

def partition(control,end,max_step):
 c=constants(control);end,max_step=F(end),F(max_step)
 if end<=0 or max_step<=0:raise ValueError('Full finite source horizon')
 points={F(0),end}
 for start,D,db in ((c['pre'],c['de'],c['dmb']),(c['rs'],c['dr'],c['drmb'])):
  for x in (start,start+c['b'],start+db,start+D):
   if 0<x<end:points.add(x)
 times=sorted(points);out=[times[0]]
 for left,right in zip(times,times[1:]):
  n=(right-left)//max_step+1
  for j in range(1,int(n)+1):out.append(left+(right-left)*F(j,n))
 return out

def ramp_branches(c,start,h,offset,D,db,rate,time_error):
 # Each branch carries a possible *real* time interval after all time/subtraction rounding.
 time=([F(start),F(1)],F(time_error));tau=sub(time,constant(offset),h);E=tau[1]
 denominator=mul(constant(2),constant(c['b']),h)
 quadratic=divide_constant(mul(constant(rate),mul(tau,tau,h),h),denominator,h)
 linear=mul(constant(rate),sub(tau,divide_constant(constant(c['b']),constant(2),h),h),h)
 tail= sub(constant(c['peak']),divide_constant(mul(constant(rate),mul(sub(constant(D),tau,h),sub(constant(D),tau,h),h),h),denominator,h),h)
 # Domains expressed in local real tau measured from start; endpoints conservatively included.
 def domain(lo,hi):return (None if lo is None else offset+lo-F(start)-E,None if hi is None else offset+hi-F(start)+E)
 return [(constant(0),domain(None,F(0)),'pre'),(quadratic,domain(F(0),c['b']),'quadratic'),(linear,domain(c['b'],db),'linear'),(tail,domain(max(c['b'],db),D),'quadratic_tail'),(constant(c['peak']),domain(D,None),'post')]

def enclose(control,start,h,time_error,n):
 start,h,time_error=map(F,(start,h,time_error));c=constants(control)
 if h<=0 or time_error<0 or n<2:raise ValueError('Explicit finite control/time contract')
 candidates=[]
 for returning,offset,D,db,rate in ((False,c['pre'],c['de'],c['dmb'],c['rate']),(True,c['rs'],c['dr'],c['drmb'],c['ret'])):
  outerlo=c['rs']-start-time_error if returning else F(0);outerhi=h if returning else c['rs']-start+time_error
  for value,(lo,hi),branch in ramp_branches(c,start,h,offset,D,db,rate,time_error):
   lo=max(F(0),outerlo,lo if lo is not None else F(0));hi=min(h,outerhi,hi if hi is not None else h)
   value=add(constant(-c['peak']),value,h) if returning else neg(value)
   if lo>hi:continue
   candidates.append((value,lo,hi,('return_' if returning else 'entry_')+branch))
 if not candidates:raise ValueError('No complete control branch coverage')
 covered=F(0)
 for left,right in sorted((x[1],x[2]) for x in candidates):
  if left>covered:raise ValueError('Gap in complete source branch domain coverage')
  covered=max(covered,right)
 if covered<h:raise ValueError('Uncovered source branch end')
 # Select an algebraic reference polynomial covering the cell center; all other possible branches stay in the error.
 chosen=next((x for x in candidates if x[1]<=h/2<=x[2]),None)
 if chosen is None:raise ValueError('Source center must belong to a conservatively covered branch')
 polynomial=p.trim(chosen[0][0],n)
 if any(x!=0 for x in chosen[0][0][n+1:]):raise ValueError('Source polynomial degree cannot be dropped')
 error=max(value[1]+magnitude(p.sub(value[0],polynomial),lo,hi) for value,lo,hi,_ in candidates)
 return polynomial,error,dict(branches=[dict(name=name,local_start=lo,local_end=hi) for _,lo,hi,name in candidates],time_error=time_error,source_environment_admitted=False)
