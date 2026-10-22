"""PURE candidate: rational polynomial residual enclosure for the short quadratic entry ODE.
No data I/O, labels, threshold changes or global-reference error replacement.
"""
from fractions import Fraction as F
import math

def add(a,b):return [(a[i] if i<len(a) else F(0))+(b[i] if i<len(b) else F(0)) for i in range(max(len(a),len(b)))]
def scale(a,c):return [x*c for x in a]
def sub(a,b):return add(a,scale(b,-1))
def trim(a,n):return (a+[F(0)]*(n+1))[:n+1]
def mul(a,b,n=None):
 out=[F(0)]*(len(a)+len(b)-1)
 for i,x in enumerate(a):
  for j,y in enumerate(b):out[i+j]+=x*y
 return out if n is None else trim(out,n)
def norm(a,T):return sum((abs(x)*T**k for k,x in enumerate(a)),F())
def derivative(a):return [k*a[k] for k in range(1,len(a))] or [F(0)]
def value(a,t):
 x=F(0)
 for c in a[::-1]:x=x*t+c
 return x
def divide(a,b,n):
 if not b or b[0]==0:raise ValueError('Formal divisor constant must be nonzero')
 out=[F(0)]*(n+1)
 for k in range(n+1):out[k]=((a[k] if k<len(a) else 0)-sum((b[j]*out[k-j] for j in range(1,min(k,len(b)-1)+1)),F()))/b[0]
 return out

def trig_poly(P,n,T,cosine=False):
 if P[0]!=0:raise ValueError('Taylor state deviations must start exactly0')
 out=[F(0)]*(n+1);power=[F(1)]+[F(0)]*n;lost=F(0);error=F(0);B=norm(P,T);K=n+1
 for k in range(K+1):
  parity=0 if cosine else 1
  if k%2==parity:
   coefficient=F((-1)**((k-parity)//2),math.factorial(k));out=add(out,scale(power,coefficient));error+=abs(coefficient)*lost
  full=mul(power,P);lost=lost*B+norm(full[n+1:],T)*T**(n+1);power=trim(full,n)
 error+=B**(K+1)/math.factorial(K+1)
 return trim(out,n),error

def tan_poly(alpha,n,T):
 S,es=trig_poly(alpha,n,T);C,ec=trig_poly(alpha,n,T,True);Q=divide(S,C,n);B=norm(alpha,T);lower=1-B*B/2
 if lower<=0:raise ValueError('Proved positive cosine denominator required')
 residual=norm(sub(S,mul(C,Q)),T)
 return Q,(residual+es+ec*norm(Q,T))/lower

def formal_rhs(P,alpha,n,T,v,l,lh,L,c0,s0):
 tan,_=tan_poly(alpha,n,T);theta=scale(tan,v/l);SD,_=trig_poly(P[2],n,T);CD,_=trig_poly(P[2],n,T,True);SP,_=trig_poly(P[3],n,T);CP,_=trig_poly(P[3],n,T,True)
 return [scale(sub(scale(CD,c0),scale(SD,s0)),v),scale(add(scale(CD,s0),scale(SD,c0)),v),theta,sub(theta,scale(add(scale(SP,v),scale(mul(theta,CP,n),lh)),1/L))]

def build(n,T,v,l,lh,L,entry_rate,blend,c0,s0):
 T,v,l,lh,L,entry_rate,blend,c0,s0=map(F,(T,v,l,lh,L,entry_rate,blend,c0,s0))
 if not (n>=4 and T>0 and T<=blend and min(v,l,L,blend)>0):raise ValueError('Short forward quadratic initial entry only')
 alpha=trim([F(0),F(0),-entry_rate/(2*blend)],n);P=[[F(0)]*(n+1) for _ in range(4)]
 for k in range(n):
  rhs=formal_rhs(P,alpha,n,T,v,l,lh,L,c0,s0)
  for j in range(4):P[j][k+1]=rhs[j][k]/(k+1)
 return P,alpha

def certify(P,alpha,n,T,v,l,lh,L,c0,s0,trig_initial_error=F(0),alpha_input_error=F(0),pre=F(0)):
 T,v,l,lh,L,c0,s0,trig_initial_error,alpha_input_error,pre=map(F,(T,v,l,lh,L,c0,s0,trig_initial_error,alpha_input_error,pre))
 if n<4 or len(P)!=4 or any(len(row)!=n+1 or row[0]!=0 for row in P) or len(alpha)!=n+1 or alpha[0]!=0 or pre<0:raise ValueError('Exact zero initial deviations and fixed polynomial shapes required')
 if min(T,v,l,L)>0 and alpha_input_error>=0 and trig_initial_error>=0:pass
 else:raise ValueError('Positive proof parameters and nonnegative input enclosures')
 Q,eq=tan_poly(alpha,n,T);B=norm(alpha,T)+alpha_input_error;coslower=1-B*B/2
 if coslower<=0:raise ValueError('Actual cosine denominator must stay positive')
 eq+=alpha_input_error/(coslower*coslower);theta=scale(Q,v/l);etheta=eq*v/l
 SD,esd=trig_poly(P[2],n,T);CD,ecd=trig_poly(P[2],n,T,True);SP,esp=trig_poly(P[3],n,T);CP,ecp=trig_poly(P[3],n,T,True)
 FX=scale(sub(scale(CD,c0),scale(SD,s0)),v);FY=scale(add(scale(CD,s0),scale(SD,c0)),v);product=mul(theta,CP);FP=sub(theta,scale(add(scale(SP,v),scale(trim(product,n),lh)),1/L))
 rx=norm(sub(FX,derivative(P[0])),T)+v*(abs(c0)*ecd+abs(s0)*esd+2*trig_initial_error)
 ry=norm(sub(FY,derivative(P[1])),T)+v*(abs(s0)*ecd+abs(c0)*esd+2*trig_initial_error)
 rt=norm(sub(theta,derivative(P[2])),T)+etheta
 tail=norm(product[n+1:],T)*T**(n+1)
 rp=norm(sub(FP,derivative(P[3])),T)+etheta+v/L*esp+abs(lh)/L*(etheta+norm(theta,T)*ecp+tail)
 max_yaw=norm(theta,T)+etheta;K=(v+abs(lh)*max_yaw)/L
 if K*T>=1:raise ValueError('Proved rational Gronwall majorant requires K*T<1')
 initial_xy_error=abs(pre*v)*trig_initial_error
 errors=[initial_xy_error+T*rx+v*T*T*rt/2,initial_xy_error+T*ry+v*T*T*rt/2,T*rt,T*rp/(1-K*T)]
 return dict(residual_bounds=[rx,ry,rt,rp],state_error_bounds=errors,lipschitz_phi=K,time_end=T,initial_xy_error=initial_xy_error,all_times_enclosed=True,proof='Residuals use exact rational polynomial truncation tails and global sin/cos Taylor remainder, tan numerator/cos denominator bound; delta error<=T*Rtheta, phi<=T*Rphi/(1-KT)>=Gronwall, x/y integrate yaw error plus residual. Source/alpha floating arithmetic contract must still be proved before real-data use.')
