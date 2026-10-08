import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

async function runScenario(code) {

const elements = new Map();
function element(key) {
  if (!elements.has(key)) {
    const classes = new Set();
    elements.set(key, {
      value:'', textContent:'', children:[], hidden:false, naturalWidth:200, naturalHeight:150,
      src:'old-map', style:{setProperty(key,value){this[key]=value}}, handlers:{},
      classList:{add:x=>classes.add(x), remove:(...xs)=>xs.forEach(x=>classes.delete(x)),
        contains:x=>classes.has(x), toggle(x,on){if(on) classes.add(x); else classes.delete(x)}},
      addEventListener(n,f){this.handlers[n]=f}, replaceChildren(...children){this.children=children}, setPointerCapture(){},
      getBoundingClientRect(){return {left:0,top:0,width:200,height:150}}
    });
  }
  return elements.get(key);
}
const images = [];
let objectSequence = 0;
const context = vm.createContext({
  document:{querySelector:element,querySelectorAll:()=>[],createElement:()=>({children:[],setAttribute(){},append(...children){this.children.push(...children)}})},
  window:{handlers:{},addEventListener(name,handler){this.handlers[name]=handler}}, assert, console, AbortController, images,
  URL:{createObjectURL:()=>`blob:map-${++objectSequence}`,revokeObjectURL(){}},
  Image:function(){this.handlers={};this.addEventListener=(n,f)=>this.handlers[n]=f;images.push(this)},
  worcalcNative:{api:{calculate:async()=>{throw Error('Calculation failed')},mapImage:async()=>{throw Error('Image failed')},recordImpact:async()=>{throw Error('Save failed')}}}
});
vm.runInContext(readFileSync(new URL('../src/map-marker.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../src/fire-readout.js',import.meta.url),'utf8'),context);
vm.runInContext(readFileSync(new URL('../src/app.js',import.meta.url),'utf8').replace(/load\(\);\s*$/, ''),context);
vm.runInContext(`
currentMap={identifier:'new-map'}; mapReady=true;
gun={x:10,y:20}; target={x:100,y:20};
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

test("map compass uses one 45 degree sector",async()=>runScenario(`
assert.deepEqual(compassGuideDirections(152), [135,180]);
assert.deepEqual(compassMinorTickDirections(152), [150,165]);
assert.deepEqual(compassGuideDirections(359), [315,0]);
assert.deepEqual(compassMinorTickDirections(359), [330,345]);
const east = rayPoint({x:50,y:60},90,142);
assert.ok(Math.abs(east.x-192)<1e-9);
assert.ok(Math.abs(east.y-60)<1e-9);
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
mapWrap.getBoundingClientRect=()=>({left:0,top:0,width:1000,height:800});
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
const event={pointerId:1,button:0,clientX:10,clientY:20,target:{closest:selector=>selector==='[data-sketch-gun]' || selector.startsWith('button,') ? marker : null}};
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
const event={pointerId:1,button:0,clientX:10,clientY:20,target:{closest:selector=>selector==='[data-sketch-gun]' ? marker : null}};
mapWrap.handlers.pointerdown(event);mapWrap.handlers.pointermove({...event,clientX:100,clientY:60});
mapWrap.handlers.pointercancel({...event,type:'pointercancel',clientX:100,clientY:60});
assert.equal(saves,0);assert.equal(cancelled,1);assert.equal(pointers.size,0);
`));

test("starting a pinch cancels a gun drag without saving or placing a new position",async()=>runScenario(`
let saves=0,cancelled=0,placements=0;
sketcher={active:true,beginGunMove:()=>true,previewGunMove(){},commitGunMove(){saves++;},
  cancelGunMove(){cancelled++;},canvasClick(){placements++;},positionMarkers(){}};
const marker={dataset:{sketchGun:'a'}};
const first={pointerId:1,button:0,clientX:10,clientY:20,target:{closest:selector=>selector==='[data-sketch-gun]' ? marker : null}};
const second={pointerId:2,button:0,clientX:150,clientY:100,target:{closest:()=>null}};
mapWrap.handlers.pointerdown(first);mapWrap.handlers.pointermove({...first,clientX:70,clientY:50});
mapWrap.handlers.pointerdown(second);assert.equal(cancelled,1);assert.equal(draggingSketchGun,null);
mapWrap.handlers.pointerup(second);mapWrap.handlers.pointerup(first);
assert.equal(saves,0);assert.equal(placements,0);
`));

test("Sketcher G and Escape keys arm placement and cancel its tool",async()=>runScenario(`
const tools=[];let cancelled=0;
sketcher={active:true,setTool:tool=>tools.push(tool),cancelTool(){cancelled++;}};
$('#app-chooser').hidden=true;
const event={target:{closest:()=>null},key:'g'};
window.handlers.keydown(event);assert.deepEqual(tools,['gun']);
window.handlers.keydown({...event,key:'Escape'});assert.equal(cancelled,1);
`));

test("Sketcher Delete key delegates deletion once, respecting fields and modified keys",async()=>runScenario(`
let deletions=0,prevented=0;
sketcher={active:true,deleteSelected(){deletions++;}};
$('#app-chooser').hidden=true;
const event={target:{closest:()=>null},key:'Delete',preventDefault(){prevented++;}};
window.handlers.keydown(event);assert.equal(deletions,1);assert.equal(prevented,1);
for(const change of [{repeat:true},{ctrlKey:true},{altKey:true},{metaKey:true},
  {target:{closest:selector=>{assert.match(selector,/input,select,textarea,.*contenteditable/);return {};}}}]) {
  window.handlers.keydown({...event,...change});
}
assert.equal(deletions,1);assert.equal(prevented,1);
$('#app-chooser').hidden=false;window.handlers.keydown(event);assert.equal(deletions,1);
`));
