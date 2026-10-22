const assert=require('node:assert/strict');
const path=require('node:path');
const {validateCFG,buildCases,evaluationSettings,summarize}=require('./batch_cfg.cjs');
let checks=0;
const check=(v,m)=>{assert(v,m);checks++;};
const bad=fn=>{assert.throws(fn);checks++;};
const base={name:'test',strategies:{default:{T_h_W:2,T_h_A:1,T_h_I:0.3,dt_pred:0.02,alpha_mode:'hold',safety_expand_m:0,safety_expand_enabled:false}}};
validateCFG(base);checks++;
for(const [key,value] of [['alpha_mode','unknown'],['safety_expand_m',0.1],['safety_expand_enabled',true],['dt_pred',0.001],['T_h_W',0],['unknown',1],['fan_branches',4]])
  bad(()=>validateCFG({...base,strategies:{default:{...base.strategies.default,[key]:value}}}));
bad(()=>validateCFG({...base,name:'comma,name'}));
bad(()=>validateCFG({...base,strategies:{default:{T_h_W:0.5,T_h_A:1,T_h_I:0.3}}}));
bad(()=>validateCFG({...base,state_machine:{exit_hold_frames:0}}));
bad(()=>validateCFG({...base,state_machine:{exit_require_alpha_returning:1}}));
const plan={base_cfg:'../CFG配置/exit_window_test_cfg.json',grid:{'strategies.EXIT.T_h_W':[2,3,4],'state_machine.exit_heading_delta_deg_min':[65,75]}};
const cases=buildCases(plan,__dirname);
check(cases.length===6,'Cartesian grid count');
check(new Set(cases.map(x=>x.cfg.name)).size===6,'Unique CFG names');
check(cases[0].cfg.strategies.EXIT.T_h_W===2 && cases[5].cfg.state_machine.exit_heading_delta_deg_min===75,'Grid applies parameters');
bad(()=>buildCases({...plan,max_configs:5},__dirname));
bad(()=>buildCases({...plan,grid:{'evaluation.tolerance_m':[0.3]}},__dirname));
check(buildCases({...plan,grid:{'strategies.EXIT.alpha_mode':['linear','quad','union','fan']}},__dirname).length===4,'Five implemented modes accepted');
bad(()=>buildCases({...plan,cfg_files:['x']},__dirname));
check(buildCases({cfg_files:['../CFG配置/default_cfg.json','../CFG配置/exit_window_test_cfg.json']},__dirname).length===2,'Existing CFG files');
bad(()=>evaluationSettings({evaluation:{reaction_threshold_s:0}}));
bad(()=>evaluationSettings({evaluation:{unknown:1}}));
bad(()=>evaluationSettings({evaluation:{max_targets:0}}));
bad(()=>evaluationSettings({evaluation:{negative_margin_m:0.01}}));
const stats=summarize([
  {event:'FRONT_CONTACT_IGNORED',nearest_contact_edge:'FRONT'},
  {event:'STARTUP_TRUNCATED',nearest_contact_edge:'INITIAL_OVERLAP'},
  {event:'POLYW_NO_HIT',nearest_contact_edge:'RIGHT'},
  {event:'BLINDSPOT_REACTION_INSUFFICIENT',nearest_contact_edge:'RIGHT',lead_s:0.5},
  {event:'REACTION_TIME_SUFFICIENT',nearest_contact_edge:'CORNER',lead_s:2},
  {event:'FALSE_POSITIVE',nearest_contact_edge:'NONE'},
  {event:'CORRECT_REJECTION',nearest_contact_edge:'NONE'},
  {event:'END_TRUNCATED',nearest_contact_edge:'NONE'}
]);
check(stats.eligible_positive===3 && stats.insufficient_rate===2/3,'Scope and startup/censor exclusions');
check(stats.false_positive_rate===0.5 && stats.front_ignored===1,'Negatives and front counts');
check(stats.right_positive===2 && stats.right_insufficient===2 && stats.min_lead_s===0.5,'Right subset and lead');
check(summarize([]).insufficient_rate===null && summarize([]).false_positive_rate===null,'No eligible denominator is not zero risk');
console.log('PASSED '+checks+' batch CFG unit checks');
