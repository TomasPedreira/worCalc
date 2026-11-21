import test from "node:test";
import assert from "node:assert/strict";
import "../src/map-marker.js";
import "../src/fire-readout.js";
import "../src/sketch-model.js";
import "../src/sketcher.js";
const M=globalThis.WorCalcSketch;
function setup() {
  const elements=new Map();
  const element=()=>({value:"",hidden:false,disabled:false,textContent:"",children:[],style:{},handlers:{},open:false,
    classList:{toggle(){}},attributes:{},setAttribute(name,value){this.attributes[name]=value;},addEventListener(name,handler){this.handlers[name]=handler;},
    replaceChildren(...children){this.children=children;},append(...children){this.children.push(...children);},
    focus(){},showModal(){this.open=true;},close(){this.open=false;},click(){this.handlers.click?.();}});
  const $=selector=>{if(!elements.has(selector))elements.set(selector,element());return elements.get(selector);};
  globalThis.document={querySelector:$,createElement:element}; globalThis.confirm=()=>true;
  const map={identifier:"map-1",name:"Test map",width_pixels:200,height_pixels:150};
  const options={weapons:{Ordnance:["Shell","Case"],Napoleon:["Shell"]},defaults:{cannon:"Ordnance",projectile:"Shell",method:"physics"}};
  const plan=M.createPlan(map,[],"Ordnance");
  plan.guns=[{id:"a",name:"A",x:10,y:20,cannon:"Ordnance"},{id:"b",name:"B",x:20,y:30,cannon:"Ordnance"}];
  const solution={map_id:"map-1",cannon:"Ordnance",projectile:"Shell",airburst_mode:false,calibration_mode:false,
    elevation_degrees:1.234,fuze_seconds:2.456,bearing_degrees:90,slant_range_yards:300,clearance_status:"clear",height_above_target_metres:0};
  const setting={projectile:"Shell",airburst_mode:false,elevation_degrees:1.8,fuze_seconds:3.1,notes:"Fence",solution};
  M.saveConfiguration(plan,"a",{id:"t",name:"Bridge",x:100,y:80},setting);
  let saved,mission,status,writes=0;
  const storage={load:async()=>({version:1,maps:{"map-1":plan}}),save:async data=>{saved=M.copy(data);writes++;},export:async()=>"exported"};

  const sketch=new globalThis.WorCalcSketcher({storage,calculate:async()=>solution,map:()=>map,locations:()=>[],locationsReady:()=>true,mapReady:()=>true,
    options:()=>options,position:point=>point,viewport:()=>({width:500,height:400}),fit:()=>{},status:value=>{status=value;},mission:(...values)=>{mission=values;}});
  return {sketch,$,map,options,solution,get saved(){return saved;},get mission(){return mission;},get status(){return status;},get writes(){return writes;}};
}
async function initialized() {const f=setup();await f.sketch.initialize([f.map],f.options);await f.sketch.enter();return f;}
const flush=async()=>{for(let n=0;n<8;n++)await Promise.resolve();};

test("old alignment firing cards stay hidden and recalculation preserves notes without reusing overrides",async()=>{
  const f=setup();
  f.map.coordinate_revision=1;
  f.map.coordinate_migration={from_revision:0,gun_positions:[{old_x:10,old_y:20,x:15,y:24}]};
  // The stored fixture was created under the original projection.
  await f.sketch.initialize([f.map],f.options); await f.sketch.enter();
  assert.equal(f.writes,1);
  f.sketch.selectGun("a"); f.sketch.selectTarget("t");
  assert.equal(f.$("#sketch-solution").hidden,true);
  assert.equal(f.$("#sketch-readouts").children.length,0);
  assert.match(f.$("#sketch-help").textContent,/1 saved firing setting needs recalculation/);
  f.sketch.toggleEdit(); f.sketch.selectGun("a"); f.sketch.selectTarget("t");
  assert.equal(f.$("#sketch-angle").value,""); assert.equal(f.$("#sketch-fuze").value,"");
  assert.equal(f.$("#sketch-notes").value,"Fence");
  assert.match(f.$("#sketch-simulation").textContent,/Calculate new/);
  f.solution.coordinate_revision=1;
  await f.sketch.calculateDraft(false); f.sketch.useDefaults(); await f.sketch.saveDraft();
  assert.equal(f.sketch.plan().configurations[0].solution.coordinate_revision,1);
  assert.equal(f.sketch.plan().configurations[0].notes,"Fence");
  assert.equal(M.outdatedConfigurationCount(f.sketch.plan()),0);
  assert.equal(f.sketch.plan().alignment_history[0].configurations[0].elevation_degrees,1.8);
});

test("saved guns render and move without repositioning battery references",async()=>{
  const f=await initialized();
  const layouts=[];
  f.sketch.hooks.referenceLayout=()=>layouts.push(f.sketch.markers.filter(marker=>marker.type==='gun').map(marker=>({
    id:marker.point.id,left:marker.button.style.left,top:marker.button.style.top
  })));
  f.sketch.render();
  assert.ok(f.sketch.markers.some(marker=>marker.point.id==='a' && marker.button.style.left==='10px' && marker.button.style.top==='20px'));
  f.sketch.toggleEdit();
  assert.equal(f.sketch.beginGunMove('a'),true);
  f.sketch.previewGunMove({x:70,y:80});
  assert.ok(f.sketch.markers.some(marker=>marker.point.id==='a' && marker.button.style.left==='70px' && marker.button.style.top==='80px'));
  assert.equal(layouts.length,0);
  assert.equal(f.writes,0);
});
test("workspace modes expose state and View discards edits without saving",async()=>{
  const f=await initialized();f.sketch.selectGun("a");
  assert.equal(f.$("#sketch-view").attributes["aria-pressed"],"true");
  assert.equal(f.$("#sketch-edit").attributes["aria-pressed"],"false");
  f.$("#sketch-view").click();assert.equal(f.sketch.editing,false);
  f.$("#sketch-edit").click();f.$("#sketch-x").value="80";
  assert.equal(f.$("#sketch-edit-notice").hidden,false);
  assert.equal(f.$("#sketch-edit").attributes["aria-pressed"],"true");
  f.$("#sketch-view").click();assert.equal(f.sketch.draft,null);
  assert.equal(f.$("#sketch-edit-notice").hidden,true);
  assert.equal(f.sketch.plan().guns[0].x,10);assert.equal(f.writes,0);
});
test("saved connections and solution inspector follow selection without calculations",async()=>{
  const f=await initialized();f.sketch.hooks.calculate=()=>{throw Error("Viewing must not calculate");};
  f.sketch.selectGun("a");
  const line=f.$("#sketch-connections").children[0];
  assert.equal(line.style.left,"10px");assert.equal(line.style.top,"20px");
  assert.equal(line.style.width,`${Math.hypot(90,60)}px`);
  assert.equal(f.$("#sketch-solution").hidden,true);
  f.sketch.selectTarget("t");
  const card=f.$("#sketch-solution");assert.equal(card.hidden,false);
  assert.equal(card.children[1].children[0].children[1].textContent,"1.80°");
  assert.equal(card.children[1].children[1].children[1].textContent,"3.100 s");
  assert.equal(card.children[3].textContent,"Fence");
  f.sketch.toggleEdit();assert.equal(f.$("#sketch-connections").children.length,0);assert.equal(card.hidden,true);
  f.sketch.toggleEdit();f.sketch.selectGun("b");assert.equal(f.$("#sketch-connections").children.length,0);assert.equal(card.hidden,true);
  f.sketch.leave();assert.equal(f.$("#sketch-connections").children.length,0);assert.equal(f.writes,0);
});
test("shared target list includes unconfigured points and uses normal target selection",async()=>{
  const f=await initialized();f.sketch.plan().targets.push({id:"unlinked",x:160,y:120});f.sketch.render();
  assert.equal(f.$("#sketch-shared-count").textContent,"2");
  const rows=f.$("#sketch-shared-list").children;
  assert.equal(rows[0].children[0].textContent,"1 saved solution");
  assert.equal(rows[1].children[0].textContent,"0 saved solutions");
  rows[1].click();assert.equal(f.sketch.targetId,"unlinked");assert.equal(f.sketch.gunId,null);
  assert.equal(f.$("#sketch-solution").hidden,true);assert.equal(f.writes,0);
});
test("Sketcher uses the calculator marker shapes without labels or tooltips and retains selection hooks",async()=>{
  const f=await initialized();
  const markers=f.$("#sketch-layer").children;
  for(const [index,type,position] of [[0,"gun","10, 20"],[2,"target","100, 80"]]) {
    const button=markers[index],shared=globalThis.WorCalcMapMarkers.create(type,null);
    assert.match(button.className,/marker-anchor/);
    assert.equal(button.type,"button");
    assert.equal(button.attributes["aria-label"],`${type === "gun" ? "Gun" : "Target"} at ${position}`);
    assert.equal(button.title,undefined);
    assert.equal(button.children.length,1);
    assert.equal(button.textContent,"");
    assert.equal(button.children[0].className,shared.className);
    assert.equal(button.children[0].children.length,shared.children.length);
    assert.equal(button.children[0].children.length,0);
  }
  assert.equal(markers[0].attributes["data-sketch-gun"],"a");
  markers[0].click();assert.equal(f.sketch.gunId,"a");
  f.$("#sketch-layer").children[2].click();assert.equal(f.mission[2].fuze_seconds,3.1);
});

test("view selection reads saved values and highlights only the selected gun's configurations",async()=>{
  const f=await initialized(); f.sketch.selectGun("a");
  assert.match(f.$("#sketch-layer").children[2].className,/configured/);
  f.sketch.selectTarget("t"); assert.equal(f.mission[2].elevation_degrees,1.8);
  assert.equal(f.mission[2].fuze_seconds,3.1);assert.equal(f.mission[2].clearance_status,null);
  assert.equal(f.mission[2].height_above_target_metres,null);
  f.sketch.selectGun("b"); assert.match(f.$("#sketch-layer").children[2].className,/dimmed/);
  f.sketch.selectTarget("t"); assert.equal(f.mission[2],null);
  f.sketch.canvasClick({x:120,y:90}); assert.equal(f.writes,0);
});
test("selecting a gun reveals every saved firing window without a target click or calculation",async()=>{
  const f=await initialized();
  f.sketch.hooks.calculate=async()=>{throw Error("Viewing must not calculate");};
  const settings=M.copy(M.configuration(f.sketch.plan(),"a","t"));
  await f.sketch.store.update(library=>M.saveConfiguration(library.maps["map-1"],"a",{id:"second",name:"Road",x:145,y:100},
    {...settings,elevation_degrees:2.2,fuze_seconds:3.8}));
  const writes=f.writes;f.sketch.selectGun("a");
  const windows=f.$("#sketch-readouts").children;
  assert.equal(windows.length,2);assert.equal(windows[0].className,"range-chip");
  assert.equal(windows[0].children[0].children[1].textContent,"1.80°");
  assert.equal(windows[0].children[2].children[1].textContent,"3.100 s");
  assert.equal(windows[1].children[0].children[1].textContent,"2.20°");
  assert.equal(windows[1].children[2].children[1].textContent,"3.800 s");
  assert.equal(windows[0].hidden,false);assert.ok(windows[0].style.left.endsWith("px"));
  f.sketch.selectGun("b");assert.equal(f.$("#sketch-readouts").children.length,0);
  assert.equal(f.writes,writes);assert.equal(f.mission[2],null);
});
test("edit, save and return to view reveal the new configuration and keep other firing windows",async()=>{
  const f=await initialized();f.sketch.selectGun("a");assert.equal(f.$("#sketch-readouts").children.length,1);
  f.sketch.toggleEdit();assert.equal(f.$("#sketch-readouts").children.length,0);
  f.sketch.setTool("target");await f.sketch.canvasClick({x:155,y:110});await f.sketch.calculateDraft(false);
  assert.equal(f.$("#sketch-angle").value,f.solution.elevation_degrees);
  f.$("#sketch-angle").value="2.2";f.$("#sketch-fuze").value="3.8";
  await f.sketch.saveDraft();assert.equal(f.sketch.draft.kind,"target");
  f.sketch.toggleEdit();assert.equal(f.sketch.editing,false);assert.equal(f.mission[2].elevation_degrees,2.2);
  assert.equal(f.mission[2].fuze_seconds,3.8);assert.equal(f.$("#sketch-readouts").children.length,1);
  f.sketch.selectGun("a");assert.equal(f.$("#sketch-readouts").children.length,2);
  assert.match(f.$("#sketch-state").textContent,/MAP VIEW/);
});
test("a shared target reveals only the selected gun's values and dimmed targets clear the focused mission",async()=>{
  const f=await initialized();const settings=M.copy(M.configuration(f.sketch.plan(),"a","t"));
  await f.sketch.store.update(library=>{
    const plan=library.maps["map-1"];
    M.saveConfiguration(plan,"b",plan.targets[0],{...settings,elevation_degrees:2.4,fuze_seconds:4.1});
    M.saveConfiguration(plan,"b",{id:"b-only",name:"Hill",x:155,y:110},settings);
  });
  f.sketch.selectGun("b");assert.equal(f.$("#sketch-readouts").children[0].children[0].children[1].textContent,"2.40°");
  f.sketch.selectGun("a");assert.equal(f.$("#sketch-readouts").children.length,1);
  f.sketch.selectTarget("t");assert.equal(f.mission[2].elevation_degrees,1.8);
  f.sketch.selectTarget("b-only");assert.equal(f.mission[2],null);assert.equal(f.sketch.targetId,"b-only");
  assert.deepEqual(f.sketch.selection,{kind:"target",id:"b-only"});
});
test("readouts follow pan and zoom, hide offscreen and are removed on leaving Sketcher",async()=>{
  const f=await initialized();f.sketch.selectGun("a");const chip=f.$("#sketch-readouts").children[0],before=chip.style.left;
  f.sketch.hooks.position=point=>({x:point.x+100,y:point.y+60});f.sketch.positionMarkers();
  assert.notEqual(chip.style.left,before);
  f.sketch.hooks.position=()=>({x:-100,y:0});f.sketch.positionMarkers();assert.equal(chip.hidden,true);
  f.sketch.leave();assert.equal(f.$("#sketch-readouts").children.length,0);
});

test("the gun selector distinguishes nearby or overlapping map markers",async()=>{
  const f=await initialized();
  assert.deepEqual(f.$("#sketch-gun-select").children.map(option=>option.value),["","a","b"]);
  f.$("#sketch-gun-select").handlers.change({target:{value:"a"}});
  assert.equal(f.sketch.gunId,"a");assert.equal(f.$("#sketch-target-list").children.length,1);
  f.$("#sketch-gun-select").handlers.change({target:{value:"b"}});
  assert.equal(f.sketch.gunId,"b");assert.equal(f.$("#sketch-target-list").children.length,0);
  assert.equal(f.$("#sketch-gun-select").value,"b");
  assert.equal(f.writes,0);
});
test("Place gun requires Edit before a map click saves a freely positioned gun",async()=>{
  const f=await initialized();assert.equal(f.sketch.editing,false);assert.equal(f.$("#sketch-add-gun").hidden,true);
  f.$("#sketch-add-gun").click();assert.equal(f.sketch.editing,false);assert.equal(f.sketch.tool,null);
  f.sketch.toggleEdit();f.$("#sketch-add-gun").click();assert.equal(f.sketch.editing,true);assert.equal(f.sketch.tool,"gun");
  await f.sketch.canvasClick({x:160,y:110});
  const gun=f.saved.maps["map-1"].guns.at(-1);
  assert.deepEqual({x:gun.x,y:gun.y,cannon:gun.cannon},{x:160,y:110,cannon:"Ordnance"});
  assert.equal(f.sketch.gunId,gun.id);assert.equal(f.sketch.tool,null);assert.equal(f.sketch.draft.kind,"gun");
  assert.equal(f.saved.maps["map-1"].configurations.length,1);
});
test("gun placement is independent of default positions and nearby guns do not snap",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.store.data.maps["map-1"].guns[0].cannon="Napoleon";
  f.sketch.store.data.maps["map-1"].configurations=[];f.sketch.selectGun("a");f.sketch.setTool("gun");
  await f.sketch.canvasClick({x:11,y:22});
  assert.equal(f.saved.maps["map-1"].guns.length,3);
  assert.equal(f.saved.maps["map-1"].guns.at(-1).x,11);assert.equal(f.saved.maps["map-1"].guns.at(-1).cannon,"Napoleon");
});
test("a map without default guns supports several freely placed guns",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.store.data.maps["map-1"]=M.createPlan(f.map,[],"Ordnance");
  for(const point of [{x:35,y:50},{x:145,y:80}]) {f.sketch.setTool("gun");await f.sketch.canvasClick(point);}
  assert.equal(f.saved.maps["map-1"].guns.length,2);assert.equal(f.sketch.plan().guns[0].x,35);
});
test("failed or blocked placements preserve the saved plan",async()=>{
  const f=await initialized();f.sketch.toggleEdit();const before=M.copy(f.sketch.store.data);
  f.sketch.setTool("gun");f.sketch.hooks.mapReady=()=>false;await f.sketch.canvasClick({x:120,y:60});assert.equal(f.writes,0);
  f.sketch.hooks.mapReady=()=>true;f.sketch.store.adapter.save=async()=>{throw Error("disk full");};
  await f.sketch.canvasClick({x:120,y:60});assert.deepEqual(f.sketch.store.data,before);assert.match(f.status,/disk full/);
  f.sketch.loadError="Invalid stored plan";f.sketch.editing=false;f.sketch.setTool("gun");assert.equal(f.sketch.editing,false);
});
test("gun drag previews do not write until release and cancellation restores the marker",async()=>{
  const f=await initialized();assert.equal(f.sketch.beginGunMove("a"),false);
  f.sketch.toggleEdit();assert.equal(f.sketch.beginGunMove("a"),true);
  f.sketch.previewGunMove({x:125,y:95});
  assert.equal(f.sketch.plan().guns[0].x,10);assert.equal(f.writes,0);
  assert.equal(f.$("#sketch-layer").children[0].style.left,"125px");
  f.sketch.cancelTool();assert.equal(f.$("#sketch-layer").children[0].style.left,"10px");assert.equal(f.writes,0);
});
test("saving a moved gun preserves other guns, shared targets and independent settings",async()=>{
  const f=await initialized();
  await f.sketch.store.update(library=>M.saveConfiguration(library.maps["map-1"],"b",f.sketch.plan().targets[0],
    {...M.configuration(f.sketch.plan(),"a","t"),elevation_degrees:2.2}));
  f.sketch.toggleEdit();f.sketch.beginGunMove("a");f.sketch.previewGunMove({x:60,y:40});await f.sketch.commitGunMove();
  const plan=f.saved.maps["map-1"];assert.equal(plan.guns[0].x,60);assert.equal(plan.guns[1].x,20);
  assert.equal(plan.targets.length,1);assert.equal(M.configuration(plan,"a","t").elevation_degrees,1.8);
  assert.equal(M.configuration(plan,"b","t").elevation_degrees,2.2);
  assert.equal(f.sketch.gunId,"a");assert.equal(f.sketch.gunMove,null);
});
test("failed moves restore the saved position and its settings",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.beginGunMove("a");f.sketch.previewGunMove({x:60,y:40});
  f.sketch.store.adapter.save=async()=>{throw Error("disk full");};await f.sketch.commitGunMove();
  assert.equal(f.sketch.plan().guns[0].x,10);assert.equal(M.configuration(f.sketch.plan(),"a","t").elevation_degrees,1.8);
  assert.equal(f.$("#sketch-layer").children[0].style.left,"10px");assert.equal(f.sketch.gunMove,null);assert.match(f.status,/disk full/);
});
test("adding a configuration to an existing point preserves the other gun's settings",async()=>{
  const f=await initialized();f.sketch.selectGun("b");f.sketch.toggleEdit();f.sketch.selectTarget("t");await f.sketch.calculateDraft(false);
  assert.equal(f.$("#sketch-angle").value,1.234); assert.equal(f.$("#sketch-fuze").value,2.456);
  f.$("#sketch-angle").value="2.2";f.$("#sketch-fuze").value="3.8";
  await f.sketch.saveDraft();
  const plan=f.saved.maps["map-1"];assert.equal(plan.targets.length,1);assert.equal(plan.configurations.length,2);
  assert.equal(M.configuration(plan,"a","t").elevation_degrees,1.8);
  assert.equal(M.configuration(plan,"b","t").elevation_degrees,2.2);
  assert.equal(f.sketch.draft.kind,"target");assert.equal(f.$("#sketch-form").hidden,false);
});
test("opening an existing configuration keeps saved overrides until defaults are requested",async()=>{
  const f=await initialized();f.sketch.selectGun("a");f.sketch.toggleEdit();f.sketch.selectTarget("t");await flush();
  assert.equal(f.$("#sketch-angle").value,1.8);assert.equal(f.$("#sketch-fuze").value,3.1);
  f.sketch.useDefaults();assert.equal(f.$("#sketch-angle").value,1.234);
  await f.sketch.saveDraft();assert.equal(M.configuration(f.saved.maps["map-1"],"a","t").elevation_degrees,1.234);
});
test("cancelling a new target and stale calculations cannot modify saved plans",async()=>{
  const f=await initialized();f.sketch.selectGun("a");f.sketch.toggleEdit();
  let finish;f.sketch.hooks.calculate=()=>new Promise(resolve=>{finish=resolve;});
  f.sketch.editTarget({id:"new",x:130,y:90});f.sketch.calculateDraft(false);f.sketch.closeEditor();
  finish(f.solution);await flush();assert.equal(f.sketch.draft,null);assert.equal(f.writes,0);
  assert.equal(f.sketch.plan().targets.length,1);
});
test("stale ammunition calculations are ignored and failures cannot be saved",async()=>{
  const f=await initialized();f.sketch.selectGun("a");f.sketch.toggleEdit();
  let finish;f.sketch.hooks.calculate=()=>new Promise((resolve,reject)=>{finish=resolve;finish.reject=reject;});
  f.sketch.selectTarget("t");f.sketch.calculateDraft(false);const first=finish;
  f.$("#sketch-ammo").value="Case";f.sketch.calculateDraft(false);
  finish.reject(Error("No solution"));await flush();
  first(f.solution);await flush();
  assert.equal(f.$("#sketch-save").disabled,true);assert.equal(f.sketch.draft.solution,null);
  f.sketch.hooks.calculate=async()=>{throw Error("No solution");};
  await f.sketch.saveDraft();assert.equal(f.writes,0);
});
test("save errors leave the side editor and previous settings intact for a retry",async()=>{
  const f=await initialized();f.sketch.selectGun("a");f.sketch.toggleEdit();f.sketch.selectTarget("t");await flush();
  f.sketch.store.adapter.save=async()=>{throw Error("disk full");};
  f.$("#sketch-angle").value="2.2";await f.sketch.saveDraft();
  assert.equal(f.$("#sketch-form").hidden,false);assert.match(f.$("#sketch-editor-status").textContent,/disk full/);
  assert.equal(M.configuration(f.sketch.plan(),"a","t").elevation_degrees,1.8);
});
test("changing cannon type invalidates only that gun's configurations",async()=>{
  const f=await initialized();f.sketch.selectGun("a");f.sketch.toggleEdit();f.sketch.editGun();
  f.$("#sketch-weapon").value="Napoleon";await f.sketch.saveDraft();
  assert.equal(f.saved.maps["map-1"].guns[0].cannon,"Napoleon");
  assert.equal(f.saved.maps["map-1"].targets.length,1);assert.equal(f.saved.maps["map-1"].configurations.length,0);
});
test("hidden target fields are disabled while editing a gun",async()=>{
  const f=await initialized();f.sketch.selectGun("a");f.sketch.toggleEdit();f.sketch.selectTarget("t");await flush();
  assert.equal(f.$("#sketch-target-fields").disabled,false);assert.equal(f.$("#sketch-gun-fields").disabled,true);
  f.sketch.selectGun("a");
  assert.equal(f.$("#sketch-target-fields").disabled,true);assert.equal(f.$("#sketch-gun-fields").disabled,false);
});
test("invalid file imports leave saved settings intact and report the error",async()=>{
  const f=await initialized();f.sketch.toggleEdit();const before=M.copy(f.sketch.store.data);
  await f.sketch.importFile({size:20,text:async()=>JSON.stringify({version:99,maps:{}})});
  assert.deepEqual(f.sketch.store.data,before);assert.match(f.status,/IMPORT FAILED/);assert.equal(f.sketch.busy,false);
});
test("a valid file import updates included maps after confirmation",async()=>{
  const f=await initialized();f.sketch.toggleEdit();const imported=M.copy(f.sketch.store.data);
  imported.maps["map-1"].configurations[0].elevation_degrees=2.4;
  let confirms=0;globalThis.confirm=()=>{confirms++;return true;};
  await f.sketch.importFile({size:20,text:async()=>JSON.stringify(imported)});
  assert.equal(confirms,1);assert.equal(M.configuration(f.sketch.plan(),"a","t").elevation_degrees,2.4);
  assert.equal(f.status,"PLANS IMPORTED AND SAVED");
});

test("Edit mode opens editable details in the right column without calculations or writes",async()=>{
  const f=await initialized();f.sketch.toggleEdit();let inspections=0;f.sketch.hooks.inspect=()=>{inspections++;};
  f.sketch.hooks.calculate=async()=>{throw Error("Selection must not calculate");};
  f.sketch.selectGun("a");
  assert.equal(f.sketch.editing,true);assert.equal(f.$("#sketch-form").hidden,false);
  assert.equal(f.$("#sketch-gun-fields").disabled,false);assert.equal(f.$("#sketch-x").value,10);
  assert.equal(f.$("#sketch-details-title").textContent,"Gun");
  f.sketch.selectTarget("t");assert.equal(f.$("#sketch-details-title").textContent,"Target");
  assert.equal(f.$("#sketch-target-fields").disabled,false);assert.equal(f.$("#sketch-angle").value,1.8);
  assert.equal(f.$("#sketch-fuze").value,3.1);assert.equal(f.$("#sketch-x").value,100);
  assert.equal(inspections,2);assert.equal(f.writes,0);
  f.$("#sketch-angle").value="2.1";await f.sketch.saveDraft();
  assert.equal(M.configuration(f.saved.maps["map-1"],"a","t").elevation_degrees,2.1);
});

test("deletion acts on the last selected object and never falls back to the firing gun",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.selectGun("a");f.sketch.selectTarget("t");
  f.$("#sketch-delete").click();await flush();
  assert.equal(f.sketch.plan().guns.length,2);assert.equal(f.sketch.plan().targets.length,0);
  assert.equal(f.sketch.gunId,"a");assert.equal(f.sketch.selection,null);assert.equal(f.sketch.draft,null);
  const writes=f.writes;await f.sketch.deleteSelected();assert.equal(f.writes,writes);
  f.sketch.selectGun("b");await f.sketch.deleteSelected();assert.deepEqual(f.sketch.plan().guns.map(gun=>gun.id),["a"]);
});

test("selecting a gun after a target deletes that gun and keeps the shared target and other settings",async()=>{
  const f=await initialized();f.sketch.toggleEdit();await f.sketch.store.update(library=>M.saveConfiguration(library.maps["map-1"],"b",f.sketch.plan().targets[0],
    {...M.configuration(f.sketch.plan(),"a","t"),elevation_degrees:2.2}));
  f.sketch.selectGun("b");f.sketch.selectTarget("t");f.sketch.selectGun("a");await f.sketch.deleteSelected();
  assert.deepEqual(f.sketch.plan().guns.map(gun=>gun.id),["b"]);assert.equal(f.sketch.plan().targets.length,1);
  assert.equal(M.configuration(f.sketch.plan(),"b","t").elevation_degrees,2.2);
  assert.equal(f.sketch.gunId,null);assert.equal(f.$("#sketch-form").hidden,true);
});

test("a target is editable and deletable even without a selected gun",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.selectTarget("t");
  assert.equal(f.sketch.gunId,null);assert.equal(f.$("#sketch-target-fields").disabled,true);
  f.$("#sketch-x").value="115";await f.sketch.saveDraft();
  assert.equal(f.sketch.plan().targets[0].x,115);assert.equal(f.sketch.plan().configurations.length,0);
  await f.sketch.deleteSelected();assert.equal(f.sketch.plan().targets.length,0);assert.equal(f.sketch.plan().guns.length,2);
});

test("failed deletion retains the selected point, editor and every saved configuration for retry",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.selectGun("a");f.sketch.selectTarget("t");const before=M.copy(f.sketch.store.data);
  f.sketch.store.adapter.save=async()=>{throw Error("disk full");};await f.sketch.deleteSelected();
  assert.deepEqual(f.sketch.store.data,before);assert.deepEqual(f.sketch.selection,{kind:"target",id:"t"});
  assert.equal(f.$("#sketch-form").hidden,false);assert.match(f.$("#sketch-editor-status").textContent,/disk full/);
});

test("deleting an unsaved target discards it without deleting the active gun or writing",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.selectGun("a");f.sketch.selectTarget("t");assert.equal(f.mission[2].elevation_degrees,1.8);
  f.sketch.setTool("target");await f.sketch.canvasClick({x:155,y:110});await flush();
  assert.equal(f.mission[1],null);assert.equal(f.mission[2],null);
  assert.equal(f.$("#sketch-layer").children.length,4);await f.sketch.deleteSelected();
  assert.equal(f.$("#sketch-layer").children.length,3);assert.equal(f.sketch.plan().guns.length,2);
  assert.equal(f.sketch.plan().targets.length,1);assert.equal(f.writes,0);
});

test("saving target coordinates recalculates the current gun and invalidates only that point's other configurations",async()=>{
  const f=await initialized();f.sketch.toggleEdit();await f.sketch.store.update(library=>M.saveConfiguration(library.maps["map-1"],"b",f.sketch.plan().targets[0],
    {...M.configuration(f.sketch.plan(),"a","t"),elevation_degrees:2.2}));
  let requests=[];f.sketch.hooks.calculate=async request=>{requests.push(request);return f.solution;};
  f.sketch.selectGun("a");f.sketch.selectTarget("t");f.$("#sketch-x").value="110";
  await f.sketch.saveDraft();assert.deepEqual(requests[0].target,{x:110,y:80});
  assert.equal(f.sketch.plan().targets[0].x,110);assert.equal(M.configuration(f.sketch.plan(),"b","t"),null);
  assert.equal(M.configuration(f.sketch.plan(),"a","t").elevation_degrees,f.solution.elevation_degrees);
});

test("saving gun coordinates from the inspector clears only its own settings",async()=>{
  const f=await initialized();f.sketch.toggleEdit();await f.sketch.store.update(library=>M.saveConfiguration(library.maps["map-1"],"b",f.sketch.plan().targets[0],
    {...M.configuration(f.sketch.plan(),"a","t"),elevation_degrees:2.2}));
  f.sketch.selectGun("a");f.$("#sketch-x").value="60";f.$("#sketch-y").value="40";await f.sketch.saveDraft();
  assert.equal(f.sketch.plan().guns[0].x,60);assert.equal(M.configuration(f.sketch.plan(),"a","t"),null);
  assert.equal(M.configuration(f.sketch.plan(),"b","t").elevation_degrees,2.2);
});

test("cancel resets inspector changes without writing and leaves saved selection active",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.selectGun("a");f.$("#sketch-x").value="60";f.sketch.cancelDraft();
  assert.equal(f.$("#sketch-x").value,10);assert.deepEqual(f.sketch.selection,{kind:"gun",id:"a"});
  f.sketch.selectTarget("t");f.$("#sketch-angle").value="9";f.sketch.cancelDraft();
  assert.equal(f.$("#sketch-angle").value,1.8);assert.equal(f.writes,0);
});

test("legacy storage hashes never appear in markers, tooltips, inspector, selectors or lists",async()=>{
  const f=await initialized(),plan=f.sketch.plan();
  const gunId="gun-17c9cb45-1736-4563-9518-9bb89512319a",targetId="target-62f2448e-473c-4669-a6d0-7bc9bcd5a5f3";
  plan.guns[0].id=gunId;plan.targets[0].id=targetId;
  plan.configurations[0].gun_id=gunId;plan.configurations[0].target_id=targetId;
  const before=M.copy(plan);
  const texts=element=>[element.textContent,...element.children.flatMap(texts)].join(" ");
  for(const editing of [false,true]) {
    f.sketch.editing=editing;f.sketch.selectGun(gunId);
    if(editing)assert.equal(f.$("#sketch-details-title").textContent,"Gun");
    f.sketch.selectTarget(targetId);
    if(editing)assert.equal(f.$("#sketch-details-title").textContent,"Target");
    for(const selector of ["#sketch-layer","#sketch-gun-select","#sketch-target-list","#sketch-editor-context","#sketch-selected-gun","#sketch-readouts"]) {
      const text=texts(f.$(selector));assert.ok(!text.includes(gunId));assert.ok(!text.includes(targetId));
    }
    for(const {button} of f.sketch.markers) {
      assert.equal(button.children[0].children.length,0);assert.equal(button.title,undefined);
      assert.ok(!button.attributes["aria-label"].includes(gunId));assert.ok(!button.attributes["aria-label"].includes(targetId));
    }
  }
  assert.deepEqual(f.sketch.plan(),before);assert.equal(f.writes,0);
  await f.sketch.deleteSelected();assert.equal(f.status,"TARGET DELETED");
});

test("target drag works in Edit mode and retains every pre-calculated cannon card without calculating",async()=>{
  const f=await initialized();f.sketch.toggleEdit();
  await f.sketch.store.update(library=>M.saveConfiguration(library.maps["map-1"],"b",f.sketch.plan().targets[0],
    {...M.configuration(f.sketch.plan(),"a","t"),elevation_degrees:2.2}));
  const settings=M.copy(f.sketch.plan().configurations),writes=f.writes;
  f.sketch.hooks.calculate=()=>{throw Error("Dragging must never calculate");};
  assert.equal(f.sketch.beginGunMove("t","target"),true);
  f.sketch.previewGunMove({x:130,y:100});
  assert.equal(f.$("#sketch-layer").children[2].style.left,"130px");assert.equal(f.writes,writes);
  await f.sketch.commitGunMove();
  assert.equal(f.sketch.plan().targets[0].x,130);assert.deepEqual(f.sketch.plan().configurations,settings);
  assert.equal(f.writes,writes+1);
});

test("clicking a shared target offers both cannons and only selects one when requested",async()=>{
  const f=await initialized();
  await f.sketch.store.update(library=>M.saveConfiguration(library.maps["map-1"],"b",f.sketch.plan().targets[0],
    {...M.configuration(f.sketch.plan(),"a","t"),elevation_degrees:2.2}));
  f.sketch.hooks.calculate=()=>{throw Error("Selection must never calculate");};
  f.sketch.selectGun("a");f.$("#sketch-layer").children[2].click();
  assert.equal(f.sketch.gunId,null);assert.equal(f.$("#sketch-gun-options").children.length,2);
  f.$("#sketch-gun-options").children[1].click();
  assert.equal(f.sketch.gunId,"b");assert.equal(f.mission[2].elevation_degrees,2.2);assert.equal(f.$("#sketch-form").hidden,true);
  assert.equal(f.$("#sketch-gun-options").children.length,2);
});

test("Add target can link an existing target to a different cannon",async()=>{
  const f=await initialized();f.sketch.toggleEdit();f.sketch.selectGun("b");f.sketch.setTool("target");
  f.$("#sketch-layer").children[2].click();assert.equal(f.sketch.gunId,"b");assert.equal(f.sketch.draft.gun.id,"b");
  assert.equal(f.sketch.draft.existing,null);
  await f.sketch.calculateDraft(false);await f.sketch.saveDraft();
  assert.equal(f.sketch.plan().configurations.length,2);
  assert.equal(M.configuration(f.sketch.plan(),"a","t").elevation_degrees,1.8);
});

test("View mode shows only saved target rows and blocks every editing entry point",async()=>{
  const f=await initialized(),before=M.copy(f.sketch.store.data);let calculations=0;
  f.sketch.hooks.calculate=async()=>{calculations++;return f.solution;};
  f.sketch.selectGun("a");
  assert.equal(f.$("#sketch-form").hidden,true);assert.equal(f.$("#sketch-editor-fields").disabled,true);
  assert.equal(f.sketch.draft,null);assert.equal(f.$("#sketch-target-list").children.length,1);
  assert.equal(f.$("#sketch-target-list").children[0].children[0].textContent,"1.80° · 3.100 s");
  assert.equal(f.$("#sketch-target-list").children[0].children[2].textContent,"Fence");
  for(const id of ["sketch-add-gun","sketch-add-target","sketch-import"])assert.equal(f.$("#"+id).hidden,true);
  f.sketch.setTool("gun");await f.sketch.canvasClick({x:130,y:100});await f.sketch.placeGun({x:130,y:100});
  f.sketch.setTool("target");assert.equal(f.sketch.editing,false);assert.equal(f.sketch.tool,null);
  for(const [kind,id] of [["gun","a"],["target","t"]])assert.equal(f.sketch.beginGunMove(id,kind),false);
  f.sketch.editGun();f.sketch.editTarget(f.sketch.plan().targets[0]);assert.equal(f.sketch.draft,null);
  f.$("#sketch-target-list").children[0].click();assert.equal(f.sketch.targetId,"t");assert.equal(f.$("#sketch-form").hidden,true);
  await f.sketch.deleteSelected();await f.sketch.unlinkSelected();await f.sketch.saveDraft();await f.sketch.calculateDraft(false);
  await f.sketch.importFile({size:1,text:async()=>{throw Error("View must not read imports");}});
  assert.equal(await f.sketch.persist(()=>{throw Error("View must not persist edits");}),false);
  assert.equal(f.writes,0);assert.equal(calculations,0);assert.deepEqual(f.sketch.store.data,before);
});

test("leaving Edit discards unsaved fields, disarms dragging and restores read-only selection",async()=>{
  const f=await initialized(),before=M.copy(f.sketch.store.data);f.sketch.selectGun("a");f.sketch.toggleEdit();
  assert.equal(f.$("#sketch-form").hidden,false);assert.equal(f.sketch.draft.kind,"gun");
  f.$("#sketch-x").value="90";f.sketch.beginGunMove("a");f.sketch.previewGunMove({x:90,y:60});
  f.sketch.toggleEdit();await f.sketch.commitGunMove();await f.sketch.saveDraft();await f.sketch.deleteSelected();
  assert.equal(f.sketch.draft,null);assert.equal(f.sketch.gunMove,null);assert.equal(f.sketch.gunId,"a");
  assert.equal(f.$("#sketch-form").hidden,true);assert.equal(f.$("#sketch-target-list").children.length,1);
  assert.deepEqual(f.sketch.store.data,before);assert.equal(f.writes,0);
  f.sketch.toggleEdit();assert.equal(f.$("#sketch-x").value,10);
  f.sketch.setTool("target");await f.sketch.canvasClick({x:155,y:110});f.sketch.toggleEdit();
  assert.equal(f.sketch.draft,null);assert.equal(f.sketch.targetId,null);assert.equal(f.sketch.gunId,"a");
  assert.equal(f.$("#sketch-layer").children.length,3);assert.equal(f.writes,0);
});

test("a calculation completing after leaving Edit cannot reopen the editor or save",async()=>{
  const f=await initialized();f.sketch.selectGun("a");f.sketch.toggleEdit();f.sketch.selectTarget("t");
  let finish;f.sketch.hooks.calculate=()=>new Promise(resolve=>{finish=resolve;});
  const pending=f.sketch.calculateDraft(false);f.sketch.toggleEdit();finish(f.solution);await pending;
  assert.equal(f.sketch.draft,null);assert.equal(f.$("#sketch-form").hidden,true);assert.equal(f.writes,0);
  assert.equal(f.mission[2].elevation_degrees,1.8);
});
