"""Append quarterly observations for a locked November portfolio."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
from annual_replay import ANNUAL, FEE, KEYS, attribution, evaluate_pool
from experiment_tracker import PAGES, fetch_prices, read, save

FILE = ANNUAL / 'ledger.json'


def published(seed):
    url = PAGES.replace('/experiments/', '/expanded/annual/ledger.json')
    response = requests.get(url, timeout=30, headers={'Cache-Control':'no-cache'})
    if response.status_code == 404 and datetime.now(timezone.utc).date() <= date(2026,11,19):
        return seed
    response.raise_for_status()
    previous = response.json()
    if previous['batch'] != seed['batch'] or previous['records'][:len(seed['records'])] != seed['records']:
        raise ValueError('年度批次登记或观察历史不一致')
    return previous


def observe(batch, ledger, now, fetch=fetch_prices):
    done = {r['date'] for r in ledger['records'] if r['complete']}
    for target in batch['checkpoints']:
        if target in done or now.date().isoformat() <= target:
            continue
        records = [r for r in ledger['records'] if r['date']==target]
        values = dict(records[-1]['prices']) if records else {}
        missing = [s for s in batch['picks']['benchmark'] if s not in values]
        def pair(s):
            try:
                bars = fetch(s,batch['entry'],(date.fromisoformat(target)+timedelta(days=1)).isoformat())
                return [bars[batch['entry']],bars[target]]
            except (requests.RequestException, KeyError, ValueError, TypeError, IndexError):
                return None
        with ThreadPoolExecutor(max_workers=5) as pool:
            for s, prices in zip(missing,pool.map(pair,missing)):
                if prices: values[s]=prices
        if records and len(values)==len(records[-1]['prices']):
            continue
        returns={s: (FEE*values[s][1]/values[s][0]-1)*100 if s in values else None for s in batch['picks']['benchmark']}
        result=evaluate_pool(batch['picks'],returns)
        entry=dict(date=target,observed_at=now.isoformat(),prices=values,
                   complete=len(values)==len(returns),performance=result['performance'],
                   contribution=result['contribution'],delta=result['delta'],breakdown=attribution(batch['picks'],returns))
        if target==batch['maturity']:
            entry['assessment']=('关键持仓缺价，继续核对' if result['delta'] is None else
                f"联合组相对趋势组 {result['delta']:+.2f} 个百分点。此批为一笔独立年度观察，继续跟踪。")
            if entry['breakdown']:
                legs=entry['breakdown']
                entry['assessment'] += (f" 剔除下跌股贡献 {legs['avoided_loss']:+.2f}，错过上涨股贡献 "
                                        f"{legs['missed_gain']:+.2f}，两项合计 "
                                        f"{legs['avoided_loss']+legs['missed_gain']:+.2f} 个百分点。")
        ledger['records'].append(entry)
    return ledger


if __name__ == '__main__':
    batch=read(ANNUAL/'forward.json')
    ledger=published(read(FILE))
    save(FILE,observe(batch,ledger,datetime.now(timezone.utc)))
