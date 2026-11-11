import json,csv
from pathlib import Path
p=Path(__file__).resolve().parent
src=p.parent/'stock_research'/'mature_tech_v1'/'prices'
rows=[]
for f in src.glob('*.json'):
 try:
  d={x['日期']:float(x['收盘']) for x in json.loads(f.read_text(encoding='utf-8')) if x.get('收盘') and '日期' in x and '2020-03-31'<=x['日期']<='2025-03-31'}
  if '2020-03-31' not in d or '2025-03-31' not in d: continue
  peak=max(d,key=d.get); ratio=d['2025-03-31']/d['2020-03-31']; peakratio=d[peak]/d['2020-03-31']
  if peakratio<10: rows.append([f.stem,'2020-03-31','2025-03-31',d['2020-03-31'],d['2025-03-31'],round(ratio,4),peak,round(peakratio,4),len(d),str(f.relative_to(p.parent))])
 except (ValueError,KeyError,TypeError): pass
with (p/'local_controls_provisional.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['ticker','start','end','start_close','end_close','end_multiple','peak_date','peak_multiple','observations','source']);w.writerows(sorted(rows))
print(len(rows))
