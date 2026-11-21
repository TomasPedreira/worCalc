import test from "node:test";
import assert from "node:assert/strict";
import {deathMatches, createKillTrackerController, mountKillTracker} from "../src/kill-tracker.js";
import {nativeKillTracker} from "../transport.js";
const death = {killer:{name:"Thomas Quarry",steam_id_64:"76561198168674032"},victim:{name:"Toyota Yaris",steam_id_64:"76561198649671288"}};
test("kill feed searches names and precise Steam IDs in selected role", () => {
  assert.equal(deathMatches(death," quarry "),true);
  assert.equal(deathMatches(death,"toyota","victims"),true);
  assert.equal(deathMatches(death,"76561198168674032","killers"),true);
  assert.equal(deathMatches(death,"quarry","victims"),false);
  assert.equal(deathMatches(death,"unknown"),false);
});
test("capture IPC carries explicit authorization and wraps native errors",async () => {
  const calls = [];
  const api = nativeKillTracker(async (command,args) => {calls.push([command,args]);return {};});
  await api.start(true); await api.poll(); await api.stop();
  assert.deepEqual(calls,[['native_kill_tracker',{operation:'start',authorized:true}],['native_kill_tracker',{operation:'poll',authorized:false}],['native_kill_tracker',{operation:'stop',authorized:false}]]);
  await assert.rejects(nativeKillTracker(async()=>{throw "Unsupported build";}).start(true),/Unsupported build/);
});
test("capture requires authorization, polls serially, and preserves feed on stop",async()=>{
  let scheduled, updates=[], started=0, stopped=0;
  const controller = createKillTrackerController({start:async()=>{started++;return {running:true,deaths:[death],directory:'capture'};},poll:async()=>({running:true,deaths:[death]}),stop:async()=>{stopped++;}},snapshot=>updates.push(snapshot),fn=>{scheduled=fn;return 1;},()=>{scheduled=null;});
  await controller.start(false); assert.equal(started,0); assert.match(updates.at(-1).error,/Authorize/);
  await controller.start(true); assert.equal(started,1); assert.equal(updates.at(-1).deaths.length,1);
  await scheduled(); assert.equal(updates.at(-1).deaths.length,2);
  await controller.stop(); assert.equal(stopped,1); assert.equal(scheduled,null);
  assert.equal(updates.at(-1).running,false); assert.equal(updates.at(-1).directory,'capture'); assert.equal(updates.at(-1).deaths.length,2);
});
test("a pending poll cannot revive capture after stopping",async()=>{
  let scheduled, resolvePoll, latest;
  const controller=createKillTrackerController({start:async()=>({running:true,deaths:[]}),poll:()=>new Promise(resolve=>{resolvePoll=resolve;}),stop:async()=>{}},snapshot=>{latest=snapshot;},fn=>{scheduled=fn;},()=>{scheduled=null;});
  await controller.start(true); const pending=scheduled(); await controller.stop();
  resolvePoll({running:true,deaths:[death]}); await pending;
  assert.equal(latest.running,false); assert.equal(scheduled,null); assert.equal(latest.deaths.length,0);
});
test("failed capture start and poll show error and stop scheduling",async()=>{
  let scheduled, latest;
  const schedule=fn=>{scheduled=fn;};
  const failed=createKillTrackerController({start:async()=>{throw Error('Unsupported build');}},s=>{latest=s;},schedule);
  await failed.start(true); assert.match(latest.error,/Unsupported build/); assert.equal(scheduled,undefined);
  const controller=createKillTrackerController({start:async()=>({running:true,deaths:[]}),poll:async()=>{throw Error('Game exited');}},s=>{latest=s;},schedule);
  await controller.start(true); scheduled=scheduled(); await scheduled;
  assert.equal(latest.running,false); assert.match(latest.error,/Game exited/);
});
test("large existing buffers are bounded and a new empty session clears the feed",async()=>{
  let latest, starts=0;
  const controller=createKillTrackerController({start:async()=>({running:true,deaths:starts++===0 ? Array(150000).fill(death) : []}),stop:async()=>{}},s=>{latest=s;},()=>1,()=>{});
  await controller.start(true); assert.equal(latest.deaths.length,2000);
  await controller.stop(); await controller.start(true);
  assert.equal(latest.deaths.length,0); assert.equal(latest.feedChanged,true);
});
test("standalone tracker starts without a hub or attaching to the game and renders names as text",async()=>{
  const elements=new Map();
  const make=()=>({hidden:false,value:'',checked:true,handlers:{},children:[],addEventListener(n,fn){this.handlers[n]=fn;},focus(){},append(item){this.children.push(item);},replaceChildren(...items){this.children=items;}});
  const document={querySelector(selector){if(!elements.has(selector))elements.set(selector,make());return elements.get(selector);},createElement:make};
  let starts=0;
  mountKillTracker(document,{start:async()=>{starts++;return {running:false,deaths:[{...death,killer:{...death.killer,name:'<script>unsafe</script>'}}]};}});
  assert.equal(starts,0);
  assert.equal(elements.has('#app-chooser'),false);assert.equal(elements.has('#choose-kill-tracker'),false);
  await elements.get('#kill-start').handlers.click();
  assert.equal(elements.get('#kill-rows').children[0].children[1].textContent,'<script>unsafe</script>');
  assert.equal(starts,1);assert.equal(elements.has('#kill-tracker-back'),false);
});
