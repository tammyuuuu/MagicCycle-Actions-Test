"""Extract the SEC Q1 issuer universe and four required accounting amounts by accession."""
import csv
import hashlib
import io
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from experiment_tracker import save

REVENUE = ('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax')
OP = 'OperatingIncomeLoss'
CFO = 'NetCashProvidedByUsedInOperatingActivities'


def extract(path, year):
    with zipfile.ZipFile(path) as z:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig'),delimiter='\t')
        issuers = {}
        for r in rows('sub.txt'):
            sic = int(r['sic'] or 0)
            if not (3570<=sic<=3579 or 3660<=sic<=3679 or 7370<=sic<=7379):
                continue
            if r['form']=='10-K' and r['fp']=='FY' and r['period'][:4]==str(year-1):
                if r['cik'] not in issuers or r['filed']<issuers[r['cik']]['filed']:
                    issuers[r['cik']]={k:r[k] for k in ('adsh','cik','name','period','filed','sic')}
        by_id={r['adsh']:r for r in issuers.values()}
        values=defaultdict(set)
        tags=set(REVENUE+(OP,CFO))
        for r in rows('num.txt'):
            if r['adsh'] not in by_id or r['tag'] not in tags or r['qtrs']!='4' or r['uom']!='USD' or r['coreg'] or r.get('segments') or not r['value']:
                continue
            diff=(date.fromisoformat(by_id[r['adsh']]['period'])-date.fromisoformat(r['ddate'])).days
            lag=round(diff/365)
            if lag in (0,1) and abs(diff-365*lag)<=14:
                values[r['adsh'],r['tag'],lag].add(float(r['value']))
        for r in issuers.values():
            def amount(tags,lag):
                for tag in tags:
                    v=values[r['adsh'],tag,lag]
                    if len(v)==1:return next(iter(v))
            r.update(revenue=amount(REVENUE,0),prior=amount(REVENUE,1),op=amount((OP,),0),cash=amount((CFO,),0))
    return dict(year=year,sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),rows=list(issuers.values()))


if __name__=='__main__':
    import sys
    save(Path(sys.argv[3]),extract(Path(sys.argv[1]),int(sys.argv[2])))
