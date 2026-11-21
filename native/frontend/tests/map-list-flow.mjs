/* Map entry borders in the native WebView at phone and landscape sizes. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {createServer} from 'node:net';
import {mkdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';

const {chromium} = createRequire(import.meta.url)(process.env.WORCALC_PLAYWRIGHT_PATH || 'playwright');
const output = resolve('artifacts/validation/map-list');
await mkdir(output,{recursive:true});
const server = createServer();
await new Promise(done => server.listen(0,'127.0.0.1',done));
const port = server.address().port;
await new Promise(done => server.close(done));
const executable = resolve('target/debug/worcalc-app.exe');
const child = spawn(executable,[],{cwd:dirname(executable),windowsHide:true,env:{...process.env,
  WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`,
  WEBVIEW2_USER_DATA_FOLDER:resolve(output,`webview-${Date.now()}`)}});
let browser;
try {
  for (let attempt=0;attempt<100;attempt++) {
    try {if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break;} catch {}
    if (child.exitCode != null) throw Error('Native application exited before its WebView was ready');
    await new Promise(done => setTimeout(done,200));
  }
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  const page = browser.contexts()[0].pages()[0];
  const errors = [];
  page.on('pageerror',error => errors.push(error.message));
  await page.waitForFunction(() => !document.querySelector('#workspace').inert &&
    !document.querySelector('#map-wrap').classList.contains('map-loading'));
  assert.equal(await page.evaluate(() => __TAURI_INTERNALS__.invoke('plugin:app|identifier')),
    'pt.tomaspedreira.worcalc.flowtest','Use isolated workflow storage only');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#open-drawer').click();
  await page.locator('#map-search').fill('Pry Ford');
  await page.locator('.map-card').filter({has:page.getByText('Pry Ford',{exact:true})}).click();
  await page.waitForFunction(() => document.querySelector('#map-name').textContent === 'Pry Ford' &&
    !document.querySelector('#map-wrap').classList.contains('map-loading'));
  await page.locator('#open-drawer').click();
  await page.locator('#map-search').fill('pry');
  for (const {width,height} of [{width:320,height:740},{width:390,height:844},{width:480,height:900},{width:844,height:390}]) {
    await page.setViewportSize({width,height});
    await page.mouse.move(width-1,height-1);
    const entries = await page.locator('.map-card:visible').evaluateAll(cards => cards.map(card => {
      const style = getComputedStyle(card),box = card.getBoundingClientRect();
      return {name:card.querySelector('b').textContent,active:card.classList.contains('active'),
        color:style.borderTopColor,borderStyle:style.borderTopStyle,borderWidth:parseFloat(style.borderTopWidth),
        left:box.left,right:box.right};
    }));
    assert.ok(entries.length > 1,'Search must include selected and unselected maps');
    for (const entry of entries) {
      assert.ok(entry.borderWidth >= 1 && entry.borderStyle === 'solid',`${entry.name}: visible border at ${width}px`);
      assert.doesNotMatch(entry.color,/transparent|rgba\([^)]*,\s*0\)/,`${entry.name}: border must remain visible without hover`);
      assert.ok(entry.left >= 0 && entry.right <= width,`${entry.name}: border must fit in the phone viewport`);
    }
    const active = entries.filter(entry => entry.active);
    assert.equal(active.length,1);
    assert.equal(active[0].name,'Pry Ford');
    assert.notEqual(active[0].color,entries.find(entry => !entry.active).color,'Selection must retain its distinct border');
    if (width === 390) await page.screenshot({path:resolve(output,'mobile-map-borders.png')});
  }
  await page.locator('#map-search').fill('East Woods');
  assert.ok(await page.locator('.map-card:visible').count() > 0,'Search remains usable');
  assert.equal(await page.locator('.map-card.active:visible').count(),0,'Filtering does not mark an unrelated map as selected');
  assert.deepEqual(errors,[]);
  console.log('PASS native mobile map list: visible borders without hover, selected border, search, portrait and landscape.');
} finally {if (browser) await browser.close();if (child.exitCode == null) child.kill();}
