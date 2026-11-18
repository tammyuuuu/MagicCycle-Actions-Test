"""Render the research homepage from report-backed studies and Azure monitor state."""
import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from research_inventory import collect
from quarterly_view import quarterly_section
from experiment_cards import cards as experiment_cards

ROOT = Path('research_monitor')
DOCS = Path('docs')
REPO = 'https://github.com/tammyuuuu/MagicCycle-Actions-Test'
LABELS = {'research': '研究预测', 'last_quarter': '上一季外推', 'guidance_midpoint': '微软指引中点'}
escape = html.escape


def inline(text, original):
    """Render the small Markdown subset used by the existing research reports."""
    text = escape(text)
    base = REPO + '/blob/main/' + original
    def link(match):
        label, target = match.groups()
        address = html.unescape(target)
        if not address.startswith(('https://', 'http://')):
            local = (Path(original).parent / address).resolve()
            allowed_roots = [Path(name).resolve() for name in ('stock_research', 'investor_holdings_research')]
            allowed = any(local.is_relative_to(folder) for folder in allowed_roots)
            relative = (Path(original).parent / address).as_posix()
            name = hashlib.sha256(relative.encode()).hexdigest()[:16] + Path(address).suffix
            saved = ROOT / 'evidence' / name
            if allowed and local.is_file() and local.suffix in ('.csv', '.md') and local.stat().st_size < 1000000:
                saved.parent.mkdir(exist_ok=True)
                shutil.copy2(local, saved)
            if saved.exists():
                evidence = DOCS / 'research' / 'evidence'
                evidence.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, evidence / name)
                address = 'research/evidence/' + name
            else:
                return label + '（原报告附件）'
        return f'<a href="{escape(address, quote=True)}">{label}</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    return re.sub(r'`([^`]+)`', r'<code>\1</code>', text)


def report_html(report):
    blocks = []
    table = []
    def flush_table():
        if table:
            rows = []
            for index, line in enumerate(table):
                if re.fullmatch(r'[\s|:\-]+', line):
                    continue
                tag = 'th' if index == 0 else 'td'
                cells = ''.join(f'<{tag}>{inline(cell.strip(), report["original"])}</{tag}>' for cell in line.strip('|').split('|'))
                rows.append('<tr>' + cells + '</tr>')
            blocks.append('<div class="table-scroll"><table>' + ''.join(rows) + '</table></div>')
            table.clear()
    for line in report['content'].splitlines():
        if line.startswith('|'):
            table.append(line)
            continue
        flush_table()
        if not line.strip():
            continue
        heading = re.match(r'^#{1,6}\s+(.+)', line)
        if heading:
            blocks.append('<h4>' + inline(heading.group(1), report['original']) + '</h4>')
        else:
            blocks.append('<p>' + inline(line, report['original']) + '</p>')
    flush_table()
    return ''.join(blocks)


def project_card(project):
    sources = ''.join(f'<li><a href="{escape(source)}">{escape(source)}</a></li>' for source in project['sources'])
    reports = []
    for report in project['reports']:
        saved = Path(report['snapshot']).relative_to(ROOT).as_posix()
        reports.append(f'<details class="report"><summary>{escape(report["title"])}</summary><a href="research/{saved}">下载原始报告</a><div class="report-body">{report_html(report)}</div></details>')
    search = escape(' '.join([project['title'], project['question'], project['summary']]), quote=True)
    return f'''<details class="study" data-status="{project['status']}" data-search="{search}">
+<summary><div class="card-meta"><span class="status">{project['status']}</span><span>{escape(project['report_date'])}</span></div><h3>{escape(project['title'])}</h3><p class="question">{escape(project['question'])}</p><p class="conclusion">{escape(project['summary'])}</p><span class="expand-label">查看结论与证据 <span aria-hidden="true">＋</span></span></summary>
+<div class="study-body"><dl><dt>当前进展</dt><dd>{escape(project['progress'])}</dd><dt>下一步行动</dt><dd>{escape(project['next_action'])}</dd></dl><h4>原始报告与数据</h4>{''.join(reports)}<details class="source-list"><summary>数据来源 · {len(project['sources'])} 项</summary><ul>{sources or '<li>来源说明见原始报告。</li>'}</ul></details></div></details>'''.replace('\n+', '\n')


def azure_card(monitor, validation):
    observation = monitor.get('observation', {})
    errors = observation.get('errors_pp', {})
    rows = ''.join(f'<tr><th scope="row">{LABELS[key]}</th><td>{value}%</td><td>{errors.get(key, "等待披露")}</td></tr>' for key, value in [('research', 49), ('last_quarter', 48), ('guidance_midpoint', 49.5)])
    status = {'waiting': '等待披露', 'completed': '已评分', 'error': '监测异常'}[monitor['status']]
    checked = datetime.fromisoformat(monitor['checked_at']).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M 北京时间')
    health = 'IR 首页尚未链接 Q2 正式公告。' if monitor['status'] == 'waiting' else monitor.get('detail', '首次正式披露值已锁定。')
    winners = '、'.join(LABELS[key] for key in observation.get('winners', []))
    result = f'实际增速 {observation["actual"]}%，误差最小为{winners}。' if observation else 'Q2 预测为 49%；上一季为 48%，公司指引中点为 49.5%。'
    from datetime import timedelta
    checked_day = datetime.fromisoformat(monitor['checked_at']).astimezone(ZoneInfo('Asia/Shanghai'))
    next_check = checked_day.replace(hour=16,minute=30,second=0,microsecond=0)
    if next_check <= checked_day:
        next_check += timedelta(days=1)
    while next_check.weekday() >= 5:
        next_check += timedelta(days=1)
    next_label = '年度复评 2027-11-18' if observation else '下次计划检查 '+next_check.strftime('%Y-%m-%d %H:%M')+' 北京时间'
    annual_review = '年度复评日 2027-11-18。届时按独立到期预测数及各基线误差评定。'
    if checked_day.date().isoformat() >= '2027-11-18':
        if observation:
            annual_review = ('独立到期预测 1 项。研究预测绝对误差 '+str(errors['research'])+' 个百分点，持平外推 '+str(errors['last_quarter'])+'，指引中点 '+str(errors['guidance_midpoint'])+'。'+('继续跟踪，研究误差小于两项对照，需新增独立季度。' if errors['research'] < min(errors['last_quarter'],errors['guidance_midpoint']) else '归档本次预测，误差未同时优于两项对照。'))
        else:
            annual_review = '到期可评分预测 0 项，待核查官方披露及指标可比性后复评。'
    action = '复核实际披露与原文，比较三种预测的误差及原因。' if observation else '等待截至 2026-12-31 财季首次正式披露，自动锁定实际值并评分。'
    return f'''<details class="study azure"><summary><div class="card-meta"><span class="status">{status}</span><span>自动监测</span></div><h3>微软 Azure 的效率提升能否支撑增长加速？</h3><p class="conclusion">{escape(result)}</p><p class="question">{escape(health)}</p><strong>{next_label}</strong><span class="expand-label">查看预测与监测 <span aria-hidden="true">＋</span></span></summary><div class="study-body"><dl><dt>当前进展</dt><dd>FY27 Q1 真实公告已验证，固定汇率同比为 {validation['actual']}%。最近检查 {escape(checked)}。</dd><dt>下一步行动</dt><dd>{action}</dd></dl><div class="table-scroll"><table><caption>FY27 Q2 · Azure 固定汇率同比增速</caption><thead><tr><th>预测依据</th><th>预测值</th><th>绝对误差 / 百分点</th></tr></thead><tbody>{rows}</tbody></table></div><p>以首次成功抓取的正式披露计算绝对误差，最小值并列记平局。首次观测锁定后保留，后续修订不覆盖。</p><h4>满一年综合评定</h4><p>{annual_review}</p><h4>效率提升的原文</h4><blockquote lang="en">our ability to also create additional capacity within our existing fleet gave us some room to be able to convert that actually</blockquote><p>Amy Hood 回答 Karl Keirstead，说明现有设备释放容量。供给延迟、新效率收益及 token 定价仍影响下季结果。</p><p><a href="https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1">阅读微软业绩会原文 ↗</a></p><div class="evidence-links"><a href="research/registration.md">原始登记</a><a href="research/addendum.json">追加对照与时间戳</a><a href="research/validation.json">上季抓取验证</a><a href="research/q1_release.html">公告快照</a><a href="research/runtime/status.json">当前监测结果</a></div></div></details>'''


def main():
    DOCS.mkdir(exist_ok=True)
    projects = collect()
    monitor = json.loads((ROOT / 'runtime/status.json').read_text(encoding='utf8'))
    validation = json.loads((ROOT / 'validation.json').read_text(encoding='utf8'))
    data = {'built_at': datetime.now(timezone.utc).isoformat(), 'monitor': monitor, 'projects': projects, 'validation': validation}
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    version = hashlib.sha256(payload.encode()).hexdigest()
    (DOCS / 'research.json').write_text(payload, encoding='utf8')
    shutil.copytree(ROOT, DOCS / 'research', dirs_exist_ok=True)
    focused = [project for project in projects if project['focus']]
    archived = [project for project in projects if not project['focus']]
    experiments = experiment_cards()
    substitutions = {
        "{{QUARTERLY}}": quarterly_section(),
        "{{EXPERIMENTS}}": "".join(experiments),
        '{{VERSION}}': version,
        '{{FOCUS_COUNT}}': str(len(focused) + 1 + len(experiments)),
        '{{ARCHIVE_COUNT}}': str(len(archived)),
        '{{TOTAL_COUNT}}': str(len(projects) + 1 + len(experiments)),
        '{{AZURE}}': azure_card(monitor, validation),
        '{{FOCUSED}}': ''.join(project_card(project) for project in focused),
        '{{ARCHIVED}}': ''.join(project_card(project) for project in archived),
        '{{BUILT}}': data['built_at'],
    }
    page = Path('templates/research_home.html').read_text(encoding='utf8')
    for key, value in substitutions.items():
        page = page.replace(key, value)
    (DOCS / 'index.html').write_text(page, encoding='utf8')
    (DOCS / 'assets').mkdir(exist_ok=True)
    shutil.copy2('assets/research.css', DOCS / 'assets/research.css')
    shutil.copy2('assets/research.js', DOCS / 'assets/research.js')
    shutil.copy2('assets/xingxun-serif-650.woff', DOCS / 'assets/xingxun-serif-650.woff')


if __name__ == '__main__':
    main()
