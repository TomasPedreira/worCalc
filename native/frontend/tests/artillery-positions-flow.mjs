/* Verify battery references in the native WebView with isolated app storage. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {createServer} from 'node:net';
import {mkdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.WORCALC_PLAYWRIGHT_PATH || 'playwright');
const output = resolve('artifacts/validation/artillery-positions');
const variant = process.argv[2] || 'calculator';
await mkdir(output, {recursive:true});
const server = createServer();
await new Promise(done => server.listen(0, '127.0.0.1', done));
const port = server.address().port;
await new Promise(done => server.close(done));
const executable = resolve('target/debug/worcalc-app.exe');
const child = spawn(executable, [], {cwd:dirname(executable), windowsHide:true, env:{...process.env,
  WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`,
  WEBVIEW2_USER_DATA_FOLDER:resolve(output, `webview-${Date.now()}`)}});
let browser;
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    try {if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break;} catch {}
    if (child.exitCode != null) throw Error('Native application exited before its WebView was ready');
    await new Promise(done => setTimeout(done, 200));
  }
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  const page = browser.contexts()[0].pages()[0];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.waitForFunction(() => document.querySelector('#workspace')?.inert === false &&
    !document.querySelector('#map-wrap').classList.contains('map-loading'));
  assert.equal(await page.evaluate(() => __TAURI_INTERNALS__.invoke('plugin:app|identifier')),
    'pt.tomaspedreira.worcalc.flowtest', 'Use isolated workflow storage only');
  assert.equal(await page.locator('body').getAttribute('data-app-variant'),variant);
  async function openMapLibrary() {
    if (await page.locator('#open-drawer').isVisible() && !await page.locator('#drawer.open').count()) {
      await page.locator('#open-drawer').click();
    }
  }
  async function selectMap(name) {
    await openMapLibrary();
    await page.locator('#map-search').fill(name);
    await page.locator('.map-card').filter({has:page.getByText(name, {exact:true})}).click();
    await page.waitForFunction(name => document.querySelector('#map-name').textContent === name &&
      !document.querySelector('#map-wrap').classList.contains('map-loading'), name);
  }
  async function checkLabels() {
    const labels = await page.evaluate(() => Array.from(document.querySelectorAll('.artillery-position-label'), label => ({
      text:label.textContent,background:getComputedStyle(label).backgroundColor,height:label.getBoundingClientRect().height,
    })));
    assert.ok(labels.length > 0);
    for (const label of labels) {
      assert.doesNotMatch(label.text, /Artillery base|Artillery staging|CSA|USA/);
      assert.equal(label.background, 'rgba(0, 0, 0, 0)');
      assert.ok(label.height > 0 && label.height <= 12);
    }
  }
  async function labelOffsets() {
    return page.locator('.artillery-position-label').evaluateAll(labels => labels.map(label => {
      const box = label.getBoundingClientRect(), anchor = label.parentElement.getBoundingClientRect();
      return {name:label.textContent,x:Math.round((box.left-anchor.left)*100)/100,
        y:Math.round((box.top-anchor.top)*100)/100,width:Math.round(box.width*100)/100,hidden:label.hidden};
    }));
  }
  async function checkStaticPlacement() {
    const initial = await labelOffsets();
    const map = await page.locator('#map-wrap').boundingBox();
    const imageBefore = await page.locator('#map-image').boundingBox();
    await page.locator('#map-wrap').dispatchEvent('wheel', {clientX:map.x+map.width*.9,clientY:map.y+map.height*.5,deltaY:-650});
    assert.ok((await page.locator('#map-image').boundingBox()).width > imageBefore.width*2, 'The test must zoom the map');
    assert.deepEqual(await labelOffsets(), initial, 'Zoom must not reflow names');
    await page.locator('#map-wrap').dispatchEvent('wheel', {clientX:map.x+20,clientY:map.y+20,deltaY:-400});
    assert.deepEqual(await labelOffsets(), initial, 'Names must stay anchored near viewport edges');
    await page.mouse.move(map.x+map.width/2,map.y+map.height/2);
    await page.mouse.down();
    await page.mouse.move(map.x+map.width/2+120,map.y+map.height/2+80,{steps:5});
    await page.mouse.up();
    assert.deepEqual(await labelOffsets(), initial, 'Pan must not reflow or hide names');
    await page.setViewportSize({width:440,height:850});
    assert.deepEqual(await labelOffsets(), initial, 'Phone width must keep the same label placement');
    await page.setViewportSize({width:1280,height:850});
    await page.locator('#map-wrap').dispatchEvent('keydown', {key:'f',bubbles:true});
    assert.deepEqual(await labelOffsets(), initial, 'Fit must restore the same placement');
  }
  for (const [map, battery] of [['Confederate Encampment','Battery French'], ['Wagon Road','Battery Lane'], ["Hooker's Push",'Battery Matthews']]) {
    await selectMap(map);
    await page.locator('.artillery-position-label').filter({hasText:battery}).waitFor();
    await checkLabels();
  }
  await page.screenshot({path:resolve(output, 'crowded-batteries.png')});
  await selectMap('Pry Ford');
  await page.locator('.artillery-position-label').filter({hasText:'Battery Daquin'}).waitFor();
  await checkLabels();
  await checkStaticPlacement();
  await page.locator('#map-wrap').screenshot({path:resolve(output, 'pry-ford-compact.png')});
  await selectMap('River Crossing');
  await page.locator('.artillery-position-label').filter({hasText:'Battery Manly'}).waitFor();
  assert.equal(await page.locator('.artillery-position-label').filter({hasText:'Battery Manly'}).count(), 1);
  await checkLabels();
  await selectMap('Confederate Encampment');
  await page.locator('.artillery-position-label').filter({hasText:'Battery French'}).waitFor();
  const labels = await page.locator('.artillery-position-label').allTextContents();
  assert.ok(labels.includes('Battery French'));
  assert.ok(labels.includes('Battery Matthews'));
  await page.screenshot({path:resolve(output, 'calculator.png')});
  await openMapLibrary();
  await page.locator('#artillery-names').uncheck();
  assert.equal(await page.locator('.artillery-position-label').count(), 0);
  await page.locator('#artillery-names').check();
  assert.deepEqual(await page.locator('.artillery-position-label').allTextContents(), labels);
  if (variant === 'calculator') await page.locator('#drawer .close').click();
  if (variant === 'sketcher') assert.equal(await page.locator('.location-anchor:not([hidden]) .gun_spawn').count(), 0);
  await page.screenshot({path:resolve(output, 'sketcher.png')});
  await checkLabels();
  await page.setViewportSize({width:900,height:850});
  await checkLabels();
  await page.screenshot({path:resolve(output, 'sketcher-compact.png')});
  await page.setViewportSize({width:1280,height:850});
  await openMapLibrary();
  await page.locator('#artillery-names').uncheck();
  if (variant === 'sketcher') assert.equal(await page.locator('.location-anchor:not([hidden])').count(), 0);
  await page.locator('#artillery-names').check();
  await selectMap('East Woods');
  await page.waitForFunction(() => !document.querySelector('.artillery-position-label'));
  assert.equal(await page.locator('.artillery-position-label').count(), 0);
  assert.deepEqual(errors, []);
  console.log(`Native ${variant} artillery references passed: fixed labels through zoom, pan, edges, phone width, fit, toggle and map changes.`);
} finally {
  if (browser) await browser.close();
  if (child.exitCode == null) child.kill();
}
