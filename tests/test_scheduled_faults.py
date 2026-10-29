import unittest

from sim.actuator import encode
from sim.control import SimulatorControl
from sim.faults import demo_faults


class ScheduledFaultTests(unittest.TestCase):
    def test_day_long_scenario_remains_encodable_and_faulted(self):
        controller = SimulatorControl(demo_faults())
        controller.sample(0)
        values = dict(controller.sample(86_400))
        self.assertGreater(values[0x112][1], 6)
        self.assertGreater(values[0x10D][0], 65)
        for reading in values.values():
            self.assertEqual(len(encode(*reading)), 8)
