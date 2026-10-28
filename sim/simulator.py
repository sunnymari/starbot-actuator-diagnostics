"""Step 2: every 100 ms, send one CAN frame per joint on the virtual bus."""

import threading
import time

import can

from sim.actuator import JOINTS, encode

CHANNEL = "test"
PERIOD_S = 0.100  # 100 ms = 10 Hz telemetry


def run_simulator(stop_event, cycles=None):
    """Send all joints every PERIOD_S until stop_event is set (or `cycles` cycles have run)."""
    with can.Bus(interface="virtual", channel=CHANNEL) as bus:
        cycle = 0
        next_tick = time.monotonic()
        while not stop_event.is_set() and (cycles is None or cycle < cycles):
            for joint in JOINTS:
                msg = can.Message(
                    arbitration_id=joint.can_id,
                    data=encode(*joint.read()),
                    is_extended_id=False,
                )
                bus.send(msg)
            cycle += 1

            # Schedule against a fixed clock so timing doesn't drift.
            next_tick += PERIOD_S
            stop_event.wait(max(0.0, next_tick - time.monotonic()))


def main():
    print(f"Sending {len(JOINTS)} joints every {PERIOD_S * 1000:.0f} ms on virtual channel '{CHANNEL}'.")
    print("Ctrl+C to stop. To see decoded frames, run `python -m sim.receiver` instead")
    print("(the virtual bus only works inside one process, so the receiver starts its own simulator).")
    stop_event = threading.Event()
    try:
        run_simulator(stop_event)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
