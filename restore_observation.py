"""Recover the immutable first observation from the previous Pages deployment."""
import hashlib
import json
from pathlib import Path
import requests

base = 'https://tammyuuuu.github.io/MagicCycle-Actions-Test/research/runtime/'
response = requests.get(base + 'first_observation.json', timeout=45)
if response.status_code == 404:
    print('No published first observation yet')
else:
    response.raise_for_status()
    observation = response.json()
    snapshot = requests.get(base + 'first_release.html', timeout=45)
    snapshot.raise_for_status()
    if hashlib.sha256(snapshot.content).hexdigest() != observation['sha256']:
        raise SystemExit('Published snapshot checksum mismatch; refusing to overwrite')
    if observation.get('period_end') != 'December 31, 2026':
        raise SystemExit('Unexpected published period')
    runtime = Path('research_monitor/runtime')
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / 'first_observation.json').write_text(json.dumps(observation, indent=2), encoding='utf8')
    (runtime / 'first_release.html').write_bytes(snapshot.content)
    print('Restored immutable first observation')
