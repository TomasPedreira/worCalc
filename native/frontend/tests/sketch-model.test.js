import test from "node:test";
import assert from "node:assert/strict";
import "../src/sketch-model.js";
const M = globalThis.WorCalcSketch;
const maps = [{identifier:"map-1",name:"Test battlefield",width_pixels:200,height_pixels:150},
  {identifier:"map-2",name:"Second map",width_pixels:200,height_pixels:150}];
const options = {weapons:{Ordnance:["Shell","Case"]},defaults:{cannon:"Ordnance",projectile:"Shell",method:"physics"}};
const target = {id:"shared",name:"Crossroads",x:100,y:80};
function fixture() {
  const plan = M.createPlan(maps[0],[],"Ordnance");
  plan.guns = [{id:"a",name:"Gun A",x:10,y:20,cannon:"Ordnance"},{id:"b",name:"Gun B",x:20,y:30,cannon:"Ordnance"}];
  return plan;
}
function setting(angle=1.2,fuze=2.4) {
  return {projectile:"Shell",airburst_mode:false,elevation_degrees:angle,fuze_seconds:fuze,notes:"",
    solution:{map_id:"map-1",cannon:"Ordnance",projectile:"Shell",calibration_mode:false,airburst_mode:false,
      elevation_degrees:1.2,fuze_seconds:2.4,bearing_degrees:74,slant_range_yards:300,clearance_status:"clear"}};
}
const library = plan => ({version:1,maps:{"map-1":plan}});
const correctedMaps = () => [{...maps[0],coordinate_revision:1,
  coordinate_migration:{from_revision:0,gun_positions:[{old_x:10,old_y:20,x:15,y:24}]}},maps[1]];

test("alignment migration preserves originals, moves only exact default guns and retires old firing values",()=>{
  const plan=fixture(); M.saveConfiguration(plan,"a",target,setting(2.3,4.5));
  const value=library(plan), before=M.copy(value), catalog=correctedMaps();
  const checked=M.validateLibrary(value,catalog,options), migrated=checked.maps["map-1"];
  assert.deepEqual(value,before);
  assert.equal(migrated.coordinate_revision,1);
  assert.deepEqual([migrated.guns[0].x,migrated.guns[0].y],[15,24]);
  assert.deepEqual([migrated.guns[1].x,migrated.guns[1].y],[20,30]);
  assert.deepEqual([migrated.targets[0].x,migrated.targets[0].y],[100,80]);
  assert.equal(M.configuration(migrated,"a",target.id),null);
  assert.deepEqual(migrated.alignment_history[0].configurations,before.maps["map-1"].configurations);
  assert.deepEqual(migrated.alignment_history[0].guns,before.maps["map-1"].guns);
  assert.equal(M.previousConfiguration(migrated,"a",target.id).elevation_degrees,2.3);
  assert.equal(M.outdatedConfigurationCount(migrated),1);
  assert.deepEqual(M.validateLibrary(checked,catalog,options),checked);
  const updated=setting(); updated.solution.coordinate_revision=1;
  M.saveConfiguration(migrated,"a",target,updated);
  assert.equal(M.outdatedConfigurationCount(migrated),0);
  assert.doesNotThrow(()=>M.validateLibrary(checked,catalog,options));
});
test("neutral map plans retain their firing values and new plans carry the corrected revision",()=>{
  const plan=fixture(); M.saveConfiguration(plan,"a",target,setting(2.3,4.5));
  const value=library(plan), checked=M.validateLibrary(value,maps,options);
  assert.deepEqual(checked.maps["map-1"].configurations,plan.configurations);
  assert.equal(checked.maps["map-1"].alignment_history,undefined);
  const fresh=M.createPlan(correctedMaps()[0],[],"Ordnance");
  assert.equal(fresh.coordinate_revision,1);
  const migrated=M.validateLibrary(value,correctedMaps(),options);
  M.saveConfiguration(migrated.maps["map-1"],"a",target,setting());
  assert.throws(()=>M.validateLibrary(migrated,correctedMaps(),options),/outdated map alignment/);
});
test("alignment migration is saved once and a failed migration write preserves the original document",async()=>{
  const plan=fixture(); M.saveConfiguration(plan,"a",target,setting()); const original=library(plan);
  let saved=M.copy(original), writes=0, fail=true;
  const adapter={load:async()=>saved,save:async value=>{if(fail)throw Error("Disk full");saved=M.copy(value);writes++;}};
  const store=new M.LibraryStore(adapter,correctedMaps(),options);
  await assert.rejects(store.load(),/Disk full/);
  assert.equal(store.ready,false); assert.deepEqual(saved,original);
  fail=false; await store.load(); assert.equal(writes,1);
  await store.load(); assert.equal(writes,1);
  const imported=new M.LibraryStore(adapter,correctedMaps(),options); await imported.load();
  await imported.import(original);
  assert.equal(imported.data.maps["map-1"].coordinate_revision,1);
  assert.equal(imported.data.maps["map-1"].alignment_history.length,1);
  assert.equal(imported.data.maps["map-1"].configurations.length,0);
});
test("alignment revisions and archive shape are validated before accepting a plan",()=>{
  for(const revision of [-1,0.5,2,"1"]) {
    const plan=fixture(); plan.coordinate_revision=revision;
    assert.throws(()=>M.validateLibrary(library(plan),correctedMaps(),options),/alignment/);
  }
  const migrated=M.validateLibrary(library(fixture()),correctedMaps(),options);
  migrated.maps["map-1"].alignment_history[0].configurations=null;
  assert.throws(()=>M.validateLibrary(migrated,correctedMaps(),options),/previous map alignment/);
});
test("guns share a physical target but retain independent fire settings", () => {
  const plan=fixture();
  M.saveConfiguration(plan,"a",target,setting());
  M.saveConfiguration(plan,"b",target,setting(2.5,3.1));
  assert.equal(plan.targets.length,1); assert.equal(plan.configurations.length,2);
  assert.equal(M.visibleTargets(plan,"a")[0].configuration.elevation_degrees,1.2);
  assert.equal(M.visibleTargets(plan,"b")[0].configuration.elevation_degrees,2.5);
  assert.equal(M.visibleTargets(plan,null)[0].configuration,null);
  M.saveConfiguration(plan,"a",target,setting(1.8,2.6));
  assert.equal(plan.configurations.length,2);
  assert.equal(M.configuration(plan,"b","shared").elevation_degrees,2.5);
  assert.doesNotThrow(()=>M.validateLibrary(library(plan),maps,options));
});
test("a second point at the same position reuses existing target geometry", () => {
  const plan=fixture(); M.saveConfiguration(plan,"a",target,setting());
  assert.equal(M.saveConfiguration(plan,"b",{...target,id:"new",x:100.2},setting()),"shared");
  assert.equal(plan.targets.length,1);
  assert.equal(M.configuration(plan,"b","shared").fuze_seconds,2.4);
});
test("removing a gun or link preserves other guns and shared targets", () => {
  const plan=fixture(); M.saveConfiguration(plan,"a",target,setting()); M.saveConfiguration(plan,"b",target,setting(2,3));
  M.unlinkTarget(plan,"a",target.id); assert.equal(plan.targets.length,1);
  assert.equal(plan.configurations.length,1); assert.equal(plan.configurations[0].gun_id,"b");
  M.removeGun(plan,"a"); assert.equal(plan.targets.length,1); assert.equal(plan.configurations.length,1);
  M.removeTarget(plan,target.id); assert.equal(plan.targets.length,0); assert.equal(plan.configurations.length,0);
});
test("moving a gun clears only its outdated fire settings and keeps shared targets",()=>{
  const plan=fixture();M.saveConfiguration(plan,"a",target,setting());M.saveConfiguration(plan,"b",target,setting(2,3));
  M.moveGun(plan,"a",{x:120,y:60});
  assert.deepEqual({x:plan.guns[0].x,y:plan.guns[0].y},{x:120,y:60});
  assert.equal(plan.targets.length,1);assert.equal(M.configuration(plan,"a",target.id),null);
  assert.equal(M.configuration(plan,"b",target.id).elevation_degrees,2);
  assert.doesNotThrow(()=>M.validateLibrary(library(plan),maps,options));
});
test("unchanged or invalid gun moves preserve existing fire settings",()=>{
  const plan=fixture();M.saveConfiguration(plan,"a",target,setting());const before=M.copy(plan);
  M.moveGun(plan,"a",{x:10,y:20});assert.deepEqual(plan,before);
  for(const point of [{x:-1,y:10},{x:201,y:10},{x:NaN,y:10}]) assert.throws(()=>M.moveGun(plan,"a",point),/outside/);
  assert.deepEqual(plan,before);
});
test("only gun spawn references inside the map become initial gun positions", () => {
  const plan=M.createPlan(maps[0],[{kind:"gun_spawn",name:"A",pixel_x:10,pixel_y:20},
    {kind:"gun_spawn",name:"Duplicate",pixel_x:10,pixel_y:20},{kind:"battery",name:"Crew",pixel_x:30,pixel_y:20},
    {kind:"gun_spawn",name:"Outside",pixel_x:-1,pixel_y:20}],"Ordnance");
  assert.equal(plan.guns.length,1); assert.equal(plan.guns[0].id,"gun-1"); assert.equal("name" in plan.guns[0],false); assert.equal(plan.targets.length,0);
});
test("predefined guns use the matching weapon profile from the game reference", () => {
  const plan=M.createPlan(maps[0],[{kind:"gun_spawn",name:"12-pounder Napoleon (USA) · Entity-1",pixel_x:10,pixel_y:20}],
    "Ordnance",{Ordnance:["Shell"],"12-pounder Napoleon":["Shell"]});
  assert.equal(plan.guns[0].cannon,"12-pounder Napoleon");
});
test("imports reject mismatched maps, duplicate pairs, dangling references and invalid values", () => {
  const plan=fixture(); M.saveConfiguration(plan,"a",target,setting());
  const bad = change => {const value=library(M.copy(plan));change(value.maps["map-1"]);return value;};
  for (const value of [bad(p=>p.width=400),bad(p=>p.map_name="Different map"),bad(p=>p.mode="Contention"),bad(p=>p.guns=[]),
    bad(p=>p.targets[0].x=201),bad(p=>p.configurations.push(p.configurations[0])),
    bad(p=>p.configurations[0].fuze_seconds=-1),bad(p=>p.configurations[0].elevation_degrees=NaN),
    bad(p=>p.configurations[0].solution.cannon="Wrong cannon"),bad(p=>p.configurations[0].projectile="Wrong ammo"),
    bad(p=>p.configurations[0].solution.height_difference_metres="string"),bad(p=>p.configurations[0].solution.elevation_source=99)]) {
    assert.throws(()=>M.validateLibrary(value,maps,options));
  }
  assert.throws(()=>M.validateLibrary({version:99,maps:{}},maps,options));
});
test("failed writes retain the saved document and do not prevent a retry", async () => {
  let fail=true; const store=new M.LibraryStore({load:async()=>library(fixture()),save:async()=>{if(fail)throw Error("Disk full");}},maps,options);
  await store.load();
  await assert.rejects(store.update(data=>M.saveConfiguration(data.maps["map-1"],"a",target,setting())),/Disk full/);
  assert.equal(store.data.maps["map-1"].targets.length,0);
  fail=false; await store.update(data=>M.saveConfiguration(data.maps["map-1"],"a",target,setting()));
  assert.equal(store.data.maps["map-1"].targets.length,1);
});
test("queued writes and import/export round trips preserve all guns' settings", async () => {
  let saved; const adapter={load:async()=>library(fixture()),save:async data=>{saved=JSON.stringify(data);}};
  const store=new M.LibraryStore(adapter,maps,options);await store.load();
  await Promise.all([store.update(data=>M.saveConfiguration(data.maps["map-1"],"a",target,setting())),
    store.update(data=>M.saveConfiguration(data.maps["map-1"],"b",target,setting(2,3)))]);
  const restored=new M.LibraryStore({load:async()=>JSON.parse(saved),save:async()=>{}},maps,options);
  await restored.load();assert.deepEqual(restored.data,store.data);
  await restored.update(data=>{data.maps["map-2"]=M.createPlan(maps[1],[],"Ordnance");});
  await restored.import(JSON.parse(saved)); assert.equal(Object.keys(restored.data.maps).length,2);
  assert.equal(restored.data.maps["map-1"].configurations.length,2);
});
test("corrupt saved plans are surfaced and cannot be silently overwritten", async () => {
  let writes=0;const store=new M.LibraryStore({load:async()=>({version:2,maps:{}}),save:async()=>writes++},maps,options);
  await assert.rejects(store.load(),/Unsupported/);
  await assert.rejects(store.update(()=>{}),/could not be loaded/); assert.equal(writes,0);
  await store.import(library(fixture())); assert.equal(store.ready,true); assert.equal(writes,1);
});

test("legacy names are removed without changing map IDs, point IDs or independent settings",async()=>{
  const plan=fixture();M.saveConfiguration(plan,"a",target,setting());M.saveConfiguration(plan,"b",target,setting(2,3));
  plan.targets[0].name="Legacy waypoint";
  const original=library(plan),checked=M.validateLibrary(original,maps,options);
  assert.equal(original.maps["map-1"].guns[0].name,"Gun A");
  assert.deepEqual(checked.maps["map-1"].guns.map(gun=>gun.id),["a","b"]);
  assert.equal(checked.maps["map-1"].targets[0].id,"shared");
  assert.ok([...checked.maps["map-1"].guns,...checked.maps["map-1"].targets].every(point=>!("name" in point)));
  assert.deepEqual(checked.maps["map-1"].configurations,original.maps["map-1"].configurations);
  assert.deepEqual(M.validateLibrary(JSON.parse(JSON.stringify(checked)),maps,options),checked);
});

test("deleted numeric IDs are not reused after saving and reopening a plan",()=>{
  const plan=M.createPlan(maps[0],[{kind:"gun_spawn",name:"A",pixel_x:10,pixel_y:20}],"Ordnance");
  M.removeGun(plan,"gun-1");assert.equal(M.nextPointId(plan,"gun"),"gun-2");
  const gunId=M.nextPointId(plan,"gun");plan.guns.push({id:gunId,x:10,y:20,cannon:"Ordnance"});M.retainPointId(plan,"gun",gunId);
  const targetId=M.nextPointId(plan,"target");M.saveConfiguration(plan,gunId,{id:targetId,x:100,y:80},setting());
  M.removeTarget(plan,targetId);
  const restored=M.validateLibrary(JSON.parse(JSON.stringify(library(plan))),maps,options).maps["map-1"];
  assert.equal(M.nextPointId(restored,"target"),"target-2");assert.equal(M.nextPointId(restored,"gun"),"gun-3");
});

test("moving a shared target clears its settings for every gun and preserves unrelated pairs",()=>{
  const plan=fixture();M.saveConfiguration(plan,"a",target,setting());M.saveConfiguration(plan,"b",target,setting(2,3));
  M.saveConfiguration(plan,"b",{id:"other",x:150,y:90},setting(3,4));
  M.moveTarget(plan,"shared",{x:110,y:85});
  assert.deepEqual(plan.targets[0],{id:"shared",x:110,y:85});
  assert.equal(M.configuration(plan,"a","shared"),null);assert.equal(M.configuration(plan,"b","shared"),null);
  assert.equal(M.configuration(plan,"b","other").elevation_degrees,3);assert.equal(plan.guns.length,2);
  assert.doesNotThrow(()=>M.validateLibrary(library(plan),maps,options));
});

test("unchanged or invalid target moves preserve all saved settings",()=>{
  const plan=fixture();M.saveConfiguration(plan,"a",target,setting());const before=M.copy(plan);
  M.moveTarget(plan,target.id,target);assert.deepEqual(plan,before);
  for(const point of [{x:-1,y:10},{x:201,y:10},{x:NaN,y:10}])assert.throws(()=>M.moveTarget(plan,target.id,point),/outside/);
  assert.deepEqual(plan,before);
});

test("deleting a gun preserves shared geometry and another gun's pairs; deleting a target removes all its pairs",()=>{
  const plan=fixture();M.saveConfiguration(plan,"a",target,setting());M.saveConfiguration(plan,"b",target,setting(2,3));
  M.saveConfiguration(plan,"b",{id:"other",x:150,y:90},setting(3,4));
  const gunRemoved=M.copy(plan);M.removeGun(gunRemoved,"a");
  assert.deepEqual(gunRemoved.guns.map(gun=>gun.id),["b"]);assert.equal(gunRemoved.targets.length,2);
  assert.equal(M.configuration(gunRemoved,"b","shared").elevation_degrees,2);
  M.removeTarget(plan,"shared");assert.equal(plan.guns.length,2);
  assert.deepEqual(plan.targets.map(point=>point.id),["other"]);
  assert.equal(plan.configurations.length,1);assert.equal(plan.configurations[0].target_id,"other");
});

test("saved-plan repositioning preserves settings and rejects invalid moves",()=>{
  const plan=fixture();M.saveConfiguration(plan,"a",target,setting());M.saveConfiguration(plan,"b",target,setting(2.5,3.1));
  const settings=M.copy(plan.configurations);
  M.moveSavedPoint(plan,"gun","a",{x:50,y:50});M.moveSavedPoint(plan,"target","shared",{x:130,y:100});
  assert.deepEqual(plan.configurations,settings);assert.equal(plan.targets[0].x,130);
  assert.deepEqual(M.validateLibrary(library(plan),maps,options).maps["map-1"].configurations,settings);
  const before=M.copy(plan);assert.throws(()=>M.moveSavedPoint(plan,"target","shared",{x:-1,y:0}),/outside/);
  assert.deepEqual(plan,before);
});
