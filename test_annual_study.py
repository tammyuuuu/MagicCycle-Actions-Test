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
            if row.get('breakdown') is not None:
                self.assertAlmostEqual(sum(row['breakdown'].values()), row['delta'])
            if all(row.get('net',{}).get(k) is not None for k in ('trend','combined')):
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

    def test_mature_2024_repeated_settlement(self):
        from copy import deepcopy
        from pathlib import Path
        from annual_track import settle_history
        study=read(ANNUAL/'study.json')
        row=next(r for r in study['rows'] if r['year']==2024)
        expected=deepcopy(row)
        pairs=read(Path('tests/fixtures/annual-2024-closes.json'))
        def fetch(sources,s,start,end):
            self.assertEqual((start,end),('2024-11-19','2025-11-19'))
            return {start:pairs[s][0],row['maturity']:pairs[s][1]}
        def unexpected(*args):
            self.fail('unexpected price fetch')
        ledger={}
        settle_history(study,ledger,pairs,datetime(2025,11,18,20,59,tzinfo=timezone.utc),unexpected,2024)
        self.assertFalse(ledger['settlements']['2024']['records'])
        settle_history(study,ledger,pairs,datetime(2025,11,18,21,30,tzinfo=timezone.utc),fetch,2024)
        for k in KEYS:
            self.assertAlmostEqual(row['net'][k],expected['net'][k])
        self.assertAlmostEqual(row['delta'],expected['delta'])
        first=deepcopy((study,ledger))
        settle_history(study,ledger,pairs,datetime(2025,11,19,tzinfo=timezone.utc),unexpected,2024)
        self.assertEqual((study,ledger),first)

    def test_annual_directions_and_render(self):
        from annual_track import assessment
        from annual_view import maturity_review
        batch=read(ANNUAL/'forward.json')
        d=batch['maturity']
        winners=set(batch['picks']['combined'])-set(batch['picks']['trend'])
        def prices(s,start,end):
            return {start:100,d:130 if s in winners else 90}
        records=observe(dict(batch,checkpoints=[d]),{'records':[]},datetime(2027,11,19,tzinfo=timezone.utc),prices)['records']
        last=records[-1]
        self.assertIn('继续跟踪',last['assessment'])
        self.assertIn('调整',assessment(dict(last,delta=-1)))
        self.assertIn('持平',assessment(dict(last,delta=0)))
        self.assertIn('缺价',assessment(dict(last,complete=False)))
        html=maturity_review(batch,records)
        for phrase in ('实际扣费收益','相对全池','换入','剔除','缺价股票',next(iter(winners))):
            self.assertIn(phrase,html)
