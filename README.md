# Starbot actuator diagnostics

A live diagnostics demo for 28 simulated humanoid actuators, streaming real
8-byte frames through python-can's virtual CAN bus. Pink Starbot shows where
a problem is; grouped diagnostic trouble codes explain what happened and why.
These are synthetic demo thresholds, not manufacturer or Tesla limits.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m viz.server
```

Open http://localhost:8000. The default is a healthy baseline with manual fault
controls. For the spec's port, use `python -m viz.server --port 8765` and open
http://localhost:8765. The browser needs internet access to fetch the pinned
three.js modules from jsDelivr on first load.

`--scenario` enables the original timed knee-current drift, hip-temperature
ramp, neck encoder glitches and wrist dropout. `--no-faults` is retained as an
explicit healthy-start alias. All commands run from the project root.

## Two-minute demo

1. Each marker is one actuator. Select **left knee**, then **Overcurrent spike**.
   The marker turns yellow while pending, then red after five bad samples.
   Inspect the rule, threshold, trigger time, freeze-frame and 10-second charts.
2. Select **left wrist roll**, then **Drop heartbeat**. After 500 ms without a
   frame its marker becomes a grey pulsing hollow ring, labeled **No heartbeat**.
   Sensor faults remain red. Click either event row to select its actuator.
3. Return to the knee and click **Clear selected DTCs · 0x14** while the fault
   is still injected. It re-pends, then confirms. This models clearing local
   diagnostic storage; it is not a full UDS transport implementation.
4. Click **Reset all injections**. Telemetry becomes healthy immediately;
   latched codes heal after 20 good samples (about two seconds at 10 Hz).
   Healed records remain dimmed in history. Select **neck yaw** and inject
   **Encoder drift** to verify its visible yellow/red marker and grouped row.
5. Stop the server with Ctrl+C while leaving the page open. Within one second,
   the STALE banner appears, all markers become grey, controls disable and the
   last-frame timers keep counting. Restart the same command: the page resumes
   without a reload. Restart begins a new simulation and diagnostic history.
6. “Faster fault isolation means less downtime per robot. That is how
   diagnostics makes robots cheaper to build.”

**Overtemp ramp** and **Encoder drift** ramp simulated temperature/position
error; **Overcurrent spike** changes simulated current; **Drop heartbeat**
stops that actuator's frames. All controls run through encoding, CAN delivery,
decoding and the detector. Reset removes both manual and scheduled injections;
it does not erase DTC history. Repeated injection of the same fault restarts its
ramp without creating duplicate controls or event rows.

## Rules and DTC semantics

Edit [diagnostics/rules.json](diagnostics/rules.json), then restart the server.
It is the single source for sensor thresholds, the 500 ms heartbeat timeout,
1 s connection stale threshold, five-sample confirmation and 20-sample healing.

| DTC | Rule | Warning | Critical | Units |
| --- | --- | --- | --- | --- |
| C10001 | Motor overtemp | >50 | >65 | °C |
| C10002 | Overcurrent | >5 | >6 | A |
| C10003 | Absolute position error | >1.5 | >3 | deg |
| C10004 | Undervoltage | <44 | <40 | V |
| C10005 | Heartbeat timeout | — | >500 | ms since frame |

A first violation creates PENDING (yellow). Five consecutive violating samples
confirm it; a critical escalation also requires five consecutive critical
samples. A confirmed event remains latched until 20 consecutive samples pass
its warning threshold. Its original confirmed trigger and freeze-frame stay
visible while readings recover, explaining a red marker with normal readings.
Heartbeat recovery remains grey until its good-sample window completes.

Each `(actuator_id, code)` has one record. Occurrences counts **violating
samples**, not separate incidents. First/last seen track those violations;
confirmation and healing times are separate. A healed recurrence reuses its
row and cumulative count. Clear deletes the selected actuator's records so
any present fault must be detected again. Active critical records sort first,
then active warnings, then healed records. Timeout records use grey styling.

`actuator_id` uses side, joint name and the hexadecimal CAN ID, e.g.
`ACT-L-KNEE-112`. The legacy draft examples mixed fault-number suffixes with
actuator identity; DTC identity is now independently `C10001`–`C10005`.

Snapshots include `last_update_ms` for each actuator and the connection.
These are **server monotonic milliseconds**, valid within one `server_id`.
The browser advances server-supplied ages with its own monotonic elapsed time;
it never compares browser and server wall clocks. GET requests time out after
650 ms; reconnect backs off 0.5, 1, 2, 4, then at most 5 seconds. HTTP polling
continues after server restart. A responding server with a silent CAN feed
also becomes stale. History is in memory; restart intentionally clears it.

## Architecture in five lines

1. `sim/control.py` applies injections to independent simulated actuator state.
2. `sim/simulator.py` encodes 28 actuator messages at 10 Hz on a private virtual CAN channel.
3. `diagnostics/detector.py` decodes frames, debounces DTCs and retains 10 seconds of readings.
4. `diagnostics/live.py` supplies thread-safe, grouped snapshots; `viz/server.py` serves JSON and simulator commands.
5. `viz/web/viewer.mjs` renders three.js markers, DTC details and charts, and polls with stale/reconnect handling.

The virtual bus connects listeners **inside one Python process**. `LiveFeed`
starts simulator and listener together. HTTP remains polling, as in the
original prototype; no WebSocket or additional service is required.

## Hosted demo on Vercel

The published site is an explicitly labeled **browser simulation**. A Web Worker
runs isolated actuator state for each visitor, sends encoded 8-byte buffers over
an in-browser message bus, and applies the same rules and DTC state machine.
Ten fixture scenarios generated by the Python detector check parity with the
browser detector (debounce, escalation, healing, grouping, timeout and clear).
This adapter is not a physical CAN interface and does not run python-can.
The local `python -m viz.server` command retains the full Python virtual-CAN path.

Fault controls, grouped DTCs, freeze-frames, charts and all 28 markers work in
both modes. On the hosted site, **Pause connection** demonstrates stale markers
and increasing ages; **Resume connection** restores polling with backoff.
Each tab has its own simulation, and refreshing starts a new session. No server
history, user data, credentials, or database are needed for the hosted demo.

```bash
npm test
npm run build
vercel --prod
```

Vercel uses `vercel.json` to build `dist/`. The build copies the shared rules and
sets the explicit browser-runtime attribute; it never changes the local mode.
To regenerate detector parity fixtures after a rule/state-machine change:

```bash
python scripts/export-browser-parity.py
npm test
```

## Robot asset

The supplied **Meshy AI Pink Starbot** FBX and PNGs were converted to
[viz/web/robot.glb](viz/web/robot.glb): 9.5 MB with embedded base color, normal
and packed metallic/roughness textures, centered at 1.9 m tall. Model source:
Marissa's supplied Meshy export. No CC BY license information accompanied the
files, so no third-party author or license is inferred.

The supplied model is **static**: no skeleton, animation clips or separate
visor material. It contains 28 named diagnostic anchors; markers attach to
those nodes. Bone animation and a worried visor expression require a different
or edited source asset. The loader also supports Mixamo bones with or without
`mixamorig`, `mixamorig:` or `mixamorig_` prefixes, using the spec's joint map
and small offsets for shared bones. Bone names print once on load. Static
markers intentionally draw over the shell so the neck is not occluded.

To regenerate the supplied Starbot (Blender required):

```bash
blender --background --python viz/import_starbot.py -- /path/to/starbot_fbx_folder viz/web/robot.glb
```

On macOS Blender is usually `/Applications/Blender.app/Contents/MacOS/Blender`.
The existing server asset location `viz/web/robot.glb` is retained rather than
moving it to the spec's proposed `assets/robot.glb`. Missing/unloadable models
fall back to the original procedural robot. The included GLB is under 20 MB;
no optimization CLI or new heavy dependency was added.

## Verification

```bash
python -m unittest discover -s tests -v
node --test tests/viewer-state.test.mjs
```

Tests cover pending/confirmed/healed states, critical escalation, consecutive
sample resets, freeze-frame latching, grouped records, healing and recurrence,
clear-and-reconfirm, strict rule boundaries, timeout/startup/malformed frames,
per-joint freshness, simulator isolation/reset, and browser stale/backoff math.
See [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md) for the build audit and browser checks.

Other entry points remain available:

```bash
python -m sim.hello_can
python -m sim.receiver --cycles 2
python -m sim.receiver --faults
python -m viz.dashboard --no-faults
```

The original `sim/actuator.py` datasheet constants remain for the introductory
model; the demo detector uses `diagnostics/rules.json`. Demo current baselines
are capped at 60% of the warning threshold so all joints start healthy (the
old 6 A hip baseline exceeded the new global 5 A warning threshold). Scheduled ramps saturate at 100 °C / 20 A to stay encodable in long runs. Sensor
noise remains simulated and faults are observable only after CAN decoding.
