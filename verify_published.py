import hashlib, json, time, urllib.request
from pathlib import Path
base='https://tammyuuuu.github.io/MagicCycle-Actions-Test/'
expected=Path('docs/research.json').read_bytes(); version=hashlib.sha256(expected).hexdigest()
for attempt in range(12):
    try:
        suffix='?run='+str(time.time_ns())
        with urllib.request.urlopen(base+'research.json'+suffix,timeout=15) as r: actual=r.read()
        with urllib.request.urlopen(base+suffix,timeout=15) as r: page=r.read().decode('utf8')
        annual_ok = True
        for name in ('study.json','ledger.json'):
            path='research/expanded/annual/'+name
            with urllib.request.urlopen(base+path+suffix,timeout=15) as response:
                annual_ok &= json.load(response)==json.loads((Path('docs')/path).read_bytes())
        if annual_ok and json.loads(actual)==json.loads(expected) and version in page:
            print('Research deployment verified'); break
    except Exception as exc: print(str(exc))
    time.sleep(10)
else: raise SystemExit('Published research data mismatch')
