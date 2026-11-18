import unittest
from datetime import datetime, timezone
from annual_replay import ANNUAL, KEYS, portfolios, read, segments
from annual_track import observe


class AnnualTests(unittest.TestCase):
    def test_locked_portfolios_and_attribution(self):
        study = read(ANNUAL/'study.json')
        batch = read(ANNUAL/'forward.json')
        self.assertEqual(portfolios(batch['inputs']), batch['picks'])
        self.assertLess(batch['registered_at'][:10], batch['entry'])
        self.assertEqual(batch['maturity'], batch['checkpoints'][-1])
        for row in study['rows']:
            if 'net' in row:
                self.assertAlmostEqual(sum(row['breakdown'].values()), row['delta'])
                self.assertAlmostEqual(row['net']['combined']-row['net']['trend'],row['delta'])
        for k in KEYS:
            self.assertEqual(segments(study['rows'],k),study['compounded'][k])
        self.assertEqual(len(segments([{'year':y,'net':{'test':10}} for y in [2020,2022]],'test')),2)

    def test_incomplete_observation_and_retry(self):
        batch=dict(entry='2026-11-19',checkpoints=['2027-11-18'],maturity='2027-11-18',
                   picks=dict(trend=['A'],combined=['B'],benchmark=['A','B']))
        ledger={'records':[]}
        now=datetime(2027,11,19,tzinfo=timezone.utc)
        def fetch(s,a,b):
            return {} if s=='A' else {batch['entry']:100,batch['maturity']:110}
        observe(batch,ledger,now,fetch)
        self.assertFalse(ledger['records'][0]['complete'])
        self.assertIsNone(ledger['records'][0]['delta'])
        full=lambda s,a,b:{batch['entry']:100,batch['maturity']:90}
        observe(batch,ledger,now,full)
        self.assertTrue(ledger['records'][1]['complete'])
        self.assertGreater(ledger['records'][1]['delta'],19)
        observe(batch,ledger,now,full)
        self.assertEqual(len(ledger['records']),2)
