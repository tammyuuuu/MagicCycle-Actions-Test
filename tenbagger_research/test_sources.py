import csv, json, os, sys
from datetime import datetime, timezone
import requests

# Set SEC_USER_AGENT to a real name and contact email before accessing SEC.
ua = os.environ.get('SEC_USER_AGENT')
tests = [
 ('stooq_active', 'https://stooq.com/q/d/l/', {'s':'aapl.us','i':'d','d1':'20100101','d2':'20201231'}),
 ('stooq_delisted_probe', 'https://stooq.com/q/d/l/', {'s':'lehmq.us','i':'d'}),
 ('sec_submissions', 'https://data.sec.gov/submissions/CIK0000320193.json', {}),
 ('sec_companyfacts', 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json', {}),
 ('sec_filing_delisted', 'https://data.sec.gov/submissions/CIK0000807585.json', {}),
]
results=[]
for name,url,params in tests:
    item={'test':name,'url':url,'params':params,'utc':datetime.now(timezone.utc).isoformat()}
    if name.startswith('sec_') and not ua:
        item['status']='skipped: set SEC_USER_AGENT to real contact'; results.append(item); continue
    try:
        r=requests.get(url,params=params,headers={'User-Agent':ua or 'Historical research test'},timeout=25)
        item.update(status=r.status_code, bytes=len(r.content), content_type=r.headers.get('Content-Type'), final_url=r.url)
        if r.ok and 'json' in r.headers.get('Content-Type',''):
            obj=r.json(); item['top_keys']=list(obj)[:12]
        elif r.ok: item['preview']=r.text[:200]
    except requests.RequestException as e: item['error']=str(e)[:400]
    results.append(item)
out=os.path.join(os.path.dirname(__file__),'source_test_results.json')
with open(out,'w',encoding='utf-8') as f: json.dump(results,f,ensure_ascii=False,indent=2)
print(json.dumps(results,ensure_ascii=False,indent=2))
