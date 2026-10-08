/* Exercise the embedded Tauri WebView and native plan files, never a web server. */
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {createRequire} from "node:module";
import {createServer} from "node:net";
import {mkdir, readFile, writeFile, unlink} from "node:fs/promises";
import {dirname, resolve, basename} from "node:path";
import {fileURLToPath} from "node:url";
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.WORCALC_PLAYWRIGHT_PATH || "playwright");
const root=resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const executable=resolve(root,"target/debug/worcalc-app.exe");
const output=resolve(root,"artifacts/validation/desktop-flow");
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let processHandle,browser,page,exportPath,launchNumber=0;
const errors=[],checks=[];
await mkdir(output,{recursive:true});
async function launch() {
  const server=createServer();await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const port=server.address().port;await new Promise(resolve=>server.close(resolve));
  processHandle=spawn(executable,[],{cwd:dirname(executable),windowsHide:true,env:{...process.env,
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`,
    WEBVIEW2_USER_DATA_FOLDER:resolve(output,`webview-${Date.now()}-${++launchNumber}`)}});
  processHandle.on("error",error=>errors.push(error.message));
  let ready=false;
  for(let attempt=0;attempt<100;attempt++) {
    try {ready=(await fetch(`http://127.0.0.1:${port}/json/version`)).ok;} catch {}
    if(ready)break;if(processHandle.exitCode!=null)throw Error("Native workflow app exited before its WebView was ready");
    await pause(200);
  }
  assert.ok(ready,"The native WebView must be running");
  browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  page=browser.contexts()[0].pages()[0];
  page.on("pageerror",error=>errors.push(error.message));
  page.on("dialog",dialog=>dialog.accept());
  await page.waitForSelector("#choose-sketcher:enabled");
  const identifier=await page.evaluate(()=>globalThis.__TAURI_INTERNALS__.invoke("plugin:app|identifier"));
  assert.equal(identifier,"pt.tomaspedreira.worcalc.flowtest","Refuse to change the normal application's plan files");
}
async function stop() {
  if(browser){await browser.close();browser=null;}
  if(processHandle && processHandle.exitCode==null){processHandle.kill();await pause(250);}
  processHandle=null;
}
async function stored(){return page.evaluate(()=>worcalcNative.sketchStorage.load());}
async function mapClick(x,y) {
  const image=page.locator("#map-image"),box=await image.boundingBox();
  const size=await image.evaluate(image=>({width:image.naturalWidth,height:image.naturalHeight}));
  await page.mouse.click(box.x+x*box.width/size.width,box.y+y*box.height/size.height);
}
async function saveInspector(){
  await page.locator("#sketch-save").click();
  await page.waitForFunction(()=>!document.querySelector("#sketch-editor-fields").disabled && document.querySelector("#mode-pill").textContent.startsWith("SELECTED DETAILS"));
}
async function inspector(){await page.locator("#sketch-form").waitFor();await page.waitForSelector("#sketch-save:enabled");}
async function gun(id){await page.locator(`[data-sketch-gun="${id}"] .marker`).click();}
async function target(id){await page.locator(`[data-sketch-target="${id}"] .marker`).click();}
async function enterSketch() {
  await page.locator("#choose-sketcher").click();
  await page.waitForSelector("#sketch-toolbar:not([hidden])");
  await page.waitForFunction(()=>document.querySelector("#map-image").complete && document.querySelector("#map-image").naturalWidth>0);
  await page.waitForFunction(async()=>Boolean((await worcalcNative.sketchStorage.load()).maps["map-1"]));
}
async function placeGun(x,y) {
  const before=await page.locator("#sketch-gun-select").inputValue();
  await page.locator("#sketch-add-gun").click();await mapClick(x,y);
  await page.waitForFunction(previous=>document.querySelector("#sketch-gun-select").value!==previous,before);
  const id=await page.locator("#sketch-gun-select").inputValue();assert.ok(id);
  await inspector();
  assert.equal(await page.locator("#sketch-details-title").innerText(),"Gun");
  await page.locator("#sketch-weapon").selectOption("3-inch Ordnance");await saveInspector();
  return id;
}
async function addTarget(x,y,elevation,fuze) {
  await page.locator("#sketch-add-target").click();await mapClick(x,y);await inspector();
  const id=await page.locator(".sketch-marker.target.selected").getAttribute("data-sketch-target");
  if(elevation!=null)await page.locator("#sketch-angle").fill(String(elevation));
  if(fuze!=null)await page.locator("#sketch-fuze").fill(String(fuze));
  await page.screenshot({path:resolve(output,`inspector-${id}.png`)});
  await saveInspector();return id;
}
async function values() {
  return page.locator("#sketch-readouts .range-chip").evaluateAll(chips=>chips.map(chip=>({target:chip.getAttribute("data-sketch-readout"),
    elevation:chip.querySelector(":scope > div:first-child b").textContent,fuze:chip.querySelector(":scope > div:last-child b").textContent})));
}
function check(name){checks.push(name);console.log("PASS",name);}
try {
  await launch();await page.evaluate(()=>worcalcNative.sketchStorage.save({version:1,maps:{}}));
  await page.reload();await page.waitForSelector("#choose-sketcher:enabled");await enterSketch();
  const defaults=(await stored()).maps["map-1"].guns.length;
  assert.equal(await page.locator("#sketch-name, #sketch-dialog, #sketch-gun-settings").count(),0);
  const a=await placeGun(700,800);
  const bridge=await addTarget(1000,1000);
  let library=await stored(),plan=library.maps["map-1"];
  assert.ok([...plan.guns,...plan.targets].every(point=>!("name" in point)));
  const defaultSetting=plan.configurations.find(setting=>setting.gun_id===a && setting.target_id===bridge);
  assert.equal(defaultSetting.elevation_degrees,defaultSetting.solution.elevation_degrees);
  assert.equal(defaultSetting.fuze_seconds,defaultSetting.solution.fuze_seconds);
  check("Freely place unlabelled guns and targets and save exact simulator defaults in the right-column inspector");
  const road=await addTarget(1300,1050,2.2,3.8);
  await page.locator("#sketch-edit").click();
  assert.equal(await page.locator("#elevation").innerText(),"2.20°");assert.equal(await page.locator("#fuze").innerText(),"3.800 s");
  await gun(a);assert.equal((await values()).length,2);
  await page.screenshot({path:resolve(output,"view-gun-a.png")});
  check("Return to view mode and reveal every saved target and firing window with one gun click");
  const b=await placeGun(500,1050);
  await target(bridge);await inspector();
  assert.ok(!(await page.locator("#sketch-editor-context").innerText()).includes(b));
  await page.locator("#sketch-angle").fill("2.4");await page.locator("#sketch-fuze").fill("4.1");await saveInspector();
  library=await stored();plan=library.maps["map-1"];
  assert.equal(plan.guns.length,defaults+2);assert.equal(plan.targets.length,2);assert.equal(plan.configurations.length,3);
  assert.deepEqual(plan.configurations.find(setting=>setting.gun_id===a && setting.target_id===bridge),defaultSetting);
  await page.locator("#sketch-edit").click();await gun(b);
  assert.deepEqual(await values(),[{target:bridge,elevation:"2.40°",fuze:"4.100 s"}]);
  assert.equal(await page.locator(`[data-sketch-target="${road}"]`).evaluate(marker=>getComputedStyle(marker).opacity),"0.3");
  await page.screenshot({path:resolve(output,"view-gun-b.png")});
  check("Reuse one physical target for two guns, each with its own saved settings");
  await page.evaluate(()=>{
    globalThis.flowCalls=[];const original=globalThis.__TAURI_INTERNALS__.invoke;
    globalThis.__TAURI_INTERNALS__.invoke=function(command,args,...rest){flowCalls.push({command,args});return original.call(this,command,args,...rest);};
  });
  const before=await stored();await gun(a);await target(bridge);await gun(b);await target(bridge);await target(road);await mapClick(1500,1200);
  assert.equal(await page.locator("#range-chip").evaluate(chip=>chip.hidden),true);
  assert.deepEqual(await stored(),before);
  assert.equal(await page.evaluate(()=>flowCalls.filter(call=>call.command==="native_request" && call.args.operation==="calculate" ||
    call.command==="native_sketch" && call.args.operation==="save").length),0);
  check("Viewing uses saved values without recalculation or writes and clears unrelated firing information");
  await gun(a);await page.locator("#sketch-edit").click();await page.locator("#sketch-add-target").click();await mapClick(1500,1200);await inspector();
  await page.locator("#sketch-cancel").click();await page.locator("#sketch-form").waitFor({state:"hidden"});
  assert.deepEqual(await stored(),before);await page.locator("#sketch-edit").click();
  check("Cancel leaves no new target or configuration");
  await stop();await launch();await enterSketch();await gun(b);
  assert.deepEqual(await stored(),before);assert.deepEqual(await values(),[{target:bridge,elevation:"2.40°",fuze:"4.100 s"}]);
  check("Saved plans survive closing and reopening the native process");
  await page.locator("#sketch-export").click();await page.waitForFunction(()=>document.querySelector("#mode-pill").textContent.startsWith("Exported to "));
  exportPath=(await page.locator("#mode-pill").innerText()).slice("Exported to ".length);
  assert.match(basename(exportPath),/^worcalc-plans-\d+-\d+\.json$/);
  const exported=await readFile(exportPath);assert.deepEqual(JSON.parse(exported),before);
  await writeFile(resolve(output,"exported-plan.json"),exported);
  await target(bridge);await inspector();
  assert.equal(await page.locator("#sketch-angle").inputValue(),"2.4");assert.equal(await page.locator("#sketch-fuze").inputValue(),"4.1");
  await page.locator("#sketch-defaults").click();
  const bSetting=before.maps["map-1"].configurations.find(setting=>setting.gun_id===b && setting.target_id===bridge);
  assert.equal(Number(await page.locator("#sketch-angle").inputValue()),bSetting.solution.elevation_degrees);
  assert.equal(Number(await page.locator("#sketch-fuze").inputValue()),bSetting.solution.fuze_seconds);
  await page.locator("#sketch-angle").fill("4.8");await page.locator("#sketch-fuze").fill("5.2");await saveInspector();
  assert.equal((await stored()).maps["map-1"].configurations.find(setting=>setting.gun_id===b && setting.target_id===bridge).elevation_degrees,4.8);
  await page.locator("#sketch-file").setInputFiles({name:"exported-plan.json",mimeType:"application/json",buffer:exported});
  await page.waitForFunction(()=>document.querySelector("#mode-pill").textContent==="PLANS IMPORTED AND SAVED");
  assert.deepEqual(await stored(),before);await gun(b);assert.deepEqual(await values(),[{target:bridge,elevation:"2.40°",fuze:"4.100 s"}]);
  check("Selecting in view mode opens editable saved settings; Save, defaults and export/import round-trip correctly");

  await target(bridge);await page.locator("#sketch-notes").fill("abc");
  await page.locator("#sketch-notes").press("Home");await page.keyboard.press("Delete");
  assert.equal(await page.locator("#sketch-notes").inputValue(),"bc");assert.deepEqual(await stored(),before);
  await page.locator("#sketch-cancel").click();
  check("Delete inside the inspector edits text without deleting a gun or target");

  async function restore(){
    await page.locator("#sketch-file").setInputFiles({name:"exported-plan.json",mimeType:"application/json",buffer:exported});
    await page.waitForFunction(()=>document.querySelector("#mode-pill").textContent==="PLANS IMPORTED AND SAVED");
    assert.deepEqual(await stored(),before);
  }
  await gun(a);await target(bridge);await page.keyboard.press("Delete");
  await page.waitForFunction(id=>!document.querySelector(`[data-sketch-target="${id}"]`),bridge);
  plan=(await stored()).maps["map-1"];
  assert.equal(plan.guns.length,defaults+2);assert.equal(plan.targets.length,1);
  assert.equal(plan.configurations.length,1);assert.equal(plan.configurations[0].target_id,road);
  const afterDelete=await stored();await page.keyboard.press("Delete");assert.deepEqual(await stored(),afterDelete);
  check("Delete removes the most recently selected shared target and all its gun settings without falling back to the gun");

  await restore();await gun(b);await target(bridge);await gun(a);await page.keyboard.press("Delete");
  await page.waitForFunction(id=>!document.querySelector(`[data-sketch-gun="${id}"]`),a);
  plan=(await stored()).maps["map-1"];
  assert.equal(plan.guns.length,defaults+1);assert.equal(plan.targets.length,2);
  assert.equal(plan.configurations.length,1);assert.equal(plan.configurations[0].gun_id,b);
  await target(road);await inspector();assert.equal(await page.locator("#sketch-ammo").isDisabled(),true);
  await page.locator("#sketch-delete").click();
  await page.waitForFunction(id=>!document.querySelector(`[data-sketch-target="${id}"]`),road);
  assert.equal((await stored()).maps["map-1"].targets.length,1);
  check("Selecting a gun after a target deletes only that gun; targets remain selectable and deletable without an active gun");

  await restore();await target(bridge);await inspector();
  await page.locator("#sketch-x").fill("1010");await saveInspector();
  plan=(await stored()).maps["map-1"];
  assert.equal(plan.targets.find(point=>point.id===bridge).x,1010);
  assert.equal(plan.configurations.length,1);assert.equal(plan.configurations[0].target_id,road);
  check("Editing shared target coordinates in the side column clears its outdated gun settings only");
  await restore();await gun(a);await page.locator("#sketch-edit").click();
  const anchor=await page.locator(`[data-sketch-gun="${a}"] .marker`).boundingBox();
  await page.mouse.move(anchor.x+anchor.width/2,anchor.y+anchor.height/2);await page.mouse.down();
  await page.mouse.move(anchor.x+anchor.width/2+50,anchor.y+anchor.height/2+10,{steps:5});await page.mouse.up();
  await page.waitForFunction(()=>document.querySelector("#sketch-details-title").textContent==="Gun" && !document.querySelector("#sketch-editor-fields").disabled);
  plan=(await stored()).maps["map-1"];
  assert.notEqual(plan.guns.find(point=>point.id===a).x,700);assert.equal(plan.targets.length,2);
  assert.equal(plan.configurations.length,1);assert.equal(plan.configurations[0].gun_id,b);
  check("Gun dragging still works with the side inspector open and preserves another gun's shared-target settings");
  await restore();await gun(a);await page.locator("#sketch-edit").click();await page.locator("#sketch-add-target").click();
  await mapClick(1500,1200);await inspector();await page.locator("#sketch-details-title").click();await page.keyboard.press("Delete");
  await page.locator("#sketch-form").waitFor({state:"hidden"});assert.deepEqual(await stored(),before);
  check("Delete discards an unsaved target without modifying the saved plan");
  await page.screenshot({path:resolve(output,"deletion-complete.png")});
  await page.locator("#choose-app").click();await page.locator("#choose-calculator").click();
  await page.locator("#gun-mode").click();await mapClick(700,800);await page.locator("#target-mode").click();await mapClick(1000,1000);
  await page.waitForFunction(()=>!document.querySelector("#range-chip").hidden);
  assert.equal(await page.locator("#elevation").innerText(),`${defaultSetting.elevation_degrees.toFixed(2)}°`);
  assert.equal(await page.locator("#fuze").innerText(),`${defaultSetting.fuze_seconds.toFixed(3)} s`);
  assert.equal(await page.locator("#sketch-readouts").evaluate(layer=>layer.hidden),true);
  check("The original calculator still places guns and targets and uses the same firing display");

  await page.locator("#choose-app").click();await enterSketch();
  const legacy=JSON.parse(JSON.stringify(before)),legacyPlan=legacy.maps["map-1"];
  const replacements={
    [a]:"gun-17c9cb45-1736-4563-9518-9bb89512319a",
    [b]:"gun-97e2b3c4-8d44-4a62-885f-0a534680081a",
    [bridge]:"target-62f2448e-473c-4669-a6d0-7bc9bcd5a5f3",
    [road]:"target-d0b577bd-2de8-44e7-a166-903a2888adbc"
  };
  for(const point of [...legacyPlan.guns,...legacyPlan.targets])point.id=replacements[point.id] || point.id;
  for(const setting of legacyPlan.configurations){setting.gun_id=replacements[setting.gun_id];setting.target_id=replacements[setting.target_id];}
  await page.locator("#sketch-file").setInputFiles({name:"legacy-ids.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(legacy))});
  await page.waitForFunction(()=>document.querySelector("#mode-pill").textContent==="PLANS IMPORTED AND SAVED");
  await gun(replacements[a]);await target(replacements[bridge]);
  for(const editing of [false,true]) {
    if(editing)await page.locator("#sketch-edit").click();
    await page.locator(`[data-sketch-gun="${replacements[a]}"] .marker`).hover();
    await page.locator(`[data-sketch-target="${replacements[bridge]}"]`).focus();
    assert.equal(await page.locator("#sketch-layer .marker span, #sketch-layer [title]").count(),0);
    const visibleText=await page.locator("#sketch-panel").innerText();
    const optionText=await page.locator("#sketch-gun-select option").allTextContents();
    const ariaText=await page.locator("#sketch-layer [aria-label], #sketch-readouts [aria-label]").evaluateAll(elements=>elements.map(element=>element.getAttribute("aria-label")));
    for(const id of Object.values(replacements)) {
      assert.ok(!visibleText.includes(id));assert.ok(optionText.every(text=>!text.includes(id)));assert.ok(ariaText.every(text=>!text.includes(id)));
    }
  }
  assert.deepEqual(await stored(),legacy);
  await page.screenshot({path:resolve(output,"unlabelled-legacy-points.png")});
  check("Existing hashed IDs stay internal: no marker labels, hover titles, focus labels or IDs in the side panel and lists");
  assert.deepEqual(errors,[]);
  await writeFile(resolve(output,"results.json"),JSON.stringify({checks,errors,guns:2,sharedTargets:2,configurations:3},null,2));
} catch(error) {
  if(page)await page.screenshot({path:resolve(output,"failure.png")}).catch(()=>{});
  throw error;
} finally {
  await stop();
  if(exportPath)await unlink(exportPath);
}
