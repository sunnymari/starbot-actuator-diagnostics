// Hosted demo only. The local Python application remains the real python-can implementation.
// Both runtimes use diagnostics/rules.json and shared DTC parity fixtures.
const sideTypes=[['shoulder_pitch','shoulder'],['shoulder_roll','shoulder'],['shoulder_yaw','shoulder'],['elbow','elbow'],['wrist_pitch','wrist'],['wrist_roll','wrist'],['hip_pitch','hip'],['hip_roll','hip'],['hip_yaw','hip'],['knee','knee'],['ankle_pitch','ankle'],['ankle_roll','ankle']];
const nominal={shoulder:3,elbow:2,wrist:1,hip:6,knee:5,ankle:4,neck:.8,torso:5};
export const JOINTS=sideTypes.flatMap(([name,type])=>['left','right'].map(side=>({name:`${side}_${name}`,type}))).concat(['neck_pitch','neck_yaw','torso_pitch','torso_yaw'].map(name=>({name,type:name.split('_')[0]}))).map((j,i)=>({...j,can_id:0x100+i}));
export function encodeFrame(values) {
  if(values.length!==4)throw new Error('Expected four actuator values');
  const bytes=new ArrayBuffer(8),view=new DataView(bytes);
  values.forEach((value,i)=>{
    const scaled=value*100,base=Math.floor(scaled);
    // Match Python round(): exact half ties round to the even integer.
    const integer=scaled-base===.5?(base%2===0?base:base+1):Math.round(scaled);
    if(!Number.isFinite(integer)||integer<(i===3?0:-32768)||integer>(i===3?65535:32767))throw new RangeError('Actuator value outside CAN field range');
    i===3?view.setUint16(i*2,integer):view.setInt16(i*2,integer);
  });
  return bytes;
}
export function decodeFrame(bytes) {
  if(bytes.byteLength!==8)throw new Error('Expected an 8-byte actuator frame');
  const view=new DataView(bytes);
  return [view.getInt16(0)/100,view.getInt16(2)/100,view.getInt16(4)/100,view.getUint16(6)/100];
}
export function actuatorId(j) {
  const parts=j.name.split('_'),side=parts.shift();
  const label=side==='left'||side==='right'?parts.join('-'):j.name.replaceAll('_','-');
  return `ACT-${side==='left'?'L':side==='right'?'R':'C'}-${label.toUpperCase()}-${j.can_id.toString(16).toUpperCase().padStart(3,'0')}`;
}
export class BrowserEngine {
  constructor(config) {
    this.config=structuredClone(config);this.records=new Map();this.history=new Map(JOINTS.map(j=>[j.name,[]]));
    this.lastSeen=new Map();this.lastUpdate=null;this.injections=new Map();this.serverId=`browser-${Math.random().toString(36).slice(2)}`;
  }
  observe(j,rule,value,now,reading=null,timeout=false) {
    const critical=timeout?this.config.heartbeat_timeout_ms:rule.critical,warning=timeout?critical:rule.warning;
    const compare=limit=>rule.comparison==='<'?value<limit:value>limit;
    const isCritical=compare(critical),bad=compare(warning),key=`${j.name}/${rule.code}`;
    let d=this.records.get(key);
    if(!bad) {
      if(d&&d.state!=='HEALED') {
        d.bad_samples=d.critical_samples=0;d.good_samples++;d.last_value=value;
        if(d.good_samples>=this.config.heal_samples){d.state='HEALED';d.healed_at_s=now;}
      }
      return;
    }
    if(!d) {
      d={code:rule.code,actuator_id:actuatorId(j),joint:j.name,rule:rule.rule,threshold:isCritical?critical:warning,
        value_at_trigger:value,units:rule.units,first_seen_s:now,last_seen_s:now,occurrences:0,state:'PENDING',freeze_frame:null,
        severity:'WARNING',comparison:rule.comparison,absolute:!!rule.absolute,bad_samples:0,critical_samples:0,good_samples:0,
        confirmed_at_s:null,healed_at_s:null,confirmed_after_samples:0,last_value:null};
      this.records.set(key,d);
    }
    if(d.state==='HEALED')Object.assign(d,{state:'PENDING',severity:'WARNING',bad_samples:0,critical_samples:0,good_samples:0,
      freeze_frame:null,confirmed_at_s:null,healed_at_s:null,confirmed_after_samples:0,threshold:isCritical?critical:warning,value_at_trigger:value});
    d.last_seen_s=now;d.last_value=value;d.occurrences++;d.bad_samples++;d.critical_samples=isCritical?d.critical_samples+1:0;d.good_samples=0;
    const count=this.config.confirm_samples,severity=d.critical_samples>=count?'CRITICAL':'WARNING';
    if(d.bad_samples>=count&&(d.state==='PENDING'||(severity==='CRITICAL'&&d.severity!=='CRITICAL'))) {
      Object.assign(d,{state:'CONFIRMED',severity,threshold:severity==='CRITICAL'?critical:warning,value_at_trigger:value,
        confirmed_at_s:now,confirmed_after_samples:count,freeze_frame:reading?{...reading}:null});
    } else if(d.state==='PENDING'){d.threshold=isCritical?critical:warning;d.value_at_trigger=value;}
  }
  receive(canId,bytes,now) {
    const j=JOINTS.find(j=>j.can_id===canId);if(!j)return;
    const [temperature_c,current_a,position_error_deg,voltage_v]=decodeFrame(bytes);
    const reading={t:now,temperature_c,current_a,position_error_deg,voltage_v};
    this.history.set(j.name,[...this.history.get(j.name),reading].filter(r=>now-r.t<=this.config.history_seconds));
    this.lastSeen.set(j.name,now);this.lastUpdate=now;
    for(const rule of this.config.rules)this.observe(j,rule,rule.absolute?Math.abs(reading[rule.field]):reading[rule.field],now,reading);
    this.observe(j,this.config.heartbeat,0,now,reading,true);
  }
  checkTimeouts(now) {
    for(const j of JOINTS) {
      const age=Math.max(0,now-(this.lastSeen.get(j.name)??0))*1000;
      if(age>this.config.heartbeat_timeout_ms)this.observe(j,this.config.heartbeat,age,now,this.history.get(j.name).at(-1)??null,true);
    }
  }
  dtcs() {
    const rank=d=>d.state==='HEALED'?2:d.severity==='CRITICAL'?0:1;
    return [...this.records.values()].sort((a,b)=>rank(a)-rank(b)||b.last_seen_s-a.last_seen_s||a.actuator_id.localeCompare(b.actuator_id)||a.code.localeCompare(b.code));
  }
  command(action,name,kind,now) {
    if(!['inject','reset','clear'].includes(action))throw new Error('Unknown action');
    if(action!=='reset'&&!JOINTS.some(j=>j.name===name))throw new Error('Unknown joint');
    if(action==='inject') {
      if(!['overtemp','overcurrent','encoder','heartbeat','undervoltage'].includes(kind))throw new Error('Unknown fault');
      this.injections.set(`${name}/${kind}`,{name,kind,since:now});
    } else if(action==='reset')this.injections.clear();
    else for(const [key,d] of this.records)if(d.joint===name)this.records.delete(key);
    return {ok:true,action,joint:name};
  }
  values(j,now) {
    const limit=this.config.rules.find(r=>r.code==='C10002').warning;
    const values=[35+.1*Math.sin(now+j.can_id),Math.min(nominal[j.type],limit*.6)+.04*Math.sin(2*now+j.can_id),.03*Math.sin(now),48+.05*Math.cos(now)];
    let online=true;
    for(const injection of this.injections.values())if(injection.name===j.name) {
      const age=Math.max(0,now-injection.since);
      if(injection.kind==='overtemp')values[0]=Math.min(75,35+30*age);
      if(injection.kind==='overcurrent')values[1]=8.5;
      if(injection.kind==='encoder')values[2]=Math.min(5,4*age);
      if(injection.kind==='heartbeat')online=false;
      if(injection.kind==='undervoltage')values[3]=38;
    }
    return online?values:null;
  }
  snapshot(selected,now) {
    const records=this.dtcs();
    const joints=JOINTS.map(j=>{
      const last=this.lastSeen.get(j.name),reading=this.history.get(j.name).at(-1),age=Math.max(0,now-(last??0));
      const dtcs=records.filter(d=>d.joint===j.name&&d.state!=='HEALED');
      const noData=last==null||age*1000>this.config.heartbeat_timeout_ms||dtcs.some(d=>d.rule==='TIMEOUT');
      const status=noData?'NO DATA':dtcs.some(d=>d.severity==='CRITICAL')?'CRITICAL':dtcs.length?'WARNING':'OK';
      return {name:j.name,can_id:j.can_id,actuator_id:actuatorId(j),status,dtcs,
        last_update_ms:last==null?null:last*1000,age_s:age,has_frame:!!reading,
        temperature_c:reading?.temperature_c??null,current_a:reading?.current_a??null,
        position_error_deg:reading?.position_error_deg??null,voltage_v:reading?.voltage_v??null,
        hint:dtcs.some(d=>d.code==='C10002')&&dtcs.some(d=>d.code==='C10003')?'High current with position error: possible mechanical binding. Inspect the joint; this is a hypothesis.':null};
    });
    return {server_id:this.serverId,elapsed_s:now,sampled_at_ms:now*1000,
      connection:{last_update_ms:this.lastUpdate==null?null:this.lastUpdate*1000,age_s:Math.max(0,now-(this.lastUpdate??0))},
      config:this.config,faults:[...this.injections.values()].map(i=>`${i.kind} on ${i.name}`),joints,dtcs:records,
      history:{[selected]:(this.history.get(selected)??[]).filter(r=>now-r.t<=this.config.history_seconds)},invalid_frames:0};
  }
}
