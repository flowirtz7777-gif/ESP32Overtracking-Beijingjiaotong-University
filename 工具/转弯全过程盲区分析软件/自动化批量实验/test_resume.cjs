const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {run}=require('./batch_cfg.cjs');

(async()=>{
  const dir=path.resolve(process.argv[2]);
  const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json'),'utf8'));
  const previous=JSON.parse(fs.readFileSync(path.join(dir,'summary.json'),'utf8'));
  assert(previous.length===manifest.jobs && previous.every(r=>r.status==='ok'));
  const last=previous.at(-1);
  const file=path.join(dir,'jobs',last.scenario_id+'__'+last.cfg_id,'report.json');
  const original=fs.readFileSync(file,'utf8');
  // Simulate an interrupted checkpoint without removing any result CSV.
  fs.writeFileSync(file,JSON.stringify({...last,status:'failed',error:'test: interrupted checkpoint'},null,2));
  try {
    const result=await run(manifest.planFile,{resume:dir});
    assert(result.reports.length===previous.length);
    for(let i=0;i<previous.length;i++) {
      const before=previous[i],after=result.reports[i];
      assert(after.status==='ok');
      for(const key of ['miss_count','late_count','false_positive','eligible_positive','front_ignored','target_csv_sha256'])
        assert.deepEqual(after[key],before[key],key+' changed after resume');
      if(i<previous.length-1) assert(after.analysis_wall_s===before.analysis_wall_s,'Completed job reran unexpectedly');
    }
    const report={passed:true,skipped:previous.length-1,rerun:1,
      regenerated_csv_sha256:crypto.createHash('sha256').update(fs.readFileSync(last.result_csv)).digest('hex')};
    fs.writeFileSync(path.join(dir,'resume_test_report.json'),JSON.stringify(report,null,2));
    console.log('PASSED resume skipped completed jobs, reran interrupted checkpoint and preserved metrics');
  } catch(error) {
    fs.writeFileSync(file,original);
    throw error;
  }
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
