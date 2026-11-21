"""Prospective weekly SGE Au99.99 close experiment (CNY per gram)."""
from datetime import date, datetime, time, timedelta, timezone
from html import escape, unescape
from math import exp, log, sqrt
from pathlib import Path
from statistics import mean
import json
import re

import requests

LEDGER = Path("research_monitor/experiments/gold.json")
CN = timezone(timedelta(hours=8))
HORIZONS = (5, 21, 63)
SOURCE = "https://www.sge.com.cn/sjzx/quotation_daily_new"
# 2027 national holiday notice, 国办发明电〔2026〕10号. Weekends never count.
BREAKS = [("2027-01-01", "2027-01-03"), ("2027-02-05", "2027-02-13"),
          ("2027-04-03", "2027-04-05"), ("2027-05-01", "2027-05-05"),
          ("2027-06-09", "2027-06-09"), ("2027-09-15", "2027-09-15"),
          ("2027-10-01", "2027-10-07")]


def session(day):
    if day.year > 2027:
        import exchange_calendars
        return exchange_calendars.get_calendar("XSHG").is_session(day.isoformat())
    return day.weekday() < 5 and not any(a <= day.isoformat() <= b for a, b in BREAKS)


def advance(day, count):
    while count:
        day += timedelta(days=1)
        count -= int(session(day))
    return day


def parse_quote(page, day):
    cells = lambda row: [unescape(re.sub("<[^>]+>", "", s)).strip() for s in
                         re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.I | re.S)]
    rows = [cells(row) for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, re.I | re.S)]
    header = next(row for row in rows if "收盘价" in row and "合约" in row)
    matches = [r for r in rows if len(r) == len(header) and
               r[header.index("日期")] == day and r[header.index("合约")] == "Au99.99"]
    row, = matches
    high, low, close = (float(row[header.index(k)]) for k in ("最高价", "最低价", "收盘价"))
    if not 0 < low <= close <= high:
        raise ValueError("Invalid Au99.99 bar")
    return dict(high=high, low=low, close=close)


def fetch(day):
    errors = []
    for host in (SOURCE, SOURCE.replace("sge.com.cn", "sgenow.cn")):
        try:
            r = requests.get(host, params={"end_date": day, "start_date": day}, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            r.raise_for_status()
            return dict(**parse_quote(r.content.decode("utf8"), day), source=r.url)
        except (requests.RequestException, ValueError, StopIteration) as exc:
            errors.append(str(exc))
    raise RuntimeError(f"{day} Au99.99 行情未核实: {errors}")


def register(day, bar, now):
    close, high, low = (bar[k] for k in ("close", "high", "low"))
    midpoint = sqrt(high * low)
    sigma = log(high / low) / sqrt(4 * log(2))
    # Half of the log-distance to the day's midpoint eventually reverses.
    forecasts = []
    for h in HORIZONS:
        center = close * exp(0.5 * (1 - exp(-h / 5)) * log(midpoint / close))
        radius = 1.281551566 * sigma * sqrt(h)
        forecasts.append(dict(h=h, target=str(advance(day, h)), point=round(center, 2),
                              low=round(center * exp(-radius), 2), high=round(center * exp(radius), 2)))
    return dict(origin=str(day), cutoff=f"{day}T15:30:00+08:00", registered=now.isoformat(),
                model="range-reversion-v1", bar=bar, forecasts=forecasts,
                support=f"收盘 {close:.2f}，日内高低价几何中点 {midpoint:.2f}，假设两者差距部分回归。",
                counter=f"当日高低价 {low:.2f}–{high:.2f}，收盘偏离中点也可能反映持续趋势。")


def metrics(pairs):
    if not pairs:
        return "待验证（0 项）"
    base = mean(abs(f["actual"] - c) for f, c in pairs)
    mae = mean(abs(f["actual"] - f["point"]) for f, c in pairs)
    sign = lambda x: (x > 0) - (x < 0)
    direction = mean(sign(f["actual"] - c) == sign(f["point"] - c) for f, c in pairs)
    hit = mean(f["low"] <= f["actual"] <= f["high"] for f, _ in pairs)
    width = mean(f["high"] - f["low"] for f, _ in pairs)
    gain = f"{1-mae/base:.1%}" if base else "无定义"
    return f"{len(pairs)} 项 · MAE {mae:.2f} · 较持平改善 {gain} · 方向 {direction:.0%} · 区间命中 {hit:.0%} · 平均宽度 {width:.2f}"


def save(records):
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    tmp.replace(LEDGER)


def update(now, register_new=True):
    records = json.loads(LEDGER.read_text(encoding="utf8"))
    day = now.date()
    available = day if now.time() >= time(15, 30) else day - timedelta(days=1)
    pending = {f["target"] for r in records for f in r["forecasts"]
               if "actual" not in f and f["target"] <= str(available)}
    # Only register after the last session of the week and before the next session.
    origin = available
    while not session(origin):
        origin -= timedelta(days=1)
    new = (register_new and origin.isocalendar().week != advance(origin, 1).isocalendar().week
           and day < advance(origin, 1) and str(origin) > records[-1]["origin"])
    failures = []
    for target in sorted(pending | ({str(origin)} if new else set())):
        try:
            bar = fetch(target)
        except RuntimeError as exc:
            failures.append(str(exc))
            continue
        for r in records:
            for f in r["forecasts"]:
                if f["target"] == target and "actual" not in f:
                    f.update(actual=bar["close"], actual_source=bar["source"], observed=now.isoformat())
        if new and target == str(origin):
            records.append(register(origin, bar, now))
    save(records)
    if failures:
        raise RuntimeError("\n".join(failures))


def gold_card():
    records = json.loads(LEDGER.read_text(encoding="utf8"))
    latest = records[-1]
    pending = [f["target"] for r in records for f in r["forecasts"] if "actual" not in f]
    rows, history, annual = [], [], []
    anniversary = datetime.fromisoformat(records[0]["registered"]).date() + timedelta(days=365)
    for f in latest["forecasts"]:
        h = f["h"]
        pairs = [(p, r["bar"]["close"]) for r in records for p in r["forecasts"] if p["h"] == h and "actual" in p]
        history.append(f"<li>{h} 日 · {metrics(pairs)}</li>")
        annual.append(f"<li>{h} 日 · {metrics([(p,c) for p,c in pairs if p['target'] <= str(anniversary)])}</li>")
        label = "21 日（主要）" if h == 21 else f"{h} 日"
        rows.append(f"<tr><th>{label}</th><td>{f['target']}</td><td>{f['point']:.2f}</td><td>{f['low']:.2f}–{f['high']:.2f}</td></tr>")
    review = f"首年复评 {anniversary}，以截至该日到期的 21 日 MAE 相对持平改善为主。"
    if datetime.now(CN).date() >= anniversary:
        primary = [(p, r["bar"]["close"]) for r in records for p in r["forecasts"]
                   if p["h"] == 21 and p["target"] <= str(anniversary) and "actual" in p]
        if primary:
            delta = mean(abs(p["actual"] - c) - abs(p["actual"] - p["point"]) for p, c in primary)
            review += f"主期限每次平均比持平基准少误差 {delta:.2f} 元/克。" if delta > 0 else f"主期限未超越基准，平均多误差 {-delta:.2f} 元/克。"
        review += "<ul>" + "".join(annual) + "</ul>"
    return f"""<article class="study gold-forecast"><div class="card-meta">历史登记 · 已暂停新增 · {latest['origin']}</div>
<h3>上金所 Au99.99 收盘价</h3><p>{escape(latest['support'])} {escape(latest['counter'])}</p>
<div class="table-scroll"><table><caption>点预测与名义 80% 区间（元/克）</caption><thead><tr><th>交易日</th><th>预计目标日</th><th>点预测</th><th>区间</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p><strong>原登记待验证日期 {min(pending, default='待登记')}</strong></p><h4>历史成绩</h4><ul>{''.join(history)}</ul>
<details><summary>方法与年度评价</summary><p>Python 数值脚本根据当日高低价估算 Parkinson 波动率，以平方根时间缩放构造对数正态区间。单日波动外推可能高估或低估风险，80% 是模型假设下的覆盖率。登记前回看（2026-04-13 至 11-20，周五起算）中，21 日的 23 项预测 MAE 为 60.95 元/克，较持平改善 1.1%，区间仅命中 39%。</p><p>{review}</p><p>每周发行使相邻的 21 日和 63 日预测共享大部分未来行情，同期各期限的价格区间也可能相交。命中次数相关，不能当作独立重复验证。</p><a href="research/experiments/gold.json">完整登记与结算</a></details></article>"""


if __name__ == "__main__":
    update(datetime.now(CN))
