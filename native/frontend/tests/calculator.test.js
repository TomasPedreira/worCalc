import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const windowsUserAgent = 'Mozilla/5.0 (Windows NT 10.0)';

async function runScenario(code, userAgent = 'Mozilla/5.0 (Linux; Android 15)') {

const elements = new Map();
function createElement() {
  const classes = new Set();
  return {
    value:'', textContent:'', children:[], hidden:false, naturalWidth:200, naturalHeight:150, attributes:{}, dataset:{},
    src:'old-map', style:{setProperty(key,value){this[key]=value}}, handlers:{},
    classList:{add:x=>classes.add(x), remove:(...xs)=>xs.forEach(x=>classes.delete(x)),
      contains:x=>classes.has(x), toggle(x,on){if(on) classes.add(x); else classes.delete(x)}},
    addEventListener(n,f){this.handlers[n]=f}, replaceChildren(...children){this.children=children}, setPointerCapture(){},
    append(...children){for (const child of children) child.parentNode=this; this.children.push(...children)},
    remove(){this.parentNode.children=this.parentNode.children.filter(child=>child!==this)},
    setAttribute(name,value){this.attributes[name]=value},
    getBoundingClientRect(){return {left:0,top:0,width:200,height:150}}
  };
}
function element(key) {
  if (!elements.has(key)) elements.set(key, createElement());
  return elements.get(key);
}
const images = [];
let objectSequence = 0;
const context = vm.createContext({
  document:{querySelector:element,querySelectorAll:()=>[],createElement},
  navigator:{userAgent},
  window:{handlers:{},addEventListener(name,handler){this.handlers[name]=handler}}, assert, console, AbortController, images,
  URL:{createObjectURL:()=>`blob:map-${++objectSequence}`,revokeObjectURL(){}},
  Image:function(){this.handlers={};this.addEventListener=(n,f)=>this.handlers[n]=f;images.push(this)},
  worcalcNative:{api:{calculate:async()=>{throw Error('Calculation failed')},mapImage:async()=>{throw Error('Image failed')},recordImpact:async()=>{throw Error('Save failed')}}}
});
vm.runInContext(readFileSync(new URL('../src/map-marker.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../src/fire-readout.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../src/artillery-positions.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../src/app.js',import.meta.url),'utf8').replace(/load\(\);\s*$/, ''),context);
vm.runInContext(`
currentMap={identifier:'new-map'}; mapReady=true;
gun={x:10,y:20}; target=supportsMultipleTargets ? null : {x:100,y:20};
`,context);

return await vm.runInContext('(async()=>{'+code+'})()',context);
}

test("calculator gun and target use the shared map marker presentation",async()=>runScenario(`
for (const type of ['gun','target']) {
  const marker=$('#'+type+'-anchor').children[0];
  assert.equal(marker.className,'marker '+type);
  assert.equal(marker.children[0].textContent,type.toUpperCase());
}
`));

const desktopTargetGestures = `
const pressTarget = (shiftKey, x, y) => {
  window.handlers.keydown({key:shiftKey ? 'T' : 't',shiftKey});
  const pointer={pointerId:1,button:0,clientX:x,clientY:y,target:{closest:()=>null}};
  mapWrap.handlers.pointerdown(pointer);endPointer(pointer);
};
const pressMarker = marker => ({
  pointerId:1,button:0,clientX:0,clientY:0,target:{closest:selector=>selector==='[data-marker]' ? marker : null},
});
const rightClick = marker => {
  let prevented=false;
  mapWrap.handlers.contextmenu({
    button:2,target:{closest:()=>marker},preventDefault(){prevented=true},
  });
  return prevented;
};
`;

test("Windows shows a separate result for every target and dragging recalculates only that target",async()=>runScenario(desktopTargetGestures+`
const calculated=[];
nativeApi.calculate=async ({target})=>{
  calculated.push([target.x,target.y]);
  return {elevation_degrees:target.x/100,fuze_seconds:target.y/10,height_above_target_metres:target.y/100,bearing_degrees:90,clearance_status:'clear'};
};
pressTarget(true,120,50);
pressTarget(true,140,65);
pressTarget(false,155,70);
await Promise.resolve();
const entries=[...desktopTargets.values()];
assert.deepEqual(entries.map(entry=>entry.metrics.map(metric=>metric.value.textContent)),[
  ['1.20°','5.000 s','+0.5 m'],['1.40°','6.500 s','+0.7 m'],['1.55°','7.000 s','+0.7 m']
]);
assert.ok(entries.every(entry=>!entry.readout.hidden&&entry.line.classList.contains('clear')));
const first=desktopTargets.keys().next().value;
const click=pressMarker(first);
mapWrap.handlers.pointerdown(click);endPointer(click);
assert.deepEqual(calculated,[[120,50],[140,65],[155,70]]);
mapWrap.handlers.pointerdown(click);
const moved={...click,clientX:125,clientY:55};
mapWrap.handlers.pointermove(moved);endPointer(moved);
await Promise.resolve();
assert.deepEqual(calculated,[[120,50],[140,65],[155,70],[125,55]]);
assert.deepEqual(entries.map(entry=>entry.solution.elevation_degrees),[1.25,1.4,1.55]);
$('#burst-mode').value='airburst';changeBurstMode();
await Promise.resolve();
assert.deepEqual(calculated.slice(4),[[125,55],[140,65],[155,70]]);
clearMission(false);
assert.equal(desktopTargets.size,0);assert.equal(mapWrap.children.length,0);
`, windowsUserAgent));

test("right-click removes individual Windows targets and discards a deleted target's pending result",async()=>runScenario(desktopTargetGestures+`
let resolveDeleted, requests=0;
nativeApi.calculate=async () => {
  requests+=1;
  if (requests===1) return new Promise(resolve=>{resolveDeleted=resolve});
  return {slant_range_yards:300,bearing_degrees:90,elevation_degrees:1.2,fuze_seconds:2.4};
};
pressTarget(true,120,50);
pressTarget(true,140,70);
const [first,second]=[...desktopTargets.keys()];
const deleted=desktopTargets.get(first);
assert.equal(rightClick(null),false);
assert.equal(rightClick(first),true);
assert.equal(requests,2);
await Promise.resolve();
const remaining=desktopTargets.get(second);
resolveDeleted({slant_range_yards:400,bearing_degrees:100,elevation_degrees:9.2,fuze_seconds:5});
await Promise.resolve();await Promise.resolve();
assert.equal(deleted.solution,null);
assert.equal(remaining.solution.elevation_degrees,1.2);
assert.equal(remaining.readout.hidden,false);
assert.equal(rightClick(second),true);
assert.equal(desktopTargets.size,0);assert.equal(mapWrap.children.length,0);
`, windowsUserAgent));

test("Windows calibration uses the explicitly chosen target without changing the other readouts",async()=>runScenario(desktopTargetGestures+`
$('#calculation-mode').value='test';
nativeApi.calculate=async ({target})=>({calculation_id:String(target.x),elevation_degrees:target.x/100});
const impactsSaved=[];
nativeApi.recordImpact=async impact=>{impactsSaved.push(impact)};
pressTarget(true,120,50);pressTarget(true,140,70);
await Promise.resolve();
assert.equal($('#calibration-target-field').hidden,false);
await markImpact(90,95);
assert.equal(impactsSaved.length,0);
$('#calibration-target').value='2';$('#calibration-target').handlers.change();
assert.equal($('#actual-elevation').value,'1.40');
await markImpact(90,95);
assert.equal(impactsSaved[0].calculation_id,'140');
assert.ok([...desktopTargets.values()].every(entry=>!entry.readout.hidden));
`, windowsUserAgent));

test("Android keeps single-target placement and ignores right-click removal",async()=>runScenario(desktopTargetGestures+`
pressTarget(true,120,50);
assert.equal(target.x,120);assert.equal(desktopTargets.size,0);
assert.equal(rightClick(targetAnchor),false);assert.equal(target.x,120);
`, 'Mozilla/5.0 (Linux; Android 15)'));

const quickOptions = `
options={weapons:{'3-inch Ordnance':['Shell','Case'],'10-pounder Parrott':['Shell','Case'],'12-pounder Napoleon':['Shell','Case']},
  defaults:{cannon:'3-inch Ordnance'},physics:{}};
for(const cannon of Object.keys(options.weapons))options.physics[cannon]={Shell:{speed:370,drag:.1},Case:{speed:375,drag:.1}};
populateCannons();$('#burst-mode').value='ground';refreshProjectiles('Shell');
`;

test("calculator exposes two cannon families while Sketcher retains its native models",async()=>runScenario(quickOptions+`
assert.deepEqual(Array.from($('#cannon-select').children,option=>[option.textContent,option.value]),[
  ['Rifled','3-inch Ordnance'],['Smoothbore','12-pounder Napoleon']]);
applicationMode='sketcher';populateCannons();
assert.deepEqual(Array.from($('#cannon-select').children,option=>option.value),Object.keys(options.weapons));
`));

test("compact settings recalculate with exact native values and preserve other choices",async()=>runScenario(quickOptions+`
let requests=[];nativeApi.calculate=async data=>{requests.push(data);throw Error('offline');};
$('#quick-projectile').handlers.click();
assert.equal($('#projectile-select').value,'Case');assert.equal($('#quick-projectile').textContent,'CASE');
assert.equal(requests.at(-1).projectile,'Case');
$('#quick-burst').handlers.click();
assert.equal($('#quick-burst').textContent,'AIRBURST');assert.equal(requests.at(-1).airburst_mode,true);
$('#quick-cannon').handlers.click();
assert.equal($('#quick-cannon').textContent,'SMOOTHBORE');
assert.equal(requests.at(-1).cannon,'12-pounder Napoleon');assert.equal(requests.at(-1).projectile,'Case');assert.equal(requests.at(-1).airburst_mode,true);
$('#quick-cannon').handlers.click();assert.equal(requests.at(-1).cannon,'3-inch Ordnance');
$('#quick-projectile').handlers.click();$('#quick-burst').handlers.click();
assert.equal(requests.length,6);assert.equal(requests.at(-1).projectile,'Shell');assert.equal(requests.at(-1).airburst_mode,false);
assert.equal($('#quick-cannon').classList.contains('active'),false);
assert.equal($('#quick-projectile').classList.contains('active'),false);
assert.equal($('#quick-burst').classList.contains('active'),false);
`));

test("advanced controls synchronize compact labels and placement controls share state",async()=>runScenario(quickOptions+`
gun=null;
$('#cannon-select').value='12-pounder Napoleon';$('#cannon-select').handlers.change();
$('#projectile-select').value='Case';$('#projectile-select').handlers.change();
$('#burst-mode').value='airburst';$('#burst-mode').handlers.change();
assert.equal($('#quick-cannon').textContent,'SMOOTHBORE');assert.equal($('#quick-projectile').textContent,'CASE');assert.equal($('#quick-burst').textContent,'AIRBURST');
$('#mobile-gun-mode').handlers.click();assert.equal(mode,'gun');assert.equal($('#gun-mode').classList.contains('active'),true);
$('#mobile-target-mode').handlers.click();assert.equal(mode,'target');assert.equal($('#target-mode').classList.contains('active'),true);
assert.equal($('#mobile-gun-mode').attributes['aria-pressed'],'false');assert.equal($('#mobile-target-mode').attributes['aria-pressed'],'true');
$('#mobile-target-mode').handlers.click();assert.equal(mode,'pan');
assert.equal(modePill.classList.contains('idle-hint'),true);
showStatus('NO SOLUTION');assert.equal(modePill.classList.contains('idle-hint'),false);assert.equal(modePill.textContent,'NO SOLUTION');
`));

test("compact controls ignore clicks until options load",async()=>runScenario(`
options=null;
for(const id of ['quick-cannon','quick-projectile','quick-burst'])$('#'+id).handlers.click();
assert.equal(options,null);
`));

test("pointer activation clears button focus while keyboard activation preserves it",async()=>runScenario(`
let blurs=0;
const target={closest:selector=>{assert.equal(selector,'button');return {blur(){blurs++;}};}};
window.handlers.click({target,detail:1});assert.equal(blurs,1);
window.handlers.click({target,detail:0});assert.equal(blurs,1);
window.handlers.click({target:{closest:()=>null},detail:1});assert.equal(blurs,1);
applicationMode='sketcher';window.handlers.click({target,detail:1});assert.equal(blurs,1);
`));

test("calculator starts with a filled map on phone and desktop while FIT shows the whole map",async()=>runScenario(`
for (const [width,height] of [[320,680],[1280,720]]) {
  mapWrap.getBoundingClientRect=()=>({left:0,top:0,width,height});
  resetView();
  assert.ok(sceneWidth*zoom>=width);assert.ok(sceneHeight*zoom>=height);
  assert.ok(zoom>1);
  fitWholeMap();assert.equal(zoom,1);
  assert.equal(translateX,(width-sceneWidth)/2);assert.equal(translateY,(height-sceneHeight)/2);
}
applicationMode='sketcher';resetView();assert.equal(zoom,1);
`));

test("explosion height follows the calculated burst and clears with a stale solution",async()=>runScenario(`
const solution={slant_range_yards:300,bearing_degrees:90,elevation_degrees:1.2,fuze_seconds:2.4};
for(const [height,text] of [[1.24,'+1.2 m'],[-0.26,'-0.3 m'],[0,'+0.0 m'],[null,'N/A']]) {
  displaySolution({...solution,height_above_target_metres:height});
  assert.equal($('#explosion-height').textContent,text);
}
displaySolution({...solution,height_above_target_metres:1.24});
clearSolution();assert.equal($('#explosion-height').textContent,'—');
`));

test("calculator firing window stays above explosion height and bottom controls",async()=>runScenario(`
mapWrap.getBoundingClientRect=()=>({left:0,top:0,width:320,height:640,bottom:640});
$('.status-bar').getBoundingClientRect=()=>({left:8,top:532,width:140,height:48});
rangeChip.offsetWidth=190;rangeChip.offsetHeight=54;
gun={x:40,y:100};target={x:240,y:620};
updateRangeChipPosition();
assert.ok(parseFloat(rangeChip.style.top)+54<=524,'firing window must clear the visible explosion-height readout');
`));

test("map compass uses one 45 degree sector",async()=>runScenario(`
assert.deepEqual(compassGuideDirections(152), [135,180]);
assert.deepEqual(compassMinorTickDirections(152), [150,165]);
assert.deepEqual(compassGuideDirections(359), [315,0]);
assert.deepEqual(compassMinorTickDirections(359), [330,345]);
const east = rayPoint({x:50,y:60},90,142);
assert.ok(Math.abs(east.x-192)<1e-9);
assert.ok(Math.abs(east.y-60)<1e-9);
`));

test("corrected map metadata does not rotate compass cardinals a second time",async()=>runScenario(`
currentMap={identifier:'map-17',coordinate_revision:1};
gun={x:100,y:100};
for (const [point,degrees,label] of [[{x:100,y:50},0,'N'],[{x:150,y:100},90,'E'],[{x:100,y:150},180,'S'],[{x:50,y:100},270,'W']]) {
  target=point;
  assert.equal(missionBearing(),degrees);
  updateAimCompass(missionBearing());
  assert.equal($('#aim').textContent,label);
  assert.equal($('#aim-mark').style['--angle'],degrees+'deg');
}
`));

test("map compass renders from gun without blocking the map",async()=>runScenario(`
updateAimOverlay();
assert.match($('#aim-overlay').innerHTML,/aim-guide/);
assert.match($('#aim-overlay').innerHTML,/data-bearing="90"/);
assert.match($('#aim-overlay').innerHTML,/data-bearing="135"/);
assert.match($('#aim-overlay').innerHTML,/data-bearing="105"/);
assert.match($('#aim-overlay').innerHTML,/data-bearing="120"/);
assert.equal(($('#aim-overlay').innerHTML.match(/class="aim-guide"/g) || []).length,4);
assert.doesNotMatch($('#aim-overlay').innerHTML,/aim-minor-guide|aim-tick-guide/);
assert.match($('#aim-overlay').innerHTML,/>E<|>SE</);
assert.match($('#aim-overlay').innerHTML,/>\\+1</);
assert.match($('#aim-overlay').innerHTML,/>\\+2</);
`));

test("map compass survives zoom with gun outside viewport",async()=>runScenario(`
baseScale=1;zoom=4;translateX=-200;translateY=-120;
gun={x:10,y:20};target={x:100,y:100};
updateAimOverlay();
assert.equal(($('#aim-overlay').innerHTML.match(/class="aim-guide"/g) || []).length,4);
const point=rayPoint({x:-160,y:-40},135,500);
assert.ok(Math.abs(Math.hypot(point.x+160,point.y+40)-500)<1e-9);
`));

test("game compass aim has two ticks between named directions",async()=>runScenario(`
assert.deepEqual(gameCompassAim(14), {
  bearing:14,markDegrees:15,instruction:'N +1'
});
assert.deepEqual(gameCompassAim(31), {
  bearing:31,markDegrees:30,instruction:'N +2'
});
assert.deepEqual(gameCompassAim(44), {
  bearing:44,markDegrees:45,instruction:'NE'
});
assert.equal(gameCompassAim(359).instruction,'N');
`));

test("solution updates visible compass aim",async()=>runScenario(`
nativeApi.calculate=async()=>({
  slant_range_yards:300,height_difference_metres:0,bearing_degrees:74.2,
  elevation_degrees:1.2,fuze_seconds:2.4,clearance_status:'clear',
  height_above_target_metres:0
});
await requestSolution();
assert.equal($('#aim').textContent,'NE +2');
assert.equal($('#aim-degrees').textContent,'75° tick');
assert.equal($('#aim-mark').style['--angle'],'75deg');
assert.equal($('#aim-needle').style['--angle'],'74.2deg');
`));

test("drag at fit zoom moves map and keeps a visible strip",async()=>runScenario(`
sceneWidth=200;sceneHeight=150;zoom=1;translateX=0;translateY=0;
const event={pointerId:1,button:0,clientX:50,clientY:50,target:{closest:()=>null}};
mapWrap.handlers.pointerdown(event);
mapWrap.handlers.pointermove({...event,clientX:90,clientY:80});
mapWrap.handlers.pointerup({...event,clientX:90,clientY:80});
assert.equal(translateX,40);assert.equal(translateY,30);
assert.deepEqual(gun,{x:10,y:20});assert.deepEqual(target,{x:100,y:20});
translateX=9999;translateY=-9999;applyView();
assert.ok(translateX<200);assert.ok(translateY+150>0);
`));

test("middle click saves impact without moving shot",async()=>runScenario(`
$('#calculation-mode').value='test';
latestSolution={calculation_id:'shot-123'};
$('#actual-elevation').value='-0.10';
document.createElement=()=>({style:{}});
let payload;
nativeApi.recordImpact=async data=>{payload=data;return {}};
let prevented=false;
mapWrap.handlers.pointerdown({button:1,clientX:80,clientY:40,preventDefault(){prevented=true}});
await new Promise(resolve=>Promise.resolve().then(resolve));
assert.equal(prevented,true);
assert.equal(payload.calculation_id,'shot-123');
assert.equal(payload.actual_elevation_degrees,-0.10);
assert.deepEqual(payload.impact,{x:80,y:40});
assert.deepEqual(gun,{x:10,y:20});
assert.deepEqual(target,{x:100,y:20});
assert.equal(pointers.size,0);
`));

test("middle click on target marker records exact target center",async()=>runScenario(`
$('#calculation-mode').value='test';
latestSolution={calculation_id:'shot-123'};
$('#actual-elevation').value='0.42';
document.createElement=()=>({style:{}});
let payload;
nativeApi.recordImpact=async data=>{payload=data;return {}};
const targetMarker={closest:selector=>selector==='[data-marker="target"]' ? {} : null};
mapWrap.handlers.pointerdown({button:1,clientX:95,clientY:25,target:targetMarker,
                              preventDefault(){}});
await new Promise(resolve=>Promise.resolve().then(resolve));
assert.deepEqual(payload.impact,{x:100,y:20});
assert.equal(payload.actual_elevation_degrees,0.42);
`));

test("wheel zoom anchors cursor and readout is beside target",async()=>runScenario(`
sceneWidth=200;sceneHeight=150;
const before=imagePoint(100,75);
mapWrap.handlers.wheel({clientX:100,clientY:75,deltaY:-300,preventDefault(){}});
assert.ok(zoom>1);
assert.deepEqual(imagePoint(100,75),before);
zoom=1;translateX=0;translateY=0;
mapWrap.getBoundingClientRect=()=>({left:0,top:0,width:1000,height:800,bottom:800});
$('.status-bar').getBoundingClientRect=()=>({left:8,top:688,width:140,height:48});
target={x:500,y:400};gun={x:100,y:400};
updateRangeChipPosition();
assert.ok(parseFloat(rangeChip.style.left)>500);
assert.ok(parseFloat(rangeChip.style.top)>400);
`));

test("gun and target markers use screen coordinates at zoom",async()=>runScenario(`
baseScale=0.5;zoom=4;translateX=12;translateY=18;
gun={x:10,y:20};target={x:100,y:20};
updateMissionGeometry();
assert.equal(gunAnchor.style.left,'32px');
assert.equal(gunAnchor.style.top,'58px');
assert.equal(targetAnchor.style.left,'212px');
assert.equal(targetAnchor.style.top,'58px');
`));

test("obstruction colours line without hiding values or adding warning",async()=>runScenario(`
for (const status of ['obstructed', 'clear', null]) {
  nativeApi.calculate=async()=>({
    slant_range_yards:300,height_difference_metres:0,
    elevation_degrees:status ? 0.1 : null,fuze_seconds:status ? 1.2 : null,clearance_status:status,
    height_above_target_metres:null
  });
  await requestSolution();
  assert.equal($('#elevation').textContent,status ? '0.10°' : 'No solution');
  assert.equal($('#fuze').textContent,status ? '1.200 s' : '—');
  assert.doesNotMatch(modePill.textContent,/BLOCKED/);
  assert.equal(shotLine.classList.contains('obstructed'),status === 'obstructed');
  assert.equal(shotLine.classList.contains('clear'),status === 'clear');
}
`));

test("unrestricted angle is displayed as normal elevation",async()=>runScenario(`
nativeApi.calculate=async()=>({
  slant_range_yards:342,height_difference_metres:-84.3,
  elevation_degrees:-15.2,fuze_seconds:0.9,clearance_status:'clear',
  height_above_target_metres:0,elevation_source:'physics'
});
await requestSolution();
assert.equal($('#elevation').textContent,'-15.20°');
assert.equal($('#elevation-label').textContent,'ELEVATION');
`));

test("static gun start marker is distinct from crew spawn",async()=>runScenario(`
document.createElement=()=>({style:{},children:[],append(x){this.children.push(x)}});
let rendered=[];
$('#location-layer').replaceChildren=(...items)=>rendered=items;
baseScale=2;
locations=[{kind:'gun_spawn',name:'Parrott',pixel_x:20,pixel_y:30},
           {kind:'battery',name:'Crew',pixel_x:50,pixel_y:60}];
renderLocations();
assert.equal(rendered[0].style.left,'40px');
assert.equal(rendered[0].children[0].textContent,'G');
assert.match(rendered[0].children[0].title,/before movement/);
assert.match(rendered[0].children[0].className,/gun_spawn/);
assert.match(rendered[1].children[0].title,/crew spawn/);
zoom=3;translateX=5;translateY=7;updateLocationPositions();
assert.equal(rendered[0].style.left,'125px');
assert.equal(rendered[0].style.top,'187px');
assert.deepEqual(gun,{x:10,y:20});
`));

test("artillery names are visible beside their crew spawns and can be toggled without changing the mission",async()=>runScenario(`
document.createElement=()=>({style:{},children:[],append(x){this.children.push(x)}});
locations=[{kind:'battery',faction:'CSA',name:'Spawnpoint_CE_CSA_Arty_French_Forward',pixel_x:50,pixel_y:60},
  {kind:'gun_spawn',name:'Parrott',pixel_x:20,pixel_y:30}];
renderLocations();
assert.equal(locationAnchors[0].children[1].textContent,'Battery French');
assert.equal(locationAnchors[0].children[0].hidden,true);
assert.equal(locationAnchors[1].children.length,1);
assert.match(locationAnchors[0].children[0].title,/Spawnpoint_CE/);
$('#artillery-names').handlers.change({target:{checked:false}});
assert.equal(locationAnchors[0].children.length,1);
assert.equal(locationAnchors[0].hidden,true);
$('#artillery-names').handlers.change({target:{checked:true}});
assert.equal(locationAnchors[0].children[1].textContent,'Battery French');
assert.deepEqual(gun,{x:10,y:20});assert.deepEqual(target,{x:100,y:20});
`));

test("Sketcher shows artillery references without restoring the other static marker overlays",async()=>runScenario(`
document.createElement=()=>({style:{},children:[],append(x){this.children.push(x)}});
applicationMode='sketcher';
locations=[{kind:'battery',faction:'USA',name:'Spawnpoint_HP_USA_Arty_Matthews_Forward',pixel_x:50,pixel_y:60},
  {kind:'gun_spawn',name:'Parrott',pixel_x:20,pixel_y:30},{kind:'spawn',name:'Infantry',pixel_x:10,pixel_y:40}];
renderLocations();
assert.equal(locationAnchors[0].hidden,false);
assert.equal(locationAnchors[0].children[1].textContent,'Battery Matthews');
assert.equal(locationAnchors[1].hidden,true);assert.equal(locationAnchors[2].hidden,true);
$('#artillery-names').handlers.change({target:{checked:false}});
assert.ok(locationAnchors.every(anchor=>anchor.hidden));
applicationMode='calculator';renderLocations();
assert.equal(locationAnchors[0].hidden,true);
assert.equal(locationAnchors[1].hidden,false);assert.equal(locationAnchors[2].hidden,false);
`));

test("battery names keep their fixed anchor through zoom, pan and viewport edges",async()=>runScenario(`
document.createElement=()=>({style:{},offsetWidth:120,children:[],append(x){this.children.push(x)}});
locations=[{kind:'battery',faction:'CSA',name:'Spawnpoint_WR_CSA_Arty_Lane_Forward',pixel_x:50,pixel_y:30}];
renderLocations();
const name=locationAnchors[0].children[1];
const originalStyle={...name.style};
zoom=3;translateX=5;translateY=7;updateLocationPositions();
assert.equal(locationAnchors[0].style.left,'155px');
assert.equal(locationAnchors[0].style.top,'97px');
assert.deepEqual(name.style,originalStyle);
translateX=-200;updateLocationPositions();
assert.equal(locationAnchors[0].style.left,'-50px');
assert.deepEqual(name.style,originalStyle);
assert.notEqual(name.hidden,true);
assert.equal(locationAnchors[0].children[1],name);
`));

test("only compact battery names are drawn and base references stay hidden",async()=>runScenario(`
document.createElement=()=>({style:{},children:[],append(x){this.children.push(x)}});
locations=[{kind:'battery',faction:'CSA',name:'Spawnpoint_PFord_CSA_Arty_Daquin_Forward',pixel_x:50,pixel_y:60},
  {kind:'battery',faction:'CSA',name:'Spawnpoint_PFord_CSA_Arty_Base',pixel_x:20,pixel_y:30},
  {kind:'battery',faction:'USA',name:'CQ1_Spawnpoint_USA_Artillery_Staging',pixel_x:30,pixel_y:40}];
renderLocations();
assert.equal(locationAnchors[0].children[1].textContent,'Battery Daquin');
assert.equal(locationAnchors[0].children.length,2);
assert.equal(locationAnchors[1].hidden,true);assert.equal(locationAnchors[2].hidden,true);
assert.equal(locationAnchors[1].children.length,1);assert.equal(locationAnchors[2].children.length,1);
`));

test("nearby gun starts and mission markers do not move battery names",async()=>runScenario(`
document.createElement=()=>({style:{},offsetWidth:75,offsetHeight:10,children:[],append(x){this.children.push(x)}});
locations=[{kind:'battery',faction:'CSA',name:'Spawnpoint_PFord_CSA_Arty_Daquin_Forward',pixel_x:50,pixel_y:60},
  {kind:'gun_spawn',name:'Parrott',pixel_x:65,pixel_y:60}];
renderLocations();
const label=locationAnchors[0].children[1];
const originalStyle={...label.style};
const originalAnchor={...locationAnchors[0].style};
locations[1].pixel_x=51;locations[1].pixel_y=61;
gun={x:51,y:60};target={x:52,y:60};
updateLocationPositions();
assert.deepEqual(label.style,originalStyle);
assert.deepEqual(locationAnchors[0].style,originalAnchor);
`));

test("duplicate crew references share one label while separate battery positions keep their names",async()=>runScenario(`
document.createElement=()=>({style:{},children:[],append(x){this.children.push(x)}});
locations=[
  {kind:'battery',faction:'CSA',name:'Spawnpoint_RC_CSA_Arty_Manly_Forward',pixel_x:50,pixel_y:60},
  {kind:'battery',faction:'CSA',name:'Spawnpoint_RC_CSA_Arty_Manly_Forward-2',pixel_x:51,pixel_y:61},
  {kind:'battery',faction:'CSA',name:'Spawnpoint_RC_CSA_Arty_Manly_Forward-6',pixel_x:80,pixel_y:60}];
renderLocations();
assert.equal(locationAnchors.length,3);
assert.equal(locationAnchors.filter(anchor=>anchor.children.length>1).length,2);
`));

test("calibration mode change recalculates existing mission",async()=>runScenario(`
let requests=[];
nativeApi.calculate=async data=>{requests.push(data);throw Error('offline')};
$('#method-select').value='Unified physics (provisional)';
$('#calculation-mode').value='test';
$('#calculation-mode').handlers.change();
assert.equal(requests.length,1);
assert.equal(requests[0].calibration_mode,true);
assert.equal($('#impact-mode').hidden,false);
gun=null;
$('#calculation-mode').value='operational';
$('#calculation-mode').handlers.change();
assert.equal(requests.length,1);
assert.equal($('#impact-mode').hidden,true);
`));

test("airburst mode recalculates and is sent to solver",async()=>runScenario(`
let requests=[];
nativeApi.calculate=async data=>{requests.push(data);throw Error('offline')};
$('#method-select').value='Unified physics (provisional)';
$('#burst-mode').value='airburst';
$('#burst-mode').handlers.change();
assert.equal(requests.length,1);
assert.equal(requests[0].airburst_mode,true);
gun=null;
$('#burst-mode').value='ground';
$('#burst-mode').handlers.change();
assert.equal(requests.length,1);
`));

test("marker move invalidates values even when request fails",async()=>runScenario(`
latestSolution={elevation_degrees:1};
$('#elevation').textContent='1.000°'; $('#fuze').textContent='2.000 s';
shotLine.classList.add('clear');
moveMarker('target',120,30);
assert.equal(latestSolution,null);
assert.equal($('#elevation').textContent,'—');
assert.equal($('#fuze').textContent,'—');
assert.equal(shotLine.classList.contains('clear'),false);
await requestSolution();
assert.equal(latestSolution,null);
assert.equal(rangeChip.hidden,true);
`));

test("map loading and failure block placement and calculation",async()=>runScenario(`
let rejectLoad;
nativeApi.mapImage=()=>new Promise((resolve,reject)=>{rejectLoad=reject});
const loading=loadMapImage({identifier:'new-map',image_path:'maps/map-1.webp'});
const event={pointerId:1,clientX:50,clientY:50,target:{closest:()=>null}};
setMode('gun');
mapWrap.handlers.pointerdown(event); endPointer(event);
assert.deepEqual(gun,{x:10,y:20});
assert.equal(pointers.size,0);
rejectLoad(Error('offline')); await loading;
mapWrap.handlers.pointerdown(event); endPointer(event);
assert.deepEqual(gun,{x:10,y:20});
let requests=0;nativeApi.calculate=async()=>{requests++;throw Error('offline')};
await requestSolution(); assert.equal(requests,0);
`));

test("only current displayed image enables placement",async()=>runScenario(`
nativeApi.mapImage=async()=>({});
await loadMapImage({identifier:'new-map',image_path:'maps/map-1.webp'});
images[0].handlers.load();
assert.equal(mapReady,false);
mapImage.handlers.load(); assert.equal(mapReady,true);
await loadMapImage({identifier:'new-map',image_path:'maps/map-1.webp'});
mapImage.handlers.load(); assert.equal(mapReady,false);
images[1].handlers.load(); mapImage.handlers.load();
assert.equal(mapReady,true);
setMode('gun');
const event={pointerId:1,clientX:50,clientY:50,target:{closest:()=>null}};
mapWrap.handlers.pointerdown(event); endPointer(event);
assert.deepEqual(gun,{x:50,y:50});
`));

test("Sketcher map clicks use the calculator coordinate transform and map dragging does not place a gun",async()=>runScenario(`
const placed=[];
sketcher={active:true,canvasClick:point=>placed.push(point),status(){},positionMarkers(){}};
zoom=2;baseScale=0.5;translateX=10;translateY=15;
const event={pointerId:1,button:0,clientX:90,clientY:70,target:{closest:()=>null}};
mapWrap.handlers.pointerdown(event);mapWrap.handlers.pointerup(event);
assert.deepEqual(placed,[{x:80,y:55}]);
mapWrap.handlers.pointerdown(event);
mapWrap.handlers.pointermove({...event,clientX:110,clientY:80});
mapWrap.handlers.pointerup({...event,clientX:110,clientY:80});
assert.equal(placed.length,1);
`));

test("Sketcher gun buttons can be dragged and the move is saved only on pointer release",async()=>runScenario(`
let preview=null,saves=0;
sketcher={active:true,beginGunMove:id=>{assert.equal(id,'a');return true;},
  previewGunMove:point=>{preview=point;},commitGunMove(){saves++;},status(){}};
const marker={dataset:{sketchGun:'a'}};
const event={pointerId:1,button:0,clientX:10,clientY:20,target:{closest:selector=>selector==='[data-sketch-gun],[data-sketch-target]' || selector.startsWith('button,') ? marker : null}};
mapWrap.handlers.pointerdown(event);
mapWrap.handlers.pointermove({...event,clientX:110,clientY:95});
assert.deepEqual(preview,{x:110,y:95});assert.equal(saves,0);
mapWrap.handlers.pointerup({...event,clientX:110,clientY:95});
assert.equal(saves,1);assert.equal(draggingSketchGun,null);
assert.deepEqual(gun,{x:10,y:20});
`));

test("cancelled pointer drags never save a Sketcher gun move",async()=>runScenario(`
let saves=0,cancelled=0;
sketcher={active:true,beginGunMove:()=>true,previewGunMove(){},commitGunMove(){saves++;},cancelGunMove(){cancelled++;}};
const marker={dataset:{sketchGun:'a'}};
const event={pointerId:1,button:0,clientX:10,clientY:20,target:{closest:selector=>selector==='[data-sketch-gun],[data-sketch-target]' ? marker : null}};
mapWrap.handlers.pointerdown(event);mapWrap.handlers.pointermove({...event,clientX:100,clientY:60});
mapWrap.handlers.pointercancel({...event,type:'pointercancel',clientX:100,clientY:60});
assert.equal(saves,0);assert.equal(cancelled,1);assert.equal(pointers.size,0);
`));

test("starting a pinch cancels a gun drag without saving or placing a new position",async()=>runScenario(`
let saves=0,cancelled=0,placements=0;
sketcher={active:true,beginGunMove:()=>true,previewGunMove(){},commitGunMove(){saves++;},
  cancelGunMove(){cancelled++;},canvasClick(){placements++;},positionMarkers(){}};
const marker={dataset:{sketchGun:'a'}};
const first={pointerId:1,button:0,clientX:10,clientY:20,target:{closest:selector=>selector==='[data-sketch-gun],[data-sketch-target]' ? marker : null}};
const second={pointerId:2,button:0,clientX:150,clientY:100,target:{closest:()=>null}};
mapWrap.handlers.pointerdown(first);mapWrap.handlers.pointermove({...first,clientX:70,clientY:50});
mapWrap.handlers.pointerdown(second);assert.equal(cancelled,1);assert.equal(draggingSketchGun,null);
mapWrap.handlers.pointerup(second);mapWrap.handlers.pointerup(first);
assert.equal(saves,0);assert.equal(placements,0);
`));

test("Sketcher G and Escape keys arm placement and cancel its tool",async()=>runScenario(`
const tools=[];let cancelled=0;
sketcher={active:true,setTool:tool=>tools.push(tool),cancelTool(){cancelled++;}};
$('#workspace').inert=false;
const event={target:{closest:()=>null},key:'g'};
window.handlers.keydown(event);assert.deepEqual(tools,['gun']);
window.handlers.keydown({...event,key:'Escape'});assert.equal(cancelled,1);
`));

test("Sketcher Delete key delegates deletion once, respecting fields and modified keys",async()=>runScenario(`
let deletions=0,prevented=0;
sketcher={active:true,deleteSelected(){deletions++;}};
$('#workspace').inert=false;
const event={target:{closest:()=>null},key:'Delete',preventDefault(){prevented++;}};
window.handlers.keydown(event);assert.equal(deletions,1);assert.equal(prevented,1);
for(const change of [{repeat:true},{ctrlKey:true},{altKey:true},{metaKey:true},
  {target:{closest:selector=>{assert.match(selector,/input,select,textarea,.*contenteditable/);return {};}}}]) {
  window.handlers.keydown({...event,...change});
}
assert.equal(deletions,1);assert.equal(prevented,1);
$('#workspace').inert=true;window.handlers.keydown(event);assert.equal(deletions,1);
`));

test("Sketcher target pointer drags use target identity and never move calculator markers",async()=>runScenario(`
let preview=null,saves=0;
sketcher={active:true,beginGunMove:(id,kind)=>{assert.equal(id,'t');assert.equal(kind,'target');return true;},
  previewGunMove:point=>{preview=point;},commitGunMove(){saves++;}};
const marker={dataset:{sketchTarget:'t'}};
const event={pointerId:1,button:0,clientX:100,clientY:80,target:{closest:selector=>selector==='[data-sketch-gun],[data-sketch-target]' ? marker : null}};
mapWrap.handlers.pointerdown(event);mapWrap.handlers.pointermove({...event,clientX:140,clientY:90});
assert.deepEqual(preview,{x:140,y:90});assert.equal(saves,0);
mapWrap.handlers.pointerup({...event,clientX:140,clientY:90});assert.equal(saves,1);
assert.deepEqual(gun,{x:10,y:20});
`));
