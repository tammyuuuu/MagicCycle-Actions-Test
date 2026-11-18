"""Parallel one-year vintages on the February/May/August/November registration cycle."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
import argparse
import requests

from experiment_tracker import ROOT, PAGES, chart, evaluate, fetch_prices, prediction, read, save

FOLDER = ROOT / 'v1'
RULES = read(FOLDER / 'rules.json')
PAIRS = [('growth', 'finance'), ('finance', 'combined'), ('trend', 'combined')]
FIRST = date(2026, 11, 18)
SYMBOLS = list(RULES['universe'])


def anchors(first_year, end):
    for year in range(first_year, end.year + 1):
        for month in (2, 5, 8, 11):
            anchor = date(year, month, 18)
            if anchor <= end:
                yield anchor


def replacements(pred, record=None):
    comparisons = []
    for parent, child in PAIRS:
        old, new = (pred['portfolios'][key] for key in (parent, child))
        removed = sorted(set(old['picks']) - set(new['picks']))
        added = sorted(set(new['picks']) - set(old['picks']))
        ties = {}
        for key, portfolio, changed in [(parent, old, removed), (child, new, added)]:
            boundary = portfolio['scores'][portfolio['picks'][-1]]
            tied = sorted(s for s,v in portfolio['scores'].items() if abs(v-boundary)<1e-12)
            if set(tied)-set(portfolio['picks']):
                ties[key] = tied
        delta = None if record is None else record['results'][child]['net_pct']-record['results'][parent]['net_pct']
        comparisons.append(dict(parent=parent, child=child, out=removed, added=added,
                                boundary_ties=ties, net_difference_pp=delta))
    return comparisons


def new_batch(anchor, cutoff, entry, maturity, prices, facts):
    pred = prediction(RULES, cutoff, prices, facts)
    for symbol,row in pred['inputs'].items():
        row['trend_start_adj_close'] = prices[symbol][row['trend_start']]
        row['trend_end_adj_close'] = prices[symbol][cutoff]
    return dict(anchor=anchor.isoformat(), prediction=pred, entry=entry, maturity=maturity,
                benchmark={s:1/len(SYMBOLS) for s in SYMBOLS}, rules_version='v1',
                locked_at=datetime.now(timezone.utc).isoformat(), comparisons=replacements(pred))


def score(batch, prices, days):
    record = evaluate(batch['prediction'],prices,batch['entry'],batch['maturity'],days)
    batch.update(result=record, comparisons=replacements(batch['prediction'],record))


def summary(batches, asof):
    closed = [b for b in batches if b.get('result',{}).get('observed_close','9999')<=asof]
    pending = [b for b in batches if b not in closed]
    overlap = {b['anchor']:[c['anchor'] for c in batches if c != b and
                           max(b['entry'],c['entry']) < min(b['maturity'],c['maturity'])]
               for b in batches}
    return dict(asof=asof,matured=[b['anchor'] for b in closed],
                pending=[{'anchor':b['anchor'],'maturity':b['maturity']} for b in pending],
                overlap=overlap, rules={k:dict(
                    mean_net_pct=mean(b['result']['results'][k]['net_pct'] for b in closed),
                    mean_excess_pp=mean(b['result']['results'][k]['excess_pp'] for b in closed))
                    for k in [r['id'] for r in RULES['rules']] if closed},
                added_information={parent+' → '+child:mean(b['result']['results'][child]['net_pct']-
                    b['result']['results'][parent]['net_pct'] for b in closed) for parent,child in PAIRS if closed})


def historical(raw):
    prices = {s:chart(read(raw/f'{s}_chart.json'),s) for s in SYMBOLS}
    facts = {s:read(raw/f'{s}_facts.json') for s in SYMBOLS}
    days = sorted(prices['MSFT'])
    limit = min(max(x) for x in prices.values())
    batches, skipped = [], []
    # BWXT became independently traded on 2015-07-01. Its trend window must start after that.
    for anchor in anchors(2015,date.fromisoformat(limit)):
        if anchor <= date(2015,7,1):
            continue
        cutoff = max(d for d in days if d <= anchor.replace(day=6).isoformat())
        entry = min(d for d in days if d > anchor.isoformat())
        anniversary = anchor.replace(year=anchor.year+1).isoformat()
        maturity = next((d for d in days if d >= anniversary),anniversary)
        try:
            trend_days = [d for d in days if d<=cutoff][-64:]
            if trend_days[0] < '2015-07-01' or any(set(trend_days)-p.keys() for p in prices.values()):
                raise ValueError('趋势窗口存在缺失或早于 BWXT 独立交易')
            batch = new_batch(anchor, cutoff, entry, maturity, prices, facts)
            if maturity<=limit:
                score(batch,prices,days)
            batches.append(batch)
        except (ValueError, KeyError, IndexError) as exc:
            skipped.append({'anchor':anchor.isoformat(),'reason':str(exc)})
    save(FOLDER/'quarterly-history.json',dict(asof=limit,batches=batches,skipped=skipped))


def live():
    import exchange_calendars as xc
    cal = xc.get_calendar('XNYS')
    now = datetime.now(timezone.utc)
    today = now.date()
    path = FOLDER/'quarterly-live.json'
    state = read(path)
    response = requests.get(PAGES+'v1/quarterly-live.json',timeout=40)
    if response.status_code == 404 and today < date(2027,2,18):
        pass
    else:
        response.raise_for_status()
        state = response.json()
    seen = {b['anchor'] for b in state['batches']} | {b['anchor'] for b in state['missed']}
    for anchor in anchors(2027,today):
        if anchor.isoformat() in seen:
            continue
        entry = cal.date_to_session(anchor+timedelta(days=1),direction='next')
        if now >= cal.session_close(entry).to_pydatetime():
            state['missed'].append(dict(anchor=anchor.isoformat(),reason='未在建仓收盘前锁定，跳过该批'))
            continue
        cutoff = cal.date_to_session(anchor.replace(day=6),direction='previous').date().isoformat()
        start = (anchor-timedelta(days=155)).isoformat()
        prices = {s:fetch_prices(s,start,anchor.isoformat()) for s in SYMBOLS}
        facts = {}
        for s,cik in RULES['universe'].items():
            response = requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',
                                    headers={'User-Agent':'Cycle research github.com/tammyuuuu/MagicCycle-Actions-Test'},timeout=40)
            response.raise_for_status()
            facts[s] = response.json()
        trend_days = [d.date().isoformat() for d in cal.sessions_in_range(start,cutoff)][-64:]
        if any(set(trend_days)-series.keys() for series in prices.values()):
            raise ValueError('Incomplete trend price window')
        maturity = cal.date_to_session(anchor.replace(year=anchor.year+1),direction='next')
        state['batches'].append(new_batch(anchor,cutoff,entry.date().isoformat(),maturity.date().isoformat(),prices,facts))
    for batch in state['batches']:
        anchor = date.fromisoformat(batch['anchor'])
        for months in (3, 6, 9, 12):
            offset = anchor.month - 1 + months
            nominal = date(anchor.year + offset // 12, offset % 12 + 1, 18)
            if nominal > today:
                break
            target = cal.date_to_session(nominal, direction='next')
            key = target.date().isoformat()
            checks = batch.setdefault('checks', {})
            if key in checks:
                continue
            if now < cal.session_close(target).to_pydatetime() + timedelta(hours=1):
                break
            end = (target.date()+timedelta(days=1)).isoformat()
            prices = {s:fetch_prices(s,batch['entry'],end) for s in SYMBOLS}
            days = [d.date().isoformat() for d in cal.sessions_in_range(batch['entry'],key)]
            record = evaluate(batch['prediction'],prices,batch['entry'],key,days)
            checks[key] = record
            batch['comparisons'] = replacements(batch['prediction'],record)
            if months == 12:
                batch['result'] = record
    reviews = state.setdefault('annual_reviews', {})
    for year in range(FIRST.year+1, today.year+1):
        anniversary = date(year, FIRST.month, FIRST.day)
        if anniversary > today:
            break
        review_day = cal.date_to_session(anniversary,direction='next')
        if now < cal.session_close(review_day).to_pydatetime()+timedelta(hours=1):
            break
        asof = review_day.date().isoformat()
        if asof not in reviews:
            batches = [b for b in state['batches'] if b['anchor']<=asof]
            reviews[asof] = summary(batches,asof)
    save(path,state)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--history',type=Path)
    args=parser.parse_args()
    if args.history:
        historical(args.history)
    else:
        live()
