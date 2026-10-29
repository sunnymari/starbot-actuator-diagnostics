"""Step 4: fault detector.

The plumbing is done: every CAN frame goes through `Detector.update()`, which
decodes it and saves it in a per-joint history. The dashboard and the 3D
viewer show whatever alerts your checks return.

TODO (Marissa): fill in the three check methods below. Each returns a list of
Alert objects (an empty list means healthy). Run `python -m viz.dashboard` to
watch your alerts show up live while the demo faults play out:

    t=5s   left_knee        current starts creeping up (wear)
    t=15s  right_hip_pitch  temperature starts climbing (overheating)
    t=20s  neck_yaw         position error spikes now and then (encoder glitch)
    t=30s  left_wrist_roll  stops sending frames (dropout)

Limits live in sim/actuator.py: TEMPERATURE_LIMIT_C, current_limit_a(joint_type),
POSITION_ERROR_LIMIT_DEG, VOLTAGE_RANGE_V, FRAME_TIMEOUT_S.
"""

from collections import deque
from dataclasses import dataclass

from sim.actuator import (  # noqa: F401  (the limits are here for your checks)
    FRAME_TIMEOUT_S,
    JOINT_BY_ID,
    JOINTS,
    POSITION_ERROR_LIMIT_DEG,
    TEMPERATURE_LIMIT_C,
    VOLTAGE_RANGE_V,
    current_limit_a,
    decode,
)

HISTORY_LENGTH = 100  # 100 frames = the last 10 seconds per joint

WARNING = "WARNING"
CRITICAL = "CRITICAL"

# Number part of the fault code, e.g. ACT-L-KNEE-003.
OVERTEMP = 1
OVERCURRENT = 2
OVERCURRENT_TREND = 3
OVERTEMP_TREND = 4
POSITION_ERROR = 5
VOLTAGE = 6
TIMEOUT = 7


@dataclass
class Reading:
    t: float                  # time.monotonic() when the frame arrived
    temperature_c: float
    current_a: float
    position_error_deg: float
    voltage_v: float


@dataclass
class Alert:
    joint: str
    code: str
    severity: str             # WARNING or CRITICAL
    message: str

    def __str__(self):
        return f"{self.code} | {self.severity} | {self.message}"


def fault_code(joint_name, number):
    """left_knee + 3 -> ACT-L-KNEE-003, neck_yaw + 7 -> ACT-C-NECK-YAW-007."""
    side, _, rest = joint_name.partition("_")
    if side in ("left", "right"):
        prefix = side[0].upper()
    else:
        prefix, rest = "C", joint_name  # center joints: neck, torso
    return f"ACT-{prefix}-{rest.upper().replace('_', '-')}-{number:03d}"


class Detector:
    def __init__(self):
        self.history = {joint.name: deque(maxlen=HISTORY_LENGTH) for joint in JOINTS}
        self.last_seen = {}   # joint name -> time of its latest frame

    def update(self, msg, now):
        """Decode one CAN frame, store it, and return any alerts for that joint."""
        joint = JOINT_BY_ID.get(msg.arbitration_id)
        if joint is None:
            return []
        reading = Reading(now, *decode(msg.data))
        self.history[joint.name].append(reading)
        self.last_seen[joint.name] = now
        return self.check_thresholds(joint, reading) + self.check_trends(joint)

    def check_thresholds(self, joint, reading):
        """Compare one reading against the limits.

        `joint.name`, `joint.joint_type`, and the Reading fields are what you need.
        Ideas: WARNING when a value passes ~85% of its limit, CRITICAL past the limit.
        Build an alert like:
            Alert(joint.name, fault_code(joint.name, OVERTEMP), CRITICAL,
                  f"temperature {reading.temperature_c:.1f} C over {TEMPERATURE_LIMIT_C} C limit")
        """
        alerts = []
        # TODO: temperature, current, position error, voltage
        return alerts

    def check_trends(self, joint):
        """Look at the joint's history and predict trouble before it happens.

        self.history[joint.name] is a deque of Readings, oldest first. Ideas:
          - wait until there are enough readings (e.g. 50) so noise doesn't fool you
          - numpy.polyfit(times, currents, 1) gives (slope, intercept)
          - if the slope is clearly positive, time to limit = (limit - latest) / slope
          - report it, e.g. "overcurrent trend | est. 40 s to limit"
        """
        alerts = []
        # TODO: current trend, temperature trend
        return alerts

    def check_timeouts(self, now):
        """Called about every 100 ms for all joints. Flag joints that went quiet.

        self.last_seen[name] is when each joint last sent a frame. A joint that
        has never sent anything won't be in it yet.
        """
        alerts = []
        # TODO: compare now - last_seen against FRAME_TIMEOUT_S
        return alerts
