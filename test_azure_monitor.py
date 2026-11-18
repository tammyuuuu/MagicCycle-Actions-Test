import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import azure_monitor as monitor


class AzureMonitorTests(unittest.TestCase):
    def test_previous_official_release(self):
        parsed = monitor.extract(Path('research_monitor/q1_release.html').read_text(encoding='utf8'), 'q1')
        self.assertEqual(parsed['actual'], 48)
        with self.assertRaises(ValueError):
            monitor.extract(Path('research_monitor/q1_release.html').read_text(encoding='utf8'), 'q2')

    def test_lock_and_score_then_preserve_first_observation(self):
        # Synthetic future disclosure exercises the exact parser and persistence path.
        release = Path('research_monitor/q1_release.html').read_text(encoding='utf8').replace('September 30, 2026', 'December 31, 2026').replace('October 28, 2026', 'January 28, 2027')
        home = Mock(text='fy-2027-q2/press-release-webcast')
        response = Mock(text=release, content=release.encode(), status_code=200)
        with tempfile.TemporaryDirectory() as folder, patch.object(monitor, 'RUNTIME', Path(folder)), patch.object(monitor, 'fetch', side_effect=[home, response]):
            self.assertTrue(monitor.run())
            first = (Path(folder) / 'first_observation.json').read_bytes()
            result = json.loads(first)
            self.assertEqual(result['errors_pp'], {'research': 1, 'last_quarter': 0, 'guidance_midpoint': 1.5})
            self.assertEqual(result['winners'], ['last_quarter'])
            with patch.object(monitor, 'fetch', side_effect=AssertionError('Must use locked observation')):
                self.assertTrue(monitor.run())
            self.assertEqual(first, (Path(folder) / 'first_observation.json').read_bytes())

    def test_network_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(monitor, 'RUNTIME', Path(folder)), patch.object(monitor, 'fetch', side_effect=RuntimeError('403')):
            self.assertFalse(monitor.run())
            self.assertEqual(json.loads((Path(folder) / 'status.json').read_text())['status'], 'error')


if __name__ == '__main__':
    unittest.main()
