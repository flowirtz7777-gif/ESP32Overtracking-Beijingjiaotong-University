const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url'),{chromium}=require('playwright');
(async()=>{
  const root=path.resolve(__dirname,'..'),out=path.join(root,'logs','steering_browser_'+Date.now());fs.mkdirSync(out);
  const b=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await b.newPage({viewport:{width:1600,height:1080}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(path.join(root,'index.html')).href);
    assert.equal(await page.locator('#max-targets').inputValue(),'7000');
    const proof=await page.evaluate(()=>{
      const points=TargetSampling.generate(data,cfg,{maximum:7000,spacing:.1,tolerance:.05,boundaryBand:.2,negativeMargin:.5});
      const ids=new Set(points.map(p=>`${Math.round(p.x/.1)},${Math.round(p.y/.1)}`));
      const counts={};points.forEach(p=>counts[p.sampleGroup]=(counts[p.sampleGroup]||0)+1);
      const modeChecks=[];
      for(const mode of SteeringPrediction.modes) {
        const s={...strategyCfg.strategies.default,alpha_mode:mode};
        const seq=predictRightEdgeSequence(800,1.13,s);
        modeChecks.push({mode,branches:(seq.branches || [seq]).length,vertices:seq.length});
      }
      const branch1=[{H:[0,0],T:[1,0]},{H:[0,1],T:[1,1]}],branch2=[{H:[10,0],T:[11,0]},{H:[10,1],T:[11,1]}];
      const seq=branch1.slice();seq.branches=[branch1,branch2];
      const disconnected=!pointInSweptSegmentsTol([5,.5],seq,0) && pointInSweptSegmentsTol([.5,.5],seq,0);
      strategyCfg.strategies.default.alpha_mode='fan';strategyCfg.strategies.EXIT.alpha_mode='fan';
      updateWindowGrid();currentIndex=800;render();
      const c=document.getElementById('scene-poly'),ctx=c.getContext('2d'),pixels=ctx.getImageData(0,0,c.width,c.height).data;
      const colors=new Set();for(let i=0;i<pixels.length;i+=64) colors.add(pixels[i]+','+pixels[i+1]+','+pixels[i+2]);
      return {count:points.length,unique:ids.size,counts,far:points.filter(p=>p.sampleSource==='far_body').length,
        modes:modeChecks,disconnected,canvasColors:colors.size,polyDisabled:document.querySelector('option[value="poly"]').disabled};
    });
    assert.equal(proof.count,7000);assert.equal(proof.unique,7000);assert.equal(proof.far,0);
    assert.deepEqual(proof.counts,{interior:2334,boundary:2333,negative:2333});
    assert.deepEqual(proof.modes.map(m=>m.branches),[1,1,1,3,7]);
    assert(proof.disconnected && proof.polyDisabled && proof.canvasColors>10);
    await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1));
    await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({passed:true,...proof,errors},null,2));
    console.log('PASSED 7000 points/five modes/no bridging/nonblank canvas/desktop-mobile: '+out);
  } finally {await b.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
