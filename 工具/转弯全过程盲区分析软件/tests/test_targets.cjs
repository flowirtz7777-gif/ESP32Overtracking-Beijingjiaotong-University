const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const api = require('../target_sampling.js');
let checks = 0;
function check(value, name) { assert(value, name); checks++; }
const d = {time_s:[0,1,5], xH_m:[0,2,0], yH_m:[0,0,0], theta_t_rad:[0,0,0]};
const p = {l:4,l_h:1.8,L:2,width:2};
const q = [[-1,0],[1.5,0],[8,0],[0.03,1.039],[0.04,1.04]];
const idx = api.firstContacts(q,d,p,0.05);
check(idx[0]===0 && idx[1]===1 && Number.isNaN(idx[2]) && idx[3]===0 && idx[4]===1,
  'global earliest sampled contact, including rounded corners');
const c=[5,5,5,0.5,NaN,NaN,NaN], w=[NaN,4.5,3,0.1,1,NaN,4.5];
const events=['POLYW_NO_HIT','BLINDSPOT_REACTION_INSUFFICIENT','REACTION_TIME_SUFFICIENT',
  'STARTUP_TRUNCATED','FALSE_POSITIVE','CORRECT_REJECTION','END_TRUNCATED'];
events.forEach((event,i)=>check(api.classify(c[i],w[i],2,5,2,1)===event,event));
const scopeEdges=['FRONT','FRONT','FRONT','FRONT','FRONT','NONE','NONE'];
const scopeEvents=['FRONT_CONTACT_IGNORED','FRONT_CONTACT_IGNORED','FRONT_CONTACT_IGNORED',
  'FRONT_CONTACT_IGNORED','FALSE_POSITIVE','CORRECT_REJECTION','END_TRUNCATED'];
scopeEvents.forEach((event,i)=>check(api.classify(c[i],w[i],2,5,2,1,scopeEdges[i])===event,'front scope '+event));
for(const edge of ['RIGHT','LEFT','REAR','CORNER','INITIAL_OVERLAP','NONE',''])
  events.forEach((event,i)=>check(api.classify(c[i],w[i],2,5,2,1,edge)===event,'non-front unchanged '+edge));
const options={spacing:0.5,maximum:90,tolerance:0.05,boundaryBand:0.2,negativeMargin:0.5};
const a=api.generate(d,p,options), b=api.generate(d,p,options);
check(JSON.stringify(a)===JSON.stringify(b),'deterministic generation');
check(a.length<=90 && ['interior','boundary','negative'].every(g=>a.some(r=>r.sampleGroup===g)),'three strata and budget');
check(a.filter(r=>r.sampleGroup==='negative').every(r=>Number.isNaN(r.trueContactIdx)),'verified negative labels');
check(a.filter(r=>r.sampleGroup==='interior').every(r=>Number.isFinite(r.trueContactIdx)),'verified interior labels');
assert.throws(()=>api.firstContacts([[NaN,0]],d,p,0.05)); checks++;
assert.throws(()=>api.generate(d,p,{...options,negativeMargin:0.01})); checks++;
if(process.argv[2]){
  const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
  const actual=api.firstContacts(fixture.queries,fixture.data,fixture.params,0.05);
  fixture.expected_idx.forEach((r,i)=>check(r===null ? Number.isNaN(actual[i]) : actual[i]===r-1,'MATLAB contact parity'));
  fixture.events.forEach((r,i)=>check(api.classify(fixture.contacts[i]??NaN,fixture.warnings[i]??NaN,
    fixture.horizons[i],5,2,1)===r,'MATLAB event parity'));
  if(fixture.scope_events) fixture.scope_events.forEach((r,i)=>check(api.classify(
    fixture.contacts[i]??NaN,fixture.warnings[i]??NaN,fixture.horizons[i],5,2,1,
    fixture.scope_edges[i])===r,'MATLAB front exclusion parity'));
  const generated=api.generate(fixture.data,fixture.params,options);
  check(generated.length===fixture.generated.length,'MATLAB sample count parity');
  fixture.generated.forEach((r,i)=>{
    check(Math.abs(generated[i].x-r.x_m)<1e-8 && Math.abs(generated[i].y-r.y_m)<1e-8 &&
      generated[i].sampleGroup===r.sample_group,'MATLAB coordinate/group parity');
    check(r.true_contact_idx===null ? Number.isNaN(generated[i].trueContactIdx) :
      generated[i].trueContactIdx===r.true_contact_idx-1,'MATLAB generated contact parity');
    if(r.nearest_contact_edge) check(generated[i].nearestContactEdge===r.nearest_contact_edge,'MATLAB contact-edge descriptor parity');
  });
}
const dir=path.join(__dirname,'..','logs'); fs.mkdirSync(dir,{recursive:true});
const log=path.join(dir,'js_target_tests_'+Date.now()+'.json');
fs.writeFileSync(log,JSON.stringify({passed:checks,fixture:process.argv[2]||null,createdAt:new Date().toISOString()},null,2));
console.log('PASSED: '+checks+' target checks; '+log);
