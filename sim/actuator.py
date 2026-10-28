"""Actuator model, joint list, and the 8-byte CAN frame format.

Frame layout (big-endian, 8 bytes):
    bytes 0-1  temperature_c       int16,  x100  (35.20 C  -> 3520)
    bytes 2-3  current_a           int16,  x100  (4.10 A   -> 410)
    bytes 4-5  position_error_deg  int16,  x100  (-0.05 deg -> -5)
    bytes 6-7  voltage_v           uint16, x100  (48.00 V  -> 4800)

Scaling by 100 keeps two decimal places while fitting each value in 2 bytes.
"""

import random
import struct

FRAME_FORMAT = ">hhhH"  # > big-endian, h = int16, H = uint16
SCALE = 100

# Nominal current draw (amps) by joint type. Legs carry the body, so they work harder.
NOMINAL_CURRENT_A = {
    "shoulder": 3.0,
    "elbow": 2.0,
    "wrist": 1.0,
    "hip": 6.0,
    "knee": 5.0,
    "ankle": 4.0,
    "neck": 0.8,
    "torso": 5.0,
}


class Actuator:
    """One joint actuator. Each read() returns its sensor values plus a little noise."""

    def __init__(self, name, can_id, joint_type):
        self.name = name
        self.can_id = can_id
        self.joint_type = joint_type

        # Healthy baseline values. Step 3 (fault injection) will push these around.
        self.temperature_c = 35.0
        self.current_a = NOMINAL_CURRENT_A[joint_type]
        self.position_error_deg = 0.0
        self.voltage_v = 48.0

    def read(self):
        """Return (temperature_c, current_a, position_error_deg, voltage_v) with sensor noise."""
        return (
            self.temperature_c + random.gauss(0, 0.2),
            self.current_a + random.gauss(0, 0.1),
            self.position_error_deg + random.gauss(0, 0.05),
            self.voltage_v + random.gauss(0, 0.1),
        )


def encode(temperature_c, current_a, position_error_deg, voltage_v):
    """Pack four floats into 8 bytes for a CAN frame."""
    return struct.pack(
        FRAME_FORMAT,
        round(temperature_c * SCALE),
        round(current_a * SCALE),
        round(position_error_deg * SCALE),
        round(voltage_v * SCALE),
    )


def decode(data):
    """Unpack 8 bytes back into (temperature_c, current_a, position_error_deg, voltage_v)."""
    raw = struct.unpack(FRAME_FORMAT, bytes(data))
    return tuple(value / SCALE for value in raw)


def build_joints():
    """Create the 28 actuators. Left joints get even CAN IDs, right joints odd.

    0x100 left_shoulder_pitch, 0x101 right_shoulder_pitch, 0x102 left_shoulder_roll, ...
    Neck and torso (no side) come last.
    """
    limb_joints = [
        ("shoulder_pitch", "shoulder"),
        ("shoulder_roll", "shoulder"),
        ("shoulder_yaw", "shoulder"),
        ("elbow", "elbow"),
        ("wrist_pitch", "wrist"),
        ("wrist_roll", "wrist"),
        ("hip_pitch", "hip"),
        ("hip_roll", "hip"),
        ("hip_yaw", "hip"),
        ("knee", "knee"),
        ("ankle_pitch", "ankle"),
        ("ankle_roll", "ankle"),
    ]
    center_joints = [
        ("neck_pitch", "neck"),
        ("neck_yaw", "neck"),
        ("torso_pitch", "torso"),
        ("torso_yaw", "torso"),
    ]

    joints = []
    can_id = 0x100
    for joint_name, joint_type in limb_joints:
        for side in ("left", "right"):
            joints.append(Actuator(f"{side}_{joint_name}", can_id, joint_type))
            can_id += 1
    for joint_name, joint_type in center_joints:
        joints.append(Actuator(joint_name, can_id, joint_type))
        can_id += 1
    return joints


JOINTS = build_joints()
JOINT_BY_ID = {joint.can_id: joint for joint in JOINTS}
