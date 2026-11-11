import json,time,requests
from pathlib import Path
out=Path('tenbagger_research/cohort_raw');out.mkdir(exist_ok=True)
tickers='ANET ATOM BELFA CLRO ENPH INOD KOPN MARA MSTR PI AAOI ACIW ADBE ADTN AEIS AIRG ALRM AMD AMKR APH LEHMQ SIVB'.split()
for t in tickers:
 try:
  r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/'+t,params={'period1':1585612800,'period2':1743552000,'interval':'1d','events':'div,splits'},headers={'User-Agent':'Mozilla/5.0'},timeout=25)
  (out/(t+'.json')).write_text(json.dumps({'status':r.status_code,'body':r.json()}),encoding='utf8');print(t,r.status_code,flush=True)
 except Exception as e:(out/(t+'.json')).write_text(json.dumps({'error':str(e)}),encoding='utf8')
 time.sleep(.5)
