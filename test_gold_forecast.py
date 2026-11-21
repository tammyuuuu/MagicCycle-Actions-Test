from datetime import date, datetime
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import gold_forecast as gold


class GoldTest(unittest.TestCase):
    def test_retries_preserve_forecasts_and_settle_once(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "gold.json"
            seed = json.loads(gold.LEDGER.read_text(encoding="utf8"))[0]
            for forecast in seed["forecasts"]:
                for key in ("actual", "actual_source", "observed"):
                    forecast.pop(key, None)
            ledger.write_text(json.dumps([seed]), encoding="utf8")
            now = datetime(2026, 11, 27, 18, tzinfo=gold.CN)
            bar = dict(close=770, low=760, high=780, source="fixture")
            with patch.object(gold, "LEDGER", ledger), patch.object(gold, "fetch", return_value=bar) as fetch:
                gold.update(now)
                first = ledger.read_bytes()
                gold.update(now)
                self.assertEqual(first, ledger.read_bytes())
                fetch.assert_called_once_with("2026-11-27")
                records = json.loads(first)
                self.assertEqual(len(records), 2)
                self.assertEqual(records[0]["forecasts"][0]["actual"], 770)
                self.assertEqual(records[0]["forecasts"][1:], seed["forecasts"][1:])
                self.assertEqual(records[0]["forecasts"][2]["target"], "2027-02-26")
                self.assertIn("原登记待验证日期 2026-12-04", gold.gold_card())

    def test_seed_reproduces(self):
        seed = json.loads(gold.LEDGER.read_text(encoding="utf8"))[0]
        generated = gold.register(date.fromisoformat(seed["origin"]), seed["bar"],
                                  datetime.fromisoformat(seed["registered"]))
        for observed, expected in zip(seed["forecasts"], generated["forecasts"], strict=True):
            self.assertEqual({k: observed[k] for k in expected}, expected)
