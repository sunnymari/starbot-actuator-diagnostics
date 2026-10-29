import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {BrowserEngine,JOINTS,encodeFrame,decodeFrame} from '../viz/web/browser-engine.mjs';
const fixtures=JSON.parse(readFileSync(new URL('./fixtures/browser-parity.json',import.meta.url)));
const config=JSON.parse(readFileSync(new URL('../diagnostics/rules.json',import.meta.url)));
const normalize=value=>typeof value==='number'?Math.round(value*1e6)/1e6:Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,normalize(v)])):value;
test('hosted demo uses exactly the Python thresholds and CAN identities',()=>{
  assert.deepEqual(config,fixtures.config);
  assert.deepEqual(JOINTS.map(({name,can_id})=>({name,can_id})),fixtures.joints);
});
for(const scenario of fixtures.cases)test(`Python/browser DTC parity: ${scenario.name}`,()=>{
  const engine=new BrowserEngine(config);
  for(const action of scenario.actions) {
    if(action.action==='sample')engine.receive(JOINTS.find(j=>j.name===action.joint).can_id,encodeFrame(action.values),action.t);
    else if(action.action==='timeout')engine.checkTimeouts(action.t);
    else engine.command('clear',action.joint,null,0);
  }
  assert.deepEqual(normalize(engine.dtcs()),scenario.expected);
});
test('CAN wire encoding is eight-byte, big-endian, signed sensor fields',()=>{
  const bytes=encodeFrame([35.2,4.1,-.05,48]);
  assert.equal(bytes.byteLength,8);assert.deepEqual([...new Uint8Array(bytes)],[13,192,1,154,255,251,18,192]);
  assert.deepEqual(decodeFrame(bytes),[35.2,4.1,-.05,48]);
  assert.deepEqual(decodeFrame(encodeFrame([.125,-.125,-.025,48])),[.12,-.12,-.02,48]);
  assert.throws(()=>encodeFrame([1000,3,0,48]),RangeError);
});
test('injections alter encoded readings and sessions stay independent',()=>{
  const engine=new BrowserEngine(config),other=new BrowserEngine(config),joint=JOINTS.find(j=>j.name==='left_knee');
  engine.command('inject',joint.name,'overcurrent',0);
  assert.equal(decodeFrame(encodeFrame(engine.values(joint,1)))[1],8.5);
  assert.ok(other.values(joint,1)[1]<5);
  engine.command('inject',joint.name,'heartbeat',1);assert.equal(engine.values(joint,2),null);
  engine.command('reset',null,null,2);assert.ok(engine.values(joint,3)[1]<5);
});
test('snapshot never labels missing or timed-out frames healthy',()=>{
  const e=new BrowserEngine(config);
  assert.ok(e.snapshot('left_knee',0).joints.every(j=>j.status==='NO DATA'));
  e.receive(0x112,encodeFrame([35,3,0,48]),.1);
  assert.equal(e.snapshot('left_knee',.2).joints.find(j=>j.name==='left_knee').status,'OK');
  assert.equal(e.snapshot('left_knee',.7).joints.find(j=>j.name==='left_knee').status,'NO DATA');
});
