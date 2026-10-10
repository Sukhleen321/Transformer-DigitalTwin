/* Acceptance on the actual monitoring grid, using the isolated running backend. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const [api, web, out, browserModule, executablePath, mode = 'enabled'] = process.argv.slice(2);
const { chromium } = require(browserModule);
const A = 'LIVE-DEMO-A', B = 'LIVE-DEMO-B';
const names = ['measured_oil_temperature','top_oil_temperature','hot_spot_temperature','top_oil_rise','winding_hot_spot_gradient','total_loss','ageing_acceleration_factor','equivalent_ageing_hours','fem_hot_spot_temperature','hot_spot_difference'];
const units = ['°C','°C','°C','K','K','W','1','h','°C','K'];
const oldTitles = ['Oil-leak detection','Pressure monitoring','Electrical-fault monitoring','Thermal capacity','Overload capacity','Predictive maintenance'];

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true, args: ['--disable-gpu','--disable-features=CDPScreenshotNewSurface'] });
  const report = { mode, samples: [], checks: [], layouts: [], requests: [], page_errors: [] };
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1100}});
    page.setDefaultTimeout(20000);
    page.on('pageerror', e => report.page_errors.push(e.message));
    const failed = [];
    page.on('requestfailed', r => {if(r.url().includes('/api/v1/demo/')) failed.push(r.url());});
    page.on('response', r => {if(r.url().includes('/api/v1/demo/')) report.requests.push({url:r.url(),status:r.status()});});
    await page.goto(web);
    assert.equal(report.requests.length,0);
    const firstResponse = page.waitForResponse(r=>r.url().endsWith(`/demo/transformers/${A}/physics`));
    await page.getByRole('button',{name:`Monitor ${A}`,exact:true}).click();
    await page.getByRole('heading',{name:'Transformer monitoring',level:1,exact:true}).waitFor();
    const grid=page.getByRole('region',{name:'Transformer monitoring features'});
    const all=grid.locator(':scope > article'), cards=grid.locator('[data-physics-component]');
    assert.equal(await all.count(),16);assert.equal(await cards.count(),10);
    assert.deepEqual((await all.locator('h3').allTextContents()).slice(0,6),oldTitles);
    const originalSix=await all.evaluateAll(nodes=>nodes.slice(0,6).map(n=>n.innerText));
    async function unavailable() {
      await page.waitForFunction(()=>[...document.querySelectorAll('[data-physics-component] .feature-value')].length===10 && [...document.querySelectorAll('[data-physics-component] .feature-value')].every(n=>n.textContent==='Unavailable'));
    }
    async function numeric(asset, body) {
      await page.waitForFunction(({asset,sequence})=>[...document.querySelectorAll('[data-physics-component]')].every(n=>n.dataset.asset===asset && (!sequence || n.dataset.sequence===String(sequence)) && n.querySelector('.feature-value').textContent!=='Unavailable'),{asset,sequence:body?.sequence});
      const values=await cards.locator('.feature-value').allTextContents();
      assert.equal(values.length,10);
      values.forEach((v,i)=>{assert.match(v,/\d/);assert.ok(v.endsWith(` ${units[i]}`));});
      if(body) {
        const rendered=await cards.evaluateAll(nodes=>nodes.map(n=>({key:n.dataset.physicsComponent,status:n.querySelector('.console-badge').textContent,times:[...n.querySelectorAll('time')].map(t=>t.dateTime),value:n.querySelector('.feature-value').textContent,text:n.innerText})));
        rendered.forEach((c,i)=>{
          assert.equal(c.key,names[i]);assert.equal(c.status,body.components[c.key].status);
          assert.equal(c.value,`${new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(body.components[c.key].value)} ${units[i]}`);
          assert.equal(c.times[0],body.timestamp);assert.equal(c.times[1],body.evaluated_at);
          assert.ok(Date.now()-Date.parse(c.times[2])<10000);assert.ok(c.text.includes('LIVE SIMULATION'));assert.ok(c.text.includes('SYNTHETIC'));
        });
        assert.ok(rendered[0].text.includes('SIMULATED SENSOR'));assert.ok(!rendered[0].text.includes('MEASURED'));
        report.samples.push({response:body,rendered});
      }
      return values;
    }
    const first=await (await firstResponse).json();
    if(mode==='disabled') {
      await unavailable();
      await grid.getByRole('button',{name:'Retry physics'}).waitFor();
      assert.ok((await cards.first().innerText()).includes('disabled'));
      assert.equal(await all.count(),16);
      report.checks.push('Actual disabled backend returns 404; all ten cards unavailable beside unchanged six');
      report.success=true;
      return;
    }
    await numeric(A,first);
    let next;
    do {next=await (await page.waitForResponse(r=>r.url().endsWith(`/demo/transformers/${A}/physics`) && r.status()===200)).json();} while(next.sequence<=first.sequence);
    await numeric(A,next);
    assert.notEqual(next.timestamp,first.timestamp);
    for(const key of names.filter(k=>k!=='hot_spot_difference')) assert.notEqual(next.components[key].value,first.components[key].value,key);
    report.checks.push('All sixteen cards share one grid; ten numeric readings match two successive live HTTP events, statuses and times');
    async function layout(width,columns,file) {
      await page.setViewportSize({width,height:1100});
      const geometry=await grid.evaluate(el=>({columns:getComputedStyle(el).gridTemplateColumns.split(' ').length,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth}));
      assert.equal(geometry.columns,columns);assert.ok(geometry.overflow<=1,JSON.stringify(geometry));
      report.layouts.push({width,...geometry});
      if(file) await page.screenshot({path:path.join(out,file),fullPage:true});
    }
    await layout(1440,3,'dashboard-desktop.png');
    await layout(900,2,null);
    await layout(390,1,'dashboard-mobile.png');
    for(const summary of await cards.locator('summary').all()){await summary.click();assert.ok(await summary.evaluate(n=>n.parentElement.open));}
    await layout(390,1,null);
    for(const summary of await cards.locator('summary').all()) await summary.click();
    await page.setViewportSize({width:1440,height:1100});
    report.checks.push('Desktop/tablet/mobile: 3/2/1 columns, no horizontal overflow, all ten details controls work');
    const pattern='**/api/v1/demo/transformers/*/physics';
    await page.route(pattern,route=>route.abort('failed'));
    await page.getByRole('button',{name:'Refresh',exact:true}).click();
    await grid.getByRole('button',{name:'Retry physics'}).waitFor();await unavailable();
    await page.unroute(pattern);await grid.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Actual request network failure clears every physics card; Retry recovers from live API');
    await page.route(pattern,async route=>{const r=await route.fetch({url:`${api}/api/v1/demo/transformers/MISSING/physics`});await route.fulfill({response:r});});
    await page.getByRole('button',{name:'Refresh',exact:true}).click();await grid.getByRole('button',{name:'Retry physics'}).waitFor();await unavailable();
    await page.unroute(pattern);await grid.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Actual missing-result 404 has unavailable cards and working retry');
    await page.route(pattern,async route=>{const r=await route.fetch();const body=await r.json();delete body.components.total_loss;await route.fulfill({response:r,json:body});});
    await page.getByRole('button',{name:'Refresh',exact:true}).click();await grid.getByRole('button',{name:'Retry physics'}).waitFor();await unavailable();
    assert.ok((await cards.first().innerText()).includes('expected contract'));
    await page.unroute(pattern);await grid.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Deliberately malformed live payload is rejected, without fixture or stale fallback');
    let release,seenResolve;const gate=new Promise(r=>release=r),seen=new Promise(r=>seenResolve=r);
    await page.route(pattern,async route=>{if(route.request().url().endsWith(`/${A}/physics`)){const r=await route.fetch();seenResolve();await gate;try{await route.fulfill({response:r});}catch{}}else await route.continue();});
    await page.getByRole('button',{name:'Refresh',exact:true}).click();await seen;await unavailable();
    await page.getByRole('combobox',{name:'Asset',exact:true}).selectOption(B);await numeric(B);release();await page.waitForTimeout(200);
    assert.ok(failed.some(u=>u.endsWith(`/${A}/physics`)));
    assert.ok((await cards.evaluateAll(ns=>ns.map(n=>n.dataset.asset))).every(id=>id===B));
    await page.unroute(pattern);report.checks.push('Refresh clears cards; asset change aborts old request and ignores its late response');
    await page.getByRole('button',{name:'System / source health',exact:true}).click();await page.waitForTimeout(300);
    const count=report.requests.length;await page.waitForTimeout(4500);assert.equal(report.requests.length,count);
    await page.getByRole('button',{name:'Transformer monitoring',exact:true}).click();await numeric(B);
    await page.route(pattern,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(first)}));
    await page.getByRole('combobox',{name:'Asset',exact:true}).selectOption(A);await grid.getByRole('button',{name:'Retry physics'}).waitFor();await unavailable();
    assert.ok((await cards.first().innerText()).includes('Older simulation event'));
    await page.unroute(pattern);await grid.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Leaving monitoring stops polling; returning resumes it and retains per-asset event ordering');
    assert.deepEqual(await all.evaluateAll(nodes=>nodes.slice(0,6).map(n=>n.innerText)),originalSix);
    fs.writeFileSync(path.join(out,'stop-producer'),'Stop only owned verification producer');
    await page.waitForTimeout(19000);await unavailable();
    assert.ok((await cards.first().innerText()).includes('stale') || (await cards.first().innerText()).includes('STALE'));
    report.checks.push('Stopped producer expires numeric cards; original six unchanged throughout');
    assert.deepEqual(report.page_errors,[]);report.success=true;
  } finally {
    fs.writeFileSync(path.join(out,mode==='disabled'?'browser-disabled.json':'browser.json'),JSON.stringify(report,null,2));
    await browser.close();
  }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
