"""Restore a published observation before replacing the Pages deployment."""
import hashlib
import json
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = 'https://tammyuuuu.github.io/MagicCycle-Actions-Test/research/runtime/'


def restore():
    session = requests.Session()
    retries = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    status = session.get(BASE + 'status.json', timeout=45)
    status.raise_for_status()
    published = status.json()
    if published.get('status') in ('waiting', 'error') and not published.get('observation'):
        print('Published monitor has no locked observation yet')
        return
    response = session.get(BASE + 'first_observation.json', timeout=45)
    response.raise_for_status()
    observation = response.json()
    snapshot = session.get(BASE + 'first_release.html', timeout=45)
    snapshot.raise_for_status()
    if hashlib.sha256(snapshot.content).hexdigest() != observation['sha256']:
        raise ValueError('Published snapshot checksum mismatch; refusing to overwrite')
    if observation.get('period_end') != 'December 31, 2026':
        raise ValueError('Unexpected published period')
    runtime = Path('research_monitor/runtime')
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / 'first_observation.json').write_text(json.dumps(observation, indent=2), encoding='utf8')
    (runtime / 'first_release.html').write_bytes(snapshot.content)
    print('Restored immutable first observation')


if __name__ == '__main__':
    restore()
