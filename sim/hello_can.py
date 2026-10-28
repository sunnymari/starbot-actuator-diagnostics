"""Step 1: send one CAN message and receive it.

Two buses on the same virtual channel act like two devices plugged into the
same CAN wire. Whatever one sends, the other receives.
"""

import can

CHANNEL = "test"


def main():
    with can.Bus(interface="virtual", channel=CHANNEL) as sender, \
         can.Bus(interface="virtual", channel=CHANNEL) as receiver:

        msg = can.Message(
            arbitration_id=0x123,
            data=[0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02, 0x03, 0x04],
            is_extended_id=False,  # standard 11-bit ID, like most robot buses
        )
        sender.send(msg)
        print(f"sent:     {msg}")

        received = receiver.recv(timeout=1.0)
        if received is None:
            print("nothing received (timed out)")
        else:
            print(f"received: {received}")


if __name__ == "__main__":
    main()
