"""Exercise the real simulator -> virtual CAN -> decoder -> DTC path."""
import time
import unittest

from diagnostics.live import LiveFeed


class CANIntegrationTests(unittest.TestCase):
    def wait_for(self, feed, predicate, timeout=3):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            snapshot=feed.snapshot('left_knee')
            if predicate(snapshot): return snapshot
            time.sleep(.02)
        self.fail('Live CAN state did not reach expected condition')

    def test_live_demo_confirm_clear_timeout_reset_heal(self):
        feed=LiveFeed().start()
        try:
            self.wait_for(feed,lambda s:all(j['status']=='OK' for j in s['joints']))
            feed.control('inject','left_knee','overcurrent')
            pending=self.wait_for(feed,lambda s:any(d['code']=='C10002' and d['state']=='PENDING' for d in s['dtcs']))
            knee=next(j for j in pending['joints'] if j['name']=='left_knee')
            self.assertEqual(knee['status'],'WARNING')
            confirmed=self.wait_for(feed,lambda s:any(d['code']=='C10002' and d['severity']=='CRITICAL' for d in s['dtcs']))
            self.assertGreater(confirmed['dtcs'][0]['freeze_frame']['current_a'],6)
            feed.control('clear','left_knee')
            self.wait_for(feed,lambda s:any(d['code']=='C10002' and d['state']=='PENDING' for d in s['dtcs']))
            self.wait_for(feed,lambda s:any(d['code']=='C10002' and d['severity']=='CRITICAL' for d in s['dtcs']))
            feed.control('inject','left_wrist_roll','heartbeat')
            dropped=self.wait_for(feed,lambda s:any(d['code']=='C10005' and d['state']=='CONFIRMED' for d in s['dtcs']))
            wrist=next(j for j in dropped['joints'] if j['name']=='left_wrist_roll')
            self.assertEqual(wrist['status'],'NO DATA')
            self.assertEqual(len(dropped['dtcs']),2)
            feed.control('reset')
            healthy=self.wait_for(feed,lambda s:len(s['dtcs'])==2 and all(d['state']=='HEALED' for d in s['dtcs']))
            self.assertTrue(all(j['status']=='OK' for j in healthy['joints']))
            self.assertEqual(healthy['faults'],[])
        finally:
            feed.stop()


if __name__=='__main__': unittest.main()
