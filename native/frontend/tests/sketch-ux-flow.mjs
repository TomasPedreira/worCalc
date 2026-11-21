/* Native WebView smoke test; isolated workflow application storage only. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {createServer} from 'node:net';
import {mkdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
const {chromium}=createRequire(import.meta.url)(process.env.WORCALC_PLAYWRIGHT_PATH || 'playwright');
const output=resolve('artifacts/validation/sketch-ux');await mkdir(output,{recursive:true});
const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const executable=resolve('target/debug/worcalc-app.exe');
const child=spawn(executable,[],{cwd:dirname(executable),windowsHide:true,env:{...process.env,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`,WEBVIEW2_USER_DATA_FOLDER:resolve(output,`webview-${Date.now()}`)}});
let browser;
try {
  for(let i=0;i<100;i++){try{if((await fetch(`http://127.0.0.1:${port}/json/version`)).ok)break;}catch{} await new Promise(r=>setTimeout(r,200));}
  browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);const page=browser.contexts()[0].pages()[0];
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.waitForFunction(()=>!document.querySelector('#workspace').inert);
  assert.equal(await page.evaluate(()=>__TAURI_INTERNALS__.invoke('plugin:app|identifier')),'pt.tomaspedreira.worcalc.flowtest');
  await page.screenshot({path:resolve(output,'home.png')});
  await page.evaluate(async()=>{
    const map=(await worcalcNative.api.maps()).find(m=>m.identifier==='map-1'),options=await worcalcNative.api.options();
    const cannon=options.defaults.cannon,projectile=options.weapons[cannon][0],plan=WorCalcSketch.createPlan(map,[],cannon);
    plan.guns=[{id:'a',x:700,y:800,cannon},{id:'b',x:900,y:700,cannon}];
    const setting={projectile,airburst_mode:false,elevation_degrees:1.8,fuze_seconds:3.1,notes:'Saved card',solution:{map_id:map.identifier,cannon,projectile,airburst_mode:false,calibration_mode:false,elevation_degrees:1.8,fuze_seconds:3.1,bearing_degrees:90,slant_range_yards:300}};
    WorCalcSketch.saveConfiguration(plan,'a',{id:'t',x:1000,y:1000},setting);
    WorCalcSketch.saveConfiguration(plan,'b',plan.targets[0],{...setting,elevation_degrees:2.2});
    await worcalcNative.sketchStorage.save({version:1,maps:{'map-1':plan}});
  });
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#workspace').inert);
  await page.waitForSelector('[data-sketch-target="t"] .marker');
  const before=await page.evaluate(()=>worcalcNative.sketchStorage.load());
  await page.locator('[data-sketch-target="t"] .marker').click();
  assert.equal(await page.locator('#sketch-gun-options button').count(),2);
  await page.locator('#sketch-gun-options button').nth(1).click();
  assert.equal(await page.locator('#sketch-form').isVisible(),false);
  assert.equal(await page.locator('#sketch-view').getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('#sketch-connections .sketch-connection').count(),1);
  assert.equal(await page.locator('#sketch-shared-list button').count(),1);
  assert.match(await page.locator('#sketch-target-list').innerText(),/2.20°/);
  await page.locator('[data-sketch-gun="a"] .marker').click();
  assert.equal(await page.locator('#sketch-target-list button').count(),1);
  assert.equal(await page.locator('#sketch-form').isVisible(),false);
  for(const id of ['sketch-add-gun','sketch-add-target','sketch-import'])assert.equal(await page.locator('#'+id).isVisible(),false);
  await page.keyboard.press('Delete');await page.keyboard.press('g');await page.keyboard.press('t');
  for(const selector of ['[data-sketch-target="t"] .marker','[data-sketch-gun="a"] .marker']) {
    await page.locator(selector).click({trial:true});
    const box=await page.locator(selector).boundingBox(),x=box.x+box.width/2,y=box.y+box.height/2;
    await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+25,y+20,{steps:8});await page.mouse.up();
  }
  assert.deepEqual(await page.evaluate(()=>worcalcNative.sketchStorage.load()),before);
  assert.equal(await page.locator('#sketch-form').isVisible(),false);
  await page.screenshot({path:resolve(output,'view-only.png')});
  await page.locator('#sketch-edit').click();
  await page.locator('[data-sketch-gun="a"] .marker').click();
  assert.equal(await page.locator('#sketch-form').isVisible(),true);
  assert.equal(await page.locator('#sketch-edit-notice').isVisible(),true);
  assert.equal(await page.locator('#sketch-connections .sketch-connection').count(),0);
  for(const width of [1280,900]) {
    await page.setViewportSize({width,height:850});
    const map=await page.locator('#map-wrap').boundingBox(),panel=await page.locator('#sketch-panel').boundingBox();
    assert.ok(map.x+map.width<=panel.x+1);assert.equal(await page.locator('#backdrop').isVisible(),false);
    const scrollbar=await page.locator('#sketch-panel').evaluate(element=>({
      width:getComputedStyle(element).scrollbarWidth,
      fallback:getComputedStyle(element,'::-webkit-scrollbar').display,
      scrollable:element.scrollHeight>element.clientHeight,
    }));
    assert.equal(scrollbar.width,'none');assert.equal(scrollbar.fallback,'none');assert.equal(scrollbar.scrollable,true);
    await page.mouse.move(panel.x+panel.width/2,panel.y+panel.height/2);await page.mouse.wheel(0,250);
    await page.waitForFunction(()=>document.querySelector('#sketch-panel').scrollTop>0);
    await page.locator('#sketch-panel').evaluate(element=>{element.scrollTop=0;});
    await page.screenshot({path:resolve(output,`edit-${width}.png`)});
  }
  for(const selector of ['[data-sketch-target="t"] .marker','[data-sketch-gun="a"] .marker']) {
    await page.locator(selector).click({trial:true});
    const box=await page.locator(selector).boundingBox(),x=box.x+box.width/2,y=box.y+box.height/2;
    await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+25,y+20,{steps:8});await page.mouse.up();
    await page.waitForFunction(()=>!document.querySelector('#sketch-editor-fields').disabled);
  }
  const after=await page.evaluate(()=>worcalcNative.sketchStorage.load());
  assert.notEqual(after.maps['map-1'].targets[0].x,before.maps['map-1'].targets[0].x);
  assert.notEqual(after.maps['map-1'].guns[0].x,before.maps['map-1'].guns[0].x);
  assert.deepEqual(after.maps['map-1'].configurations,before.maps['map-1'].configurations);
  await page.locator('#sketch-x').fill('600');
  await page.locator('#sketch-edit').click();
  assert.equal(await page.locator('#sketch-form').isVisible(),false);
  await page.keyboard.press('Delete');
  assert.deepEqual(await page.evaluate(()=>worcalcNative.sketchStorage.load()),after);
  await page.locator('[data-sketch-target="t"] .marker').click();await page.screenshot({path:resolve(output,'sidebar.png')});
  await page.locator('#sketch-gun-options button').nth(0).click();
  assert.equal(await page.locator('#sketch-solution').isVisible(),true);
  await page.setViewportSize({width:1280,height:850});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.locator('#map-search').fill('Smokestacks');
  await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().x>=0);
  await page.screenshot({path:resolve(output,'solution-1280.png')});
  assert.deepEqual(errors,[]);console.log('PASS native read-only selection, blocked View drags/shortcuts, explicit Edit, preserved saved cards and non-overlapping sidebar');
} finally {if(browser)await browser.close();if(child.exitCode===null)child.kill();}
