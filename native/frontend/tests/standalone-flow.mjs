/* Native app isolation and launch behavior, using the dedicated flow-test ID. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {createServer} from 'node:net';
import {mkdir,readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
const {chromium} = createRequire(import.meta.url)(process.env.WORCALC_PLAYWRIGHT_PATH || 'playwright');
const variant = process.argv[2] || 'calculator';
const {version} = JSON.parse(await readFile(resolve('package.json'),'utf8'));
assert.ok(['calculator','sketcher','kill-tracker'].includes(variant));
const output = resolve('artifacts/validation/standalone',variant);
await mkdir(output,{recursive:true});
const server = createServer();await new Promise(done=>server.listen(0,'127.0.0.1',done));
const port = server.address().port;await new Promise(done=>server.close(done));
const executable = resolve('target/debug/worcalc-app.exe');
const child = spawn(executable,[],{cwd:dirname(executable),windowsHide:true,env:{...process.env,
  WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`,
  WEBVIEW2_USER_DATA_FOLDER:resolve(output,`webview-${Date.now()}`)}});
let browser;
try {
  for(let attempt=0;attempt<100;attempt++) {
    try {if((await fetch(`http://127.0.0.1:${port}/json/version`)).ok)break;}catch{}
    if(child.exitCode!=null)throw Error('Native app exited before the WebView was ready');
    await new Promise(done=>setTimeout(done,200));
  }
  browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  const page=browser.contexts()[0].pages()[0],errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.waitForFunction(()=>globalThis.worcalcNative);
  assert.equal(await page.evaluate(()=>__TAURI_INTERNALS__.invoke('plugin:app|identifier')),'pt.tomaspedreira.worcalc.flowtest');
  assert.equal(await page.evaluate(()=>__TAURI_INTERNALS__.invoke('plugin:app|version')),version);
  assert.equal(await page.locator('body').getAttribute('data-app-variant'),variant);
  assert.equal(await page.locator('#app-chooser,#choose-app,#choose-calculator,#choose-sketcher,#choose-kill-tracker').count(),0);
  async function rejects(command,args) {
    assert.equal(await page.evaluate(async({command,args})=>{
      try {await __TAURI_INTERNALS__.invoke(command,args);return false;}catch{return true;}
    },{command,args}),true,`${variant} must not expose ${command}`);
  }
  if(variant==='kill-tracker') {
    await page.waitForSelector('#kill-start');
    assert.equal(await page.locator('#map-image,#sketch-panel').count(),0);
    assert.equal(await page.locator('#kill-authorize').isChecked(),false);
    assert.equal(await page.evaluate(async()=> (await worcalcNative.killTracker.poll()).running),false);
    await page.locator('#kill-start').click();
    await page.waitForFunction(()=>document.querySelector('#kill-status').textContent.includes('Authorize'));
    await rejects('native_request',{operation:'maps',data:null});
    await rejects('native_resource',{path:'maps/map-1.webp'});
    await rejects('native_sketch',{operation:'load',data:null});
  } else {
    await page.waitForFunction(()=>!document.querySelector('#workspace').inert && !document.querySelector('#map-wrap').classList.contains('map-loading'));
    assert.equal(await page.locator('#kill-start').count(),0);
    await rejects('native_kill_tracker',{operation:'poll',authorized:false});
    assert.equal(await page.evaluate(async()=> (await worcalcNative.api.maps()).length),99);
    if(variant==='calculator') {
      assert.equal(await page.locator('#sketch-panel,#sketch-edit').count(),0);
      await rejects('native_sketch',{operation:'load',data:null});
      await page.setViewportSize({width:1280,height:850});
      await page.locator('#mobile-fit').click();
      const image=page.locator('#map-image'),box=await image.boundingBox();
      const size=await image.evaluate(image=>({width:image.naturalWidth,height:image.naturalHeight}));
      const click=(x,y)=>page.mouse.click(box.x+x*box.width/size.width,box.y+y*box.height/size.height);
      await page.evaluate(() => {
        const calculate = worcalcNative.api.calculate;
        globalThis.requests = [];
        worcalcNative.api.calculate = request => { requests.push(request); return calculate(request); };
      });
      await page.locator('#mobile-gun-mode').click();await click(700,800);
      await page.locator('#mobile-target-mode').click();await click(1000,1000);
      const markers = page.locator('.desktop-target .marker');
      const readouts = page.locator('.target-readout');
      const compass = () => page.locator('#aim-overlay .aim-guide').evaluateAll(lines =>
        lines.map(line => Number(line.dataset.bearing)).sort((first, second) => first - second));
      const waitForReadouts = count => page.waitForFunction(count => {
        const cards = [...document.querySelectorAll('.target-readout')];
        return cards.length === count && cards.every(card =>
          !card.hidden && [...card.querySelectorAll('b')].every(value => value.textContent !== '—'));
      }, count);
      await waitForReadouts(1);
      assert.deepEqual(await compass(),[90,105,120,135]);
      await page.keyboard.press('Shift+t');
      assert.equal(await page.locator('#mode-pill').innerText(),'CLICK MAP TO ADD A TARGET');
      await click(1120,680);
      await waitForReadouts(2);
      assert.deepEqual(await compass(),[45,60,75,90,105,120,135]);
      await page.keyboard.press('Shift+t');
      await click(1200,1000);
      await waitForReadouts(3);
      assert.deepEqual(await compass(),[45,60,75,90,105,120,135]);
      const values = await readouts.evaluateAll(cards => cards.map(card => [...card.querySelectorAll('b')].map(value => value.textContent)));
      for (const [elevation, fuze, height] of values) {
        assert.match(elevation,/^-?\d+\.\d+°$/);
        assert.match(fuze,/^\d+\.\d+ s$/);
        assert.match(height,/^[+-]\d+\.\d m$/);
      }
      const boxes = await Promise.all((await readouts.all()).map(card => card.boundingBox()));
      for (const [index, first] of boxes.entries()) {
        for (const second of boxes.slice(index + 1)) {
          assert.ok(first.x + first.width <= second.x || second.x + second.width <= first.x ||
              first.y + first.height <= second.y || second.y + second.height <= first.y);
        }
      }
      await markers.first().click();
      assert.equal(await page.evaluate(() => requests.length),3);
      await page.locator('#quick-burst').click();
      await waitForReadouts(3);
      assert.equal(await page.evaluate(() => requests.slice(3).filter(request => request.airburst_mode).length),3);
      await page.screenshot({path:resolve(output,'windows-multiple-targets.png')});
      const moved = await markers.last().boundingBox();
      const unchanged = await readouts.first().innerText();
      await page.mouse.move(moved.x + moved.width / 2,moved.y + moved.height / 2);
      await page.mouse.down();
      await page.mouse.move(moved.x + moved.width / 2 + 26,moved.y + moved.height / 2 + 18,{steps:4});
      await page.mouse.up();
      await waitForReadouts(3);
      assert.equal(await readouts.first().innerText(),unchanged);
      assert.equal(await page.evaluate(() => requests.length),7);
      await markers.nth(1).click({button:'right'});
      assert.deepEqual(await readouts.evaluateAll(cards => cards.map(card => card.dataset.targetNumber)),['1','3']);
      assert.equal(await page.evaluate(() => requests.length),7);
      await page.keyboard.press('t');
      assert.equal(await page.locator('#mode-pill').innerText(),'CLICK MAP TO PLACE A SINGLE TARGET');
      assert.equal(await markers.count(),2);
      await click(1050,600);
      await waitForReadouts(1);
      assert.deepEqual(await compass(),[45,60,75,90]);
      assert.deepEqual(await readouts.evaluateAll(cards => cards.map(card => card.dataset.targetNumber)),['1']);
      assert.equal(await page.evaluate(() => requests.length),8);
      await page.setViewportSize({width:390,height:844});
      await page.locator('#open-drawer').click();await page.locator('#mobile-advanced').click();await page.locator('#cannon-select').waitFor({state:'visible'});
      await page.screenshot({path:resolve(output,'phone-controls.png')});
      await page.locator('#backdrop').click({position:{x:5,y:5}});
      await page.setViewportSize({width:1280,height:850});
    } else {
      await page.waitForFunction(()=>document.body.classList.contains('sketch-workspace'));
      assert.equal(await page.locator('#sketch-view').getAttribute('aria-pressed'),'true');
      assert.ok(Object.keys(await page.evaluate(async()=> (await worcalcNative.sketchStorage.load()).maps)).length>0);
    }
  }
  await page.screenshot({path:resolve(output,'standalone.png')});
  assert.deepEqual(errors,[]);
  console.log(`PASS standalone ${variant}: direct launch, version ${version} and native command isolation.`);
} finally {if(browser)await browser.close();if(child.exitCode==null)child.kill();}
