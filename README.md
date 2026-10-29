# optimus-actuator-diagnostics

A CAN-bus diagnostics simulator for a humanoid robot's joint actuators.
It simulates 28 joint actuators that stream telemetry over a (virtual) CAN bus,
injects realistic faults, and runs a detector that flags them, shown in a live
terminal dashboard and a 3D robot view.

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

## Step 3: fault injection

[sim/faults.py](sim/faults.py) makes joints misbehave over time. The demo scenario
(compressed so everything happens within about two minutes):

| Starts | Joint             | Fault                                     |
|--------|-------------------|-------------------------------------------|
| 5 s    | `left_knee`       | current creeps up 0.05 A/s (wear)         |
| 15 s   | `right_hip_pitch` | temperature climbs 0.5 °C/s (overheating) |
| 20 s   | `neck_yaw`        | position error spikes ±3° (encoder glitch)|
| 30 s   | `left_wrist_roll` | stops sending frames (dropout)            |

```bash
python -m sim.receiver --faults
```

Limits the detector checks against live in [sim/actuator.py](sim/actuator.py):
80 °C, 1.6 × nominal current, 2° position error, 44–52 V, 0.5 s frame timeout.

## Step 4: fault detector

[diagnostics/detector.py](diagnostics/detector.py) gets every frame, keeps the last
10 s per joint, and runs three checks: thresholds, trends (predicting time to
limit with a linear fit), and timeouts. Alerts look like:

```
ACT-L-KNEE-003 | WARNING | overcurrent trend | est. 40 s to limit
```

## Step 5: live dashboard

```bash
python -m viz.dashboard
```

A table of all 28 joints, colored by the detector's status, plus an alert log.
`--no-faults` runs with every joint healthy.

## Step 6: 3D robot view

```bash
python -m viz.server
```

Open http://localhost:8000. Each joint is a marker that turns yellow or red
when the detector flags it; hover one for its live readings.

Without a model it draws a placeholder robot. To use your own, export a GLB
from Blender to `viz/web/robot.glb` with an Empty (or bone) named after each
joint (`left_knee`, `right_hip_pitch`, `neck_yaw`, ...). Markers snap to those.

## Project layout

```
sim/            actuator model, faults, simulator, receiver, hello_can
diagnostics/    fault detector, live feed (simulator + bus + detector in one process)
viz/            terminal dashboard, 3D viewer server, web/ (three.js page)
```
