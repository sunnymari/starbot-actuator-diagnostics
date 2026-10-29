"""Thread-safe simulator commands. Injections alter telemetry before CAN encoding."""
import threading
import time

from diagnostics.config import CONFIG
from sim.actuator import NOMINAL_CURRENT_A, build_joints

FAULTS = {'overtemp', 'overcurrent', 'encoder', 'heartbeat', 'undervoltage'}


class SimulatorControl:
    def __init__(self, scheduled=(), config=None):
        self.lock = threading.Lock()
        self.joints = build_joints()  # independent state for every simulator instance
        self.names = {j.name for j in self.joints}
        self.scheduled = list(scheduled)
        self.injections = {}
        current_warning = next(r['warning'] for r in (config or CONFIG)['rules'] if r['code'] == 'C10002')
        self.baselines = {j.name: min(NOMINAL_CURRENT_A[j.joint_type], current_warning * 0.6) for j in self.joints}

    def inject(self, name, kind):
        if name not in self.names or kind not in FAULTS:
            raise ValueError('Choose a known joint and fault type')
        with self.lock:
            self.injections[(name, kind)] = time.monotonic()

    def reset(self):
        with self.lock:
            self.injections.clear()
            self.scheduled.clear()

    def describe(self):
        with self.lock:
            return ([f.describe() for f in self.scheduled] +
                    [f'{kind} on {name}' for name, kind in self.injections])

    def sample(self, elapsed):
        with self.lock:
            now = time.monotonic()
            by_name = {j.name: j for j in self.joints}
            for j in self.joints:
                j.temperature_c, j.current_a = 35.0, self.baselines[j.name]
                j.position_error_deg, j.voltage_v, j.online = 0.0, 48.0, True
            for fault in self.scheduled:
                fault.apply(by_name[fault.joint_name], elapsed)
            for (name, kind), since in self.injections.items():
                j, age = by_name[name], now - since
                if kind == 'overtemp':
                    j.temperature_c = min(75.0, 35.0 + 30.0 * age)
                elif kind == 'overcurrent':
                    j.current_a = 8.5
                elif kind == 'encoder':
                    j.position_error_deg = min(5.0, 4.0 * age)
                elif kind == 'heartbeat':
                    j.online = False
                elif kind == 'undervoltage':
                    j.voltage_v = 38.0
            return [(j.can_id, j.read()) for j in self.joints if j.online]
