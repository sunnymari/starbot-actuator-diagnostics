"""Debounced diagnostic trouble codes, driven exclusively by decoded CAN frames."""
from collections import deque
from dataclasses import asdict, dataclass
import time

from diagnostics.config import CONFIG, frame_age_s
from sim.actuator import JOINT_BY_ID, JOINTS, decode

WARNING, CRITICAL = 'WARNING', 'CRITICAL'
ACTIVE = {'PENDING', 'CONFIRMED'}


@dataclass
class Reading:
    t: float
    temperature_c: float
    current_a: float
    position_error_deg: float
    voltage_v: float


def actuator_id(joint):
    side, _, rest = joint.name.partition('_')
    prefix = side[0].upper() if side in ('left', 'right') else 'C'
    label = rest if side in ('left', 'right') else joint.name
    return f'ACT-{prefix}-{label.upper().replace("_", "-")}-{joint.can_id:03X}'


@dataclass
class DTC:
    code: str
    actuator_id: str
    joint: str
    rule: str
    threshold: float
    value_at_trigger: float
    units: str
    first_seen_s: float
    last_seen_s: float
    occurrences: int = 0  # number of violating samples, grouped for the life of this record
    state: str = 'PENDING'
    freeze_frame: dict | None = None
    severity: str = WARNING
    comparison: str = '>'
    absolute: bool = False
    bad_samples: int = 0
    critical_samples: int = 0
    good_samples: int = 0
    confirmed_at_s: float | None = None
    healed_at_s: float | None = None
    confirmed_after_samples: int = 0
    last_value: float | None = None


class Detector:
    def __init__(self, config=None, started_at=None):
        self.config = config or CONFIG
        self.started_at = time.monotonic() if started_at is None else started_at
        self.history = {j.name: deque() for j in JOINTS}
        self.last_seen = {}
        self.dtcs = {}  # (joint name, DTC code) -> one record, including healed history
        self.invalid_frames = 0

    def _freeze(self, reading):
        if reading is None:
            return None
        result = asdict(reading)
        result['t'] -= self.started_at
        return result

    def _observe(self, joint, rule, value, now, reading=None, timeout=False):
        critical = self.config['heartbeat_timeout_ms'] if timeout else rule['critical']
        warning = critical if timeout else rule['warning']
        compare = (lambda limit: value < limit) if rule['comparison'] == '<' else (lambda limit: value > limit)
        is_critical, bad = compare(critical), compare(warning)
        key, elapsed = (joint.name, rule['code']), now - self.started_at
        dtc = self.dtcs.get(key)
        if not bad:
            if dtc and dtc.state in ACTIVE:
                dtc.bad_samples = dtc.critical_samples = 0
                dtc.good_samples += 1
                dtc.last_value = value
                if dtc.good_samples >= self.config['heal_samples']:
                    dtc.state, dtc.healed_at_s = 'HEALED', elapsed
            return
        if dtc is None:
            dtc = DTC(rule['code'], actuator_id(joint), joint.name, rule['rule'],
                      critical if is_critical else warning, value, rule['units'], elapsed, elapsed,
                      comparison=rule['comparison'], absolute=rule.get('absolute', False))
            self.dtcs[key] = dtc
        if dtc.state == 'HEALED':
            dtc.state, dtc.severity = 'PENDING', WARNING
            dtc.bad_samples = dtc.critical_samples = dtc.good_samples = 0
            dtc.freeze_frame = dtc.confirmed_at_s = dtc.healed_at_s = None
            dtc.confirmed_after_samples = 0
            dtc.threshold, dtc.value_at_trigger = (critical if is_critical else warning), value
        dtc.last_seen_s, dtc.last_value = elapsed, value
        dtc.occurrences += 1
        dtc.bad_samples += 1
        dtc.critical_samples = dtc.critical_samples + 1 if is_critical else 0
        dtc.good_samples = 0
        count = self.config['confirm_samples']
        # Pending stays yellow. Escalating a confirmed warning also debounces.
        confirmed = dtc.bad_samples >= count
        severity = CRITICAL if dtc.critical_samples >= count else WARNING
        if confirmed and (dtc.state == 'PENDING' or (severity == CRITICAL and dtc.severity != CRITICAL)):
            dtc.state, dtc.severity = 'CONFIRMED', severity
            dtc.threshold = critical if severity == CRITICAL else warning
            dtc.value_at_trigger, dtc.confirmed_at_s = value, elapsed
            dtc.confirmed_after_samples = count
            dtc.freeze_frame = self._freeze(reading)
        elif dtc.state == 'PENDING':
            dtc.threshold = critical if is_critical else warning
            dtc.value_at_trigger = value

    def update(self, msg, now):
        joint = JOINT_BY_ID.get(msg.arbitration_id)
        if joint is None:
            return []
        if msg.is_error_frame or msg.is_remote_frame or msg.dlc != 8 or len(msg.data) != 8:
            self.invalid_frames += 1
            return []
        reading = Reading(now, *decode(msg.data))
        history = self.history[joint.name]
        history.append(reading)
        while history and now - history[0].t > self.config['history_seconds']:
            history.popleft()
        self.last_seen[joint.name] = now
        for rule in self.config['rules']:
            value = getattr(reading, rule['field'])
            self._observe(joint, rule, abs(value) if rule.get('absolute') else value, now, reading)
        self._observe(joint, self.config['heartbeat'], 0, now, reading, timeout=True)
        return self.active_for(joint.name)

    def check_timeouts(self, now):
        for joint in JOINTS:
            age_ms = frame_age_s(self.last_seen.get(joint.name), now, self.started_at) * 1000
            if age_ms > self.config['heartbeat_timeout_ms']:
                latest = self.history[joint.name][-1] if self.history[joint.name] else None
                self._observe(joint, self.config['heartbeat'], age_ms, now, latest, timeout=True)
        return [d for d in self.dtcs.values() if d.rule == 'TIMEOUT' and d.state in ACTIVE]

    def active_for(self, name):
        return [d for (joint, _), d in self.dtcs.items() if joint == name and d.state in ACTIVE]

    def clear(self, name):
        for key in [key for key in self.dtcs if key[0] == name]:
            del self.dtcs[key]

    def records(self):
        def order(d):
            return (2 if d.state == 'HEALED' else 0 if d.severity == CRITICAL else 1,
                    -d.last_seen_s, d.actuator_id, d.code)
        return [asdict(d) for d in sorted(self.dtcs.values(), key=order)]
