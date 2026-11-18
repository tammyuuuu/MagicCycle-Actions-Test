"""November only. Preserve existing vintages; calculate returns only after selection."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
from statistics import mean
from experiment_tracker import chart, read, save
from expanded_study import FEE, OUT, RAW, RULES, SEC, SYMBOLS, evaluate_pool, portfolios

ANNUAL=OUT/'annual'
KEYS=('finance','trend','combined','benchmark')
YEARS=range(2020,2027)


def attribution(picks,returns):
    trend=set(picks['trend'])
    combined=set(picks['combined'])
    k=len(trend)
    legs=defaultdict(float)
    for s in trend^combined:
        v=returns[s]
        if v is None:return None
        if s in trend:
            label='avoided_loss' if v<0 else 'missed_gain'
            legs[label]-=v/k
        else:
            label='added_gain' if v>=0 else 'added_loss'
            legs[label]+=v/k
    return {key:legs[key] for key in ('avoided_loss','missed_gain','added_gain','added_loss')}


def segments(rows,key):
    groups=[]
    for row in rows:
        val=row.get('net',{}).get(key)
        if val is None:continue
        if not groups or row['year']!=groups[-1][-1][0]+1:groups.append([])
        groups[-1].append((row['year'],val))
    return [dict(first=g[0][0],last=g[-1][0],years=len(g),
                 cagr=(math.prod(1+r/100 for _,r in g)**(1/len(g))-1)*100) for g in groups]


def map_symbols():
    snap=read(Path('stock_research/sec_tickers.json'))
    rows=sorted((r for r in snap['data'] if r[3] in ('NYSE','Nasdaq')),key=lambda r:(len(r[2]),r[2]))
    out={}
    for cik,_,symbol,_ in rows:out.setdefault(str(cik),symbol)
    return out


def run():
    historical=read(OUT/'results.json')['batches']
    original=read(Path('research_monitor/experiments/v1/quarterly-history.json'))['batches']
    base={b['anchor'][:4]:b for b in original if b['anchor'][5:7]=='11'}
    base['2026']=read(Path('research_monitor/experiments/v1/quarterly-live.json'))['batches'][0]
    prices={s:chart(read(RAW/f'{s}_chart.json'),s) for s in SYMBOLS}
    for p in (SEC/'prices').glob('*.json'):
        if p.stem not in prices:prices[p.stem]={r['日期']:r['收盘'] for r in read(p)}
    calendar=sorted(prices['MSFT'])
    mapping=map_symbols()
    reports=[]
    for year in YEARS:
        row=dict(year=year)
        reports.append(row)
        if year<2022:
            b=next(b for b in historical if b['month']==f'{year}-11')
            picks=b['expanded']['picks']; returns=b['returns']; result=b['expanded']
            row.update(coverage=b['coverage'],eligible=len(returns),entry=b['entry'],maturity=b['maturity'])
        else:
            snapshot=ANNUAL/'inputs'/f'{year}.json'
            if not snapshot.exists():
                row.update(status='缺少可核验的当年原始申报池')
                continue
            sec=read(snapshot)
            old=base[str(year)]
            pred=old['prediction']; cutoff=pred['cutoff']
            inputs=dict(pred['inputs'])
            days=[d for d in calendar if d<=cutoff][-64:]
            counts=Counter()
            excluded={}
            duplicate=Counter(mapping.get(r['cik']) for r in sec['rows'])
            for r in sec['rows']:
                cik=r['cik'];s=mapping.get(cik)
                if cik in {str(x) for x in RULES['universe'].values()}:reason='已计入四股'
                elif not s or duplicate[s]>1 or s in SYMBOLS:reason='无唯一代码映射'
                elif s not in prices:reason='无所存行情'
                elif None in (r['revenue'],r['prior'],r['op'],r['cash']) or min(r['revenue'],r['prior'])<=0:reason='财务输入不足'
                elif not all((prices[s].get(d) or 0)>0 for d in days):reason='趋势窗口不足'
                else:
                    reason='可评分'
                    inputs[s]=dict(cik=cik,accession=r['adsh'],filed=r['filed'],growth=r['revenue']/r['prior']-1,
                                   margin=r['op']/r['revenue'],cash=r['cash']/r['revenue'],trend=prices[s][cutoff]/prices[s][days[0]]-1)
                counts[reason]+=1
                if reason!='可评分':excluded[cik]=reason
            entry=old['entry']; maturity=old['maturity']
            picks=portfolios(inputs)
            row.update(coverage=dict(counts),eligible=len(inputs),entry=entry,maturity=maturity,cutoff=cutoff,
                       source=sec.get('source','https://www.sec.gov/files/dera/data/financial-statement-data-sets/2025q1.zip'),snapshot_sha256=sec['sha256'],inputs=inputs,picks=picks,excluded=excluded)
            if year>=2025:
                row['status']='登记后跟踪' if year==2026 else '截至分析时到期收盘未取得'
                continue
            returns={}
            for s in inputs:
                a,b=(prices[s].get(d) for d in (entry,maturity))
                returns[s]=(FEE*b/a-1)*100 if a and b and min(a,b)>0 else None
            result=evaluate_pool(picks,returns)
        row.update(status='历史回放',picks=picks,returns=returns,net={k:result['performance'][k]['net'] for k in KEYS},
                   missing={k:result['performance'][k]['missing'] for k in KEYS},
                   breakdown=attribution(picks,returns),delta=result['delta'])
        if row['breakdown'] is not None:
            assert math.isclose(sum(row['breakdown'].values()),row['delta'],abs_tol=1e-8)
    save(ANNUAL/'study.json',dict(asof=datetime.now(timezone.utc).isoformat(),rows=reports,
                                 compounded={k:segments(reports,k) for k in KEYS}))


if __name__=='__main__':run()
