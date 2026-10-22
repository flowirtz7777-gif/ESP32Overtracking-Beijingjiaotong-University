const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const original = path.join(root, '边界点盲区日志', 'turn_blindspot_boundary_log_2026-10-12T17-27-02-142Z.csv');
  const lines = fs.readFileSync(original, 'utf8').trim().split(/\r?\n/);
  const header = lines.shift().split(',');
  const oldRows = lines.map(line => Object.fromEntries(line.split(',').map((v,i) => [header[i],v])));
  const out = path.join(root, 'logs', 'front_scope_' + Date.now());
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1600,height:1080},acceptDownloads:true});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(pathToFileURL(path.join(root,'index.html')).href);
    await page.locator('#spacing').fill('0.35');
    await page.locator('#max-targets').fill('700');
    await page.locator('#build-targets').click();
    await page.waitForFunction(() => document.getElementById('load-status').textContent.startsWith('已生成并分析'),
      null, {timeout:180000});
    const state = await page.evaluate(() => ({logs:logRows, targets, summary:document.getElementById('summary-grid').innerText}));
    assert.equal(state.logs.length,700);
    const counts = {};
    for (const row of state.logs) {
      counts[row.event] = (counts[row.event] || 0) + 1;
      const old = oldRows.find(r => r.target === row.target);
      assert(old);
      assert(Math.abs(row.x_m - Number(old.x_m)) <= 0.000501 && Math.abs(row.y_m - Number(old.y_m)) <= 0.000501);
      assert.equal(row.nearest_contact_edge, old.nearest_contact_edge);
      assert.equal(row.event, old.nearest_contact_edge === 'FRONT' ? 'FRONT_CONTACT_IGNORED' : old.event);
      if (Number.isFinite(row.time_s)) assert(Math.abs(row.time_s - Number(old.time_s)) < 1e-6);
    }
    assert.deepEqual(counts,{STARTUP_TRUNCATED:54, FRONT_CONTACT_IGNORED:198,
      REACTION_TIME_SUFFICIENT:184, BLINDSPOT_REACTION_INSUFFICIENT:2, CORRECT_REJECTION:255, FALSE_POSITIVE:7});
    const eligible = counts.REACTION_TIME_SUFFICIENT + counts.BLINDSPOT_REACTION_INSUFFICIENT;
    assert.equal(eligible,186);
    assert(state.summary.includes('前沿忽略') && state.summary.includes('非前沿样例不足率'));
    await page.locator('#time-slider').evaluate(el => {el.value='800';el.dispatchEvent(new Event('input',{bubbles:true}));});
    await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth+1));
    assert.deepEqual(errors,[]);
    const logDownload = page.waitForEvent('download');
    await page.locator('#export-log').click();
    const download = await logDownload;
    const logCsv = path.join(out,'web_log.csv');
    await download.saveAs(logCsv);
    assert.equal(fs.readFileSync(logCsv,'utf8').split('FRONT_CONTACT_IGNORED').length-1,198);
    const targetDownload = page.waitForEvent('download');
    await page.locator('#export-targets').click();
    const targetCsv = path.join(out,'web_targets.csv');
    await (await targetDownload).saveAs(targetCsv);
    const scenarioCsv = path.join(out,'builtin_scenario.csv');
    const scenario = await page.evaluate(() => {
      const cols={...data};
      for(const name of ['theta_ref','theta','theta_t','alpha','phi'])
        cols[name+'_deg']=data[name+'_rad'].map(v=>v*180/Math.PI);
      const keys=Object.keys(cols);
      return [keys.join(','),...data.time_s.map((_,i)=>keys.map(k=>cols[k][i]).join(','))].join('\n');
    });
    fs.writeFileSync(scenarioCsv,scenario,'utf8');
    const report={passed:true,original,counts,eligiblePositive:eligible,insufficientRate:2/eligible,
      logCsv,targetCsv,scenarioCsv,pageErrors:errors};
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
    console.log('PASSED front exclusion: '+JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exit(1);});
