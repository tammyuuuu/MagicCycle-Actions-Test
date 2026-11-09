from pathlib import Path
import json, html, shutil
from datetime import datetime
from asset_states import render_rail, render_basis
rows=json.loads(Path('docs/index.json').read_text(encoding='utf8'))
if not rows or any(r.get('status')=='error' for r in rows): raise SystemExit('数据校验失败，不生成页面')
styles=Path('templates/_styles.html').read_text(encoding='utf8')
cards=[]
for r in rows:
 e=html.escape
 m=r['metrics']; date=e(r.get('date','未知'))
 cards.append(f'<article class="card"><h2>{e(r["name"])} <small>{e(r["symbol"])}</small></h2><p>行情日期 {date} · 收盘 {m.get("price", "—")} · {e(r.get("market_update", "行情数据"))}</p>{render_rail(r)}<details><summary>查看判断依据</summary>{render_basis(r)}</details></article>')
now=datetime.now().strftime('%Y-%m-%d %H:%M')
page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#202e4b"><title>星循 · 今日提醒测试版</title>{styles}<style>body{{margin:0}} .test-wrap{{max-width:760px;margin:auto;padding:16px}} .test-header{{background:#202e4b;color:white;padding:20px 16px}} .test-header h1{{margin:0}} .test-note{{font-size:14px;line-height:1.6}} .card{{margin:14px 0}} small{{font-size:14px}} a{{color:inherit}}</style></head><body><header class="test-header"><div class="test-wrap"><h1>星循 · 今日提醒</h1><p class="test-note">独立测试版 · 北京时间更新于 {now}<br>若自动更新失败，页面会保留上次成功数据；请核对每张卡片的行情日期。<br><a href="https://github.com/tammyuuuu/MagicCycle-Actions-Test/actions">查看更新状态与运行日志</a></p></div></header><main class="test-wrap">{''.join(cards)}</main></body></html>'''
Path('docs/index.html').write_text(page,encoding='utf8')
Path('docs/assets').mkdir(exist_ok=True)
shutil.copy2('assets/xingxun-serif-650.woff', 'docs/assets/xingxun-serif-650.woff')
