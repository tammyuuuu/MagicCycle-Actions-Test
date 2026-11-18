from html import escape
from quarterly_studies import FOLDER, read, summary

NAMES = dict(growth='营收增长',finance='综合财务',trend='价格趋势',combined='财务＋趋势')


def comparison(c):
    switch = '、'.join(c['out'])+' → '+'、'.join(c['added']) if c['out'] else '持仓相同'
    diff = c['net_difference_pp']
    earned = ('等待收盘验证' if c['out'] else '相同持仓差额为零') if diff is None else f'组合净收益差 {diff:+.2f} 个百分点'
    tie = '；'.join(NAMES[k]+'入选边界同分，按代码排序（'+'、'.join(v)+'）' for k,v in c['boundary_ties'].items()) or '入选边界无同分'
    return f'<p><b>{NAMES[c["parent"]]} → {NAMES[c["child"]]}</b>　{switch}。{earned}。{tie}。</p>'


def group(batches,asof):
    stats = summary(batches,asof)
    rows = []
    for b in reversed(batches):
        keys = stats['overlap'][b['anchor']]
        overlap = '持有期与 '+ '、'.join(keys)+' 批次重叠' if keys else '无重叠批次'
        when = b.get('result',{}).get('observed_close') or max(b.get('checks',{}),default='尚无验证')
        rows.append(f'<details><summary>{b["anchor"]} · {"已到期" if b.get("result") else "未到期"} · 到期 {b["maturity"]}</summary><p>{overlap}。验证截至 {when}。</p>'+''.join(comparison(c) for c in b['comparisons'])+'</details>')
    means = '；'.join(NAMES[k]+f' {v["mean_net_pct"]:+.2f}%（相对基准 {v["mean_excess_pp"]:+.2f} 个百分点）' for k,v in stats['rules'].items())
    return f'<p>已到期 {len(stats["matured"])} 批，未到期 {len(stats["pending"])} 批。到期批次等权平均净收益：{means or "尚无成绩"}。</p>'+''.join(rows)


def quarterly_section():
    history = read(FOLDER/'quarterly-history.json')
    live = read(FOLDER/'quarterly-live.json')
    batches = live['batches']
    last = batches[-1]
    example = next(b for b in reversed(history['batches']) if 'result' in b and any(c['out'] for c in b['comparisons']))
    change = next(c for c in example['comparisons'] if c['out'])
    reviews = []
    for day,review in sorted(live.get('annual_reviews',{}).items()):
        returns = '；'.join(f'{NAMES[k]}净收益 {v["mean_net_pct"]:+.2f}%，相对基准 {v["mean_excess_pp"]:+.2f} 个百分点' for k,v in review['rules'].items())
        reviews.append(f'<p>{day}：已到期 {len(review["matured"])} 批，未到期 {len(review["pending"])} 批。{returns}。</p>')
    return ('<section><h2>季度重选与换股贡献</h2><p>每年 2、5、8、11 月 18 日登记，按当月 6 日或之前最近收盘评分，下一个交易日收盘建仓。每批独立等权持有一年，按季度核验。</p>'
            +f'<h3>最近登记 · {last["anchor"]}</h3>'+''.join(comparison(c) for c in last['comparisons'])
            +f'<h3>最近到期的历史换股示例 · {example["anchor"]} 批次</h3>'+comparison(change)
            +'<p>差额为两组同日起止、扣除相同费率后的组合收益之差。两只股票各占一半，未换部分相互抵消。</p>'
            +'<details><summary>登记后各批次与年度汇总</summary>'+group(batches,'9998')+(''.join(reviews) or '<p>首次年度汇总预计 2027-11-18。</p>')+'</details>'
            +f'<details><summary>历史回放 · 截至 {history["asof"]}</summary><p>按今天固定的四股回看，存在样本选择和幸存者偏差。使用当时已申报年报、供应商事后复权价。缺少完整输入的 {len(history["skipped"])} 批已排除。重叠批次共享市场区间，平均值不代表独立试验或连续组合年化收益。</p>'
            +group(history['batches'],history['asof'])+'</details><p><a href="research/experiments/v1/quarterly-live.json">批次登记及逐期账本</a> · <a href="research/experiments/v1/quarterly-history.json">回放输入与成绩</a></p></section>')
