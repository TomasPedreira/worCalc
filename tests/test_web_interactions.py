"""Execute browser state transitions in Node with a minimal DOM test double."""

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
function element(key) {
  if (!elements.has(key)) {
    const classes = new Set();
    elements.set(key, {
      value:'', textContent:'', hidden:false, naturalWidth:200, naturalHeight:150,
      src:'old-map', style:{setProperty(){}}, handlers:{},
      classList:{add:x=>classes.add(x), remove:(...xs)=>xs.forEach(x=>classes.delete(x)),
        contains:x=>classes.has(x), toggle(x,on){if(on) classes.add(x); else classes.delete(x)}},
      addEventListener(n,f){this.handlers[n]=f}, replaceChildren(){}, setPointerCapture(){},
      getBoundingClientRect(){return {left:0,top:0,width:200,height:150}}
    });
  }
  return elements.get(key);
}
const images = [];
let objectSequence = 0;
const context = vm.createContext({
  document:{querySelector:element,querySelectorAll:()=>[]},
  window:{addEventListener(){}}, assert, console, AbortController, images,
  URL:{createObjectURL:()=>`blob:map-${++objectSequence}`,revokeObjectURL(){}},
  Image:function(){this.handlers={};this.addEventListener=(n,f)=>this.handlers[n]=f;images.push(this)},
  fetch:async()=>{throw Error('network failed')}
});
vm.runInContext(fs.readFileSync('worcalc/web/static/app.js','utf8').replace(/load\(\);\s*$/, ''),context);
vm.runInContext(`
currentMap={identifier:'new-map'}; mapReady=true;
gun={x:10,y:20}; target={x:100,y:20};
`,context);
"""


@unittest.skipUnless(NODE, "Node.js is required for browser interaction tests")
class WebInteractionTests(unittest.TestCase):
    def test_drag_at_fit_zoom_moves_map_and_keeps_a_visible_strip(self):
        self.run_scenario(r"""
          sceneWidth=200;sceneHeight=150;zoom=1;translateX=0;translateY=0;
          const event={pointerId:1,button:0,clientX:50,clientY:50,target:{closest:()=>null}};
          mapWrap.handlers.pointerdown(event);
          mapWrap.handlers.pointermove({...event,clientX:90,clientY:80});
          mapWrap.handlers.pointerup({...event,clientX:90,clientY:80});
          assert.equal(translateX,40);assert.equal(translateY,30);
          assert.deepEqual(gun,{x:10,y:20});assert.deepEqual(target,{x:100,y:20});
          translateX=9999;translateY=-9999;applyView();
          assert.ok(translateX<200);assert.ok(translateY+150>0);
        """)

    def test_middle_click_saves_impact_without_moving_shot(self):
        self.run_scenario(r"""
          $('#calculation-mode').value='test';
          latestSolution={calculation_id:'shot-123'};
          $('#actual-elevation').value='-0.10';
          document.createElement=()=>({style:{}});
          let payload;
          fetch=async(url,init)=>{assert.equal(url,'/api/impacts');payload=JSON.parse(init.body);return {ok:true,json:async()=>({})}};
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
        """)

    def test_middle_click_on_target_marker_records_exact_target_center(self):
        self.run_scenario(r"""
          $('#calculation-mode').value='test';
          latestSolution={calculation_id:'shot-123'};
          $('#actual-elevation').value='0.42';
          document.createElement=()=>({style:{}});
          let payload;
          fetch=async(url,init)=>{payload=JSON.parse(init.body);return {ok:true,json:async()=>({})}};
          const targetMarker={closest:selector=>selector==='[data-marker="target"]' ? {} : null};
          mapWrap.handlers.pointerdown({button:1,clientX:95,clientY:25,target:targetMarker,
                                        preventDefault(){}});
          await new Promise(resolve=>Promise.resolve().then(resolve));
          assert.deepEqual(payload.impact,{x:100,y:20});
          assert.equal(payload.actual_elevation_degrees,0.42);
        """)

    def test_wheel_zoom_anchors_cursor_and_readout_is_beside_target(self):
        self.run_scenario(r"""
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
        """)

    def test_gun_and_target_markers_use_screen_coordinates_at_zoom(self):
        self.run_scenario(r"""
          baseScale=0.5;zoom=4;translateX=12;translateY=18;
          gun={x:10,y:20};target={x:100,y:20};
          updateMissionGeometry();
          assert.equal(gunAnchor.style.left,'32px');
          assert.equal(gunAnchor.style.top,'58px');
          assert.equal(targetAnchor.style.left,'212px');
          assert.equal(targetAnchor.style.top,'58px');
        """)

    def test_obstruction_does_not_hide_firing_values_or_show_warning(self):
        self.run_scenario(r"""
          for (const status of ['obstructed', null]) {
            fetch=async()=>({ok:true,json:async()=>({
              slant_range_yards:300,height_difference_metres:0,
              elevation_degrees:status ? 0.1 : null,fuze_seconds:status ? 1.2 : null,clearance_status:status,
              height_above_target_metres:null
            })});
            await requestSolution();
            assert.equal($('#elevation').textContent,status ? '0.10°' : 'No solution');
            assert.equal($('#fuze').textContent,status ? '1.200 s' : '—');
            assert.doesNotMatch(modePill.textContent,/BLOCKED/);
            assert.equal(shotLine.classList.contains('obstructed'),false);
          }
        """)

    def test_static_gun_start_marker_is_distinct_from_crew_spawn(self):
        self.run_scenario(r"""
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
        """)

    def run_scenario(self, scenario):
        script = HARNESS + "\nvm.runInContext(" + repr(
            "(async()=>{" + scenario + "})()"
        ) + ",context).catch(error=>{console.error(error);process.exitCode=1});"
        result = subprocess.run(
            [NODE, "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_calibration_mode_change_recalculates_existing_mission(self):
        self.run_scenario(r"""
          let requests=[];
          fetch=async(url,init)=>{requests.push(JSON.parse(init.body));throw Error('offline')};
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
        """)

    def test_marker_move_invalidates_values_even_when_request_fails(self):
        self.run_scenario(r"""
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
        """)

    def test_map_loading_and_failure_block_placement_and_calculation(self):
        self.run_scenario(r"""
          let rejectLoad;
          fetch=()=>new Promise((resolve,reject)=>{rejectLoad=reject});
          const loading=loadMapImage({identifier:'new-map',image_url:'/new'});
          const event={pointerId:1,clientX:50,clientY:50,target:{closest:()=>null}};
          setMode('gun');
          mapWrap.handlers.pointerdown(event); endPointer(event);
          assert.deepEqual(gun,{x:10,y:20});
          assert.equal(pointers.size,0);
          rejectLoad(Error('offline')); await loading;
          mapWrap.handlers.pointerdown(event); endPointer(event);
          assert.deepEqual(gun,{x:10,y:20});
          let requests=0;fetch=async()=>{requests++;throw Error('offline')};
          await requestSolution(); assert.equal(requests,0);
        """)

    def test_only_current_displayed_image_enables_placement(self):
        self.run_scenario(r"""
          fetch=async()=>({ok:true,blob:async()=>({})});
          await loadMapImage({identifier:'new-map',image_url:'/new'});
          images[0].handlers.load();
          assert.equal(mapReady,false);
          mapImage.handlers.load(); assert.equal(mapReady,true);
          await loadMapImage({identifier:'new-map',image_url:'/retry'});
          mapImage.handlers.load(); assert.equal(mapReady,false);
          images[1].handlers.load(); mapImage.handlers.load();
          assert.equal(mapReady,true);
          setMode('gun');
          const event={pointerId:1,clientX:50,clientY:50,target:{closest:()=>null}};
          mapWrap.handlers.pointerdown(event); endPointer(event);
          assert.deepEqual(gun,{x:50,y:50});
        """)
