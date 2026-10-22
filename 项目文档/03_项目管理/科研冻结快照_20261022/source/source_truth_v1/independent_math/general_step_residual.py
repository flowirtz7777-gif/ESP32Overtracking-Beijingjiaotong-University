"""PURE general short-step residual certificate. No source/control/truth admission.
Nonzero initial theta,phi and constant/linear/quadratic alpha are supported.
Initial tube errors are propagated explicitly; no empirical-suffix splice.
"""
from fractions import Fraction as F
from math import factorial
from functools import lru_cache
from . import validated_entry_core as p

@lru_cache(maxsize=256)
def trig_center(x,cosine=False):
 x=F(x)
 if abs(x)>4:raise ValueError('Bounded synthetic/general-step center domain')
 degree=64;v=sum((F((-1)**(k//2),factorial(k))*x**k for k in range(0 if cosine else 1,degree+1,2)),F(0));e=abs(x)**(degree+1)/factorial(degree+1)
 rounded=F(round(v*2**100),2**100)
 return rounded,e+abs(rounded-v)

def trig_series(center,deviation,n,h,cosine=False):
 S,es=p.trig_poly(deviation,n,h);C,ec=p.trig_poly(deviation,n,h,True)
 s,e0s=trig_center(F(center));c,e0c=trig_center(F(center),True)
 if cosine:return p.sub(p.scale(C,c),p.scale(S,s)),abs(c)*ec+abs(s)*es+e0s+e0c
 return p.add(p.scale(C,s),p.scale(S,c)),abs(s)*ec+abs(c)*es+e0s+e0c

def yaw_series(alpha,n,h,v,l,alpha_error):
 zero=list(alpha);center=zero[0];zero[0]=F(0)
 S,es=trig_series(center,zero,n,h);C,ec=trig_series(center,zero,n,h,True);B=p.norm(alpha,h)+alpha_error;lower=1-B*B/2
 if lower<=0:raise ValueError('Whole alpha tube positive cosine bound')
 Q=p.divide(S,C,n);err=(p.norm(p.sub(S,p.mul(C,Q)),h)+es+ec*p.norm(Q,h))/lower+alpha_error/(lower*lower)
 return p.scale(Q,v/l),err*v/l

def rhs(center,P,alpha,n,h,v,l,lh,L):
 yaw,_=yaw_series(alpha,n,h,v,l,F(0));sd,_=trig_series(center[2],P[2],n,h);cd,_=trig_series(center[2],P[2],n,h,True);sp,_=trig_series(center[3],P[3],n,h);cp,_=trig_series(center[3],P[3],n,h,True)
 return [p.scale(cd,v),p.scale(sd,v),yaw,p.sub(yaw,p.scale(p.add(p.scale(sp,v),p.scale(p.mul(yaw,cp,n),lh)),1/L))]

def build(center,alpha,n,h,v,l,lh,L):
 if len(alpha)>n+1:raise ValueError('No silent truncation of supplied control polynomial')
 center=list(map(F,center));alpha=p.trim(list(map(F,alpha)),n);h,v,l,lh,L=map(F,(h,v,l,lh,L))
 if len(center)!=4 or n<4 or min(h,v,l,L)<=0:raise ValueError('Step shape and positive physical parameters')
 P=[[F(0)]*(n+1) for _ in range(4)]
 for k in range(n):
  fields=rhs(center,P,alpha,n,h,v,l,lh,L)
  for j in range(4):P[j][k+1]=fields[j][k]/(k+1)
 return P,alpha

def certify(center,P,alpha,n,h,v,l,lh,L,initial_errors,alpha_error):
 center=list(map(F,center));initial_errors=list(map(F,initial_errors));h,v,l,lh,L,alpha_error=map(F,(h,v,l,lh,L,alpha_error))
 if len(center)!=4 or len(initial_errors)!=4 or any(e<0 for e in initial_errors) or alpha_error<0 or n<4 or len(P)!=4 or any(len(row)!=n+1 or row[0]!=0 for row in P) or len(alpha)!=n+1 or min(h,v,l,L)<=0:raise ValueError('Explicit full initial tube and polynomial contract')
 yaw,eyaw=yaw_series(alpha,n,h,v,l,alpha_error)
 SD,esd=trig_series(center[2],P[2],n,h);CD,ecd=trig_series(center[2],P[2],n,h,True);SP,esp=trig_series(center[3],P[3],n,h);CP,ecp=trig_series(center[3],P[3],n,h,True)
 product=p.mul(yaw,CP);tail=p.norm(product[n+1:],h)*h**(n+1)
 phi=p.sub(yaw,p.scale(p.add(p.scale(SP,v),p.scale(p.trim(product,n),lh)),1/L))
 rx=p.norm(p.sub(p.scale(CD,v),p.derivative(P[0])),h)+v*ecd
 ry=p.norm(p.sub(p.scale(SD,v),p.derivative(P[1])),h)+v*esd
 rt=p.norm(p.sub(yaw,p.derivative(P[2])),h)+eyaw
 rp=p.norm(p.sub(phi,p.derivative(P[3])),h)+(1+abs(lh)/L)*eyaw+v/L*esp+abs(lh)/L*(p.norm(yaw,h)*ecp+tail)
 K=(v+abs(lh)*(p.norm(yaw,h)+eyaw))/L
 if K*h>=1:raise ValueError('Finite rational step majorant K*h<1 required')
 ex,ey,et,ep=initial_errors
 errors=[ex+h*rx+v*h*et+v*h*h*rt/2,ey+h*ry+v*h*et+v*h*h*rt/2,et+h*rt,(ep+h*rp)/(1-K*h)]
 return dict(residual_bounds=[rx,ry,rt,rp],all_times_state_error_bounds=errors,end_state_error_bounds=errors,lipschitz_phi=K,scientific_admission=False)

def recenter(center,P,h,end_errors,bits=80):
 if bits<32 or len(center)!=4 or len(end_errors)!=4 or any(F(e)<0 for e in end_errors):raise ValueError('Explicit endpoint tube and center precision')
 exact=[F(c)+p.value(row,F(h)) for c,row in zip(center,P)]
 rounded=[F(round(x*2**bits),2**bits) for x in exact]
 return rounded,[F(e)+abs(a-b) for e,a,b in zip(end_errors,exact,rounded)]
