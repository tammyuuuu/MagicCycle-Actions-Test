"""Archive official releases, lock the first comparable observation, and score it."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path('research_monitor')
RUNTIME = ROOT / 'runtime'
BASE = 'https://www.microsoft.com/en-us/investor/'
PREDICTIONS = {'research': 49, 'last_quarter': 48, 'guidance_midpoint': 49.5}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ReleaseParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, data):
        self.text.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def extract(document, quarter):
    parser = ReleaseParser()
    parser.feed(document)
    text = ' '.join(' '.join(parser.text).split())
    end = {'q1': 'September 30, 2026', 'q2': 'December 31, 2026'}[quarter]
    if not re.search(r'quarter ended\s+' + re.escape(end), text, re.I):
        raise ValueError('Release period does not match ' + end)
    if 'Percentage Change Y/Y Constant Currency' not in text:
        raise ValueError('Constant currency header missing')
    matches = [row for row in parser.rows if row and row[0] == 'Azure revenue']
    values = []
    for row in matches:
        cells = [cell for cell in row[1:] if cell]
        if len(cells) == 3 and re.fullmatch(r'-?\d+(?:\.\d+)?%', cells[-1]):
            values.append(float(cells[-1][:-1]))
    if len(values) != 1:
        raise ValueError('Azure constant currency row ambiguous or changed')
    date = re.search(r'REDMOND.*?—\s*([A-Za-z]+ \d{1,2}, 202[67])\s*—', text)
    if not date:
        raise ValueError('Publication date missing')
    return {'actual': values[0], 'period_end': end, 'publication_date': date.group(1)}


def fetch(url):
    response = requests.get(url, timeout=45)
    return response


def run(validate=False):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    checked = timestamp()
    report = {'checked_at': checked, 'status': 'waiting', 'target': 'FY27 Q2'}
    try:
        if validate:
            url = BASE + 'earnings/fy-2027-q1/press-release-webcast'
            response = fetch(url)
            response.raise_for_status()
            observation = extract(response.text, 'q1')
            assert observation['actual'] == 48, observation
            (ROOT / 'q1_release.html').write_text(response.text, encoding='utf8')
            (ROOT / 'validation.json').write_text(json.dumps({**observation, 'url': url, 'validated_at': checked}, indent=2), encoding='utf8')
        locked = RUNTIME / 'first_observation.json'
        if locked.exists():
            observation = json.loads(locked.read_text(encoding='utf8'))
            report.update(status='completed', observation=observation)
        else:
            url = BASE + 'earnings/fy-2027-q2/press-release-webcast'
            home = fetch(BASE + 'default')
            home.raise_for_status()
            if 'fy-2027-q2/press-release-webcast' not in home.text.lower():
                report['detail'] = 'IR homepage has not linked the Q2 release'
                (RUNTIME / 'status.json').write_text(json.dumps(report, indent=2), encoding='utf8')
                print(json.dumps(report))
                return True
            response = fetch(url)
            if response.status_code in (404, 410):
                report['detail'] = 'Official Q2 release not available'
            else:
                response.raise_for_status()
                # A placeholder page is not a financial disclosure.
                if not re.search(r'quarter ended\s+(?:<[^>]+>|\s)*December', response.text, re.I):
                    report['detail'] = 'Q2 endpoint has no dated release yet'
                else:
                    observation = extract(response.text, 'q2')
                    observation.update(first_seen_at=checked, url=url,
                                       sha256=hashlib.sha256(response.content).hexdigest())
                    observation['errors_pp'] = {name: abs(observation['actual'] - value) for name, value in PREDICTIONS.items()}
                    best = min(observation['errors_pp'].values())
                    observation['winners'] = [name for name, error in observation['errors_pp'].items() if error == best]
                    (RUNTIME / 'first_release.html').write_bytes(response.content)
                    locked.write_text(json.dumps(observation, indent=2), encoding='utf8')
                    report.update(status='completed', observation=observation)
    except Exception as exc:
        report.update(status='error', detail=str(exc))
    (RUNTIME / 'status.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))
    return report['status'] != 'error'


if __name__ == '__main__':
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--validate-q1', action='store_true')
    raise SystemExit(0 if run(arguments.parse_args().validate_q1) else 1)
