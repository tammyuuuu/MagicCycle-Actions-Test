"""Settle locked portfolios from matched adjusted closes and append new evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

import requests

from annual_replay import ANNUAL, FEE, KEYS, attribution, evaluate_pool, segments
from experiment_tracker import PAGES, fetch_prices, read, save

FILE = ANNUAL / 'ledger.json'


def published(seed):
    url = PAGES.replace('/experiments/', '/expanded/annual/ledger.json')
    response = requests.get(url, params={'run':datetime.now(timezone.utc).timestamp()},
                            timeout=30, headers={'Cache-Control':'no-cache'})
    response.raise_for_status()
    previous = response.json()
    if previous['batch'] != seed['batch'] or previous['records'][:len(seed['records'])] != seed['records']:
        raise ValueError('年度批次登记或观察历史不一致')
    return previous


def historical_bars(sources, symbol, start, end):
    """Exclusive end, matching the Yahoo adapter. f53 is the Eastmoney close."""
    secid = sources[symbol]
    if secid == 'Yahoo':
        return fetch_prices(symbol,start,end)
    url = 'https://63.push2his.eastmoney.com/api/qt/stock/kline/get'
    params = dict(secid=secid,klt=101,fqt=1,fields1='f1,f2,f3,f4,f5,f6',
                  fields2='f51,f52,f53',beg=start.replace('-',''),end=end.replace('-',''))
    response = requests.get(url,params=params,timeout=15)
    response.raise_for_status()
    data = response.json()['data']
    if not data or data.get('code') != symbol or str(data.get('market')) != secid.split('.')[0]:
        raise ValueError('行情与锁定证券不匹配')
    bars = {}
    for line in data['klines']:
        day, _, close = line.split(',')[:3]
        bars[day] = float(close)
    return bars


def assessment(record):
    if not record['complete']:
        return '待补证。缺价持仓保留原权重，完整年度评定待行情补齐。'
    delta = record['delta']
    legs = record['breakdown']
    offset = legs['avoided_loss'] + legs['missed_gain']
    if abs(delta) < 1e-8:
        decision = '本批联合与趋势持平，新增财务指标未体现增益。'
    elif delta < 0:
        decision = '本批联合落后趋势，复核换股和评分权重后再决定是否调整。'
    elif offset <= 0:
        decision = '本批联合领先，但避跌未超过踏空成本；复核换入股的贡献。'
    else:
        decision = '本批联合领先，且避跌超过踏空成本，支持按原规则继续跟踪。'
    return decision + '季度观察均属同一笔年度持仓。'


def observe(batch, ledger, now, fetch=fetch_prices):
    done = {r['date'] for r in ledger['records'] if r['complete']}
    for target in batch['checkpoints']:
        # All dates in these locked schedules are regular NYSE sessions.
        close = datetime.combine(date.fromisoformat(target), time(16),ZoneInfo('America/New_York'))
        if target in done or now <= close:
            continue
        records = [r for r in ledger['records'] if r['date']==target]
        values = dict(records[-1]['prices']) if records else {}
        missing = [s for s in batch['picks']['benchmark'] if s not in values]
        def pair(s):
            try:
                bars = fetch(s,batch['entry'],(date.fromisoformat(target)+timedelta(days=1)).isoformat())
                prices = [bars[batch['entry']], bars[target]]
                if all(isfinite(v) and v>0 for v in prices):
                    return prices
            except (requests.RequestException, KeyError, ValueError, TypeError, IndexError):
                pass
            return None
        with ThreadPoolExecutor(max_workers=5) as pool:
            for s, prices in zip(missing,pool.map(pair,missing)):
                if prices: values[s]=prices
        if records and len(values)==len(records[-1]['prices']):
            continue
        returns={s: (FEE*values[s][1]/values[s][0]-1)*100 if s in values else None for s in batch['picks']['benchmark']}
        result=evaluate_pool(batch['picks'],returns)
        performance=result['performance']
        benchmark=performance['benchmark']['net']
        relative={k: v['net']-benchmark if benchmark is not None and v['net'] is not None else None
                  for k,v in performance.items()}
        entry=dict(date=target,observed_at=now.isoformat(),prices=values,returns=returns,
                   complete=len(values)==len(returns),performance=performance,relative=relative,
                   contribution=result['contribution'],delta=result['delta'],breakdown=attribution(batch['picks'],returns))
        if target==batch['maturity']:
            entry['assessment']=assessment(entry)
        ledger['records'].append(entry)
    return ledger


def settle_history(study, ledger, sources, now, fetch=historical_bars, year=2025):
    row=next(r for r in study['rows'] if r['year']==year)
    if set(sources)!=set(row['picks']['benchmark']):
        raise ValueError('行情清单与原始基准不一致')
    history=ledger.setdefault('settlements',{}).setdefault(str(year),{'records':[]})
    batch=dict(row,checkpoints=[row['maturity']])
    observe(batch,history,now,lambda s,a,b:fetch(sources,s,a,b))
    if not history['records']:
        return
    record=history['records'][-1]
    row.update(status='已到期结算' if record['complete'] else '已到期，部分价格待核验',
               net={k:record['performance'][k]['net'] for k in KEYS},
               missing={k:record['performance'][k]['missing'] for k in KEYS},
               returns=record['returns'],breakdown=record['breakdown'],delta=record['delta'],
               settled_asof=record['observed_at'])
    study.update(asof=record['observed_at'],compounded={k:segments(study['rows'],k) for k in KEYS})


if __name__ == '__main__':
    now=datetime.now(timezone.utc)
    ledger=published(read(FILE))
    study=read(ANNUAL/'study.json')
    settle_history(study,ledger,read(ANNUAL/'2025-price-sources.json'),now)
    observe(read(ANNUAL/'forward.json'),ledger,now)
    save(ANNUAL/'study.json',study)
    save(FILE,ledger)
