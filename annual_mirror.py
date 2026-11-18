"""Reconstruct SEC quarterly extracts from a content-verified public FSDS mirror."""
from pathlib import Path
import duckdb
from annual_sec import extract
from experiment_tracker import save
import zipfile
import hashlib

db = Path('sec_edgar.duckdb')
digest = 'fdfd9c5807dac4725a1fb0b84b42a547be75f9a70d3568280a45930d1776a044'
with db.open('rb') as handle:
    assert hashlib.file_digest(handle, 'sha256').hexdigest() == digest
con = duckdb.connect(str(db), read_only=True)
for year in [2022, 2023, 2024, 2025, 2026]:
    if con.execute('select max(filed) from submissions').fetchone()[0].isoformat() < f'{year}-04-01':
        continue
    sql = f"""select adsh, cast(cast(cik as bigint) as varchar) cik, name, sic, form, fp,
              strftime(period,'%Y%m%d') period, strftime(filed,'%Y%m%d') filed
              from submissions where filed >= date '{year}-01-01' and filed < date '{year}-04-01'
              and form='10-K' and fp='FY' and year(period)={year-1}
              and (sic between '3570' and '3579' or sic between '3660' and '3679' or sic between '7370' and '7379')"""
    con.execute(f"create or replace temp table candidates as {sql}")
    con.execute("copy candidates to 'sub.txt' (header, delimiter '\t')")
    con.execute("""copy (select n.adsh,tag,qtrs,uom,coreg,segments,value,strftime(ddate,'%Y%m%d') ddate
                from numbers n join candidates c on n.adsh=c.adsh where qtrs=4 and uom='USD'
                and tag in ('OperatingIncomeLoss','NetCashProvidedByUsedInOperatingActivities',
                'RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet',
                'RevenueFromContractWithCustomerIncludingAssessedTax')) to 'num.txt' (header, delimiter '\t')""")
    with zipfile.ZipFile('slice.zip','w') as z:
        for name in ('sub.txt','num.txt'):
            z.write(name)
    data = extract(Path('slice.zip'),year)
    data.update(source='https://huggingface.co/datasets/erlenbusch/sec-edgar', database_sha256=digest)
    save(Path(f'annual-inputs/{year}.json'),data)
