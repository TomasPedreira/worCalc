import test from "node:test";
import assert from "node:assert/strict";
import {createNativeApi, nativeResources, nativeSketchStorage} from "../transport.js";

test("plan persistence and export use app-private IPC", async () => {
  const calls=[];
  const adapter=nativeSketchStorage(async(command,args)=>{calls.push([command,args]);return args.operation==="export" ? "Downloads/plan.json" : {version:1,maps:{}};});
  const data=await adapter.load();await adapter.save(data);
  assert.equal(await adapter.export(data),"Exported to Downloads/plan.json");
  assert.deepEqual(calls,[["native_sketch",{operation:"load",data:null}],
    ["native_sketch",{operation:"save",data}], ["native_sketch",{operation:"export",data}]]);
});
test("native resources preserve binary IPC responses", async () => {
  const read = nativeResources(async(command,args) => {
    assert.equal(command,"native_resource");assert.deepEqual(args,{path:"maps/map-9.webp"});
    return new Uint8Array([0,128,255]).buffer;
  });
  assert.deepEqual([...await read("maps/map-9.webp")],[0,128,255]);
});
test("all calculator operations use native commands with structured data", async () => {
  const calls=[];
  const api=createNativeApi(async(command,args)=>{calls.push([command,args]);return {elevation_degrees:1.2};});
  const mission={map_id:"map-1",gun:{x:1,y:2}};
  assert.equal((await api.calculate(mission)).elevation_degrees,1.2);
  await api.maps();await api.options();await api.locations("map-1");await api.recordImpact({calculation_id:"shot"});
  assert.deepEqual(calls,[
    ["native_request",{operation:"calculate",data:mission}],
    ["native_request",{operation:"maps",data:null}],
    ["native_request",{operation:"options",data:null}],
    ["native_request",{operation:"locations",data:{map_id:"map-1"}}],
    ["native_request",{operation:"impact",data:{calculation_id:"shot"}}],
  ]);
});
test("map images use bundled assets and reject paths outside the map pack", async () => {
  let calls=0;
  const api=createNativeApi(async(command,args)=>{calls++;assert.equal(command,"native_resource");assert.equal(args.path,"maps/map-1.webp");return new Uint8Array([1,2,3]);});
  const image=await api.mapImage("maps/map-1.webp");assert.equal(image.type,"image/webp");
  assert.deepEqual([...new Uint8Array(await image.arrayBuffer())],[1,2,3]);
  for (const path of ["../observations.json","https://example.com/map.webp","maps/map-1.webp/../catalog.json"]) {
    await assert.rejects(api.mapImage(path),/Invalid map resource/);
  }
  assert.equal(calls,1);
});
test("cancelled image reads cannot supply an obsolete image", async () => {
  const controller=new AbortController();
  const api=createNativeApi(async()=>{controller.abort();return new Uint8Array([1]);});
  await assert.rejects(api.mapImage("maps/map-2.webp",controller.signal),{name:"AbortError"});
  const blocked=createNativeApi(()=>assert.fail("Cancelled request reached IPC"));
  await assert.rejects(blocked.mapImage("maps/map-2.webp",controller.signal),{name:"AbortError"});
});
test("native errors are readable errors for the UI", async () => {
  const api=createNativeApi(async()=>{throw "Shot expired";});
  await assert.rejects(api.recordImpact({}),/Shot expired/);
  await assert.rejects(api.mapImage("maps/map-1.webp"),/Shot expired/);
});
test("plan storage errors retain a readable message for load, save and export",async()=>{
  const adapter=nativeSketchStorage(async()=>{throw "Disk full";});
  for(const operation of [()=>adapter.load(),()=>adapter.save({}),()=>adapter.export({})]) {
    await assert.rejects(operation,error=>error instanceof Error && error.message==="Disk full");
  }
});
