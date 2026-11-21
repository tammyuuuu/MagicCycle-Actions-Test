import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

import gold21 as g


class Gold21Test(unittest.TestCase):
    def setUp(self):
        self.state={"batches":[],"settlements":{},"gaps":{}}
        self.now=datetime(2026,11,27,16,30,tzinfo=g.CN)
        self.data={"closes":{str(g.shift(self.now.date(),-i)):800+i*.2 for i in range(64)},
                   "macro":{s:{"values":{str(self.now.date()-timedelta(days=i)):v+i*.001 for i in range(21)}}
                            for s,v in [("DEXCHUS",7),("DFII10",2)]}}
        self.load=Mock(return_value=self.data)

    def run_at(self,now,quote=None):
        g.update(self.state,now,lambda:now,load=self.load,quote=quote or Mock())

    def test_lock_and_settle(self):
        self.run_at(self.now)
        frozen=copy.deepcopy(self.state["batches"])
        self.run_at(self.now)
        self.assertEqual(frozen,self.state["batches"])
        self.load.assert_called_once()
        row=frozen[0]
        self.assertEqual(row["target"],"2026-12-28")
        self.assertEqual(row["forecasts"]["持平"]["point"],800)
        quote=Mock(return_value=dict(close=810,source="test"))
        maturity=datetime(2026,12,28,16,tzinfo=g.CN)
        self.run_at(maturity,quote)
        self.run_at(maturity,quote)
        quote.assert_called_once_with(row["target"])
        self.assertEqual(frozen,self.state["batches"])
        stats=g.scores(frozen,self.state["settlements"])
        self.assertEqual(stats["持平"]["mae"],10)
        self.assertEqual(stats["持平"]["gain"],0)
        self.assertEqual(stats["持平"]["direction"],0)

    def test_publication_gap_and_retry(self):
        self.load.side_effect=ValueError("缺少版本")
        self.run_at(self.now)
        self.assertFalse(self.state["batches"])
        self.assertIn("2026-11-27",self.state["gaps"])
        self.load.side_effect=None
        self.run_at(self.now)
        self.assertFalse(self.state["gaps"])
        self.assertEqual(len(self.state["batches"]),1)

    def test_no_backdating(self):
        self.run_at(self.now.replace(hour=12))
        self.run_at(self.now.replace(hour=20))
        self.run_at(self.now+timedelta(days=1))
        self.load.assert_not_called()
        self.assertFalse(self.state["batches"])

    def test_model_freeze(self):
        import hashlib
        digest=hashlib.sha256(json.dumps(g.read(g.MODEL),sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest,g.MODEL_SHA256)
