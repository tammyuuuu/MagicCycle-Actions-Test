"""Register and settle frozen 21-session Au99.99 forecasts. No training at runtime."""
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, time, timedelta
from html import escape
from pathlib import Path
from statistics import mean, stdev

import requests

from gold_forecast import BREAKS, CN, fetch, update as update_legacy

ROOT = Path("research_monitor/gold21")
LEDGER = ROOT / "ledger.json"
MODEL = ROOT / "model.json"
NAMES = ("宏观", "组合收缩", "持平")
GRAPH = "https://www.sge.com.cn/graph/Dailyhq"
ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
MODEL_SHA256 = "9254b9e4a7248567ab055c8571a153697a5e8b6d9a55abcffdbcdb153cc7d54f"
FIRST = date(2026, 11, 27)
REVIEW = date(2027, 11, 27)
CLOSED = json.loads(Path("ashare_calendar.json").read_text(encoding="utf8"))["closed_ranges"] + BREAKS


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def trading(day):
    if day.year > 2027:
        import exchange_calendars
        return exchange_calendars.get_calendar("XSHG").is_session(str(day))
    return day.weekday() < 5 and not any(lo <= str(day) <= hi for lo, hi in CLOSED)


def shift(day, n):
    step = 1 if n > 0 else -1
    for _ in range(abs(n)):
        day += timedelta(days=step)
        while not trading(day):
            day += timedelta(days=step)
    return day


def inputs(day):
    bar = fetch(str(day))
    response = requests.post(GRAPH, data={"instid":"Au99.99"}, headers={"User-Agent":"Mozilla/5.0"}, timeout=20)
    response.raise_for_status()
    series = {}
    for stamp, _, close, _, _ in response.json()["time"]:
        if not math.isfinite(float(close)) or float(close) <= 0 or stamp in series:
            raise ValueError("日线无效或重复")
        series[stamp] = float(close)
    if series.get(str(day)) != bar["close"]:
        raise ValueError("周五公告与日线尚未同步")
    dates = [day]
    while len(dates) < 64:
        dates.append(shift(dates[-1], -1))
    closes = {}
    repairs = {}
    for stamp in reversed(dates):
        key = str(stamp)
        if key not in series:
            recovered = fetch(key)
            series[key] = recovered["close"]
            repairs[key] = recovered["source"]
        closes[key] = series[key]
    if set(key for key in series if min(closes) <= key <= str(day)) != set(closes):
        raise ValueError("上金所日线与交易日历不一致")
    # The audited study admitted a month-end vintage only after two calendar days.
    eligible = day - timedelta(days=2)
    vintage = (eligible + timedelta(days=1)).replace(day=1) - timedelta(days=1)
    macro = {}
    for name in ("DFII10", "DEXCHUS"):
        r = requests.get(ALFRED, params=dict(id=name, vintage_date=str(vintage),
                         cosd=str(vintage-timedelta(days=120)), coed=str(vintage)), timeout=25)
        r.raise_for_status()
        field = f"{name}_{vintage:%Y%m%d}"
        rows = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        if field not in (rows.fieldnames or []):
            raise ValueError(f"{name} 缺少指定历史版本 {vintage}")
        values = {}
        for row in rows:
            stamp = row["observation_date"]
            if row[field] in ("", "."):
                continue
            val = float(row[field])
            if stamp > str(vintage) or stamp in values or not math.isfinite(val) or (name=="DEXCHUS" and val<=0):
                raise ValueError(f"{name} 观测无效")
            values[stamp] = val
        recent = sorted(values)[-21:]
        if len(recent) != 21 or (vintage-date.fromisoformat(recent[-1])).days > 14:
            raise ValueError(f"{name} 观测不足或过旧")
        macro[name] = dict(source=r.url, values={stamp:values[stamp] for stamp in recent})
    return dict(closes=closes, bulletin=bar["source"], graph=GRAPH, repairs=repairs,
                vintage=str(vintage), macro=macro)


def features(data):
    prices = [math.log(data["closes"][d]) for d in sorted(data["closes"])]
    vals = {f"r{h}":prices[-1]-prices[-1-h] for h in (1,5,21,63)}
    vals["dev"] = mean(prices[-21:])-prices[-1]
    vals["vol"] = stdev(b-a for a,b in zip(prices[-22:-1],prices[-21:]))
    for name, snapshot in data["macro"].items():
        series = snapshot["values"]
        first,last = series[min(series)],series[max(series)]
        vals[name] = last-first if name=="DFII10" else math.log(last/first)
    return vals


def forecast(anchor, factors, model):
    branches = {}
    for name,b in model["branches"].items():
        branches[name] = b["intercept"] + sum(coef*(factors[k]-b["mean"][k])/b["sd"][k] for k,coef in b["coef"].items())
    returns = {"持平":0, "宏观":branches["macro"], "组合收缩":model["blend_weight"]*(branches["macro_blend"]+branches["price_blend"])}
    result = {}
    for name in NAMES:
        ret = returns[name]
        low,high = model["intervals"][name]
        sigma = factors["vol"]*math.sqrt(21)
        result[name] = dict(point=anchor*math.exp(ret),low=anchor*math.exp(ret+low*sigma),high=anchor*math.exp(ret+high*sigma))
    return result


def update(state, now, clock, load=inputs, quote=fetch):
    day = now.date()
    for batch in state["batches"]:
        target = batch["target"]
        if batch["origin"] in state["settlements"] or now < datetime.combine(date.fromisoformat(target),time(15,30),CN):
            continue
        try:
            bar = quote(target)
            state["settlements"][batch["origin"]] = dict(actual=bar["close"],target=target,source=bar["source"],observed=clock().isoformat())
            state["gaps"].pop("结算 "+target,None)
        except (ValueError,RuntimeError,requests.RequestException,KeyError) as exc:
            state["gaps"]["结算 "+target] = str(exc)[:320]
    issued = {b["origin"] for b in state["batches"]}
    friday = FIRST
    while friday <= day:
        key = str(friday)
        if key not in issued and trading(friday):
            if friday < day or now.time() >= time(20):
                state["gaps"].setdefault(key,"未在周五登记窗口取得完整数据，留空")
            elif now.time() >= time(15,30):
                try:
                    data = load(friday)
                    frozen = read(MODEL)
                    digest = hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()
                    if digest != MODEL_SHA256:
                        raise ValueError("冻结模型校验失败")
                    anchor = data["closes"][key]
                    predictions = forecast(anchor,features(data),frozen)
                    locked = clock()
                    if locked.date()!=day or locked.time()>=time(20):
                        raise ValueError("取数完成时已过登记窗口")
                    state["batches"].append(dict(origin=key,target=str(shift(friday,21)),
                        cutoff=f"{key}T15:30:00+08:00",registered=locked.isoformat(),
                        version=frozen["version"],model_sha256=digest,
                        anchor=anchor,inputs=data,forecasts=predictions))
                    state["gaps"].pop(key,None)
                except (ValueError,RuntimeError,requests.RequestException,KeyError) as exc:
                    state["gaps"][key]=str(exc)[:320]
        friday += timedelta(days=7)


def scores(batches, settlements):
    result = {}
    pairs = [(b,settlements[b["origin"]]["actual"]) for b in batches if b["origin"] in settlements]
    if pairs:
        flat = mean(abs(b["anchor"]-a) for b,a in pairs)
        sign = lambda x:(x>0)-(x<0)
        for name in NAMES:
            err = mean(abs(b["forecasts"][name]["point"]-a) for b,a in pairs)
            result[name] = dict(n=len(pairs),mae=err,gain=1-err/flat if flat else None,
                direction=mean(sign(b["forecasts"][name]["point"]-b["anchor"])==sign(a-b["anchor"]) for b,a in pairs),
                coverage=mean(b["forecasts"][name]["low"]<=a<=b["forecasts"][name]["high"] for b,a in pairs))
    return result


def card(today=None):
    state=read(LEDGER)
    batches=state["batches"]
    settled=state["settlements"]
    today=today or datetime.now(CN).date()
    next_day=max(today,FIRST)
    issued={b["origin"] for b in batches}
    while next_day.weekday()!=4 or not trading(next_day) or str(next_day) in issued or (str(next_day) in state["gaps"] and next_day<today):
        next_day+=timedelta(days=1)
    validation=min((b["target"] for b in batches if b["origin"] not in settled),default=None)
    latest=batches[-1] if batches else None
    head=(f'最近登记 {latest["registered"][:16].replace("T"," ")}（北京时间），起点 {latest["anchor"]:.2f} 元/克。'
          if latest else f"等待首批登记 · {next_day} 周五收盘后")
    def table(rows):
        return '<div class="table-scroll"><table>'+rows+'</table></div>'
    def score_table(items):
        rows="<tr><th>模型</th><th>到期</th><th>MAE</th><th>较持平改善</th><th>方向正确</th><th>区间命中</th></tr>"
        for name in NAMES:
            s=items.get(name)
            cells=[0,"—","—","—","—"] if not s else [s["n"],f'{s["mae"]:.2f}',f'{s["gain"]:.1%}' if s["gain"] is not None else "—",f'{s["direction"]:.1%}',f'{s["coverage"]:.1%}']
            rows+=f"<tr><th>{name}</th>"+''.join(f"<td>{v}</td>" for v in cells)+"</tr>"
        return table(rows)
    points="<tr><th>模型</th><th>点预测</th><th>80% 区间（元/克）</th></tr>"
    for name in NAMES:
        f=latest["forecasts"][name] if latest else None
        points+=f"<tr><th>{name}</th><td>"+(f'{f["point"]:.2f}</td><td>{f["low"]:.2f}–{f["high"]:.2f}' if f else "待登记</td><td>—")+"</td></tr>"
    gaps="；".join(escape(f"{k} {v}") for k,v in sorted(state["gaps"].items())[-4:]) or "暂无已知缺口"
    review="2027-11-27 复评，纳入首年登记批次，未到期批次继续结算。"
    if today>=REVIEW:
        cohort=[b for b in batches if b["origin"]<str(REVIEW)]
        stats=scores(cohort,settled)
        review+=f" 首年登记 {len(cohort)} 批，已结算 {sum(b['origin'] in settled for b in cohort)} 批。"+score_table(stats)
        independent=[]
        for batch in cohort:
            if batch["origin"] in settled and (not independent or batch["origin"]>=independent[-1]["target"]):
                independent.append(batch)
        if independent:
            review+="按起点顺序抽取互不重叠窗口的复核结果："+score_table(scores(independent,settled))
        for name in NAMES[:2]:
            if name in stats and stats[name]["gain"] is not None:
                review+=f'{name}的首年到期 MAE 较基准改善 {stats[name]["gain"]:.1%}。'
    return f"""<article class="study gold-forecast" id="gold21"><h3>Au99.99 · 21 日金价前瞻实验</h3><p>{head}</p>
{table(points)}<p><strong>{'下次验证 '+validation if validation else '首批预计验证 '+str(shift(next_day,21))+'（登记后锁定）'}</strong></p>
<h4>前瞻成绩</h4>{score_table(scores(batches,settled))}<p>数据缺口 · {gaps}</p>
<details><summary>历史测试与首年评价</summary><p>历史独立测试采用周三起点，共 186 项。宏观、收缩组合、持平的 MAE 依次为 29.26、29.61、30.24 元/克，80% 区间命中率依次为 72.0%、70.4%、71.0%。上表从周五前瞻登记起单独计分。</p><p>{review}</p><p>每周五登记。相邻窗口通常共享约 16 个交易日，重复命中可能来自同一次行情。方向按涨、跌、平分别核对。</p>
<a href="research/gold21/model.json">冻结系数与区间分位数</a> · <a href="research/gold21/ledger.json">逐批输入、预测及结算</a> · <a href="research/experiments/gold.json">此前实验原始登记</a></details></article>"""


if __name__=="__main__":
    state=read(LEDGER)
    clock=lambda: datetime.now(CN)
    update(state,clock(),clock)
    try:
        update_legacy(clock(), register_new=False)
        state["gaps"].pop("旧实验结算",None)
    except RuntimeError as exc:
        state["gaps"]["旧实验结算"]=str(exc)[:320]
    tmp=LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    tmp.replace(LEDGER)
