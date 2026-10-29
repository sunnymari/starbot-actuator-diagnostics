"""One process: simulator -> virtual CAN -> detector -> serializable snapshots."""
from dataclasses import asdict
import threading
import time
import uuid

import can

from diagnostics.config import CONFIG, frame_age_s, has_no_data
from diagnostics.detector import CRITICAL, WARNING, Detector, actuator_id
from sim.actuator import JOINT_BY_ID, JOINT_BY_NAME, JOINTS
from sim.control import SimulatorControl
from sim.faults import demo_faults
from sim.simulator import run_simulator

TIMEOUT_CHECK_S = 0.1


class LiveFeed:
    def __init__(self, faults=False, config=None):
        self.config = config or CONFIG
        self.controller = SimulatorControl(demo_faults() if faults else [], config=self.config)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.started_at = time.monotonic()
        self.detector = Detector(self.config, self.started_at)
        self.server_id = uuid.uuid4().hex
        self.channel = 'diagnostics-' + self.server_id
        self.last_update = None

    def start(self):
        self.bus = can.Bus(interface='virtual', channel=self.channel)
        self.started_at = self.detector.started_at = time.monotonic()
        self.threads = [
            threading.Thread(target=run_simulator, args=(self.stop_event,),
                             kwargs={'controller': self.controller, 'channel': self.channel}, daemon=True),
            threading.Thread(target=self._listen, daemon=True),
        ]
        for thread in self.threads:
            thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=1)
        self.bus.shutdown()

    def _listen(self):
        next_check = time.monotonic()
        while not self.stop_event.is_set():
            msg = self.bus.recv(timeout=TIMEOUT_CHECK_S)
            now = time.monotonic()
            with self.lock:
                if msg is not None and msg.arbitration_id in JOINT_BY_ID:
                    self.detector.update(msg, now)
                    if self.detector.last_seen.get(JOINT_BY_ID[msg.arbitration_id].name) == now:
                        self.last_update = now
                if now >= next_check:
                    self.detector.check_timeouts(now)
                    next_check = now + TIMEOUT_CHECK_S

    def control(self, action, joint=None, fault=None):
        if action not in {'inject', 'reset', 'clear'}:
            raise ValueError('Unknown action')
        if action != 'reset' and joint not in JOINT_BY_NAME:
            raise ValueError('Unknown joint')
        with self.lock:
            if action == 'inject':
                self.controller.inject(joint, fault)
            elif action == 'reset':
                self.controller.reset()
            else:
                self.detector.clear(joint)
        return {'ok': True, 'action': action, 'joint': joint}

    def snapshot(self, selected=None, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            records = self.detector.records()
            grouped = {j.name: [] for j in JOINTS}
            for d in records:
                if d['state'] != 'HEALED':
                    grouped[d['joint']].append(d)
            joints = []
            for joint in JOINTS:
                name = joint.name
                history = self.detector.history[name]
                reading = history[-1] if history else None
                last_seen = self.detector.last_seen.get(name)
                age = frame_age_s(last_seen, now, self.started_at)
                active = grouped[name]
                no_data = has_no_data(last_seen, now, self.started_at, self.config['heartbeat_timeout_ms'])
                no_data = no_data or any(d['rule'] == 'TIMEOUT' for d in active)
                status = ('NO DATA' if no_data else CRITICAL if any(d['severity'] == CRITICAL for d in active)
                          else WARNING if active else 'OK')
                hint = None
                if any(d['code'] == 'C10002' for d in active) and any(d['code'] == 'C10003' for d in active):
                    hint = 'High current with position error: possible mechanical binding. Inspect the joint; this is a hypothesis.'
                joints.append({
                    'name': name, 'actuator_id': actuator_id(joint), 'can_id': joint.can_id,
                    'status': status, 'dtcs': active, 'alerts': [self._text(d) for d in active],
                    'last_update_ms': None if last_seen is None else last_seen * 1000,
                    'age_s': age, 'has_frame': reading is not None, 'hint': hint,
                    **{field: getattr(reading, field) if reading else None for field in
                       ('temperature_c', 'current_a', 'position_error_deg', 'voltage_v')},
                })
            history = {}
            if selected in self.detector.history:
                history[selected] = [{**asdict(r), 't': r.t - self.started_at}
                                     for r in self.detector.history[selected] if now - r.t <= self.config['history_seconds']]
            log = [{**d, 't': d['last_seen_s'], 'text': self._text(d)} for d in records]
            return {
                'server_id': self.server_id, 'elapsed_s': now - self.started_at,
                'sampled_at_ms': now * 1000,
                'connection': {'last_update_ms': None if self.last_update is None else self.last_update * 1000,
                               'age_s': frame_age_s(self.last_update, now, self.started_at)},
                'config': self.config, 'faults': self.controller.describe(),
                'joints': joints, 'dtcs': records, 'log': log, 'history': history,
                'invalid_frames': self.detector.invalid_frames,
            }

    @staticmethod
    def _text(d):
        return (f"{d['actuator_id']} {d['code']} {d['state']} {d['rule']}: "
                f"{d['value_at_trigger']:.2f} {d['units']} {d['comparison']} {d['threshold']:.2f} {d['units']}")
