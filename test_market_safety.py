import unittest
from datetime import datetime
from unittest.mock import patch
import data_fetcher as d

class MarketSafety(unittest.TestCase):
    def test_holiday_and_close(self):
        self.assertEqual(str(d._expected_latest_trade_date(datetime(2026,10,8,14))), '2026-09-30')
        self.assertEqual(str(d._expected_latest_trade_date(datetime(2026,10,8,16))), '2026-10-08')
    def test_calendar_expiry(self):
        with self.assertRaises(ValueError): d._expected_latest_trade_date(datetime(2027,1,4,16))
    def test_failed_sources_do_not_use_sina(self):
        with patch.object(d, '_load_or_fetch', side_effect=ConnectionError('offline')), patch.object(d, '_stale_cache', return_value=(None,None)), patch.object(d, '_src_cooling', return_value=False), patch.object(d.ak, 'fund_etf_hist_sina', side_effect=AssertionError('unadjusted source called')):
            with self.assertRaises(ConnectionError): d.fetch_etf_daily('510500')

if __name__ == '__main__': unittest.main()
