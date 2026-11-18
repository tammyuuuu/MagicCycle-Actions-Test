"""Render the annual evidence directly from the locked research records."""
from html import escape
from statistics import mean
from math import prod
from annual_replay import ANNUAL, KEYS
from experiment_tracker import read


def number(value):
    return '缺价' if value is None else f'{value:+.2f}'


def maturity_review(batch, records):
    final = [r for r in records if r['date']==batch['maturity']]
    if not final:
        return '<p>年度复核待到期收盘后结算。</p>'
    record=final[-1]
    performance=record['performance']
    benchmark=performance['benchmark']['net']
    labels={'growth':'纯增长','finance':'纯财务','trend':'纯趋势','combined':'财务加趋势','benchmark':'全池等权'}
    rows=[]
    for k,label in labels.items():
        value=performance[k]['net']
        excess=None if value is None or benchmark is None else value-benchmark
        missing='、'.join(performance[k]['missing']) or '无'
        rows.append(f'<tr><th>{label}</th><td>{number(value)}</td><td>{number(excess)}</td><td>{escape(missing)}</td></tr>')
    trades=[]
    for s,impact in sorted(record['contribution'].items(),key=lambda item:-(abs(item[1]) if item[1] is not None else -1)):
        side='换入' if s in batch['picks']['combined'] else '剔除'
        trades.append(f'<tr><th>{escape(s)}</th><td>{side}</td><td>{number(impact)}</td></tr>')
    legs=record['breakdown']
    attribution_summary=('差异持仓缺价，换股总贡献待补齐。' if legs is None else
        f"避开下跌 {number(legs['avoided_loss'])}，错过上涨 {number(legs['missed_gain'])}，"
        f"换入上涨 {number(legs['added_gain'])}，换入下跌 {number(legs['added_loss'])} 个百分点。")
    return f"""<h4>到期复核 · {batch['maturity']}</h4><p>{escape(record['assessment'])}</p>
<div class="table-scroll"><table><tr><th>组合</th><th>实际扣费收益 %</th><th>相对全池（百分点）</th><th>缺价股票</th></tr>{''.join(rows)}</table></div>
<p>财务加趋势相对纯趋势 {number(record['delta'])} 个百分点。{attribution_summary}</p>
<details><summary>逐股换入与剔除贡献</summary><table><tr><th>股票</th><th>变动</th><th>贡献（百分点）</th></tr>{''.join(trades)}</table></details>"""


def annual_section():
    study=read(ANNUAL/'study.json')
    batch=read(ANNUAL/'forward.json')
    records=read(ANNUAL/'ledger.json')['records']
    history=[r for r in study['rows'] if 'net' in r]
    def cells(items):
        return '<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in items)+'</tr>'
    body=''.join(cells([r['year'],r['eligible'],*[number(r['net'][k]) for k in KEYS],number(r['delta'])]) for r in history)
    periods=''.join('<p>'+label+'：'+'；'.join(f"{s['first']}–{s['last']} 建仓，{s['years']} 批，{number(s['cagr'])}%"
                    for s in study['compounded'][key])+'。</p>' for key,label in zip(KEYS,['纯财务','纯趋势','财务加趋势','全池等权']))
    common=[r for r in history if all(r['net'][k] is not None for k in KEYS)]
    common_summary=''
    if common and common[-1]['year']-common[0]['year']+1==len(common):
        figures=[(prod(1+r['net'][k]/100 for r in common)**(1/len(common))-1)*100 for k in KEYS]
        common_summary=(f"四组都有完整收益的 {common[0]['year']}–{common[-1]['year']} 建仓期，"
                        +"、".join(f"{label} {v:+.2f}%" for label,v in zip(['纯财务','纯趋势','财务加趋势','全池等权'],figures))+"。")
    legs=[r['breakdown'] for r in history if r.get('breakdown')]
    notes=''.join('<p>'+str(r['year'])+' 年 · '+escape(r['status'])+'。'+
                  '，'.join(escape(k)+' '+str(v) for k,v in r.get('coverage',{}).items())+
                  ('。持仓缺价：'+escape('、'.join(sorted(set(sum(r['missing'].values(),[])))) or '无') if 'missing' in r else '')+'</p>' for r in study['rows'])
    done={r['date'] for r in records if r['complete']}
    next_date=next((d for d in batch['checkpoints'] if d not in done),'已完成')
    observations=''.join('<p>'+r['date']+' · 有价 '+str(len(r['prices']))+'/'+str(len(batch['picks']['benchmark']))+
                         ' · 联合减趋势 '+number(r['delta'])+' 个百分点。'+escape(r.get('assessment',''))+'</p>' for r in records)
    leg=lambda k:number(mean(r[k] for r in legs))
    verdict='避跌收益超过踏空成本' if mean(r['avoided_loss']+r['missed_gain'] for r in legs)>0 else '避跌收益未超过踏空成本'
    return f"""<section id="annual-expansion"><h2>每年 11 月选股，财务评分避跌能抵过踏空吗？</h2>
<p>在 {len(legs)} 笔可核验年度回放中，相对趋势组，联合组剔除下跌股平均贡献 {leg('avoided_loss')} 个百分点，错过上涨股平均贡献 {leg('missed_gain')} 个百分点。换入股的上涨与下跌另贡献 {leg('added_gain')} 和 {leg('added_loss')} 个百分点。当前样本中，{verdict}；完整退市收益和更长前瞻观察仍有缺口。</p>
<div class="table-scroll"><table><caption>11 月建仓年份 · 扣费收益 % · 末列为百分点</caption><tr><th>年份</th><th>股票数</th><th>纯财务</th><th>纯趋势</th><th>财务加趋势</th><th>全池等权</th><th>联合减趋势</th></tr>{body}</table></div>
<details><summary>连续年份复利、缺失年份和覆盖范围</summary>{periods}<p>{common_summary}</p><p>历史回放截至 {study["asof"][:10]}。按年度净值相乘再开年数次方，批次之间空档现金收益取零。全池 2020 年缺 CLRO 的有效价格，基准起算年较晚。2019 年及以前缺完整同口径行情。每批买卖各扣 0.1%。当前代码映射及既存价格缓存使样本偏向仍可交易的公司，退市收益覆盖率未知。较晚年份仅在既有价格档案覆盖范围内回放。</p>{notes}
<a href="research/expanded/annual/study.json">逐年评分输入、持仓、收益与归因</a> · <a href="research/expanded/annual/2025-price-sources.json">2025 批次原行情代码</a> · <a href="research/expanded/registration.json">评分及费用规则</a></details>
<h3>前瞻批次 · 2026 年 11 月</h3><p>{escape(batch['scope'])}。{len(batch['picks']['benchmark'])} 只可评分，策略各选 {len(batch['picks']['trend'])} 只。计划 {batch['entry']} 美股收盘建仓，下个待核对节点 {next_date}，满一年评定 {batch['maturity']}。</p>
<details><summary>查看登记、季度跟踪和年度评定</summary><p>同一持仓跟踪四次。入场交易日核验基准价，此后按季核对扣费清算收益。缺价保留原权重，有新增证据时追加记录。</p>{observations}{maturity_review(batch,records)}
<a href="research/expanded/annual/forward.json">锁定输入与全部持仓</a> · <a href="research/expanded/annual/ledger.json">跟踪记录</a></details></section>"""
