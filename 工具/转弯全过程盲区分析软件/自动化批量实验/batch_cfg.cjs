const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {pathToFileURL} = require('node:url');

const ROOT = path.resolve(__dirname, '..');
const stateKeys = new Set(['alpha_start_deg','enter_hold_frames','mid_heading_delta_deg',
  'exit_heading_delta_deg_min','exit_require_alpha_returning','exit_phi_abs_deg_min','exit_hold_frames',
  'done_heading_delta_deg_min','done_alpha_abs_deg_max','done_phi_abs_deg_max','done_hold_frames']);
const strategyKeys = new Set(['T_h_W','T_h_A','T_h_I','dt_pred','alpha_mode','safety_expand_m','safety_expand_enabled',
  'filter_tau_s','return_rate_deg_s','fan_rate_deg_s','fan_branches','alpha_limit_deg','alpha_dot_limit_deg_s','alpha_ddot_limit_deg_s2']);
const phases = new Set(['default','IDLE','ENTRY','MID','EXIT','DONE']);
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const readJSON = file => JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
const clone = value => JSON.parse(JSON.stringify(value));
const assert = (condition,message) => { if (!condition) throw new Error(message); };
const writeJSON = (file,value) => fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');

function validateCFG(cfg) {
  assert(cfg && typeof cfg === 'object' && !Array.isArray(cfg),'CFG must be an object');
  for (const key of Object.keys(cfg)) assert(['name','version','description','state_machine','strategies'].includes(key),'Unknown CFG field: '+key);
  assert(!/[\r\n,]/.test(String(cfg.name || '')),'CFG name cannot contain comma/newline (web CSV limitation)');
  for (const [key,value] of Object.entries(cfg.state_machine || {})) {
    assert(stateKeys.has(key),'Unknown state_machine field: '+key);
    if (key==='exit_require_alpha_returning') assert(typeof value==='boolean',key+' must be boolean');
    else {
      assert(typeof value==='number' && Number.isFinite(value) && value>=0,key+' must be finite/nonnegative');
      if (key.endsWith('_frames')) assert(Number.isInteger(value) && value>=1,key+' must be a positive integer');
    }
  }
  for (const [phase,s] of Object.entries(cfg.strategies || {})) {
    assert(phases.has(phase),'Use canonical strategy phase names, unknown: '+phase);
    assert(s && typeof s==='object' && !Array.isArray(s),'Invalid strategy: '+phase);
    for (const [key,value] of Object.entries(s)) {
      assert(strategyKeys.has(key),'Unknown strategy field: '+key);
      if (key==='alpha_mode') assert(['hold','linear','quad','union','fan'].includes(value),'Unsupported alpha_mode: '+value);
      else if (key==='safety_expand_enabled') assert(value===false,'Safety expansion is not implemented; it must be false');
      else if (key==='safety_expand_m') assert(value===0,'Safety expansion is not implemented; distance must be zero');
      else if (key==='fan_branches') assert(Number.isInteger(value) && value>=3 && value<=31 && value%2===1,'fan_branches must be odd, 3..31');
      else if (['filter_tau_s','return_rate_deg_s','fan_rate_deg_s','alpha_limit_deg','alpha_dot_limit_deg_s','alpha_ddot_limit_deg_s2'].includes(key))
        assert(typeof value==='number' && Number.isFinite(value) && value>0,'Invalid steering parameter: '+key);
      else assert(typeof value==='number' && Number.isFinite(value) && value>=(key==='dt_pred'?0.005:0.02),'Invalid/clamped strategy value: '+phase+'.'+key);
    }
    const merged={...(cfg.strategies?.default || {}),...s};
    if (['T_h_I','T_h_A','T_h_W'].every(k=>merged[k]!==undefined))
      assert(merged.T_h_I<=merged.T_h_A && merged.T_h_A<=merged.T_h_W,'Require T_h_I <= T_h_A <= T_h_W: '+phase);
  }
}

function setParameter(cfg,key,value) {
  const parts=key.split('.');
  assert(parts.length===2 && parts[0]==='state_machine' && stateKeys.has(parts[1]) ||
    parts.length===3 && parts[0]==='strategies' && phases.has(parts[1]) && strategyKeys.has(parts[2]),'Unsupported grid path: '+key);
  let cursor=cfg;
  for (const part of parts.slice(0,-1)) cursor=cursor[part] ||= {};
  cursor[parts.at(-1)]=value;
}

function buildCases(plan,baseDir) {
  const modes=Number(Boolean(plan.base_cfg))+Number(Boolean(plan.cfg_files))+Number(Boolean(plan.cfg_dir));
  assert(modes===1,'Choose exactly one of base_cfg, cfg_files or cfg_dir');
  let configs=[];
  if (plan.base_cfg) configs=[{cfg:readJSON(path.resolve(baseDir,plan.base_cfg)),parameters:{}}];
  else {
    assert(!plan.grid || !Object.keys(plan.grid).length,'grid requires base_cfg');
    const files=plan.cfg_files || fs.readdirSync(path.resolve(baseDir,plan.cfg_dir)).filter(f=>f.endsWith('.json')).sort()
      .map(f=>path.join(plan.cfg_dir,f));
    assert(Array.isArray(files) && files.length,'No CFG files');
    configs=files.map(file=>({cfg:readJSON(path.resolve(baseDir,file)),parameters:{source_cfg:file}}));
  }
  const maximum=plan.max_configs ?? 10000;
  assert(Number.isInteger(maximum) && maximum>0,'Invalid max_configs');
  for (const [key,values] of Object.entries(plan.grid || {})) {
    assert(Array.isArray(values) && values.length,'Empty/non-array grid: '+key);
    assert(configs.length*values.length<=maximum,'Grid exceeds max_configs='+maximum);
    configs=configs.flatMap(item=>values.map(value=>{
      const cfg=clone(item.cfg); setParameter(cfg,key,value);
      return {cfg,parameters:{...item.parameters,[key]:value}};
    }));
  }
  assert(configs.length<=maximum,'Too many configurations');
  return configs.map((item,i)=>{
    const id='cfg_'+String(i+1).padStart(5,'0');
    item.cfg.name=String(item.cfg.name || 'batch')+'__'+id;
    validateCFG(item.cfg);
    return {id,...item};
  });
}

function evaluationSettings(plan) {
  const values={spacing_m:0.1,tolerance_m:0.05,reaction_threshold_s:1,warmup_ignore_s:2,
    max_targets:7000,boundary_band_m:0.2,negative_margin_m:0.5,...plan.evaluation};
  const limits={spacing_m:[0.1,2],tolerance_m:[0,0.3],reaction_threshold_s:[0.1,3],warmup_ignore_s:[0,5],
    max_targets:[50,20000],boundary_band_m:[0.05,2],negative_margin_m:[0.1,5]};
  for (const [key,value] of Object.entries(values)) {
    assert(limits[key] && typeof value==='number' && Number.isFinite(value) && value>=limits[key][0] && value<=limits[key][1],'Invalid evaluation setting: '+key);
  }
  assert(Number.isInteger(values.max_targets),'max_targets must be an integer');
  assert(values.negative_margin_m>values.tolerance_m,'negative_margin_m must exceed tolerance_m');
  return values;
}

function summarize(rows) {
  const count=event=>rows.filter(r=>r.event===event).length;
  const miss=count('POLYW_NO_HIT'),late=count('BLINDSPOT_REACTION_INSUFFICIENT'),ok=count('REACTION_TIME_SUFFICIENT');
  const fp=count('FALSE_POSITIVE'),tn=count('CORRECT_REJECTION');
  const eligible=miss+late+ok;
  const right=rows.filter(r=>r.nearest_contact_edge==='RIGHT' && ['POLYW_NO_HIT','BLINDSPOT_REACTION_INSUFFICIENT','REACTION_TIME_SUFFICIENT'].includes(r.event));
  const leads=rows.filter(r=>['BLINDSPOT_REACTION_INSUFFICIENT','REACTION_TIME_SUFFICIENT'].includes(r.event) && Number.isFinite(r.lead_s)).map(r=>r.lead_s).sort((a,b)=>a-b);
  const early=rows.filter(r=>['BLINDSPOT_REACTION_INSUFFICIENT','REACTION_TIME_SUFFICIENT'].includes(r.event) &&
    Number.isFinite(r.lead_s) && Number.isFinite(r.T_h_W_s) && r.lead_s>r.T_h_W_s+1e-9).length;
  return {target_count:rows.length,front_ignored:count('FRONT_CONTACT_IGNORED'),startup_truncated:count('STARTUP_TRUNCATED'),
    end_truncated:count('END_TRUNCATED'),eligible_positive:eligible,miss_count:miss,late_count:late,sufficient_count:ok,
    insufficient_rate:eligible?(miss+late)/eligible:null,false_positive:fp,true_negative:tn,false_positive_rate:fp+tn?fp/(fp+tn):null,
    right_positive:right.length,right_insufficient:right.filter(r=>r.event!=='REACTION_TIME_SUFFICIENT').length,
    min_lead_s:leads.length?leads[0]:null,first_warning_outside_window:early};
}

function writeSummary(dir,reports) {
  const columns=['scenario_id','cfg_id','status','target_count','front_ignored','startup_truncated','end_truncated',
    'eligible_positive','miss_count','late_count','sufficient_count','insufficient_rate','false_positive','true_negative',
    'false_positive_rate','right_positive','right_insufficient','min_lead_s','first_warning_outside_window',
    'alpha_mode_default','alpha_mode_exit','analysis_wall_s','result_csv','error'];
  const cell=value=>value===undefined || value===null?'':'"'+String(value).replace(/"/g,'""')+'"';
  fs.writeFileSync(path.join(dir,'summary.csv'),[columns.join(','),...reports.map(r=>columns.map(k=>cell(r[k])).join(','))].join('\n')+'\n','utf8');
  writeJSON(path.join(dir,'summary.json'),reports);
}

async function setSettings(page,settings) {
  const ids={spacing_m:'spacing',tolerance_m:'grid-size',reaction_threshold_s:'lead-threshold',warmup_ignore_s:'warmup-ignore',
    max_targets:'max-targets',boundary_band_m:'boundary-band',negative_margin_m:'negative-margin'};
  for (const [key,id] of Object.entries(ids)) await page.locator('#'+id).fill(String(settings[key]));
}

async function waitAnalysis(page,action,prefix,timeout) {
  await page.evaluate(()=>{document.getElementById('load-status').textContent='BATCH_PENDING';});
  await action();
  await page.waitForFunction(prefix=>{
    const el=document.getElementById('load-status'),refresh=document.getElementById('refresh-analysis');
    const s=el.textContent;
    return !refresh.disabled && (s.startsWith(prefix) || /失败/.test(s));
  },prefix,{timeout});
  const status=await page.locator('#load-status').innerText();
  assert(status.startsWith(prefix),'Web analysis failed: '+status);
}

async function download(page,button,file,timeout) {
  const pending=page.waitForEvent('download',{timeout});
  await page.locator(button).click();
  const result=await pending;
  await result.saveAs(file);
  assert(fs.statSync(file).size>0,'Empty export: '+file);
}

async function run(planFile,options={}) {
  planFile=path.resolve(planFile);
  const plan=readJSON(planFile),baseDir=path.dirname(planFile),cases=buildCases(plan,baseDir),settings=evaluationSettings(plan);
  assert(Array.isArray(plan.scenarios) && plan.scenarios.length,'Provide scenarios');
  const scenarioIds=new Set();
  for (const scene of plan.scenarios) {
    assert(/^[a-zA-Z0-9_-]+$/.test(scene.id) && !scenarioIds.has(scene.id),'Scene id must be unique ASCII letters/numbers/hyphens: '+scene.id);
    scenarioIds.add(scene.id);
    for (const key of ['csv','targets_csv']) if(scene[key]) assert(fs.existsSync(path.resolve(baseDir,scene[key])),'Missing '+key+': '+scene[key]);
  }
  const sources=[__filename,path.join(ROOT,'index.html'),path.join(ROOT,'target_sampling.js'),path.join(ROOT,'steering_prediction.js'),...plan.scenarios.flatMap(s=>['csv','targets_csv'].filter(k=>s[k]).map(k=>path.resolve(baseDir,s[k])))];
  const sourceHashes=Object.fromEntries(sources.map(f=>[f,hash(fs.readFileSync(f))]));
  const fingerprint=hash(JSON.stringify({plan,cases,sourceHashes}));
  const jobs=cases.length*plan.scenarios.length;
  console.log('CFGs='+cases.length+', scenarios='+plan.scenarios.length+', jobs='+jobs+'; evaluation=exclude_front_contact');
  if(options.dryRun) return {configs:cases.length,jobs};
  const out=options.resume?path.resolve(options.resume):path.join(path.resolve(baseDir,plan.output_dir || 'results'),
    'run_'+new Date().toISOString().replace(/[:.]/g,'-')+'_'+crypto.randomBytes(3).toString('hex'));
  if(options.resume) {
    assert(readJSON(path.join(out,'manifest.json')).fingerprint===fingerprint,'Resume refused: plan/CFG/input/web source changed');
    for(const item of cases) assert(JSON.stringify(readJSON(path.join(out,'configs',item.id+'.json')))===JSON.stringify(item.cfg),'Saved CFG changed: '+item.id);
  }
  else {
    fs.mkdirSync(out,{recursive:true});
    writeJSON(path.join(out,'manifest.json'),{fingerprint,planFile,plan,sourceHashes,configs:cases.length,jobs,created_at:new Date().toISOString(),
      evaluation_scope:'exclude_front_contact',mode:'real_web_UI_headless_Edge',runtime_note:'wall time includes browser analysis/render; not MCU latency'});
    fs.mkdirSync(path.join(out,'configs'));
    for(const item of cases) writeJSON(path.join(out,'configs',item.id+'.json'),item.cfg);
    fs.mkdirSync(path.join(out,'source'));
    for(const file of [__filename,path.join(ROOT,'index.html'),path.join(ROOT,'target_sampling.js'),path.join(ROOT,'steering_prediction.js')])
      fs.copyFileSync(file,path.join(out,'source',path.basename(file)));
  }
  const timeout=plan.timeout_ms ?? 180000;
  if(options.onStart) options.onStart(out);
  assert(Number.isFinite(timeout) && timeout>0,'Invalid timeout_ms');
  const {chromium}=require('playwright');
  const browser=await chromium.launch({channel:'msedge',headless:plan.headless!==false});
  const reports=[];
  try {
    for(const scene of plan.scenarios) {
      const sceneDir=path.join(out,'scenarios',scene.id); fs.mkdirSync(sceneDir,{recursive:true});
      const context=await browser.newContext({acceptDownloads:true,viewport:{width:1600,height:1080}});
      const page=await context.newPage(); page.setDefaultTimeout(timeout);
      const errors=[]; page.on('pageerror',e=>errors.push(e.message));
      try {
        await page.goto(pathToFileURL(path.join(ROOT,'index.html')).href);
        const sceneMeta=path.join(sceneDir,'scene_snapshot.json');
        const sceneCSV=path.join(sceneDir,'scenario.csv');
        if(fs.existsSync(sceneMeta)) assert(readJSON(sceneMeta).sha256===hash(fs.readFileSync(sceneCSV)),'Frozen scenario CSV changed');
        if(scene.csv) {
          const snapshot=path.join(sceneDir,'scenario.csv');
          if(!fs.existsSync(snapshot)) fs.copyFileSync(path.resolve(baseDir,scene.csv),snapshot);
          await waitAnalysis(page,()=>page.locator('#scenario-file').setInputFiles(snapshot),'已导入场景:',timeout);
        } else {
          const csv=await page.evaluate(()=>{
            const cols={...data};
            for(const name of ['theta_ref','theta','theta_t','alpha','phi']) cols[name+'_deg']=data[name+'_rad'].map(v=>v*180/Math.PI);
            const keys=Object.keys(cols); return [keys.join(','),...data.time_s.map((_,i)=>keys.map(k=>cols[k][i]).join(','))].join('\n');
          });
          const file=path.join(sceneDir,'scenario.csv'); if(!fs.existsSync(file)) fs.writeFileSync(file,csv,'utf8');
        }
        if(!fs.existsSync(sceneMeta)) writeJSON(sceneMeta,{sha256:hash(fs.readFileSync(sceneCSV)),source:scene.csv || 'web_builtin'});
        const frozen=path.join(sceneDir,'targets.csv');
        if(fs.existsSync(frozen) || scene.targets_csv) {
          const input=fs.existsSync(frozen)?frozen:path.resolve(baseDir,scene.targets_csv);
          await waitAnalysis(page,()=>page.locator('#target-file').setInputFiles(input),'已导入固定目标点:',timeout);
          // Target CSV metadata may override controls; restore the experiment-wide settings.
          await setSettings(page,settings);
          await waitAnalysis(page,()=>page.locator('#refresh-analysis').click(),'已按当前参数刷新盲区分析。',timeout);
        } else {
          await setSettings(page,settings);
          await page.locator('#target-mode').selectOption('mixed');
          await waitAnalysis(page,()=>page.locator('#build-targets').click(),'已生成并分析',timeout);
        }
        if(!fs.existsSync(frozen)) {
          await download(page,'#export-targets',frozen,timeout);
          // Canonicalize generated coordinates through the same 12-decimal CSV used in later stages/resumes.
          await waitAnalysis(page,()=>page.locator('#target-file').setInputFiles(frozen),'已导入固定目标点:',timeout);
          await setSettings(page,settings);
          await waitAnalysis(page,()=>page.locator('#refresh-analysis').click(),'已按当前参数刷新盲区分析。',timeout);
        }
        const targetSignature=await page.evaluate(()=>JSON.stringify(targets.map(t=>[t.name,t.x,t.y,t.trueContactIdx,t.nearestContactEdge])));
        const targetHash=hash(targetSignature);
        const targetMeta=path.join(sceneDir,'target_snapshot.json');
        if(fs.existsSync(targetMeta)) {
          // Browser CSV writes 12 decimal places; use frozen CSV hash for resumed comparisons.
          assert(readJSON(targetMeta).csv_sha256===hash(fs.readFileSync(frozen)),'Frozen target CSV changed');
        } else writeJSON(targetMeta,{count:await page.evaluate(()=>targets.length),csv_sha256:hash(fs.readFileSync(frozen)),initial_points_sha256:targetHash,settings});
        assert(await page.evaluate(()=>targets.length>0),'Empty target set');
        if(plan.require_target_count) assert(await page.evaluate(()=>targets.length)===settings.max_targets,'Target count must be exactly '+settings.max_targets);
        const sourceCounts=await page.evaluate(()=>targets.reduce((a,t)=>(a[t.sampleSource]=(a[t.sampleSource]||0)+1,a),{}));
        if(plan.require_near_negatives) assert(!sourceCounts.far_body,'Far negatives are forbidden in this experiment');
        for(const item of cases) {
          const jobDir=path.join(out,'jobs',scene.id+'__'+item.id),reportFile=path.join(jobDir,'report.json');
          if(options.resume && fs.existsSync(reportFile)) {
            const previous=readJSON(reportFile);
            const files=['results.csv','cfg_requested.json','cfg_effective.json'].map(f=>path.join(jobDir,f));
            if(previous.status==='ok' && files.every(f=>fs.existsSync(f)) && hash(fs.readFileSync(files[0]))===previous.result_sha256 &&
              JSON.stringify(readJSON(files[1]))===JSON.stringify(item.cfg) && JSON.stringify(readJSON(files[2]))===JSON.stringify(previous.cfg_effective)) {
              reports.push(previous); writeSummary(out,reports); console.log('SKIP '+scene.id+'/'+item.id); continue;
            }
          }
          fs.mkdirSync(jobDir,{recursive:true});
          const started=Date.now(),report={scenario_id:scene.id,cfg_id:item.id,status:'failed',parameters:item.parameters};
          try {
            const requested=path.join(out,'configs',item.id+'.json');
            fs.copyFileSync(requested,path.join(jobDir,'cfg_requested.json'));
            await waitAnalysis(page,()=>page.locator('#cfg-file').setInputFiles(requested),'已导入 CFG:',timeout);
            assert(!errors.length,'Browser errors: '+errors.join('; '));
            const state=await page.evaluate(()=>({cfg:strategyCfg,logs:logRows,
              signature:JSON.stringify(targets.map(t=>[t.name,t.x,t.y,t.trueContactIdx,t.nearestContactEdge]))}));
            validateCFG(state.cfg);
            assert(state.cfg.name===item.cfg.name,'CFG import did not take effect');
            assert(hash(state.signature)===targetHash,'Targets/contact truth changed across CFGs');
            const stats=summarize(state.logs);
            assert(stats.target_count===await page.evaluate(()=>targets.length),'Incomplete result rows');
            assert(state.logs.filter(r=>r.nearest_contact_edge==='FRONT').every(r=>r.event==='FRONT_CONTACT_IGNORED'),'Front exclusion lost');
            await download(page,'#export-cfg',path.join(jobDir,'cfg_effective.json'),timeout);
            const exportedCFG=readJSON(path.join(jobDir,'cfg_effective.json'));
            assert(JSON.stringify(exportedCFG)===JSON.stringify(state.cfg),'Effective CFG export mismatch');
            const csvFile=path.join(jobDir,'results.csv');
            await download(page,'#export-log',csvFile,timeout);
            const exported=await page.evaluate(text=>parseCSV(text),fs.readFileSync(csvFile,'utf8'));
            assert(exported.target.length===state.logs.length && exported.event.every((v,i)=>v===state.logs[i].event),'CSV/UI result mismatch');
            Object.assign(report,stats,{status:'ok',result_csv:csvFile,result_sha256:hash(fs.readFileSync(csvFile)),
              target_csv:frozen,target_csv_sha256:hash(fs.readFileSync(frozen)),cfg_effective:exportedCFG,
              alpha_mode_default:exportedCFG.strategies.default.alpha_mode,alpha_mode_exit:exportedCFG.strategies.EXIT.alpha_mode,
              analysis_wall_s:(Date.now()-started)/1000});
          } catch(error) {
            report.error=error.stack || String(error);
            await page.screenshot({path:path.join(jobDir,'failure.png'),fullPage:true}).catch(()=>{});
            // Stop on failure; a resumed run rebuilds the page from frozen inputs.
            writeJSON(reportFile,report); reports.push(report); writeSummary(out,reports);
            throw new Error('Job failed; completed outputs preserved for --resume: '+scene.id+'/'+item.id+'\n'+report.error);
          }
          writeJSON(reportFile,report); reports.push(report); writeSummary(out,reports);
          console.log('DONE '+reports.length+'/'+jobs+' '+scene.id+'/'+item.id+' miss='+report.miss_count+' late='+report.late_count+' false='+report.false_positive);
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
  console.log('OUTPUT '+out);
  return {out,reports};
}

async function main(args) {
  const options={}; let planFile=path.join(__dirname,'batch_plan.json');
  for(let i=0;i<args.length;i++) {
    if(args[i]==='--plan') { assert(args[i+1],'Missing --plan value'); planFile=args[++i]; }
    else if(args[i]==='--resume') { assert(args[i+1],'Missing --resume value'); options.resume=args[++i]; }
    else if(args[i]==='--dry-run') options.dryRun=true;
    else throw new Error('Unknown argument: '+args[i]);
  }
  return run(planFile,options);
}
module.exports={validateCFG,buildCases,evaluationSettings,summarize,run,main};
if(require.main===module) main(process.argv.slice(2)).catch(error=>{console.error(error.stack);process.exitCode=1;});
