import copy
import unittest

import can
from diagnostics.config import CONFIG, has_no_data
from diagnostics.detector import Detector
from diagnostics.live import LiveFeed
from sim.actuator import JOINT_BY_NAME, encode
from sim.control import SimulatorControl


def message(joint='left_knee', temp=35, current=3, error=0, voltage=48):
    return can.Message(arbitration_id=JOINT_BY_NAME[joint].can_id,
                       data=encode(temp, current, error, voltage), is_extended_id=False)


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = Detector(started_at=0)
        self.now = 0

    def sample(self, count=1, **values):
        for _ in range(count):
            self.now += .1
            self.detector.update(message(**values), self.now)

    def dtc(self, code='C10002', joint='left_knee'):
        return self.detector.dtcs[(joint, code)]

    def test_pending_confirmed_and_twenty_good_samples_heal(self):
        self.sample(current=8.5)
        self.assertEqual(self.dtc().state, 'PENDING')
        self.assertEqual(self.dtc().severity, 'WARNING')
        self.sample(3, current=8.5)
        self.assertEqual(self.dtc().state, 'PENDING')
        self.sample(current=8.5)
        record = self.dtc()
        self.assertEqual((record.state, record.severity), ('CONFIRMED', 'CRITICAL'))
        self.assertEqual(record.threshold, 6)
        self.assertEqual(record.value_at_trigger, 8.5)
        self.assertAlmostEqual(record.confirmed_at_s, .5)
        freeze = record.freeze_frame.copy()
        self.sample(19)
        self.assertEqual(record.state, 'CONFIRMED')
        self.assertEqual(record.freeze_frame, freeze)
        self.sample()
        self.assertEqual(record.state, 'HEALED')
        self.assertEqual(record.occurrences, 5)
        self.assertIn('freeze_frame', self.detector.records()[0])

    def test_bad_samples_must_be_consecutive(self):
        for _ in range(6):
            self.sample(4, current=8)
            self.sample()
        self.assertEqual(self.dtc().state, 'PENDING')
        self.assertEqual(self.dtc().bad_samples, 0)
        self.sample(5, current=8)
        self.assertEqual(self.dtc().state, 'CONFIRMED')

    def test_critical_escalation_is_debounced_and_latched(self):
        self.sample(5, current=5.5)
        self.assertEqual((self.dtc().state,self.dtc().severity), ('CONFIRMED','WARNING'))
        self.sample(4, current=8)
        self.assertEqual(self.dtc().severity, 'WARNING')
        self.sample(current=8)
        self.assertEqual(self.dtc().severity, 'CRITICAL')
        self.sample(10, current=5.5)
        self.assertEqual(self.dtc().severity, 'CRITICAL')
        self.assertEqual(self.dtc().value_at_trigger, 8)

    def test_grouping_healed_recurrence_and_sort(self):
        self.sample(20, current=8)
        self.sample(20)
        self.sample(5, current=8)
        self.sample(5, joint='neck_yaw', error=-2)
        self.assertEqual(len(self.detector.records()), 2)
        knee, neck = self.detector.records()
        self.assertEqual(knee['code'], 'C10002')
        self.assertEqual(knee['occurrences'], 25)
        self.assertEqual(neck['code'], 'C10003')
        self.sample(20)
        records = self.detector.records()
        self.assertEqual(records[-1]['state'], 'HEALED')
        self.assertEqual(records[0]['joint'], 'neck_yaw')

    def test_each_sensor_rule_and_strict_boundaries(self):
        self.sample(5, temp=50, current=5, error=-1.5, voltage=44)
        self.assertEqual(self.detector.records(), [])
        self.sample(5, temp=70, current=8, error=-4, voltage=38)
        self.assertEqual({d['code'] for d in self.detector.records()}, {'C10001','C10002','C10003','C10004'})
        self.assertTrue(all(d['severity']=='CRITICAL' for d in self.detector.records()))
        self.assertEqual(self.dtc('C10003').value_at_trigger, 4)
        self.assertEqual(self.dtc('C10004').comparison, '<')

    def test_clear_present_fault_re_pends_and_re_confirms(self):
        self.sample(5, current=8)
        self.detector.clear('left_knee')
        self.assertEqual(self.detector.records(), [])
        self.sample(current=8)
        self.assertEqual(self.dtc().state, 'PENDING')
        self.sample(4, current=8)
        self.assertEqual(self.dtc().state, 'CONFIRMED')
        self.assertEqual(self.dtc().occurrences, 5)

    def test_timeout_and_recovery(self):
        self.sample()
        self.detector.check_timeouts(.6)  # exactly 500 ms: not over threshold
        self.assertNotIn(('left_knee','C10005'), self.detector.dtcs)
        for t in [.61,.71,.81,.91,1.01]:
            self.detector.check_timeouts(t)
        timeout = self.dtc('C10005')
        self.assertEqual((timeout.state, timeout.rule), ('CONFIRMED','TIMEOUT'))
        self.assertEqual(timeout.freeze_frame['current_a'], 3)
        self.now = 1.01
        self.sample(19)
        self.assertEqual(timeout.state, 'CONFIRMED')
        self.sample()
        self.assertEqual(timeout.state, 'HEALED')

    def test_missing_first_frame_and_malformed_frame(self):
        self.detector.check_timeouts(.51)
        self.assertEqual(len(self.detector.records()), 28)
        broken = can.Message(arbitration_id=0x112, data=[0,1],is_extended_id=False)
        self.detector.update(broken, .6)
        self.assertNotIn('left_knee',self.detector.last_seen)
        self.assertEqual(self.detector.invalid_frames, 1)

    def test_custom_config_changes_debounce_and_limits(self):
        config=copy.deepcopy(CONFIG)
        config['confirm_samples']=2
        config['rules'][1]['critical']=10
        d=Detector(config,0)
        for t in [.1,.2]: d.update(message(current=8),t)
        record=d.records()[0]
        self.assertEqual((record['state'],record['severity'],record['threshold']), ('CONFIRMED','WARNING',5))


class FeedTests(unittest.TestCase):
    def test_snapshot_ages_no_data_and_grouping(self):
        feed=LiveFeed()
        feed.started_at=feed.detector.started_at=0
        for t in [.1,.2,.3,.4,.5]: feed.detector.update(message(current=8),t)
        snapshot=feed.snapshot('left_knee',now=.7)
        knee=next(j for j in snapshot['joints'] if j['name']=='left_knee')
        self.assertEqual(knee['status'],'CRITICAL')
        self.assertAlmostEqual(knee['age_s'],.2)
        self.assertEqual(knee['last_update_ms'],500)
        self.assertEqual(len(snapshot['log']),1)
        self.assertEqual(len(snapshot['history']['left_knee']),5)
        snapshot=feed.snapshot(now=1.1)
        knee=next(j for j in snapshot['joints'] if j['name']=='left_knee')
        self.assertEqual(knee['status'],'NO DATA')
        self.assertAlmostEqual(knee['age_s'],.6)
        self.assertTrue(all(j['status']=='NO DATA' for j in snapshot['joints']))

    def test_stale_boundaries(self):
        self.assertTrue(has_no_data(None,0,0,500))
        self.assertFalse(has_no_data(0,.5,0,500))
        self.assertTrue(has_no_data(0,.501,0,500))

    def test_simulator_controls_change_encoded_values_and_reset(self):
        c=SimulatorControl()
        def knee(): return dict(c.sample(0))[0x112]
        self.assertLess(knee()[1],5)
        c.inject('left_knee','overcurrent')
        self.assertGreater(knee()[1],6)
        c.inject('left_knee','heartbeat')
        self.assertNotIn(0x112, dict(c.sample(0)))
        c.reset()
        self.assertLess(knee()[1],5)
        self.assertEqual(c.describe(),[])

    def test_simulators_do_not_share_mutable_joints(self):
        one,two=SimulatorControl(),SimulatorControl()
        one.inject('left_knee','overcurrent')
        self.assertGreater(dict(one.sample(0))[0x112][1],6)
        self.assertLess(dict(two.sample(0))[0x112][1],5)

    def test_invalid_control_has_no_effect(self):
        feed=LiveFeed()
        for action,name,fault in [('inject','missing','overcurrent'),('inject','left_knee','unknown'),('oops','left_knee',None)]:
            with self.assertRaises(ValueError): feed.control(action,name,fault)
        self.assertEqual(feed.controller.describe(),[])


if __name__=='__main__': unittest.main()
