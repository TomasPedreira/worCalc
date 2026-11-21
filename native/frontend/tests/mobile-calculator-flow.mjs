/* Exercise compact controls through the native WebView and real Rust calculator. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {createServer} from 'node:net';
import {mkdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
const {chromium}=createRequire(import.meta.url)(process.env.WORCALC_PLAYWRIGHT_PATH||'playwright');
const output=resolve('artifacts/validation/mobile-calculator');await mkdir(output,{recursive:true});
const server=createServer();await new Promise(done=>server.listen(0,'127.0.0.1',done));
const port=server.address().port;await new Promise(done=>server.close(done));
const executable=resolve('target/debug/worcalc-app.exe');
const child=spawn(executable,[],{cwd:dirname(executable),windowsHide:true,env:{...process.env,
 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`,WEBVIEW2_USER_DATA_FOLDER:resolve(output,`webview-${Date.now()}`)}});
let browser,page;
try {
 for(let attempt=0;attempt<100;attempt++) {
  try{if((await fetch(`http://127.0.0.1:${port}/json/version`)).ok)break;}catch{}
  if(child.exitCode!=null)throw Error('Native test app exited');await new Promise(done=>setTimeout(done,200));
 }
 browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);page=browser.contexts()[0].pages()[0];const errors=[];
 const platform=await page.context().newCDPSession(page);
 await platform.send('Network.setUserAgentOverride',{userAgent:'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36'});
 await page.reload();
 page.on('pageerror',error=>errors.push(error.message));
 await page.waitForFunction(()=>globalThis.worcalcNative&&!document.querySelector('#workspace').inert&&!document.querySelector('#map-wrap').classList.contains('map-loading'));
 assert.equal(await page.evaluate(()=>__TAURI_INTERNALS__.invoke('plugin:app|identifier')),'pt.tomaspedreira.worcalc.flowtest');
 await page.setViewportSize({width:390,height:844});
 await page.waitForFunction(()=>{
  const map=document.querySelector('#map-wrap').getBoundingClientRect(),image=document.querySelector('#map-image').getBoundingClientRect();
  return Math.abs(map.width-390)<1&&image.width>=map.width-1&&image.height>=map.height-1;
 });
 await page.evaluate(()=>{
  const original=worcalcNative.api.calculate;globalThis.mobileRequests=[];globalThis.mobileSolutions=[];
  worcalcNative.api.calculate=async request=>{mobileRequests.push(request);const solution=await original(request);mobileSolutions.push(solution);return solution;};
  globalThis.mobilePointers=[];
  for(const type of ['pointerdown','pointerup','pointercancel'])window.addEventListener(type,event=>mobilePointers.push({type,target:event.target.id||event.target.className,x:event.clientX,y:event.clientY}),true);
 });
 const box=await page.locator('#map-wrap').boundingBox();
 await page.locator('#mobile-gun-mode').click();await page.mouse.click(box.x+box.width*.3,box.y+box.height*.7,{delay:50});
 await page.locator('#gun-anchor .marker').waitFor({state:'visible'});
 await page.locator('#mobile-target-mode').click();await page.mouse.click(box.x+box.width*.62,box.y+box.height*.38,{delay:50});
 await page.waitForFunction(()=>!document.querySelector('#range-chip').hidden&&!document.querySelector('#map-wrap').classList.contains('solution-loading'));
 const before=await page.evaluate(()=>mobileRequests.at(-1));
 async function explosionHeightMatchesSolution() {
  const height=await page.evaluate(()=>mobileSolutions.at(-1).height_above_target_metres);
  const expected=height==null?'N/A':(height>=0?'+':'')+height.toFixed(1)+' m';
  assert.equal(await page.locator('#explosion-height').innerText(),expected);
  assert.equal(await page.locator('#explosion-height').isVisible(),true);
 }
 await explosionHeightMatchesSolution();
 async function buttonFill(id) {
  return page.locator('#'+id).evaluate(async element=>{
   await new Promise(requestAnimationFrame);
   await Promise.allSettled(element.getAnimations().map(animation=>animation.finished));
   const style=getComputedStyle(element);
   return {background:style.backgroundColor,image:style.backgroundImage};
  });
 }
 const neutralFill=await buttonFill('quick-projectile');
 async function change(id,text) {
  const previous=await page.evaluate(()=>mobileRequests.length);await page.locator('#'+id).click();
  await page.waitForFunction(count=>mobileRequests.length===count+1&&!document.querySelector('#map-wrap').classList.contains('solution-loading'),previous);
  assert.equal(await page.locator('#'+id).innerText(),text);
  assert.equal(await page.locator('#'+id).evaluate(element=>document.activeElement===element),false);
  assert.deepEqual(await buttonFill(id),neutralFill,id+' must not retain a different fill after a tap/click');
  const request=await page.evaluate(()=>mobileRequests.at(-1));assert.deepEqual(request.gun,before.gun);assert.deepEqual(request.target,before.target);return request;
 }
 assert.equal((await change('quick-projectile','CASE')).projectile,'Case');
 assert.equal((await change('quick-burst','AIRBURST')).airburst_mode,true);
 await explosionHeightMatchesSolution();
 const smooth=await change('quick-cannon','SMOOTHBORE');assert.equal(smooth.cannon,'12-pounder Napoleon');assert.equal(smooth.projectile,'Case');assert.equal(smooth.airburst_mode,true);
 await change('quick-cannon','RIFLED');await change('quick-projectile','SHELL');await change('quick-burst','GROUND');
 const touch=await page.context().newCDPSession(page);
 await touch.send('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
 const ammoButton=await page.locator('#quick-projectile').boundingBox();
 await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:ammoButton.x+ammoButton.width/2,y:ammoButton.y+ammoButton.height/2}]});
 await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await page.waitForFunction(()=>document.querySelector('#quick-projectile').textContent==='CASE'&&!document.querySelector('#map-wrap').classList.contains('solution-loading'));
 assert.equal(await page.locator('#quick-projectile').evaluate(element=>document.activeElement===element),false);
 assert.deepEqual(await buttonFill('quick-projectile'),neutralFill,'touch must not retain a hover shade');
 await touch.send('Emulation.setTouchEmulationEnabled',{enabled:false});await touch.detach();
 await change('quick-projectile','SHELL');
 await page.locator('#quick-cannon').focus();await page.keyboard.press('Tab');
 assert.equal(await page.locator('#quick-projectile').evaluate(element=>document.activeElement===element),true);
 await page.waitForFunction(()=>getComputedStyle(document.querySelector('#quick-projectile')).borderColor==='rgb(151, 168, 157)');
 assert.deepEqual(await page.locator('#quick-projectile').evaluate(element=>{
  const style=getComputedStyle(element);return {outline:style.outlineStyle,border:style.borderColor};
 }),{outline:'none',border:'rgb(151, 168, 157)'},'keyboard focus must use a neutral border, with no blue outline');
 await page.keyboard.press('Space');
 await page.waitForFunction(()=>document.querySelector('#quick-projectile').textContent==='CASE'&&!document.querySelector('#map-wrap').classList.contains('solution-loading'));
 assert.equal(await page.locator('#quick-projectile').evaluate(element=>document.activeElement===element),true);
 await change('quick-projectile','SHELL');
 await change('quick-cannon','SMOOTHBORE');await change('quick-projectile','CASE');await change('quick-burst','AIRBURST');
 const states=await page.context().newCDPSession(page);
 await states.send('DOM.enable');await states.send('CSS.enable');
 const {root}=await states.send('DOM.getDocument');
 await page.mouse.move(box.x+box.width*.1,box.y+box.height*.5);
 for(const id of ['quick-cannon','quick-projectile','quick-burst','mobile-gun-mode','mobile-target-mode','mobile-fit']) {
  const {nodeId}=await states.send('DOM.querySelector',{nodeId:root.nodeId,selector:'#'+id});
  const fill=await buttonFill(id);
  for(const forcedPseudoClasses of [[],['hover'],['active'],['focus'],['focus','focus-visible'],['hover','active','focus','focus-visible']]) {
   await states.send('CSS.forcePseudoState',{nodeId,forcedPseudoClasses});
   const style=await page.locator('#'+id).evaluate(element=>{
    const style=getComputedStyle(element);return {outline:style.outlineStyle,shadow:style.boxShadow,appearance:style.appearance,tap:style.webkitTapHighlightColor};
   });
   assert.deepEqual(style,{outline:'none',shadow:'none',appearance:'none',tap:'rgba(0, 0, 0, 0)'},id+' '+forcedPseudoClasses.join('/'));
   assert.deepEqual(await buttonFill(id),fill,id+' fill must stay unchanged in '+forcedPseudoClasses.join('/'));
  }
  await states.send('CSS.forcePseudoState',{nodeId,forcedPseudoClasses:[]});
 }
 await states.detach();
 assert.equal(await page.locator('#cannon-select option').allTextContents().then(labels=>labels.join(',')),'Rifled,Smoothbore');
 for(const [width,height] of [[390,844],[320,740],[844,390],[1280,850]]) {
  await page.setViewportSize({width,height});
  const name=await page.locator('.map-heading .map-name').boundingBox(),tools=await page.locator('.mobile-placement').boundingBox();
  assert.ok(tools.x>=name.x+name.width-1);assert.ok(Math.abs(tools.y+tools.height/2-name.y-name.height/2)<2);
  assert.equal(await page.locator('.status-bar').isVisible(),true);assert.equal(await page.locator('#calculator-toolbar').isVisible(),false);
  await explosionHeightMatchesSolution();
  for(const id of ['aim','distance','height'])assert.equal(await page.locator('#'+id).isVisible(),false);
  const readout=await page.locator('.status-bar').boundingBox(),settings=await page.locator('.mobile-fire-settings').boundingBox();
  assert.ok(readout.y+readout.height<=settings.y-7,'explosion height must be above the quick controls');
  assert.ok(readout.x>=0&&readout.x+readout.width<=width,'explosion height must fit narrow screens');
  assert.equal(await page.locator('#explosion-height').evaluate(element=>element.scrollWidth<=element.clientWidth),true);
  assert.equal(await page.locator('.mobile-fire-settings .active').count(),0);
  assert.equal(await page.locator('.mobile-fire-settings').evaluate(element=>element.scrollWidth<=element.clientWidth),true);
  const typography=await page.locator('.mobile-fire-settings button').evaluateAll(buttons=>buttons.map(button=>({size:getComputedStyle(button).fontSize,weight:getComputedStyle(button).fontWeight,clipped:button.scrollWidth>button.clientWidth})));
  for(const button of typography){assert.equal(button.size,'14px');assert.equal(button.weight,'700');assert.equal(button.clipped,false);}
  await page.screenshot({path:resolve(output,`mobile-${width}.png`)});
 }
 assert.equal(await page.evaluate(()=>matchMedia('(min-width:1100px) and (pointer:fine)').matches),true);
 await page.locator('#open-drawer').click();await page.locator('#mobile-advanced').click();
 await page.locator('#cannon-select').selectOption('12-pounder Napoleon');await page.locator('#projectile-select').selectOption('Case');await page.locator('#burst-mode').selectOption('airburst');
 assert.equal(await page.locator('#quick-cannon').innerText(),'SMOOTHBORE');assert.equal(await page.locator('#quick-projectile').innerText(),'CASE');assert.equal(await page.locator('#quick-burst').innerText(),'AIRBURST');
 await page.locator('#sheet .close').click();
 await page.locator('#mobile-fit').click();
 await page.waitForFunction(()=>{
  const map=document.querySelector('#map-wrap').getBoundingClientRect(),image=document.querySelector('#map-image').getBoundingClientRect();
  return image.width<=map.width+1&&image.height<=map.height+1;
 });
 assert.equal(await page.locator('.status-bar').isVisible(),true);assert.deepEqual(errors,[]);
 console.log('PASS shared native calculator layout, phone and desktop controls, preserved geometry and advanced synchronization.');
} catch(error) {
 if(page){
  await page.screenshot({path:resolve(output,'failure.png')});
  console.log(await page.evaluate(()=>({
   status:document.querySelector('#mode-pill').textContent,viewport:[innerWidth,innerHeight],
   map:document.querySelector('#map-wrap').getBoundingClientRect().toJSON(),image:document.querySelector('#map-image').getBoundingClientRect().toJSON(),
   requests:globalThis.mobileRequests,pointers:globalThis.mobilePointers,gunHidden:document.querySelector('#gun-anchor').hidden,targetHidden:document.querySelector('#target-anchor').hidden,
  })));
 }
 throw error;
} finally {if(browser)await browser.close();if(child.exitCode==null)child.kill();}
