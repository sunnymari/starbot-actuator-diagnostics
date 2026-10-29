"""Regenerate browser fixtures from the authoritative Python detector."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import can
from diagnostics.config import CONFIG
from diagnostics.detector import Detector
from sim.actuator import JOINTS, JOINT_BY_NAME, encode


def normalize(value):
    if isinstance(value,float): return round(value,6)
    if isinstance(value,list): return [normalize(v) for v in value]
    if isinstance(value,dict): return {k:normalize(v) for k,v in value.items()}
    return value


def samples(n, values, start=0, joint='left_knee'):
    return [{'action':'sample','t':round(start+(i+1)*.1,6),'joint':joint,'values':values} for i in range(n)]

cases={
    'critical-confirm':samples(5,[35,8.5,0,48]),
    'interrupted-debounce':samples(4,[35,8,0,48])+samples(1,[35,3,0,48],.4)+samples(4,[35,8,0,48],.5),
    'heal-and-recur':samples(5,[35,8,0,48])+samples(20,[35,3,0,48],.5)+samples(5,[35,8,0,48],2.5),
    'warning-critical-escalation':samples(5,[35,5.5,0,48])+samples(5,[35,8,0,48],.5)+samples(3,[35,5.5,0,48],1),
    'four-sensor-rules':samples(5,[70,8,-4,38]),
    'strict-boundaries':samples(5,[50,5,-1.5,44]),
    'clear-reconfirm':samples(5,[35,8,0,48])+[{'action':'clear','joint':'left_knee'}]+samples(5,[35,8,0,48],.5),
    'timeout':samples(1,[35,3,0,48])+[{'action':'timeout','t':t} for t in [.6,.61,.71,.81,.91,1.01]],
    'timeout-recovery':samples(1,[35,3,0,48])+[{'action':'timeout','t':t} for t in [.61,.71,.81,.91,1.01]]+samples(20,[35,3,0,48],1.01),
    'grouped-joints':samples(10,[35,8,0,48])+samples(5,[35,3,2,48],1,'neck_yaw'),
}
result={'config':CONFIG,'joints':[{'name':j.name,'can_id':j.can_id} for j in JOINTS],'cases':[]}
for name,actions in cases.items():
    detector=Detector(started_at=0)
    for action in actions:
        if action['action']=='sample':
            detector.update(can.Message(arbitration_id=JOINT_BY_NAME[action['joint']].can_id,data=encode(*action['values']),is_extended_id=False),action['t'])
        elif action['action']=='timeout': detector.check_timeouts(action['t'])
        else: detector.clear(action['joint'])
    result['cases'].append({'name':name,'actions':actions,'expected':normalize(detector.records())})
path=Path(__file__).resolve().parents[1]/'tests/fixtures/browser-parity.json'
path.write_text(json.dumps(result,indent=2)+'\n')
print(f'Exported {len(cases)} Python detector parity scenarios')
