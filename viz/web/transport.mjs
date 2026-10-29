class PythonTransport {
  mode='python';
  async snapshot(joint,signal) {
    const response=await fetch(`/state?joint=${encodeURIComponent(joint)}`,{cache:'no-store',signal});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
  async command(action,joint,fault,signal) {
    const response=await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,joint,fault}),signal});
    const result=await response.json();if(!response.ok)throw new Error(result.error??'Command failed');return result;
  }
}
class BrowserTransport {
  mode='browser';paused=false;pending=new Map();sequence=0;
  constructor() {
    this.worker=new Worker(new URL('./browser-worker.mjs',import.meta.url),{type:'module'});
    this.worker.onmessage=({data})=>{const pending=this.pending.get(data.id);if(!pending)return;this.pending.delete(data.id);pending.finish();data.error?pending.reject(new Error(data.error)):pending.resolve(data.result);};
    this.worker.onerror=()=>{for(const p of this.pending.values()){p.finish();p.reject(new Error('Browser simulator stopped'));}this.pending.clear();};
    this.ready=fetch('./diagnostic-rules.json').then(r=>{if(!r.ok)throw new Error('Demo rules unavailable');return r.json();}).then(config=>this.rpc('init',{config}));
    this.ready.catch(()=>{}); // snapshot/control surface initialization failures through normal reconnect UI.
  }
  rpc(action,args={},signal) {
    return new Promise((resolve,reject)=>{
      if(signal?.aborted)return reject(new Error('Request cancelled'));
      const id=++this.sequence;
      const abort=()=>{this.pending.delete(id);reject(new Error('Request cancelled'));};
      signal?.addEventListener('abort',abort,{once:true});
      this.pending.set(id,{resolve,reject,finish:()=>signal?.removeEventListener('abort',abort)});
      this.worker.postMessage({id,action,...args});
    });
  }
  async snapshot(joint,signal){await this.ready;if(this.paused)throw new Error('Demo connection paused');return this.rpc('snapshot',{joint},signal);}
  async command(action,joint,fault,signal){await this.ready;if(this.paused)throw new Error('Demo connection paused');return this.rpc(action,{joint,fault},signal);}
  toggleConnection(){this.paused=!this.paused;return this.paused;}
}
export function createTransport(){return document.documentElement.dataset.runtime==='browser'?new BrowserTransport():new PythonTransport();}
