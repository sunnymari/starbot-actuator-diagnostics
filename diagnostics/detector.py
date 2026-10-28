"""Step 4: fault detector.

TODO (Marissa): write the detection logic here.
  - thresholds (e.g. temperature, current, voltage limits per joint)
  - trend detection (e.g. current rising over time -> est. hours to limit)
  - timeouts (a joint that stops sending frames)
  - output codes like: ACT-L-KNEE-003 | WARNING | overcurrent trend | est. 40 hrs to limit

Decode frames with sim.actuator.decode(msg.data) and look up the joint
with sim.actuator.JOINT_BY_ID[msg.arbitration_id].
"""
