"""Every 100 ms, encode and send actuator telemetry on a virtual CAN bus."""
import threading
import time
import can

from sim.actuator import JOINTS, encode
from sim.control import SimulatorControl

CHANNEL = 'test'
PERIOD_S = 0.100


def run_simulator(stop_event, cycles=None, faults=(), controller=None, channel=CHANNEL):
    controller = controller or SimulatorControl(faults)
    with can.Bus(interface='virtual', channel=channel) as bus:
        cycle = 0
        start = next_tick = time.monotonic()
        while not stop_event.is_set() and (cycles is None or cycle < cycles):
            for can_id, values in controller.sample(time.monotonic() - start):
                bus.send(can.Message(arbitration_id=can_id, data=encode(*values), is_extended_id=False))
            cycle += 1
            next_tick += PERIOD_S
            stop_event.wait(max(0.0, next_tick - time.monotonic()))


def main():
    print(f'Sending {len(JOINTS)} joints every {PERIOD_S * 1000:.0f} ms on virtual channel {CHANNEL!r}.')
    print('Run python -m sim.receiver to receive frames in the same process. Ctrl+C stops.')
    try:
        run_simulator(threading.Event())
    except KeyboardInterrupt:
        print('stopped')


if __name__ == '__main__':
    main()
