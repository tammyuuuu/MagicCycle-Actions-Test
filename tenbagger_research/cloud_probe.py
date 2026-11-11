import json,time,datetime,traceback
from pathlib import Path
import requests
out=Path('tenbagger_research/cloud_output'); out.mkdir(parents=True,exist_ok=True)
results=[]
def save(name, fn):
 for attempt in range(1,4):
  t=time.monotonic()
  try:
   data=fn(); path=out/f'{name}_{attempt}.json'; path.write_text(json.dumps(data,ensure_ascii=False,default=str),encoding='utf-8'); results.append(dict(source=name,attempt=attempt,status='ok',seconds=round(time.monotonic()-t,2),summary=data.get('summary'),file=path.name))
  except Exception as e: results.append(dict(source=name,attempt=attempt,status='error',seconds=round(time.monotonic()-t,2),error=str(e)[:500]))
  time.sleep(2)
def yahoo():
 r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/ANET',params={'period1':1585612800,'period2':1743552000,'interval':'1d','events':'div,splits'},headers={'User-Agent':'Mozilla/5.0'},timeout=30);r.raise_for_status(); j=r.json(); x=j['chart']['result'][0]; return {'summary':{'rows':len(x.get('timestamp',[])),'events':list(x.get('events',{}))},'response':j}
def stooq():
 r=requests.get('https://stooq.com/q/d/l/',params={'s':'anet.us','i':'d','d1':'20200331','d2':'20250331'},timeout=30);r.raise_for_status(); lines=r.text.splitlines();
 if not lines or not lines[0].startswith('Date,'): raise ValueError('Not CSV: '+r.text[:200])
 return {'summary':{'rows':len(lines)-1,'first':lines[1] if len(lines)>1 else None,'last':lines[-1]},'csv':r.text}
def ak():
 import akshare as ak
 d=ak.stock_us_hist(symbol='106.ANET',start_date='20200331',end_date='20250331',adjust='qfq')
 if d.empty: raise ValueError('empty response')
 return {'summary':{'rows':len(d),'columns':list(d.columns),'first':d.iloc[0].to_dict(),'last':d.iloc[-1].to_dict()},'records':d.to_dict(orient='records')}
for n,fn in [('yahoo',yahoo),('stooq',stooq),('akshare',ak)]: save(n,fn)
(out/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False,default=str),encoding='utf-8');print(json.dumps(results,indent=2,ensure_ascii=False,default=str))
