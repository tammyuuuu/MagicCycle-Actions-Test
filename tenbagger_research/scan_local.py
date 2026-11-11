import json,csv,datetime,bisect
from pathlib import Path
root=Path(__file__).resolve().parent
files=root.parent/'stock_research'/'mature_tech_v1'/'prices'
rows=[]
for f in files.glob('*.json'):
 try:
  data=json.loads(f.read_text(encoding='utf-8')); data=sorted((x['日期'],float(x['收盘'])) for x in data if x.get('收盘') and '日期' in x and x['日期']<='2025-12-31')
  if len(data)<2: continue
  dates=[x[0] for x in data]
  for i,(date,price) in enumerate(data):
   if not date.endswith(('-01-31','-02-28','-03-31','-04-30','-05-31','-06-30','-07-31','-08-31','-09-30','-10-31','-11-30','-12-31')): continue
   target=str(int(date[:4])+5)+date[4:]; j=bisect.bisect_left(dates,target)
   if j>=len(data) or (datetime.date.fromisoformat(dates[j])-datetime.date.fromisoformat(target)).days>5: continue
   window=data[i:j+1]; peak=max(window,key=lambda x:x[1]); multiple=data[j][1]/price
   if multiple>=10 or peak[1]/price>=10:
    rows.append(dict(ticker=f.stem,start=date,end=dates[j],start_close=price,end_close=data[j][1],end_multiple=round(multiple,3),peak_date=peak[0],peak_multiple=round(peak[1]/price,3),source=str(f.relative_to(root.parent)))); break
 except (ValueError,KeyError,TypeError): pass
rows.sort(key=lambda r:r['ticker'])
with (root/'local_candidates.csv').open('w',encoding='utf-8-sig',newline='') as out:
 w=csv.DictWriter(out,fieldnames=['ticker','start','end','start_close','end_close','end_multiple','peak_date','peak_multiple','source']);w.writeheader();w.writerows(rows)
print('files',len(list(files.glob('*.json'))),'candidates',len(rows)); print(*rows,sep='\n')
