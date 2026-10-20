const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const api=require('../steering_prediction.js');
let checks=0;const check=(v,m)=>{assert(v,m);checks++;};
const time=Array.from({length:11},(_,i)=>i*0.02),alpha=[-.12,-.125,-.131,-.14,-.15,-.145,-.13,-.08,-.06,-.03,0];
const rates=api.derivatives(alpha,time,.25),changed=alpha.map((v,i)=>i>5?4:v),other=api.derivatives(changed,time,.25);
check(JSON.stringify(rates.dot.slice(0,6))===JSON.stringify(other.dot.slice(0,6)),'causal first derivative');
check(JSON.stringify(rates.ddot.slice(0,6))===JSON.stringify(other.ddot.slice(0,6)),'causal second derivative');
const union=api.normalize({alpha_mode:'union'});
for(const sign of [-1,1]) for(const tau of [.01,.1,1,10]) {
  const v=api.alphaAt(sign*.1,0,0,tau,union,2);
  check(sign*v>=0,'return never crosses zero');
  check(Math.abs(v)<=.1,'return magnitude does not increase');
}
check(api.alphaAt(.1,0,0,1,union,2)===0,'return stops at zero');
const fan=api.normalize({alpha_mode:'fan'});
check(api.alphaAt(.1,0,0,1,fan,3)===.1,'fan central branch holds');
check(Math.abs(api.alphaAt(.1,100,100,10,api.normalize({alpha_mode:'quad'})))<=40*Math.PI/180,'steering angle limited');
assert.throws(()=>api.normalize({alpha_mode:'unknown'}));checks++;
assert.throws(()=>api.normalize({fan_branches:4}));checks++;
if(process.argv[2]) {
  const f=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
  for(let i=0;i<f.alpha.length;i++) {check(Math.abs(rates.dot[i]-f.rates.dot[i])<1e-10,'native dot parity');check(Math.abs(rates.ddot[i]-f.rates.ddot[i])<1e-10,'native ddot parity');}
  const p=f.params;
  const step=(s,a,v,p,dt)=>{const [x,y,t,phi]=s,w=v*Math.sin(a)/p.l,vB=v*Math.cos(a),w2=(vB*Math.sin(phi)+p.l_h*w*Math.cos(phi))/p.L;
    return [x+vB*Math.cos(t)*dt,y+vB*Math.sin(t)*dt,t+w*dt,Math.max(-p.phi_max,Math.min(p.phi_max,phi+(w-w2)*dt))];};
  const derive=s=>{const [x,y,t,phi]=s,H=[x+p.l_h*Math.cos(t),y+p.l_h*Math.sin(t)],tt=t-phi;
    return {H,T:[H[0]-p.L*Math.cos(tt),H[1]-p.L*Math.sin(tt)],theta_t:tt};};
  const d={time_s:f.time,alpha_rad:f.alpha,v_input_mps:f.time.map(()=>3),xB_m:f.time.map(()=>f.state[0]),yB_m:f.time.map(()=>f.state[1]),
    theta_rad:f.time.map(()=>f.state[2]),phi_rad:f.time.map(()=>f.state[3])};
  for(const c of f.cases) {
    const seq=api.predict(f.k-1,f.horizon,d,p,c.strategy,step,derive),branches=seq.branches || [seq];
    const native=c.branches;
    check(branches.length===native.length,'native branch count');
    for(let b=0;b<branches.length;b++) for(let i=0;i<branches[b].length;i++) for(const key of ['H','T'])
      check(branches[b][i][key].every((v,j)=>Math.abs(v-native[b][i][key][j])<1e-8),'native edge vertex parity '+c.strategy.alpha_mode);
  }
}
const out=path.join(__dirname,'..','logs','steering_js_'+Date.now()+'.json');
fs.writeFileSync(out,JSON.stringify({passed:checks,fixture:process.argv[2]||null},null,2));
console.log('PASSED '+checks+' steering checks; '+out);
