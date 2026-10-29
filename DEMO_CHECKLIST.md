# Demo implementation audit

Audited against Marissa's `Actuator_Diagnostics_Demo_Spec.md`.

## Already present at audit start

- 28 actuator identities and 8-byte CAN encode/decode, 10 Hz virtual bus,
  simulator, scheduled faults, shared live-feed process and terminal dashboard.
- A standard-library HTTP server and polling three.js viewer with orbit controls.
- Pink Starbot from the previous model replacement: embedded GLB textures,
  28 named anchors, and a repeatable Blender conversion script.
- The detector's threshold, trend and timeout methods were still empty stubs.
  Status colors therefore did not yet represent confirmed diagnostic rules.

## Spec status

| Item | Result | Evidence / behavior |
| --- | --- | --- |
| P0-1 stale / reconnect | Complete | Advancing per-joint ages, grey markers, STALE banner, 650 ms request deadline and exponential retry; open page recovered after actual server shutdown/restart without reloading. Stale logic is covered by Node tests. |
| P0-2 explainable DTCs | Complete | Configured rules, pending/confirmed/healed states, five-bad / 20-good sample windows, trigger values, threshold units, timestamps and frozen confirmation readings. Browser observed knee pending, confirmed, clear, re-pend. |
| P0-3 grouped alerts | Complete | One record per actuator/code, count of violating samples, first/last time, critical-first / healed-last sort; clicking knee event selected that actuator. No repeated neck rows. |
| P0-4 comms styling | Complete | Wrist dropout displayed NO DATA and a pulsing hollow grey ring, while knee sensor overcurrent stayed red. Returning heartbeat remains grey during its healing window. |
| P0-5 every marker | Complete | 28/28 marker count and GLB anchor test; neck yaw was selected and visually verified yellow during encoder debounce. Status markers draw over the shell. |
| P1-1 model | Existing static asset retained; loader extended | 9.5 MB GLB, embedded textures, anchor parenting and optional Mixamo bone mapping. Actual rigged model is unavailable, so the bone adapter cannot be validated against this static asset. |
| P1-2 simulator injection | Complete | Overcurrent spike, overtemp ramp, encoder drift, heartbeat dropout and reset controls run before CAN encoding. Actual CAN integration test verifies the detection path. |
| P1-3 sparklines | Complete | Ten-second temperature/current plots with warning and critical threshold lines; visible current spike verified in browser. |
| P1-4 clear DTC | Complete | Selected actuator storage is cleared; a present injected fault re-pends and confirms. Browser and integration tests both verified this. Models local 0x14 behavior, not full UDS transport. |
| P1-5 visor | Asset limitation | The supplied mesh has one material rather than a separate visor; original heart eyes remain. No worried-expression swap. |
| P2 root-cause hint | Complete for the proposed simple rule | Active current plus position-error DTCs show a qualified possible-binding hint. No claim of a definitive mechanical diagnosis. |
| P2 digital twin | Asset limitation | No skeleton or joint animation signal in this supplied model. No fabricated animation or bone axes. |

## Validation

- **17 Python tests passed**, including an actual threaded simulator -> python-can
  -> detector integration test and validation of all 28 GLB anchors/textures.
- **5 Node tests passed** for connection freshness, continuously advancing ages,
  per-joint timeout, recovery and bounded exponential backoff.
- JavaScript syntax check passed.
- `python -m sim.receiver --cycles 2` still received 56 frames.
- Terminal dashboard rendering was checked for startup NO DATA support.
- The embedded browser counter varied between **30 and 120 fps** across
  checks with all 28 markers and the supplied GLB. A consistent **60 fps is
  not yet verified**; repeat the performance check in the actual presentation
  browser on the interview machine. Functional checks passed at both rates.
- No console errors/warnings on normal model load. Expected failed requests
  while deliberately stopping the server were part of the reconnect check.
- Narrow layout was checked: model above the stacked inspector and controls.
- Startup joint selection was tested during GLB loading and retained correctly.

Run reproducible checks from the project root:

```bash
python -m unittest discover -s tests -v
node --test tests/viewer-state.test.mjs
node --check viz/web/viewer.mjs
```

The browser fault-injection / heartbeat / clear / reset / stop / restart sequence
is documented in README. Repeat it before the interview, especially if changing
thresholds, textures, browser hardware or model assets.

## Differences from the draft spec

- Existing default port is **8000**. `--port 8765` runs the spec's chosen URL.
- Existing asset path remains **viz/web/robot.glb**, rather than assets/robot.glb.
- Actual Meshy source is a **static FBX**, not a rigged GLB. It has named anchors
  added during conversion; no Mixamo skeleton or separate visor was supplied.
- Actual CAN IDs come from `sim/actuator.py`; actuator labels now use those IDs
  consistently. Example knee is ACT-L-KNEE-112 / CAN 0x112; DTC is separately C10002.
- New demo rules are centralized in diagnostics/rules.json. Legacy introductory
  datasheet constants remain in sim/actuator.py but do not govern this demo.
- Old nominal hip current was 6 A, already over the new warning threshold of 5 A.
  The synthetic healthy simulator caps nominal current at 60% of that warning.
- The original timed scenario is available with `--scenario`; the default server
  starts healthy so the two-minute manual demonstration is repeatable.
- DTC history is retained in memory until clear or server restart. Occurrences
  counts violating samples, not separate fault episodes.

## Files changed for this audit

- `diagnostics/config.py`, `diagnostics/rules.json`, `diagnostics/detector.py`,
  `diagnostics/live.py`: rules, DTC lifecycle, freshness and grouped snapshots.
- `sim/control.py`, `sim/simulator.py`, `sim/faults.py`: isolated simulator state, real CAN injections and bounded scheduled ramps.
- `viz/server.py`, `viz/dashboard.py`: HTTP controls, fresh snapshots and terminal compatibility.
- `viz/web/index.html`, `viewer.css`, `viewer.mjs`, `viewer-state.mjs`: inspector,
  controls, grouped events, charts, model/bone attachments and reconnect behavior.
- `tests/test_diagnostics.py`, `test_can_integration.py`, `test_model.py`,
  `test_scheduled_faults.py`, `viewer-state.test.mjs`: deterministic unit and CAN integration coverage.
- `README.md`, `DEMO_CHECKLIST.md`: launch instructions, two-minute script and audit.

The earlier robot asset and `viz/import_starbot.py` are preserved. No new Python
or npm dependency is required; Node is only needed for the frontend unit tests.

A long-running old preview exposed unbounded scheduled ramps overflowing the signed CAN fields. Scheduled overheat now saturates at 100 °C and current drift at 20 A; a day-long simulated scenario is regression-tested for encodable frames.

## Vercel deployment addition

The Vercel build uses an explicitly labeled browser simulation in a Web Worker.
The Python virtual-CAN application remains the local reference implementation.
The hosted adapter has no shared state between visitors and needs no continuous
server process. It transports encoded 8-byte buffers through a browser message
bus, rather than claiming to run python-can in Vercel background threads.

- The original 17 Python tests remain passing.
- 19 Node tests pass, including ten parity scenarios exported from the Python detector.
- The static build succeeds with no npm dependencies.
- Hosted-mode overcurrent injection, confirmation, and freeze-frame were verified
  in the browser without console warnings/errors.
- Added `browser-engine.mjs`, `browser-worker.mjs`, `transport.mjs`, the browser
  parity tests/fixture generator, a static build script, and Vercel configuration.
- **Pause connection / Resume connection** demonstrates the same stale/recovery
  behavior on the hosted page. Local Python mode continues using `/state` and `/control`.
