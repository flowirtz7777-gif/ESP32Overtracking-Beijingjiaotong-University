(function(root,factory){
  const api=factory();
  if(typeof module==='object' && module.exports) module.exports=api;
  else root.SteeringPrediction=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const RAD=Math.PI/180;
  const modes=['hold','linear','quad','union','fan'];
  const defaults={filter_tau_s:0.25,return_rate_deg_s:25,fan_rate_deg_s:25,fan_branches:7,
    alpha_limit_deg:40,alpha_dot_limit_deg_s:180,alpha_ddot_limit_deg_s2:360};
  const caches=new WeakMap();
  const clip=(v,limit)=>Math.max(-limit,Math.min(limit,v));
  function normalize(s={},fallback={}) {
    const mode=s.alpha_mode || fallback.alpha_mode || 'hold';
    if(!modes.includes(mode)) throw new Error('Unsupported alpha_mode: '+mode);
    const out={alpha_mode:mode};
    for(const [key,value] of Object.entries(defaults)) {
      out[key]=s[key] ?? fallback[key] ?? (key==='filter_tau_s' && mode==='quad'?0.35:value);
      if(!Number.isFinite(out[key]) || out[key]<=0) throw new Error('Invalid steering parameter: '+key);
    }
    if(!Number.isInteger(out.fan_branches) || out.fan_branches<3 || out.fan_branches>31 || out.fan_branches%2===0)
      throw new Error('fan_branches must be odd, between 3 and 31');
    return out;
  }
  function derivatives(alpha,time,tau) {
    const dot=Array(alpha.length).fill(0),ddot=Array(alpha.length).fill(0);
    let filtered=0,second=0;
    for(let k=1;k<alpha.length;k++) {
      const dt=time[k]-time[k-1];
      if(!(dt>0)) throw new Error('Prediction requires strictly increasing scenario time');
      const a=dt/(tau+dt),previous=filtered;
      filtered+=a*((alpha[k]-alpha[k-1])/dt-filtered);
      if(k>=2) second+=a*((filtered-previous)/dt-second);
      if(k>=2) dot[k]=filtered;
      if(k>=3) ddot[k]=second;
    }
    return {dot,ddot};
  }
  function cachedRates(data,tau) {
    let cache=caches.get(data);
    if(!cache) {cache=new Map();caches.set(data,cache);}
    if(!cache.has(tau)) cache.set(tau,derivatives(data.alpha_rad,data.time_s,tau));
    return cache.get(tau);
  }
  function alphaAt(alpha,dot,ddot,tau,strategy,branch=0) {
    const s=strategy;
    dot=clip(dot,s.alpha_dot_limit_deg_s*RAD);
    ddot=clip(ddot,s.alpha_ddot_limit_deg_s2*RAD);
    let value=alpha;
    if(s.alpha_mode==='linear' || s.alpha_mode==='union' && branch===1) value+=dot*tau;
    else if(s.alpha_mode==='quad') value+=dot*tau+0.5*ddot*tau*tau;
    else if(s.alpha_mode==='union' && branch===2 && Math.abs(alpha)>=RAD)
      value=Math.sign(alpha)*Math.max(0,Math.abs(alpha)-s.return_rate_deg_s*RAD*tau);
    else if(s.alpha_mode==='fan') value+=(2*branch/(s.fan_branches-1)-1)*s.fan_rate_deg_s*RAD*tau;
    return s.alpha_mode==='hold'?value:clip(value,s.alpha_limit_deg*RAD);
  }
  function predict(k,horizon,data,p,strategy,step,derive) {
    const s=normalize(strategy),dt=strategy.dt_pred ?? 0.02;
    if(!(horizon>=0 && dt>0)) throw new Error('Invalid prediction horizon/step');
    const count=Math.max(0,Math.ceil(horizon/dt-1e-10));
    const rates=cachedRates(data,s.filter_tau_s);
    const alpha=data.alpha_rad[k] ?? 0,v=(data.v_input_mps ?? data.v_mps)[k] ?? p.speed;
    const branches=[],number=s.alpha_mode==='union'?3:s.alpha_mode==='fan'?s.fan_branches:1;
    for(let branch=0;branch<number;branch++) {
      let state=[data.xB_m[k],data.yB_m[k],data.theta_rad[k],data.phi_rad[k]];
      const seq=[];
      for(let i=0;i<=count;i++) {
        const d=derive(state,p),n=[Math.sin(d.theta_t),-Math.cos(d.theta_t)],hw=p.width/2;
        seq.push({H:[d.H[0]+hw*n[0],d.H[1]+hw*n[1]],T:[d.T[0]+hw*n[0],d.T[1]+hw*n[1]]});
        if(i<count) {
          let delta=Math.min(dt,horizon-i*dt);
          if(Math.abs(delta-dt)<1e-10) delta=dt;
          state=step(state,alphaAt(alpha,rates.dot[k],rates.ddot[k],i*dt,s,branch),v,p,delta);
        }
      }
      branches.push(seq);
    }
    // Keep the ordinary edge sequence API; OR branches must never be connected geometrically.
    const result=branches[0].slice();
    if(branches.length>1) result.branches=branches;
    return result;
  }
  return {modes,defaults,normalize,derivatives,alphaAt,predict};
});
