"""Receive actuator frames from the virtual bus, decode them, and print them.

python-can's virtual bus only connects buses inside the same Python process,
so this script starts the simulator in a background thread and listens on its
own, separate Bus object. The frames still go through the bus as real CAN messages.
"""

import argparse
import threading

import can

from sim.actuator import JOINT_BY_ID, JOINTS, decode
from sim.faults import demo_faults
from sim.simulator import CHANNEL, run_simulator


def format_frame(msg):
    joint = JOINT_BY_ID.get(msg.arbitration_id)
    name = joint.name if joint else "unknown"
    temperature_c, current_a, position_error_deg, voltage_v = decode(msg.data)
    return (
        f"0x{msg.arbitration_id:03X}  {name:<22}"
        f"temp {temperature_c:6.2f} C   "
        f"current {current_a:5.2f} A   "
        f"pos err {position_error_deg:+5.2f} deg   "
        f"voltage {voltage_v:5.2f} V"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=None,
                        help="stop after this many 100 ms cycles (default: run until Ctrl+C)")
    parser.add_argument("--faults", action="store_true",
                        help="inject the demo faults from sim/faults.py")
    args = parser.parse_args()

    # Open the listening bus first so we don't miss the first frames.
    with can.Bus(interface="virtual", channel=CHANNEL) as bus:
        stop_event = threading.Event()
        sim_thread = threading.Thread(
            target=run_simulator,
            args=(stop_event, args.cycles, demo_faults() if args.faults else ()),
            daemon=True,
        )
        sim_thread.start()

        expected = None if args.cycles is None else args.cycles * len(JOINTS)
        received = 0
        try:
            # A dropped-out joint sends fewer frames, so stop on the timeout instead.
            while expected is None or received < expected:
                msg = bus.recv(timeout=1.0)
                if msg is None:
                    print("no frames for 1 s, is the simulator running?")
                    break
                if msg.arbitration_id == JOINTS[0].can_id:
                    print(f"--- cycle {received // len(JOINTS) + 1} ---")
                print(format_frame(msg))
                received += 1
        except KeyboardInterrupt:
            print("\nstopped")
        finally:
            stop_event.set()
            sim_thread.join()

        print(f"received {received} frames")


if __name__ == "__main__":
    main()
