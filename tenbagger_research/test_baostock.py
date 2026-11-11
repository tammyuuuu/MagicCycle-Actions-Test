import sys,socket,json,datetime
from pathlib import Path
p=Path(__file__).resolve().parent;sys.path.append(str(p/'vendor'));import baostock as bs
socket.setdefaulttimeout(20)
report={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'version':getattr(bs,'__version__','unknown')}
try:
 login=bs.login();report['login']={'code':login.error_code,'message':login.error_msg}
 if login.error_code!='0':raise RuntimeError('login failed')
 for name,fun in [('all_stock_20151231',lambda:bs.query_all_stock(day='2015-12-31')),('stock_basic',lambda:bs.query_stock_basic())]:
  try:
   rs=fun();meta={'error_code':rs.error_code,'error_message':rs.error_msg,'fields':rs.fields};rows=[]
   if rs.error_code=='0':
    while rs.next():rows.append(rs.get_row_data())
   meta['rows']=len(rows);report[name]=meta
   if rows:
    import csv
    with (p/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
     w=csv.writer(f);w.writerow(rs.fields);w.writerows(rows)
  except Exception as e:report[name]={'error':repr(e)}
 bs.logout()
except Exception as e:report['error']=repr(e)
(p/'baostock_test.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False,indent=2))
