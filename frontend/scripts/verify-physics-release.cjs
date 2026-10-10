/* Actual-backend browser verification; invoked by the disposable DB helper.
 * Fault/delay checks intercept transport only and preserve actual response bodies.
 * No synthetic READY fixture, profile, telemetry or parameter is installed. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const [api, port, mode, out, browserModule, executablePath] = process.argv.slice(2);
const { chromium } = require(browserModule);
const root = path.resolve(__dirname, '..');
const A = 'PHASE7-EMPTY-A', B = 'PHASE7-EMPTY-B';

(async () => {
  process.env.VITE_API_BASE_URL = api;
  const { createServer } = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')).href);
  const server = await createServer({ root, configFile: path.join(root, 'vite.config.ts'),
    server: { host: '127.0.0.1', port: Number(port), strictPort: true }, logLevel: 'error' });
  let browser, page;
  const network = [], errors = [];
  try {
    await server.listen();
    browser = await chromium.launch({ executablePath, headless: true,
      args: ['--disable-gpu', '--disable-features=CDPScreenshotNewSurface'] });
    page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    page.setDefaultTimeout(15000);
    const responses = [], failed = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', r => { if (r.url().includes('/api/v1/')) network.push({ url: r.url(), status: r.status() }); });
    page.on('response', r => { if (r.url().endsWith('/physics')) responses.push({ url: r.url(), status: r.status() }); });
    page.on('requestfailed', r => {
      const item = { url: r.url(), error: r.failure()?.errorText };
      if (r.url().includes('/api/v1/')) network.push(item);
      if (r.url().endsWith('/physics')) failed.push(item);
    });
    page.on('console', msg => { if (msg.type() === 'error') network.push({ console: msg.text() }); });
    await page.goto(`http://127.0.0.1:${port}`);
    await page.getByRole('button', { name: `Monitor ${A}`, exact: true }).click();
    assert.equal(responses.length, 0);
    await page.getByRole('button', { name: 'Thermal & loading', exact: true }).click();
    const panel = page.getByRole('region', { name: 'Physics results' });
    const table = panel.getByRole('table');
    await table.waitFor();
    async function unavailable() {
      await table.waitFor();
      assert.equal(await table.locator('tbody tr').count(), 10);
      assert.deepEqual(await table.locator('tbody tr td:nth-child(2)').allTextContents(),
        ['UnavailableUnit: °C', 'UnavailableUnit: °C', 'UnavailableUnit: °C', 'UnavailableUnit: K',
         'UnavailableUnit: K', 'UnavailableUnit: W', 'UnavailableUnit: 1', 'UnavailableUnit: h',
         'UnavailableUnit: °C', 'UnavailableUnit: K']);
    }
    await unavailable();
    const expected = mode === 'disabled' ? 'Physics integration is disabled' : 'No retained physics result';
    assert.ok((await panel.innerText()).includes(expected));
    const initialCount = responses.length;
    await Promise.all([
      page.waitForResponse(r => r.url().endsWith(`/${A}/physics`) && r.status() === 200),
      page.getByRole('button', { name: 'Refresh', exact: true }).click(),
    ]);
    await unavailable();
    assert.equal(responses.length, initialCount + 1);
    for (const summary of await panel.locator('summary').all()) {
      await summary.evaluate(el => el.click());
      assert.equal(await summary.evaluate(el => el.parentElement.open), true);
      await summary.evaluate(el => el.click());
      assert.equal(await summary.evaluate(el => el.parentElement.open), false);
    }
    await panel.screenshot({ path: path.join(out, `${mode}-unavailable.png`) });
    const physicsPattern = '**/api/v1/transformers/*/physics';
    // A real 404 body from the actual backend, with no invented error response.
    await page.route(physicsPattern, async route => {
      const response = await route.fetch({ url: `${api}/api/v1/transformers/MISSING/physics` });
      await route.fulfill({ response });
    });
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await panel.getByRole('button', { name: 'Retry physics' }).waitFor();
    assert.equal(await table.count(), 0);
    await page.unroute(physicsPattern);
    await panel.getByRole('button', { name: 'Retry physics' }).click();
    await unavailable();
    // Real B response delivered to A transport: strict selected-asset validation.
    await page.route(physicsPattern, async route => {
      const response = await route.fetch({ url: `${api}/api/v1/transformers/${B}/physics` });
      await route.fulfill({ response });
    });
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await panel.getByRole('button', { name: 'Retry physics' }).waitFor();
    assert.equal(await table.count(), 0);
    assert.ok((await panel.innerText()).includes('mismatch'));
    await page.unroute(physicsPattern);
    await panel.getByRole('button', { name: 'Retry physics' }).click();
    await unavailable();
    let release, observed;
    const gate = new Promise(resolve => { release = resolve; });
    const seen = new Promise(resolve => { observed = resolve; });
    await page.route(physicsPattern, async route => {
      if (route.request().url().endsWith(`/${A}/physics`)) {
        const response = await route.fetch();
        observed(); await gate;
        try { await route.fulfill({ response }); } catch { /* Request was intentionally cancelled. */ }
      } else await route.continue();
    });
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await seen;
    assert.equal(await table.count(), 0); // Loading removes prior values immediately.
    await page.getByRole('combobox', { name: 'Asset', exact: true }).selectOption(B);
    await unavailable();
    const identity = panel.locator('details').last();
    await identity.locator('summary').click();
    assert.ok((await identity.innerText()).includes(`Asset ${B}`));
    release();
    await page.waitForTimeout(300);
    assert.ok((await identity.innerText()).includes(`Asset ${B}`));
    assert.ok(!(await identity.innerText()).includes(`Asset ${A}`));
    assert.ok(failed.some(r => r.url.endsWith(`/${A}/physics`)), 'Superseded A request abort observed');
    await page.unroute(physicsPattern);
    const settled = responses.length;
    await page.waitForTimeout(1200);
    assert.equal(responses.length, settled, 'No recurring physics timer');
    for (const label of ['Transformer monitoring', 'Live alarms / events', 'Predictive maintenance', 'System / source health', 'Overview']) {
      await page.getByRole('button', { name: label, exact: true }).click();
      assert.equal(await panel.count(), 0);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: `Monitor ${B}`, exact: true }).click();
    await page.getByRole('button', { name: 'Toggle navigation' }).click();
    await page.getByRole('button', { name: 'Thermal & loading', exact: true }).click();
    await unavailable();
    await page.waitForTimeout(350);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await panel.screenshot({ path: path.join(out, `${mode}-mobile.png`) });
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out, `browser-${mode}.json`), JSON.stringify({
      mode, status: 'PASS', actualUnavailable200: true, componentRows: 10,
      refresh: true, disclosures: 11, actual404TransportTest: true, retry: true,
      actualCrossAssetBodyRejected: true, assetCancellation: true,
      loadingHidesOldResult: true, navigation: true, noPhysicsPolling: true,
      mobileNoHorizontalOverflow: true, equipmentReadyResult: false, errors, responses, failed,
    }, null, 2));
    console.log(`Browser ${mode}: PASS (actual unavailable responses; no equipment READY result)`);
  } catch (error) {
    if (page) {
      fs.writeFileSync(path.join(out, `browser-${mode}-failure.json`), JSON.stringify({
        message: error.message, errors, network, pageText: await page.locator('body').innerText(),
      }, null, 2));
      await page.screenshot({ path: path.join(out, `${mode}-failure.png`) }).catch(() => {});
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    await server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
