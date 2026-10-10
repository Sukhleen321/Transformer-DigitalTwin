/* Real live HTTP and rendered UI. Fault checks reuse real backend bodies. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const [api, web, out, browserModule, executablePath] = process.argv.slice(2);
const { chromium } = require(browserModule);
const A = 'LIVE-DEMO-A', B = 'LIVE-DEMO-B';
const names = ['measured_oil_temperature','top_oil_temperature','hot_spot_temperature','top_oil_rise',
  'winding_hot_spot_gradient','total_loss','ageing_acceleration_factor','equivalent_ageing_hours','fem_hot_spot_temperature','hot_spot_difference'];
const units = ['°C','°C','°C','K','K','W','1','h','°C','K'];
(async () => {
  const browser = await chromium.launch({ executablePath, headless: true, args: ['--disable-gpu','--disable-features=CDPScreenshotNewSurface'] });
  const report = { real_response_samples: [], checks: [], network: [], page_errors: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    page.setDefaultTimeout(20000);
    const responses = [], failures = [];
    page.on('response', r => { if (r.url().includes('/api/v1/demo/') && r.url().endsWith('/physics')) { responses.push(r); report.network.push({url:r.url(),status:r.status()}); } });
    page.on('requestfailed', r => { if (r.url().includes('/api/v1/demo/')) failures.push(r.url()); });
    page.on('pageerror', e => report.page_errors.push(e.message));
    await page.goto(web);
    assert.equal(responses.length,0,'No demo reads on overview');
    await page.getByRole('button', {name:`Monitor ${A}`,exact:true}).click();
    const incoming = page.waitForResponse(r => r.url().endsWith(`/demo/transformers/${A}/physics`) && r.status() === 200);
    await page.getByRole('button',{name:'Thermal & loading',exact:true}).click();
    const panel = page.getByRole('region',{name:'Physics results'});
    const table = panel.getByRole('table');
    const first = await (await incoming).json();
    async function numeric(asset) {
      await table.waitFor();
      assert.equal(await table.locator('tbody tr').count(),10);
      const cells = await table.locator('tbody tr td:nth-child(2)').allTextContents();
      cells.forEach((text,i) => {assert.match(text,/\d/);assert.ok(text.endsWith(` ${units[i]}`),text);assert.ok(!text.includes('Unavailable'));});
      assert.ok((await panel.innerText()).includes(`Asset ${asset}`));
      assert.ok((await panel.innerText()).includes('LIVE SIMULATION'));
      assert.ok((await panel.innerText()).includes('Latest update'));
      assert.ok((await panel.innerText()).includes('Event'));
      assert.equal(await panel.locator('tbody tr small').filter({hasText:'SYNTHETIC_SIMULATED'}).count(),10);
      return cells;
    }
    const cells1 = await numeric(A);
    const format = v => new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(v);
    names.forEach((name,i) => assert.equal(cells1[i],`${format(first.components[name].value)} ${units[i]}`));
    report.real_response_samples.push(first);
    await panel.screenshot({path:path.join(out,'live-numeric-first.png')});
    let second;
    const deadline = Date.now()+16000;
    while (Date.now()<deadline) {
      const r = await page.waitForResponse(r=>r.url().endsWith(`/demo/transformers/${A}/physics`) && r.status()===200);
      const body = await r.json();
      if (body.sequence > first.sequence) { second=body; break; }
    }
    assert.ok(second,'New real simulation event received by browser');
    await page.waitForFunction(seq => document.querySelector('[aria-label="Physics results"]')?.textContent.includes(`Sequence ${seq}`),second.sequence);
    const cells2 = await numeric(A);
    names.forEach((name,i) => assert.equal(cells2[i],`${format(second.components[name].value)} ${units[i]}`));
    assert.notEqual(first.timestamp,second.timestamp);
    assert.notEqual(first.components.hot_spot_temperature.value,second.components.hot_spot_temperature.value);
    assert.notDeepEqual(cells1,cells2);
    report.real_response_samples.push(second);
    report.dashboard_values = cells2;
    await panel.screenshot({path:path.join(out,'live-numeric-second.png')});
    report.checks.push('Ten units/numbers match actual API; live poll changes event and values without reload');
    for (const summary of await panel.locator('summary').all()) {
      await summary.click();assert.ok(await summary.evaluate(el=>el.parentElement.open));await summary.click();
    }
    report.checks.push('All ten evidence controls open/close');
    const pattern='**/api/v1/demo/transformers/*/physics';
    await page.route(pattern,async route=>{const r=await route.fetch({url:`${api}/api/v1/demo/transformers/MISSING/physics`});await route.fulfill({response:r});});
    await page.getByRole('button',{name:'Refresh',exact:true}).click();
    await panel.getByRole('button',{name:'Retry physics'}).waitFor();assert.equal(await table.count(),0);
    await page.unroute(pattern);await panel.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Real backend 404 withholds values; Retry returns real live result');
    await page.route(pattern,async route=>{const r=await route.fetch({url:`${api}/api/v1/demo/transformers/${B}/physics`});await route.fulfill({response:r});});
    await page.getByRole('button',{name:'Refresh',exact:true}).click();
    await panel.getByRole('button',{name:'Retry physics'}).waitFor();assert.ok((await panel.innerText()).includes('mismatch'));assert.equal(await table.count(),0);
    await page.unroute(pattern);await panel.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Actual other-asset response rejected');
    await page.route(pattern,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(first)}));
    await page.getByRole('button',{name:'Refresh',exact:true}).click();
    await panel.getByRole('button',{name:'Retry physics'}).waitFor();assert.ok((await panel.innerText()).includes('Older simulation event'));assert.equal(await table.count(),0);
    await page.unroute(pattern);await panel.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Earlier real event replay rejected; no stale numeric fallback');
    let release, observed;
    const gate=new Promise(r=>release=r), seen=new Promise(r=>observed=r);
    await page.route(pattern,async route=>{
      if(route.request().url().endsWith(`/${A}/physics`)){const r=await route.fetch();observed();await gate;try{await route.fulfill({response:r});}catch{}}
      else await route.continue();
    });
    await page.getByRole('button',{name:'Refresh',exact:true}).click();await seen;
    assert.equal(await table.count(),0,'Pending manual refresh removes values');
    await page.getByRole('combobox',{name:'Asset',exact:true}).selectOption(B);await numeric(B);
    release();await page.waitForTimeout(300);
    assert.ok((await panel.innerText()).includes(`Asset ${B}`));assert.ok(!(await panel.innerText()).includes(`Asset ${A}`));
    assert.ok(failures.some(url=>url.endsWith(`/${A}/physics`)),'Cancelled A request observed');
    await page.unroute(pattern);
    report.checks.push('Loading clears values; asset switch aborts in-flight request and ignores old completion');
    await page.getByRole('button',{name:'System / source health',exact:true}).click();
    await page.waitForTimeout(300);const count=responses.length;await page.waitForTimeout(4500);
    assert.equal(responses.length,count,'Demo polling stops on leaving thermal view');assert.equal(await panel.count(),0);
    await page.getByRole('button',{name:'Thermal & loading',exact:true}).click();await numeric(B);
    report.checks.push('Navigation stops and resumes demo polling');
    await page.route(pattern,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(first)}));
    await page.getByRole('combobox',{name:'Asset',exact:true}).selectOption(A);
    await panel.getByRole('button',{name:'Retry physics'}).waitFor();assert.ok((await panel.innerText()).includes('Older simulation event'));assert.equal(await table.count(),0);
    await page.unroute(pattern);await panel.getByRole('button',{name:'Retry physics'}).click();await numeric(A);
    report.checks.push('Returning to a previous asset retains its watermark and rejects an older real event');
    fs.writeFileSync(path.join(out,'stop-producer'),'Owned verification stop');
    await page.waitForTimeout(19000);
    await table.waitFor();
    const cells = await table.locator('tbody tr td:nth-child(2)').allTextContents();
    assert.ok(cells.every(t=>t.startsWith('Unavailable')));
    assert.ok((await panel.innerText()).includes('stale'));
    const stale=await page.request.get(`${api}/api/v1/demo/transformers/${B}/physics`);
    assert.equal(stale.status(),200);assert.equal((await stale.json()).status,'UNAVAILABLE');
    report.checks.push('Stopped producer: actual stale API and rendered UI withhold all ten values');
    assert.deepEqual(report.page_errors,[]);
    report.success=true;
  } finally {
    fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
    await browser.close();
  }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
