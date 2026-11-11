import requests
s=requests.Session(); s.trust_env=False
for u in ['https://stooq.com/q/d/l/?s=aapl.us&i=d','https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1mo&interval=1d','https://www.sec.gov/']:
 try:
  r=s.get(u,timeout=12); print(u,r.status_code,len(r.content),r.headers.get('Content-Type'))
 except Exception as e: print(u,type(e).__name__,str(e)[:180])
