import test from "node:test";
import assert from "node:assert/strict";
import "../src/fire-readout.js";
const R=globalThis.WorCalcFireReadouts;
test("nearby target windows choose space without covering the previous firing window",()=>{
  const viewport={width:680,height:740},size={width:190,height:54};
  const first=R.position({x:300,y:350},viewport,size);
  const second=R.position({x:310,y:360},viewport,size,[first]);
  assert.ok(second.x+size.width<=first.x || first.x+size.width<=second.x || second.y+size.height<=first.y || first.y+size.height<=second.y);
});
test("firing windows stay inside the map above the status bar",()=>{
  for(const point of [{x:1,y:1},{x:679,y:739}]) {
    const box=R.position(point,{width:680,height:740},{width:190,height:54});
    assert.ok(box.x>=8 && box.x+box.width<=672);
    assert.ok(box.y>=8 && box.y+box.height<=668);
  }
});
