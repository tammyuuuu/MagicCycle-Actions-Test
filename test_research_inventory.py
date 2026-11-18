import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import research_inventory


class ReportStatusTests(unittest.TestCase):
    def test_statuses_are_backed_by_reports(self):
        projects = {project['id']: project for project in research_inventory.collect()}
        self.assertEqual(projects['be']['status'], '已结束')
        self.assertEqual(projects['crdo']['status'], '已结束')
        self.assertEqual(projects['zhu-long']['status'], '受阻')
        self.assertTrue(all(project['reports'] for project in projects.values()))

    def test_changed_source_requires_review(self):
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder) / 'changed.md'
            changed.write_text('# Updated source', encoding='utf8')
            import json
            root = Path(folder) / 'monitor'
            (root / 'reports').mkdir(parents=True)
            (root / 'reports/be-0.md').write_text('# Reviewed source', encoding='utf8')
            definition = json.loads((research_inventory.ROOT / 'projects.json').read_text(encoding='utf8'))
            definition = [p for p in definition if p['id'] == 'be']
            definition[0]['reports'] = [changed.as_posix()]
            (root / 'projects.json').write_text(json.dumps(definition), encoding='utf8')
            with patch.object(research_inventory, 'ROOT', root):
                project = research_inventory.collect()[0]
            self.assertEqual(project['status'], '待复核')
            self.assertTrue(project['focus'])


if __name__ == '__main__':
    unittest.main()
