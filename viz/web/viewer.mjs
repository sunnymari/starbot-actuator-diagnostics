import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { connectionHealth, jointHealth, nextBackoff } from './viewer-state.mjs';
import { createTransport } from './transport.mjs';

const $ = id => document.getElementById(id);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (v, digits = 2) => v == null ? '—' : v.toFixed(digits);
const label = name => name.replaceAll('_', ' ');
const STATUS_COLOR = { OK:0x5cc98a, WARNING:0xf0b429, CRITICAL:0xe5484d, 'NO DATA':0x888b9c, UNKNOWN:0x888b9c };
const SIDE_JOINTS = {
  shoulder_pitch:[.22,1.42], shoulder_roll:[.27,1.42], shoulder_yaw:[.30,1.33],
  elbow:[.32,1.15], wrist_pitch:[.33,.96], wrist_roll:[.33,.90],
  hip_pitch:[.10,.90], hip_roll:[.13,.86], hip_yaw:[.12,.81],
  knee:[.12,.50], ankle_pitch:[.12,.12], ankle_roll:[.12,.07],
};
const CENTER_JOINTS = {neck_pitch:[0,1.56],neck_yaw:[0,1.62],torso_pitch:[0,1.00],torso_yaw:[0,1.10]};
let state = null, receivedAt = null, failed = false, selected = 'left_knee';
let health = {stale:true,ageS:0}, retryMs = 0, commandBusy = false;
let jointMap = {}, hovered = null;
const transport=createTransport();
const startedAt = performance.now();
const container = $('scene');
const renderer = new THREE.WebGLRenderer({antialias:true,alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
container.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40,1,.05,50);
camera.position.set(.9,1.4,3.3);
const controls = new OrbitControls(camera,renderer.domElement);
controls.target.set(0,.95,0); controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff,0xf3d5e4,2.2));
const sun = new THREE.DirectionalLight(0xffffff,1.4); sun.position.set(2,4,3); scene.add(sun);
const floor = new THREE.Mesh(new THREE.CircleGeometry(1.2,48),new THREE.MeshStandardMaterial({color:0xffe3ef}));
floor.rotation.x = -Math.PI/2; scene.add(floor);
function resize() {
  const width=container.clientWidth,height=container.clientHeight;
  renderer.setSize(width,height); camera.aspect=width/height; camera.updateProjectionMatrix();
}
addEventListener('resize',resize); resize();
const markers = new Map();
const sphereGeometry = new THREE.SphereGeometry(.023,16,12);
const ringGeometry = new THREE.TorusGeometry(.034,.0035,6,28);
function addMarker(name,position,parent=scene) {
  const group = new THREE.Group(); group.position.copy(position); parent.add(group);
  const worldScale = parent.getWorldScale(new THREE.Vector3());
  group.scale.set(1/worldScale.x,1/worldScale.y,1/worldScale.z);
  // Status markers intentionally draw over the shell so every anchor remains visible.
  const dot = new THREE.Mesh(sphereGeometry,new THREE.MeshStandardMaterial({color:STATUS_COLOR.UNKNOWN,
    emissive:STATUS_COLOR.UNKNOWN,emissiveIntensity:.2,transparent:true,depthTest:false,depthWrite:false}));
  const ring = new THREE.Mesh(ringGeometry,new THREE.MeshBasicMaterial({color:0x888b9c,transparent:true,depthTest:false,depthWrite:false}));
  dot.renderOrder=10; ring.renderOrder=11; dot.userData.joint=name;
  ring.userData.joint=name; group.add(dot,ring);
  markers.set(name,{group,dot,ring,status:'NO DATA'});
}
function placeholderPositions() {
  const result={};
  for (const [joint,[x,y]] of Object.entries(SIDE_JOINTS)) {
    result[`left_${joint}`]=new THREE.Vector3(x,y,.1);
    result[`right_${joint}`]=new THREE.Vector3(-x,y,.1);
  }
  for (const [name,[x,y]] of Object.entries(CENTER_JOINTS)) result[name]=new THREE.Vector3(x,y,.12);
  return result;
}

    function limb(a, b, radius, material) {
      const start = new THREE.Vector3(...a), end = new THREE.Vector3(...b);
      const mesh = new THREE.Mesh(new THREE.CapsuleGeometry(radius, start.distanceTo(end), 6, 16), material);
      mesh.position.copy(start).add(end).multiplyScalar(0.5);
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), end.clone().sub(start).normalize());
      return mesh;
    }

    function buildPlaceholderRobot() {
      const shell = new THREE.MeshStandardMaterial({ color: 0xf4f1f3, roughness: 0.45 });
      const dark = new THREE.MeshStandardMaterial({ color: 0x3b3340, roughness: 0.6 });
      const robot = new THREE.Group();
      const torso = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.5, 0.2), shell);
      torso.position.set(0, 1.2, 0);
      const pelvis = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.14, 0.18), dark);
      pelvis.position.set(0, 0.9, 0);
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 32, 24), shell);
      head.scale.set(1, 1.15, 1);
      head.position.set(0, 1.76, 0);
      const visor = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.05, 0.02), dark);
      visor.position.set(0, 1.78, 0.105);
      robot.add(torso, pelvis, head, visor, limb([0, 1.45, 0], [0, 1.62, 0], 0.04, dark));
      for (const s of [1, -1]) {
        robot.add(
          limb([s * 0.27, 1.42, 0], [s * 0.32, 1.15, 0], 0.045, shell),  // upper arm
          limb([s * 0.32, 1.15, 0], [s * 0.33, 0.93, 0], 0.038, shell),  // forearm
          limb([s * 0.12, 0.84, 0], [s * 0.12, 0.50, 0], 0.06, shell),   // thigh
          limb([s * 0.12, 0.50, 0], [s * 0.12, 0.12, 0], 0.05, shell),   // shin
        );
        const foot = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.05, 0.22), dark);
        foot.position.set(s * 0.12, 0.03, 0.04);
        robot.add(foot);
      }
      scene.add(robot);
      for (const [name, position] of Object.entries(placeholderPositions())) addMarker(name, position);
    }


const boneMap={shoulder:'Arm',elbow:'ForeArm',wrist:'Hand',hip:'UpLeg',knee:'Leg',ankle:'Foot'};
const jointNames=Object.keys(placeholderPositions());
function boneNameFor(name) {
  if (name.startsWith('neck')) return 'Neck';
  if (name.startsWith('torso')) return 'Spine';
  const [side,joint]=name.split('_');
  return side[0].toUpperCase()+side.slice(1)+boneMap[joint];
}
async function loadModel() {
  try {
    const head=await fetch('robot.glb',{method:'HEAD'});
    if (!head.ok) return false;
    const gltf=await new GLTFLoader().loadAsync('robot.glb');
    scene.add(gltf.scene); gltf.scene.updateMatrixWorld(true);
    const bounds=new THREE.Box3().setFromObject(gltf.scene),size=bounds.getSize(new THREE.Vector3());
    if (size.y>0) {
      gltf.scene.scale.multiplyScalar(1.9/size.y); gltf.scene.updateMatrixWorld(true);
      bounds.setFromObject(gltf.scene);
      const center=bounds.getCenter(new THREE.Vector3());
      gltf.scene.position.add(new THREE.Vector3(-center.x,-bounds.min.y,-center.z));
      gltf.scene.updateMatrixWorld(true);
    }
    const bones=new Map();
    gltf.scene.traverse(node=>{if(node.isBone) bones.set(node.name.replace(/^mixamorig[:_]?/i,''),node);});
    console.info('Robot bone names:', [...bones.values()].map(b=>b.name));
    if (!bones.size) console.info('Static Pink Starbot: named diagnostic anchors, no animation skeleton.');
    const offsets=new Map();
    for(const [name,fallback] of Object.entries(placeholderPositions())) {
      const anchor=gltf.scene.getObjectByName(name);
      const bone=bones.get(boneNameFor(name)) ?? (name.startsWith('torso')?bones.get('Hips'):null);
      if(anchor) addMarker(name,new THREE.Vector3(),anchor);
      else if(bone) {
        const index=offsets.get(bone.uuid)??0; offsets.set(bone.uuid,index+1);
        const location=bone.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3((index-1)*.065,0,.08));
        addMarker(name,bone.worldToLocal(location),bone);
      } else {
        addMarker(name,fallback);
        console.warn(`No model anchor or bone for ${name}; using fallback position`);
      }
    }
    return true;
  } catch(error) { console.warn('Robot unavailable; using the built-in model',error); return false; }
}

function selectJoint(name) {
  // Selection can happen while the GLB is still loading.
  if(!jointNames.includes(name)) return;
  selected=name; $('joint-select').value=name; renderDetails(); renderAlerts(); drawCharts();
  $('detail').scrollTop=0;
  $('control-target').textContent=`Selected: ${label(name)}`;
}
for(const name of jointNames) {
  const option=document.createElement('option'); option.value=name; option.textContent=label(name);
  $('joint-select').appendChild(option);
}
$('joint-select').value=selected;
$('joint-select').addEventListener('change',e=>selectJoint(e.target.value));
const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
function hit(event) {
  const r=renderer.domElement.getBoundingClientRect();
  pointer.set((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1);
  raycaster.setFromCamera(pointer,camera);
  return raycaster.intersectObjects([...markers.values()].flatMap(m=>[m.dot,m.ring]))[0]?.object.userData.joint;
}
renderer.domElement.addEventListener('pointermove',e=>{
  hovered=hit(e)??null; renderer.domElement.style.cursor=hovered?'pointer':'grab';
});
let pointerDown=null;
renderer.domElement.addEventListener('pointerdown',e=>{pointerDown=[e.clientX,e.clientY];});
renderer.domElement.addEventListener('pointerup',e=>{
  if(pointerDown && Math.hypot(e.clientX-pointerDown[0],e.clientY-pointerDown[1])<6) {
    const name=hit(e); if(name) selectJoint(name);
  }
  pointerDown=null;
});
const badge=status=>`<span class="badge ${status.replaceAll(' ','_')}">${escape(status)}</span>`;
const expression=d=>`${d.absolute?'|value| ':''}${fmt(d.value_at_trigger)} ${escape(d.units)} ${escape(d.comparison)} ${fmt(d.threshold)} ${escape(d.units)}`;
function dtcCard(d) {
  const frame=d.freeze_frame;
  const recovery=d.good_samples?` · recovering ${d.good_samples}/${state.config.heal_samples} good samples`:'';
  return `<article class="dtc"><div>${badge(d.rule==='TIMEOUT'?'NO DATA':d.severity)} <span class="mono">${escape(d.code)} · ${d.state}</span></div>
    <strong>${escape(d.rule)} · ${expression(d)}</strong>
    <p>Trigger at ${fmt(d.confirmed_at_s??d.first_seen_s,1)} s · ${d.state==='PENDING'?`debouncing ${d.bad_samples}/${state.config.confirm_samples} bad samples`:`confirmed after ${d.confirmed_after_samples} samples`}${recovery}</p>
    <p class="muted">First ${fmt(d.first_seen_s,1)} s · last ${fmt(d.last_seen_s,1)} s · ${d.occurrences} violating samples</p>
    ${frame?`<div class="freeze">Freeze-frame at ${fmt(frame.t,1)} s${d.rule==='TIMEOUT'?' (last received telemetry)':''}<br>
      ${fmt(frame.temperature_c,1)} °C · ${fmt(frame.current_a)} A · ${fmt(frame.position_error_deg)} deg · ${fmt(frame.voltage_v,1)} V</div>`:'<p class="muted">Freeze-frame is captured at confirmation.</p>'}</article>`;
}
function effective(joint,now=performance.now()) {
  return jointHealth(joint,health,receivedAt==null?0:Math.max(0,now-receivedAt)/1000,state?.config.heartbeat_timeout_ms??500);
}
function renderDetails() {
  const j=jointMap[selected]; if(!j) return;
  const view=effective(j);
  $('reading-detail').innerHTML=`<div class="reading-head"><span class="mono">0x${j.can_id.toString(16).toUpperCase()}</span><span id="joint-status">${badge(view.status)}</span></div>
    <div class="mono muted">${escape(j.actuator_id)}</div>
    <p id="joint-reason" class="reason">${escape(view.reason??'Live telemetry')}</p>
    <span id="last-frame"></span>
    <div class="readings"><div>Temperature<b>${fmt(j.temperature_c,1)} °C</b></div><div>Current<b>${fmt(j.current_a)} A</b></div>
      <div>Position error<b>${fmt(j.position_error_deg)} deg</b></div><div>Voltage<b>${fmt(j.voltage_v,1)} V</b></div></div>`;
  $('dtc-detail').innerHTML=j.dtcs.length?j.dtcs.map(dtcCard).join(''):'<p class="muted small">No active DTCs for this actuator.</p>';
  if(j.hint) { const p=document.createElement('p');p.className='small';p.textContent=j.hint;$('dtc-detail').appendChild(p); }
  updateAges();
}
function renderAlerts() {
  const records=state?.dtcs??[];
  $('event-count').textContent=`${records.length} codes`;
  $('alert-list').innerHTML=records.length?records.map(d=>`<button class="event ${d.state} ${d.joint===selected?'selected':''}" data-joint="${escape(d.joint)}" aria-label="Inspect ${escape(label(d.joint))} ${d.code}">
    <span class="event-meta"><span>${badge(d.rule==='TIMEOUT'?'NO DATA':d.severity)}</span><span>${d.state} · ×${d.occurrences}</span></span>
    <strong>${escape(label(d.joint))} · ${escape(d.rule==='TIMEOUT'?'No heartbeat':d.rule)}</strong>
    <span>${expression(d)}</span><br><span class="muted">${escape(d.actuator_id)} · ${d.code}<br>${fmt(d.first_seen_s,1)} s to ${fmt(d.last_seen_s,1)} s${d.state==='HEALED'?` · healed ${fmt(d.healed_at_s,1)} s`:''}</span></button>`).join(''):'<p class="muted small">No DTCs. Inject a fault to begin.</p>';
}
$('alert-list').addEventListener('click',e=>{const row=e.target.closest('[data-joint]');if(row)selectJoint(row.dataset.joint);});
function updateAges() {
  const now=performance.now();
  health=connectionHealth(state,receivedAt??startedAt,now,failed);
  const banner=$('stale-banner'); banner.hidden=!health.stale;
  banner.textContent=`STALE: no data for ${health.ageS.toFixed(1)} s · reconnecting${retryMs?` in up to ${(retryMs/1000).toFixed(1)} s`:''}`;
  const j=jointMap[selected];
  if(j) {
    const view=effective(j,now);
    if($('last-frame')) $('last-frame').textContent=j.has_frame?`Last frame: ${view.ageS<1?`${Math.round(view.ageS*1000)} ms`:`${view.ageS.toFixed(1)} s`} ago`:`No frame received · waiting ${view.ageS.toFixed(1)} s`;
    if($('joint-status')) $('joint-status').innerHTML=badge(view.status);
    if($('joint-reason')) $('joint-reason').textContent=view.reason??(j.dtcs.some(d=>d.state==='PENDING')?'Pending fault — debounce in progress':j.dtcs.length?'Confirmed event — see trigger and recovery below':'Live telemetry');
  }
  for(const [name,m] of markers) {
    const view=effective(jointMap[name],now); m.status=view.status;
    const color=STATUS_COLOR[m.status]??STATUS_COLOR.UNKNOWN;
    m.dot.material.color.setHex(color);m.dot.material.emissive.setHex(color);
    m.dot.material.opacity=m.status==='NO DATA'?.15:1;
    m.ring.material.color.setHex(m.status==='NO DATA'?0x888b9c:0xb16bc7);
  }
  for(const button of document.querySelectorAll('#controls button,#clear-dtc')) if(button.id!=='transport-toggle')button.disabled=health.stale||commandBusy;
}
function drawCharts() {
  const history=state?.history?.[selected]??[];
  for(const [id,field,code,title,unit] of [['temp-chart','temperature_c','C10001','Temperature','°C'],['current-chart','current_a','C10002','Current','A']]) {
    const canvas=$(id),ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
    ctx.clearRect(0,0,w,h);ctx.font='19px -apple-system, sans-serif';ctx.fillStyle='#87667c';ctx.fillText(`${title} · last 10 s`,10,22);
    if(!state) continue;
    const rule=state.config.rules.find(r=>r.code===code),values=history.map(p=>p[field]);
    const max=Math.max(rule.critical*1.18,...values.map(v=>v*1.15)),bottom=h-20,top=37;
    const y=v=>bottom-(v/max)*(bottom-top),start=state.elapsed_s-10;
    for(const [limit,color] of [[rule.warning,'#d2a543'],[rule.critical,'#d86178']]) {
      ctx.setLineDash([5,5]);ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(5,y(limit));ctx.lineTo(w-65,y(limit));ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=color;ctx.font='16px sans-serif';ctx.fillText(`${limit} ${unit}`,w-62,y(limit)+5);
    }
    ctx.strokeStyle=code==='C10001'?'#be659c':'#9675c4';ctx.lineWidth=3;ctx.beginPath();
    history.forEach((p,i)=>{const x=8+Math.max(0,Math.min(10,p.t-start))/10*(w-80);if(i===0)ctx.moveTo(x,y(p[field]));else ctx.lineTo(x,y(p[field]));});ctx.stroke();ctx.lineWidth=1;
    ctx.fillStyle='#87667c';ctx.font='15px sans-serif';ctx.fillText('−10 s',8,h-2);ctx.fillText('latest',w-100,h-2);
  }
}
let missingWarned=new Set();
async function poll() {
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),650);
  try {
    const next=await transport.snapshot(selected,abort.signal);
    if(!Array.isArray(next.joints)||!Array.isArray(next.dtcs)||!next.config) throw new Error('Invalid diagnostics snapshot');
    if(state && state.server_id!==next.server_id) $('command-status').textContent='Simulator restarted · fresh diagnostic session.';
    state=next;receivedAt=performance.now();failed=false;retryMs=0;
    jointMap=Object.fromEntries(state.joints.map(j=>[j.name,j]));
    for(const j of state.joints) if(!markers.has(j.name)&&!missingWarned.has(j.name)) {console.warn(`Actuator ${j.actuator_id} has no marker`);missingWarned.add(j.name);}
    updateAges(); renderDetails();renderAlerts();drawCharts();
    const flagged=state.joints.filter(j=>effective(j).status!=='OK').length;
    $('clock').textContent=`t = ${state.elapsed_s.toFixed(1)} s · ${flagged} of ${state.joints.length} joints flagged`;
    $('injections').textContent=state.faults.length?`Injected: ${state.faults.join('; ')}`:'No injections · healthy baseline';
  } catch(error) {
    failed=true;retryMs=nextBackoff(retryMs);updateAges();
    $('clock').textContent='Telemetry unavailable · automatic reconnect';
  } finally { clearTimeout(timeout);setTimeout(poll,failed?retryMs:250); }
}
async function command(action,fault) {
  if(commandBusy||health.stale)return;
  commandBusy=true;updateAges();
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),2000);
  try {
    await transport.command(action,selected,fault,abort.signal);
    $('command-status').textContent=action==='reset'?'Injections reset. DTCs heal after healthy samples.':action==='clear'?'Stored DTCs cleared. A present fault will confirm again.':`${label(selected)}: ${fault} injected into simulator.`;
  } catch(error) { $('command-status').textContent=`Command not acknowledged: ${error.message}. Check state before retrying.`; }
  finally {clearTimeout(timeout);commandBusy=false;updateAges();}
}
for(const button of document.querySelectorAll('[data-fault]'))button.addEventListener('click',()=>command('inject',button.dataset.fault));
$('reset').addEventListener('click',()=>command('reset'));
$('clear-dtc').addEventListener('click',()=>command('clear'));
if(transport.mode==='browser') {
  $('bus-label').textContent='BROWSER DEMO · 28 ACTUATORS';
  $('runtime-note').textContent='Browser simulation · encoded 8-byte frames';
  const toggle=$('transport-toggle');toggle.hidden=false;
  toggle.addEventListener('click',()=>{
    toggle.textContent=transport.toggleConnection()?'Resume connection':'Pause connection';
  });
}

let frames=0,frameStart=performance.now();
renderer.setAnimationLoop(time=>{
  const quaternion=camera.getWorldQuaternion(new THREE.Quaternion());
  for(const [name,m] of markers) {
    const noData=m.status==='NO DATA',focus=name===selected||name===hovered;
    const pulse=m.status==='CRITICAL'?1+.18*Math.sin(time/140):1;
    m.dot.scale.setScalar(focus?pulse*1.2:pulse);
    m.ring.visible=noData||focus;
    m.ring.material.opacity=noData?.45+.35*Math.sin(time/300):.95;
    m.ring.scale.setScalar(noData?1+.12*Math.sin(time/300):1.15);
    // Convert camera orientation to the marker parent's local frame.
    m.ring.quaternion.copy(m.group.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(quaternion));
  }
  controls.update();renderer.render(scene,camera);frames++;
  if(time-frameStart>=1000) {
    $('performance').textContent=`Synthetic demo · ${Math.round(frames*1000/(time-frameStart))} fps · ${markers.size}/28 markers`;
    frames=0;frameStart=time;
  }
});
setInterval(updateAges,100);
if(!(await loadModel()))buildPlaceholderRobot();
console.info(`Diagnostic markers: ${markers.size}/28`);
selectJoint(selected);poll();
