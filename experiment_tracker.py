"""Freeze point-in-time signals and append scheduled portfolio observations."""
import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import requests

ROOT = Path('research_monitor/experiments')
PAGES = 'https://tammyuuuu.github.io/MagicCycle-Actions-Test/research/experiments/'
TAGS = {'revenue': ('RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet'),
        'operating': ('OperatingIncomeLoss',), 'cash': ('NetCashProvidedByUsedInOperatingActivities',)}


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    tmp.replace(path)


def chart(raw, symbol):
    series = raw['chart']['result'][0]
    if series['meta']['symbol'] != symbol:
        raise ValueError('Wrong price series: ' + symbol)
    values = series['indicators']['adjclose'][0]['adjclose']
    return {datetime.fromtimestamp(t, timezone.utc).date().isoformat(): v
            for t, v in zip(series['timestamp'], values, strict=True)
            if v is not None and math.isfinite(v) and v > 0}


def annual(raw, cutoff):
    tags = raw['facts']['us-gaap']
    fields = {}
    for field, choices in TAGS.items():
        records = {}
        for tag in reversed(choices):
            for row in tags.get(tag, {}).get('units', {}).get('USD', []):
                if row['form'] != '10-K' or row['filed'] > cutoff or 'start' not in row:
                    continue
                days = (date.fromisoformat(row['end']) - date.fromisoformat(row['start'])).days
                if 350 <= days <= 378:
                    records[row['filed'], row['accn'], row['end']] = row['val']
        fields[field] = records
    filed, accession, end = max(fields['revenue'])
    key = filed, accession, end
    prior = max(k for k in fields['revenue'] if k[:2] == key[:2] and k[2] < end)
    if not 350 <= (date.fromisoformat(end) - date.fromisoformat(prior[2])).days <= 378:
        raise ValueError('Missing comparative fiscal year')
    revenue = fields['revenue'][key]
    return {'filed': filed, 'accession': accession, 'end': end, 'prior_end':prior[2],
            'revenue': revenue, 'prior_revenue': fields['revenue'][prior],
            'operating_income':fields['operating'][key], 'operating_cash_flow':fields['cash'][key],
            'growth': revenue / fields['revenue'][prior] - 1,
            'margin': fields['operating'][key] / revenue, 'cash': fields['cash'][key] / revenue}


def prediction(rules, cutoff, prices, facts):
    inputs = {}
    for symbol, series in prices.items():
        days = sorted(d for d in series if d <= cutoff)
        if days[-1] != cutoff:
            raise ValueError('Missing signal date: ' + symbol)
        inputs[symbol] = dict(annual(facts[symbol], cutoff), trend_start=days[-64], trend_end=cutoff,
                              trend=series[cutoff] / series[days[-64]] - 1)
    portfolios = {}
    for rule in rules['rules']:
        scores = {}
        for symbol, row in inputs.items():
            score = 0
            for field, weight in rule['weights'].items():
                vals = [i[field] for i in inputs.values()]
                rank = 1 + sum(v < row[field] for v in vals) + (vals.count(row[field]) - 1) / 2
                score += weight * rank
            scores[symbol] = score / sum(rule['weights'].values())
        portfolios[rule['id']] = {'scores': scores, 'picks': sorted(scores, key=lambda s: (-scores[s], s))[:2]}
    return {'cutoff': cutoff, 'inputs': inputs, 'portfolios': portfolios}


def evaluate(pred, prices, start, target, calendar):
    first = min(day for day in calendar if day >= start)
    last = min(day for day in calendar if day >= target)
    days = sorted(d for d in calendar if first <= d <= last)
    def metrics(symbols):
        baseline = {s: prices[s][first] for s in symbols}
        peak = 1
        drawdown = 0
        for day in days:
            nav = mean(prices[s][day] / baseline[s] for s in symbols) / 1.001
            if day == last:
                nav *= .999
            peak = max(nav, peak)
            drawdown = min(drawdown, nav / peak - 1)
        return {'net_pct': (nav - 1)*100, 'max_drawdown_pct':drawdown*100,
                'buys':len(symbols), 'liquidation_sells':len(symbols)}
    benchmark = metrics(list(prices))
    results = {}
    for name, portfolio in pred['portfolios'].items():
        result = metrics(portfolio['picks'])
        results[name] = dict(result, picks=portfolio['picks'], excess_pp=result['net_pct']-benchmark['net_pct'])
    return {'scheduled':target,'entry':first,'observed_close':last,'benchmark':benchmark,'results':results,
            'entry_adj_close':{s:p[first] for s,p in prices.items()},'exit_adj_close':{s:p[last] for s,p in prices.items()},
            'recorded_at':datetime.now(timezone.utc).isoformat()}


def initialize(folder, raw):
    if (folder/'prediction.json').exists():
        raise ValueError('Version already registered')
    rules = read(folder/'rules.json')
    prices = {s:chart(read(raw/f'{s}_chart.json'),s) for s in rules['universe']}
    facts = {s:read(raw/f'{s}_facts.json') for s in prices}
    calendar = chart(read(raw/'MSFT_chart.json'),'MSFT')
    history = rules['history']
    historical = prediction(rules, history['cutoff'], prices, facts)
    rows = [evaluate(historical,prices,history['start'],node,calendar) for node in history['nodes']]
    save(folder/'history.json',dict(prediction=historical,records=rows))
    save(folder/'prediction.json',prediction(rules,rules['signal_cutoff'],prices,facts))
    save(folder/'ledger.json',{'records':[]})


def fetch_prices(symbol, start, end):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
    stamp = lambda d: int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())
    response = requests.get(url,params={'period1':stamp(start),'period2':stamp(end),'interval':'1d'},
                            headers={'User-Agent':'Mozilla/5.0'},timeout=45)
    response.raise_for_status()
    return chart(response.json(),symbol)


def track(folder):
    import exchange_calendars as xc
    rules = read(folder/'rules.json')
    pred = read(folder/'prediction.json')
    ledger = read(folder/'ledger.json')
    source = requests.get(PAGES + folder.name + '/ledger.json', timeout=40)
    if source.status_code != 404:
        source.raise_for_status()
        published = source.json()
        if published['records'][:len(ledger['records'])] != ledger['records']:
            raise ValueError('Conflicting published ledger')
        ledger = published
    elif date.today().isoformat() >= rules['nodes'][0] and not ledger['records']:
        # A missing ledger after initial publication must not erase scored history.
        raise ValueError('Published ledger missing after first validation date')
    done = [r['scheduled'] for r in ledger['records']]
    if done != rules['nodes'][:len(done)]:
        raise ValueError('Out-of-order validation records')
    calendar = xc.get_calendar('XNYS')
    now = datetime.now(timezone.utc)
    for node in rules['nodes'][len(done):]:
        if node > now.date().isoformat():
            break
        session = calendar.date_to_session(node,direction='next')
        if now < calendar.session_close(session).to_pydatetime()+timedelta(hours=1):
            break
        days = [d.date().isoformat() for d in calendar.sessions_in_range(rules['start'],session)]
        end = (session.date()+timedelta(days=1)).isoformat()
        prices = {s:fetch_prices(s,rules['start'],end) for s in rules['universe']}
        record = evaluate(pred,prices,rules['start'],node,days)
        ledger['records'].append(record)
        if node == rules['nodes'][-1]:
            for rule in rules['rules']:
                result = record['results'][rule['id']]
                comparisons = [rule['parent']] if 'parent' in rule else []
                if rule['id']=='combined':
                    comparisons.append('trend')
                gains = [result['net_pct']-record['results'][p]['net_pct'] for p in comparisons]
                decision = '归档' if result['excess_pp']<=0 else ('调整' if any(g<=0 for g in gains) else '继续跟踪')
                result['annual_review'] = {'decision':decision,'incremental_pp':dict(zip(comparisons,gains)),
                                           'independent_cohorts':1,'observations':len(ledger['records'])}
    save(folder/'ledger.json',ledger)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--initialize',type=Path)
    parser.add_argument('--version',default='v1')
    args=parser.parse_args()
    if args.initialize:
        initialize(ROOT/args.version,args.initialize)
    else:
        for folder in sorted(ROOT.glob('*/rules.json')):
            track(folder.parent)
