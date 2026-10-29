import {test} from 'node:test';
import assert from 'node:assert/strict';
import {connectionHealth,jointHealth,nextBackoff} from '../viz/web/viewer-state.mjs';
const snapshot={connection:{age_s:.02},config:{connection_stale_ms:1000}};
const joint={has_frame:true,age_s:.04,status:'CRITICAL',dtcs:[]};
test('connection goes stale within one second, including a silent open connection',()=>{
  assert.equal(connectionHealth(snapshot,0,500).stale,false);
  assert.equal(connectionHealth(snapshot,0,990).stale,true);
  assert.equal(connectionHealth(snapshot,0,100,true).stale,true);
});
test('ages keep increasing when disconnected and red markers turn grey',()=>{
  const view=jointHealth(joint,{stale:true},3);
  assert.equal(view.status,'NO DATA');assert.equal(view.ageS,3.04);
});
test('single missing heartbeat, startup and recovering heartbeat stay distinct',()=>{
  assert.match(jointHealth(joint,{stale:false},.47).reason,/No heartbeat.*500 ms/);
  assert.equal(jointHealth({has_frame:false},{stale:false},0).status,'NO DATA');
  assert.match(jointHealth({...joint,dtcs:[{rule:'TIMEOUT'}]},{stale:false},0).reason,/returning/);
});
test('fresh data clears the connection banner and resumes the real status',()=>{
  const connection=connectionHealth(snapshot,2000,2001,false);
  assert.equal(connection.stale,false);
  assert.equal(jointHealth(joint,connection,.001).status,'CRITICAL');
});
test('exponential reconnect caps at five seconds',()=>{
  let delay=0;const delays=Array.from({length:6},()=>delay=nextBackoff(delay));
  assert.deepEqual(delays,[500,1000,2000,4000,5000,5000]);
});
