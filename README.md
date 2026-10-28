# optimus-actuator-diagnostics

A CAN-bus diagnostics simulator for a humanoid robot's joint actuators.
It simulates 28 joint actuators that stream telemetry over a (virtual) CAN bus,
so a diagnostics layer can decode it and later flag faults.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run every command below from the project root, with the venv active.

## Step 1: first CAN message

```bash
python -m sim.hello_can
```

Opens two buses on the same virtual channel (`test`), sends one frame on the
first and receives it on the second.

## Step 2: actuator simulator

```bash
python -m sim.receiver --cycles 2
```

Starts the simulator and prints every decoded frame, grouped by 100 ms cycle.
Leave out `--cycles` to run until Ctrl+C.

`python -m sim.simulator` runs the sender alone, which is useful later when
something else in the same process listens to the bus.

**Why the receiver starts the simulator itself:** python-can's `virtual`
interface only connects buses inside one Python process. So the receiver runs
the simulator in a background thread and listens on its own separate `Bus`.
Every value still goes through a real CAN frame: encoded to 8 bytes, sent on
the bus, received and decoded.

### Joints and CAN IDs

28 actuators: 12 per side (shoulder pitch/roll/yaw, elbow, wrist pitch/roll,
hip pitch/roll/yaw, knee, ankle pitch/roll) plus neck pitch/yaw and torso pitch/yaw.
Left and right alternate: `0x100` left_shoulder_pitch, `0x101` right_shoulder_pitch,
... `0x112` left_knee, `0x113` right_knee, ... `0x11B` torso_yaw.

### Frame format (8 bytes, big-endian)

| Bytes | Field              | Type   | Scale | Example            |
|-------|--------------------|--------|-------|--------------------|
| 0–1   | temperature_c      | int16  | ×100  | 35.20 °C → 3520    |
| 2–3   | current_a          | int16  | ×100  | 4.10 A → 410       |
| 4–5   | position_error_deg | int16  | ×100  | −0.05° → −5        |
| 6–7   | voltage_v          | uint16 | ×100  | 48.00 V → 4800     |

Packed with `struct.pack(">hhhH", ...)` in [sim/actuator.py](sim/actuator.py).

## Project layout

```
sim/            actuator model, simulator, receiver, hello_can
diagnostics/    fault detector (Step 4, TODO)
viz/            visualization (later)
```
