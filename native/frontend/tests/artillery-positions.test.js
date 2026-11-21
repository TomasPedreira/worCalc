import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import '../src/artillery-positions.js';

const {label} = globalThis.WorCalcArtilleryPositions;
const battery = name => ({kind:'battery', name});

test('battery names include French, Lane and Matthews without scenario or spawn tokens', () => {
  for (const name of ['French', 'Lane', 'Matthews']) {
    assert.equal(label(battery(`Spawnpoint_CE_CSA_Arty_${name}_Forward`)), `Battery ${name}`);
  }
  assert.equal(label(battery('Spawnpoint_RC_CSA_Arty_Manly_Forward-6')), 'Battery Manly');
});

test('battery aliases use the English game titles', () => {
  for (const [raw, expected] of [['vonSehlen','Von Sehlen'], ['Von_Sehlen','Von Sehlen'],
    ['DAquin','Daquin'], ['Daquin','Daquin'], ['Philips','Phillips'], ['Phillips','Phillips'], ['Weaver','Wever']]) {
    assert.equal(label(battery(`Spawnpoint_CC_USA_Arty_${raw}_Forward`)), `Battery ${expected}`);
  }
});

test('base, staging and unnamed artillery references never become map labels', () => {
  for (const raw of ['Base', 'Base2']) assert.equal(label(battery(`Spawnpoint_CC_USA_Arty_${raw}`)), null);
  assert.equal(label(battery('CQ1_Spawnpoint_USA_Artillery_Staging')), null);
  assert.equal(label(battery('CQ1_Spawnpoint_USA_Artillery_Forward')), null);
  assert.equal(label(battery('Spawnpoint-CSA-Artillery')), null);
  assert.equal(label(battery('Spawnpoint_CC_USA_Arty_Unrecognized_Forward')), null);
  assert.equal(label({kind:'gun_spawn', name:'12-pounder Napoleon (CSA) · Entity-1617'}), null);
  assert.equal(label({kind:'spawn', name:'Spawnpoint_CC_USA_Arty_French_Forward'}), null);
});

test('every named battery in the offline pack has a readable name', () => {
  const catalog = JSON.parse(readFileSync(new URL('../../assets/catalog.json',import.meta.url),'utf8'));
  let named = 0;
  for (const map of catalog.maps) {
    for (const location of map.locations.filter(location => location.kind === 'battery')) {
      if (/_(?:Arty|Artillery)_.+_Forward(?:-\d+)?$/i.test(location.name)) {
        named++;
        assert.match(label(location), /^Battery /, `${map.identifier}: ${location.name}`);
      }
      if (label(location)) assert.doesNotMatch(label(location), /Spawnpoint|_Forward|_Arty|Artillery base/);
    }
  }
  assert.ok(named > 0);
});
