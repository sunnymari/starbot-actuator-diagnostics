import {BrowserEngine,JOINTS,encodeFrame} from './browser-engine.mjs';
let engine,startedAt;
const elapsed=()=>Math.max(0,(performance.now()-startedAt)/1000);
// The hosted adapter transports actual encoded 8-byte buffers through an in-browser
// message bus. It does not claim to be python-can or a physical CAN interface.
const bus=new MessageChannel();
bus.port1.onmessage=event=>engine.receive(event.data.canId,event.data.bytes,event.data.t);
function cycle() {
  const now=elapsed();
  for(const j of JOINTS){const values=engine.values(j,now);if(values){const bytes=encodeFrame(values);bus.port2.postMessage({canId:j.can_id,bytes,t:now},[bytes]);}}
  engine.checkTimeouts(now);
}
self.onmessage=event=>{
  const {id,action,config,joint,fault}=event.data;
  try {
    let result;
    if(action==='init'){engine=new BrowserEngine(config);startedAt=performance.now();cycle();setInterval(cycle,100);result={ok:true};}
    else if(!engine)throw new Error('Simulator is not ready');
    else if(action==='snapshot')result=engine.snapshot(joint,elapsed());
    else result=engine.command(action,joint,fault,elapsed());
    self.postMessage({id,result});
  } catch(error){self.postMessage({id,error:error.message});}
};
