import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

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
        self.assertEqual([c.args[0] for c in quote.call_args_list],["2026-12-04",row["target"]])
        results=self.state["batches"][0]["records"]
        self.assertEqual(len(results),9)
        self.assertEqual([r["h"] for r in results if "verification" not in r],[63]*4)
        for old,new in zip(frozen[0]["records"],results):
            self.assertEqual(old,{k:v for k,v in new.items() if k!="verification"})
        for r in results:
            if r["h"]==21:
                self.assertEqual(r["verification"]["actual"],810)
                self.assertEqual(r["verification"]["direction_correct"],(r["point"]>800))
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

    def test_legacy_21_only_and_immutable_history(self):
        self.run_at(self.now)
        batch=self.state["batches"][0]
        before=copy.deepcopy(self.state)
        batch["records"][0]["point"]+=1
        with self.assertRaises(ValueError):
            g.persist(before,self.state)
        with self.assertRaises(ValueError):
            g.persist(before,{"batches":[],"settlements":{},"gaps":{}})
        batch.pop("records")
        self.run_at(datetime(2026,12,28,16,tzinfo=g.CN),Mock(return_value={"close":807,"source":"test"}))
        projected=g.records(batch,self.state["settlements"])
        self.assertEqual([r["h"] for r in projected],[21]*3)
        self.assertTrue(all(r["verification"]["observed"].startswith("2026-12-28") for r in projected))

    def test_page_updates_original_rows(self):
        self.run_at(self.now)
        maturity=datetime(2026,12,4,16,tzinfo=g.CN)
        g.settle(self.state,maturity,lambda:maturity,Mock(return_value={"close":810,"source":"test"}))
        original=g.read
        with patch.object(g,"read",side_effect=lambda p:self.state if p==g.LEDGER else original(p)):
            page=g.card(maturity.date())
        self.assertIn("2026-12-04 16:00:00",page)
        self.assertIn("810.00",page)
        self.assertIn("预测持平，实际上涨",page)
        self.assertIn("待验证",page)
