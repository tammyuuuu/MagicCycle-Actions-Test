"""Presentation of preregistered historical results; no live price dependency."""
from html import escape
from pathlib import Path
from experiment_tracker import read


def fmt(value):
    return '未知' if value is None else f'{value:+.2f}'


def expanded_section():
    report=read(Path('research_monitor/expanded/results.json'))
    batches=report['batches']
    hold=report['groups']['预留']
    expanded=hold['expanded']
    ranked=list(expanded['contributions'].items())
    table=[]
    for b in batches:
        row=[b['month'],b['phase'],str(len(b['inputs'])),str(len(b['expanded']['picks']['finance'])),
             fmt(b['expanded']['performance']['combined']['net']),fmt(b['expanded']['performance']['trend']['net']),
             fmt(b['expanded']['delta']),fmt(b['v1']['delta'])]
        table.append('<tr>'+''.join(f'<td>{escape(v)}</td>' for v in row)+'</tr>')
    headers=['批次','用途','可评分','财务入选','扩池联合净收益 %','扩池趋势净收益 %','扩池差额 pp','四股差额 pp']
    coverage=[]
    for b in batches:
        counts='，'.join(f'{k} {v}' for k,v in b['coverage'].items())
        missing='、'.join(b['expanded']['performance']['benchmark']['missing']) or '无'
        coverage.append(f'<p>{b["month"]} · SEC 申报主体 {len(b["candidates"])} 家。{counts}。建仓或期末价格缺失／非正：{missing}。</p>')
    leaders='、'.join(f'{s} {v:+.2f}' for s,v in ranked[:5])
    laggards='、'.join(f'{s} {v:+.2f}' for s,v in reversed(ranked[-5:]))
    return f"""<section id="expanded-study"><h2>扩池后，财务指标改变了什么？</h2>
<p>历史预留期，两批各有 179 只股票，财务组各选 90 家，合计 91 家、89 家重复。前五家公司占两批平均资金的 {expanded['top5_pct']:.2f}%。固定选一半并等权限制了单股集中度；两季沿用同一年度财务截面，名单高度重合。同期四股财务组两次均选同两家。</p>
<p><strong>财务＋趋势相对只看趋势，扩池平均 {fmt(expanded['delta'])} 个百分点，四股 v1 为 {fmt(hold['v1']['delta'])} 个百分点。</strong>两批持有期重叠约九个月。2021 年 11 月批次两种组合都亏损，联合评分少亏 4.88 个百分点。</p>
<details><summary>查看季度差额、股票贡献和数据缺口</summary>
<div class="table-scroll"><table><caption>同日收盘建仓、持有一年、买卖各 10bp。pp 为百分点。</caption><tr>{''.join(f'<th>{v}</th>' for v in headers)}</tr>{''.join(table)}</table></div>
<p>预留期按批次等权平均。正贡献前五（百分点）：{leaders}。负贡献前五：{laggards}。贡献等于两组合权重差乘个股扣费收益。避开下跌股票也会贡献正值。全部六批（含一次实际只有四股的批次）平均差额 {fmt(report['groups']['全部']['expanded']['delta'])} 个百分点。</p>
<h3>覆盖情况</h3>{''.join(coverage)}
<p>候选以当年第一季度 SEC 原始 10-K 的 CIK、行业、报告期和申报日重建。当前代码映射与可用行情仅能覆盖其中一部分。确认 Mellanox 于 2020-04-27 被收购、Proofpoint 于 2021-08-31 私有化，两者均未进入有完整行情的可评分子池。退市事件总数、完整退出收益覆盖率未知，缺代码不推定为退市。CLRO 的未知终值保留在原持仓中；若双方权重相同，可单独识别策略差额。</p>
<p>扩池新增成分采用东方财富事后前复权价格，四股采用 v1 的供应商调整收盘，两者的股息口径可能不同。年度申报池遗漏其他季度提交年报的企业，历史股票代码亦未逐股验证。预留期属于回溯验证。</p>
<p><a href="research/expanded/registration.json">回放前登记</a> · <a href="research/expanded/results.json">逐主体覆盖、持仓、收益和逐股贡献</a> · <a href="https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets">SEC 数据说明</a></p></details></section>"""
