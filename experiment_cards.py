from html import escape
from experiment_tracker import ROOT, read

NAMES = {'growth':'只看营收增长','finance':'增长、利润率与现金流','trend':'只看价格趋势','combined':'财务评分结合价格趋势'}


def observation(row, key, rules):
    actual = row['results'][key]
    parents = {'finance':['growth'],'combined':['finance','trend']}.get(key,[])
    changes = '；'.join(f'较{NAMES[p]} {actual["net_pct"]-row["results"][p]["net_pct"]:+.2f} 个百分点' for p in parents)
    return (f'<p>{row["observed_close"]} · 持有 {", ".join(actual["picks"])}。净收益 {actual["net_pct"]:+.2f}%，'
            f'基准 {row["benchmark"]["net_pct"]:+.2f}%，相差 {actual["excess_pp"]:+.2f} 个百分点。'
            f'{changes}。最大回撤 {actual["max_drawdown_pct"]:.2f}%，买入 {actual["buys"]} 笔，模拟清算 {actual["liquidation_sells"]} 笔。</p>')


def cards():
    output = []
    for folder in sorted(ROOT.glob('*/rules.json')):
        version = folder.parent
        rules = read(folder)
        pred = read(version/'prediction.json')
        history = read(version/'history.json')
        records = read(version/'ledger.json')['records']
        next_date = next((n for n in rules['nodes'] if n not in {r['scheduled'] for r in records}), '已完成年度评定')
        for rule in rules['rules']:
            key = rule['id']
            picks = '、'.join(pred['portfolios'][key]['picks'])
            annual = records[-1]['results'][key].get('annual_review') if records else None
            summary = f'已登记等权持有 {picks}，首次验证尚未到期。'
            if records:
                last = records[-1]['results'][key]
                summary = f'最近节点净收益 {last["net_pct"]:+.2f}%，相对基准 {last["excess_pp"]:+.2f} 个百分点。'
            review = '预计 '+rules['nodes'][-1]+' 评定。'
            if annual:
                review = annual['decision']+'。'+summary+' '+rules['assessment']
            base = f'research/experiments/{version.name}'
            output.append(f"""<details class="study"><summary><span class="status">选股研究 · {escape(version.name)}</span>
<h3>{escape(rule['question'])}</h3><p>{summary}</p><strong>下次验证　{next_date}</strong></summary>
<div class="study-body"><h4>登记规则</h4><p>{escape(rules['method'])}</p><p>权重按比例归一化：{escape('、'.join({'growth':'营收增长','margin':'营业利润率','cash':'经营现金流率','trend':'价格趋势'}[k]+' × '+str(v) for k,v in rule['weights'].items()))}。首日 {rules['start']}。</p>
<h4>登记后跟踪</h4>{''.join(observation(r,key,rules) for r in records) or '<p>尚无到期记录。</p>'}
<h4>满一年综合评定</h4><p>{escape(review)}</p><p>四次观察跟踪同一组合，独立批次为一。</p>
<details><summary>历史回放 · 2024 年建仓</summary><p>固定今日样本回看，存在样本选择偏差。使用截至当时已披露的年报和供应商事后复权行情。</p>{''.join(observation(r,key,rules) for r in history['records'])}</details>
<p><a href="{base}/rules.json">带时间戳的登记</a> · <a href="{base}/prediction.json">评分输入与持仓</a> · <a href="{base}/ledger.json">验证记录</a></p></div></details>""")
    return output
