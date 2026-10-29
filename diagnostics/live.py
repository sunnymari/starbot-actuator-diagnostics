"""Runs the simulator, the CAN listener, and the detector together in one process.

The dashboard and the 3D viewer both use LiveFeed and only read `snapshot()`.
"""

import threading
import time
from collections import deque

import can

from diagnostics.detector import CRITICAL, WARNING, Detector
from sim.actuator import JOINT_BY_ID, JOINTS
from sim.faults import demo_faults
from sim.simulator import CHANNEL, run_simulator

ALERT_HOLD_S = 2.0      # a joint stays yellow/red this long after its last alert
TIMEOUT_CHECK_S = 0.1
SEVERITY_RANK = {"OK": 0, WARNING: 1, CRITICAL: 2}


class LiveFeed:
    def __init__(self, faults=True):
        self.faults = demo_faults() if faults else []
        self.detector = Detector()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.started_at = None
        self.readings = {}      # joint name -> latest Reading
        self.recent = {}        # joint name -> [(time, Alert), ...] within ALERT_HOLD_S
        self.log = deque(maxlen=200)  # (elapsed_s, Alert), only when an alert first appears

    def start(self):
        # Open the listening bus before the simulator starts so no frames are missed.
        self.bus = can.Bus(interface="virtual", channel=CHANNEL)
        self.started_at = time.monotonic()
        self.threads = [
            threading.Thread(target=run_simulator, args=(self.stop_event, None, self.faults), daemon=True),
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
        next_timeout_check = time.monotonic()
        while not self.stop_event.is_set():
            msg = self.bus.recv(timeout=TIMEOUT_CHECK_S)
            now = time.monotonic()
            alerts = []
            with self.lock:
                if msg is not None and msg.arbitration_id in JOINT_BY_ID:
                    alerts += self.detector.update(msg, now)
                    name = JOINT_BY_ID[msg.arbitration_id].name
                    self.readings[name] = self.detector.history[name][-1]
                if now >= next_timeout_check:
                    alerts += self.detector.check_timeouts(now)
                    next_timeout_check = now + TIMEOUT_CHECK_S
                for alert in alerts:
                    self._record(alert, now)

    def _record(self, alert, now):
        held = self.recent.setdefault(alert.joint, [])
        if not any(old.code == alert.code for _, old in held):
            self.log.append((now - self.started_at, alert))
        held[:] = [(t, a) for t, a in held if a.code != alert.code] + [(now, alert)]

    def snapshot(self):
        """Plain dicts, safe to print or turn into JSON."""
        now = time.monotonic()
        with self.lock:
            joints = []
            for joint in JOINTS:
                held = [(t, a) for t, a in self.recent.get(joint.name, []) if now - t <= ALERT_HOLD_S]
                self.recent[joint.name] = held
                alerts = [a for _, a in held]
                status = max((a.severity for a in alerts), key=SEVERITY_RANK.get, default="OK")
                reading = self.readings.get(joint.name)
                joints.append({
                    "name": joint.name,
                    "can_id": joint.can_id,
                    "status": status,
                    "alerts": [str(a) for a in alerts],
                    "age_s": None if reading is None else now - reading.t,
                    "temperature_c": reading and reading.temperature_c,
                    "current_a": reading and reading.current_a,
                    "position_error_deg": reading and reading.position_error_deg,
                    "voltage_v": reading and reading.voltage_v,
                })
            log = [{"t": round(t, 1), "joint": a.joint, "severity": a.severity, "text": str(a)}
                   for t, a in list(self.log)[-30:]]
        return {
            "elapsed_s": now - self.started_at,
            "faults": [f.describe() for f in self.faults],
            "joints": joints,
            "log": log,
        }
