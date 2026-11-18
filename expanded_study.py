"""Replay the preregistered expansion. Uses local archival inputs; publishes derived results."""
import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

from experiment_tracker import chart, read, save
from quarterly_studies import RULES, SYMBOLS

OUT = Path('research_monitor/expanded')
SEC = Path('stock_research/mature_tech_v1')
RAW = Path('D:/file/fun/code/cycle/stock_monitor_data/raw')
FEE = .999 / 1.001
PHASES = {'2020-05':'探索','2020-08':'探索','2020-11':'隔离','2021-05':'隔离','2021-08':'预留','2021-11':'预留'}
EXITS = {
 '1212458': ('2021-08-31','Proofpoint 私有化，每股现金 176 美元','https://www.sec.gov/Archives/edgar/data/1212458/000119312521261338/d219408dex991.htm'),
 '1356104': ('2020-04-27','Mellanox 收购完成','https://nvidianews.nvidia.com/news/nvidia-completes-acquisition-of-mellanox-creating-major-force-driving-next-gen-data-centers')
}


def portfolios(inputs):
    count = math.ceil(len(inputs)/2)
    ranks = {}
    for key in ('growth','margin','cash','trend'):
        ordered = sorted(v[key] for v in inputs.values())
        ranks[key] = {value: ordered.index(value)+1+(ordered.count(value)-1)/2 for value in set(ordered)}
    selected = {}
    for rule in RULES['rules']:
        weights = rule['weights']
        scores = {s:sum(w*ranks[k][row[k]] for k,w in weights.items())/sum(weights.values()) for s,row in inputs.items()}
        selected[rule['id']] = sorted(scores,key=lambda s:(-scores[s],s))[:count]
    selected['benchmark'] = sorted(inputs)
    return selected


def evaluate_pool(picks, returns):
    performance = {}
    for rule, members in picks.items():
        missing = [s for s in members if returns[s] is None]
        performance[rule] = {'missing':missing,'net':None if missing else mean(returns[s] for s in members)}
    finance, trend = set(picks['combined']), set(picks['trend'])
    attribution = {}
    for symbol in sorted(finance ^ trend):
        weight = (int(symbol in finance)-int(symbol in trend))/len(finance)
        attribution[symbol] = None if returns[symbol] is None else weight*returns[symbol]
    delta = None if None in attribution.values() else sum(attribution.values())
    if performance['combined']['net'] is not None and performance['trend']['net'] is not None:
        assert math.isclose(delta,performance['combined']['net']-performance['trend']['net'],abs_tol=1e-8)
    return dict(picks=picks,performance=performance,contribution=attribution,delta=delta)


def replay():
    v1 = read(Path('research_monitor/experiments/v1/quarterly-history.json'))['batches']
    prices = {s:chart(read(RAW/f'{s}_chart.json'),s) for s in SYMBOLS}
    calendar = sorted(prices['MSFT'])
    batches = []
    for old in v1:
        month = old['anchor'][:7]
        if month not in PHASES:
            continue
        year = month[:4]
        with (SEC/f'screen_{year}.csv').open(encoding='utf8') as handle:
            rows = list(csv.DictReader(handle))
        cutoff = old['prediction']['cutoff']
        window = [d for d in calendar if d<=cutoff][-64:]
        inputs = {s:dict(v,cik=str(RULES['universe'][s])) for s,v in old['prediction']['inputs'].items()}
        duplicates = Counter(r['ticker'] for r in rows)
        audit = []
        for r in rows:
            s,cik = r['ticker'],r['cik']
            item = dict(cik=cik,ticker=s,name=r['name'],accession=r['adsh'],filed=r['filed'])
            audit.append(item)
            if cik in {str(v) for v in RULES['universe'].values()}:
                item['status']='已计入四股';continue
            if cik in EXITS:
                item['exit']=EXITS[cik]
                if EXITS[cik][0]<=cutoff:
                    item['status']='信号日前已退出';continue
            if not s or duplicates[s]>1 or s in SYMBOLS:
                item['status']='无唯一代码映射';continue
            if s not in prices and (SEC/'prices'/f'{s}.json').exists():
                prices[s]={r['日期']:r['收盘'] for r in read(SEC/'prices'/f'{s}.json')}
            if s not in prices:
                item['status']='无行情';continue
            try:
                rev,prior,op,cash = (float(r[k]) for k in ('rev_0','rev_1','OperatingIncomeLoss_0','NetCashProvidedByUsedInOperatingActivities_0'))
                if min(rev,prior)<=0 or not all(map(math.isfinite,(rev,prior,op,cash))):
                    raise ValueError
            except ValueError:
                item['status']='财务输入不全或营收非正';continue
            if not all((prices[s].get(d) or 0)>0 for d in window):
                item['status']='趋势窗口不全或非正';continue
            assert r['filed']<=cutoff.replace('-','')
            inputs[s]=dict(growth=rev/prior-1,margin=op/rev,cash=cash/rev,trend=prices[s][cutoff]/prices[s][window[0]]-1,cik=cik,accession=r['adsh'])
            item['status']='可评分'
        returns={}
        for s in inputs:
            start,end=(prices[s].get(old[k]) for k in ('entry','maturity'))
            returns[s]=(FEE*end/start-1)*100 if start and end and min(start,end)>0 else None
        small={s:inputs[s] for s in SYMBOLS}
        base=evaluate_pool(portfolios(small),returns)
        for k in old['result']['results']:
            assert base['picks'][k]==old['prediction']['portfolios'][k]['picks']
            assert math.isclose(base['performance'][k]['net'],old['result']['results'][k]['net_pct'],abs_tol=1e-8)
        batches.append(dict(month=month,phase=PHASES[month],cutoff=cutoff,entry=old['entry'],maturity=old['maturity'],
                            candidates=audit,coverage=dict(Counter(i['status'] for i in audit)),inputs=inputs,returns=returns,
                            expanded=evaluate_pool(portfolios(inputs),returns),v1=base))
    return batches


def summarize(batches, pool):
    seats=Counter()
    attribution=Counter()
    sets=[]
    deltas=[]
    for b in batches:
        result=b[pool]
        ids={b['inputs'][s]['cik'] for s in result['picks']['finance']}
        for cik in ids:
            seats[cik]+=1/len(ids)
        sets.append(ids)
        if result['delta'] is not None:
            deltas.append(result['delta'])
            attribution.update(result['contribution'])
    n=len(deltas)
    return dict(companies=len(seats),top5_pct=sum(sorted(seats.values(),reverse=True)[:5])/len(batches)*100,
                adjacent_jaccard=mean(len(a&b)/len(a|b) for a,b in zip(sets,sets[1:])) if len(sets)>1 else None,
                known=n,delta=mean(deltas) if n else None,
                contributions={s:v/n for s,v in attribution.most_common()})


if __name__=='__main__':
    batches=replay()
    groups={phase:{pool:summarize([b for b in batches if phase=='全部' or b['phase']==phase],pool) for pool in ('expanded','v1')}
            for phase in ('全部','探索','隔离','预留')}
    save(OUT/'results.json',dict(batches=batches,groups=groups))
    for b in batches: print(b['month'],len(b['inputs']),b['expanded']['delta'],b['v1']['delta'])
    for k,v in groups.items():
        g=v['expanded'];print(k,g['companies'],g['top5_pct'],g['delta'],list(g['contributions'].items())[:4])
