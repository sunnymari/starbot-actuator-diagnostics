"""Step 3: fault injection.

Each fault targets one joint and changes its actuator values as time passes,
so the detector has something real to catch. `t` is seconds since the
simulator started. Times are compressed so a demo shows every fault within
about two minutes.
"""

import random


class Fault:
    """Base class. `start_s` is when the fault begins."""

    kind = "fault"

    def __init__(self, joint_name, start_s):
        self.joint_name = joint_name
        self.start_s = start_s

    def apply(self, actuator, t):
        raise NotImplementedError

    def describe(self):
        return f"{self.kind} on {self.joint_name} from t={self.start_s:.0f}s"


class CurrentDrift(Fault):
    """Bearing or gear wear: the motor draws a little more current every second."""

    kind = "current drift (wear)"

    def __init__(self, joint_name, start_s, amps_per_s):
        super().__init__(joint_name, start_s)
        self.amps_per_s = amps_per_s
        self.baseline = None

    def apply(self, actuator, t):
        if self.baseline is None:
            self.baseline = actuator.current_a
        if t >= self.start_s:
            actuator.current_a = self.baseline + self.amps_per_s * (t - self.start_s)


class Overheat(Fault):
    """Cooling failure: temperature climbs steadily."""

    kind = "overheating"

    def __init__(self, joint_name, start_s, degrees_per_s):
        super().__init__(joint_name, start_s)
        self.degrees_per_s = degrees_per_s
        self.baseline = None

    def apply(self, actuator, t):
        if self.baseline is None:
            self.baseline = actuator.temperature_c
        if t >= self.start_s:
            actuator.temperature_c = self.baseline + self.degrees_per_s * (t - self.start_s)


class Dropout(Fault):
    """Broken cable or dead controller: the joint stops sending frames."""

    kind = "dropout"

    def apply(self, actuator, t):
        actuator.online = t < self.start_s


class EncoderGlitch(Fault):
    """Dirty or loose encoder: position error occasionally jumps by a few degrees."""

    kind = "encoder glitch"

    def __init__(self, joint_name, start_s, spike_deg, probability):
        super().__init__(joint_name, start_s)
        self.spike_deg = spike_deg
        self.probability = probability

    def apply(self, actuator, t):
        glitch = t >= self.start_s and random.random() < self.probability
        actuator.position_error_deg = random.choice((-1, 1)) * self.spike_deg if glitch else 0.0


def demo_faults():
    """The default scenario: one fault of each kind on a different joint."""
    return [
        CurrentDrift("left_knee", start_s=5, amps_per_s=0.05),          # 5.0 A -> 8.0 A limit at ~65 s
        Overheat("right_hip_pitch", start_s=15, degrees_per_s=0.5),     # 35 C -> 80 C limit at ~105 s
        EncoderGlitch("neck_yaw", start_s=20, spike_deg=3.0, probability=0.05),
        Dropout("left_wrist_roll", start_s=30),
    ]
