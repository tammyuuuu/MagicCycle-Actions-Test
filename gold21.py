"""Register and settle frozen 5/21/63-session Au99.99 forecasts. No training at runtime."""
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
HORIZONS = ROOT / "horizons.json"
EXTRA_SHA256 = "555d476f0de65f2e87c077f63077a508cfe815b0bee2106b338dc1ed2569740f"
GRAPH = "https://www.sge.com.cn/graph/Dailyhq"
ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
MODEL_SHA256 = "9254b9e4a7248567ab055c8571a153697a5e8b6d9a55abcffdbcdb153cc7d54f"
FIRST = date(2026, 11, 27)
REVIEW = date(2027, 11, 21)
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
    if max(series) != str(day):
        raise ValueError("请求日期不是最新已公布日线")
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


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def register(origin, data, locked, kind):
    core, extra = read(MODEL), read(HORIZONS)
    if digest(core)!=MODEL_SHA256 or digest(extra)!=EXTRA_SHA256:
        raise ValueError("冻结参数校验失败")
    anchor=data["closes"][str(origin)]
    factors=features(data)
    targets={h:str(shift(origin,h)) for h in (5,21,63)}
    records=[]
    primary=forecast(anchor,factors,core)
    for h,target in targets.items():
        predictions=primary
        version=core["version"]
        if h!=21:
            version=extra["version"]
            predictions={}
            for name,model in extra["models"][str(h)].items():
                ret=model["intercept"]+sum(w*factors[k] for k,w in model["weights"].items())
                sigma=factors["vol"]*math.sqrt(h)
                lo,hi=model["interval"]
                predictions[name]=dict(point=anchor*math.exp(ret),low=anchor*math.exp(ret+lo*sigma),
                                       high=anchor*math.exp(ret+hi*sigma))
        for name,pred in predictions.items():
            records.append(dict(h=h,model=name,version=version,origin=str(origin),registered=locked.isoformat(),
                                anchor=anchor,target=target,**pred))
    return dict(origin=str(origin),target=targets[21],registered=locked.isoformat(),kind=kind,
                cutoff=f"{origin}T15:30:00+08:00",anchor=anchor,inputs=data,forecasts=primary,
                version=core["version"],model_sha256=MODEL_SHA256,extra_sha256=EXTRA_SHA256,records=records)


def direction(change):
    return "上涨" if change>0 else "下跌" if change<0 else "持平"


def outcome(row, observation):
    actual=observation["actual"]
    predicted_direction=direction(row["point"]-row["anchor"])
    actual_direction=direction(actual-row["anchor"])
    return dict(**observation,error=row["point"]-actual,absolute_error=abs(row["point"]-actual),
                predicted_direction=predicted_direction,actual_direction=actual_direction,
                direction_correct=predicted_direction==actual_direction,covered=row["low"]<=actual<=row["high"])


def records(batch, settlements):
    if "records" in batch:
        return batch["records"]
    # Historical 21-day batches retain their original on-disk representation.
    result=[]
    for name,pred in batch["forecasts"].items():
        row={k:batch[k] for k in ("origin","registered","anchor","target","version")}
        row.update(h=21,model=name,**pred)
        if batch["origin"] in settlements:
            row["verification"]=outcome(row,settlements[batch["origin"]])
        result.append(row)
    return result


def settle(state, now, clock, quote):
    cache={}
    for batch in state["batches"]:
        for row in records(batch,state["settlements"]):
            target=row["target"]
            if "verification" in row or now<datetime.combine(date.fromisoformat(target),time(15,30),CN):
                continue
            try:
                if target not in cache:
                    bar=quote(target)
                    cache[target]=dict(actual=bar["close"],target=target,source=bar["source"],observed=clock().isoformat())
                observation=cache[target]
                row["verification"]=outcome(row,observation)
                if row["h"]==21:
                    state["settlements"].setdefault(batch["origin"],observation)
                state["gaps"].pop("结算 "+target,None)
            except (ValueError,RuntimeError,requests.RequestException,KeyError) as exc:
                state["gaps"]["结算 "+target]=str(exc)[:320]


def update(state, now, clock, load=inputs, quote=fetch):
    day=now.date()
    settle(state,now,clock,quote)
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
                    locked=clock()
                    if locked.date()!=day or locked.time()>=time(20):
                        raise ValueError("取数完成时已过登记窗口")
                    state["batches"].append(register(friday,data,locked,"周五登记"))
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


def table(headers, rows):
    head="".join(f"<th scope='col'>{escape(h)}</th>" for h in headers)
    body="".join("<tr>"+"".join(f"<td>{escape(str(c))}</td>" for c in row)+"</tr>" for row in rows)
    return f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def price(value):
    return f"{value:.2f}"


def performance(rows):
    done=[r for r in rows if "verification" in r]
    if not done:
        return [0,"—","—","—","—"]
    mae=mean(r["verification"]["absolute_error"] for r in done)
    base=mean(abs(r["anchor"]-r["verification"]["actual"]) for r in done)
    return [len(done),price(mae),f"{1-mae/base:.1%}" if base else "—",
            f"{mean(r['verification']['direction_correct'] for r in done):.1%}",
            f"{mean(r['verification']['covered'] for r in done):.1%}"]


def card(today=None):
    state=read(LEDGER)
    today=today or datetime.now(CN).date()
    batches=sorted(state["batches"],key=lambda b:b["registered"])
    all_rows=[r for b in batches for r in records(b,state["settlements"])]
    hist=read(HORIZONS)["backtest"]
    sections=[]
    for h in (5,21,63):
        rows=[r for r in all_rows if r["h"]==h]
        latest=rows[-1]["registered"] if rows else None
        points=[[r["model"],price(r["point"]),f'{price(r["low"])}–{price(r["high"])}',r["target"]]
                for r in rows if r["registered"]==latest]
        next_due=min((r["target"] for r in rows if "verification" not in r),default="暂无")
        sections.append(f'<section><h4>{h} 个交易日'+("（主要评价）" if h==21 else "")+f'</h4><p>下次验证 {next_due}</p>')
        if latest:
            sections.append(f"<p>登记 {escape(latest[:19].replace('T',' '))}，当时金价 {price(rows[-1]['anchor'])} 元/克。</p>")
        sections.append(table(["本期模型","预测价","80% 区间","预计验证日"],points) if points else "<p>等待首次登记</p>")
        stats=[]; historical=[]; annual=[]; independent=[]
        for name,ref in hist[str(h)].items():
            selected=[r for r in rows if r["model"]==name]
            stats.append([name,*performance(selected)])
            historical.append([name,int(ref["n"]),price(ref["mae"]),f'{ref["gain"]:.2f}%',f'{ref["direction"]:.1f}%',f'{ref["coverage"]:.1f}%'])
            if today>=REVIEW:
                cohort=[r for r in selected if r["registered"][:10]<str(REVIEW)]
                annual.append([name,*performance(cohort)])
                sample=[]
                for r in cohort:
                    if "verification" in r and (not sample or r["origin"]>=sample[-1]["target"]):
                        sample.append(r)
                independent.append([name,*performance(sample)])
        labels=["模型","已验证","MAE","较持平改善","方向正确率","区间命中率"]
        sections.append("<h5>前瞻成绩</h5>"+table(labels,stats)+"<details><summary>历史独立测试成绩</summary>"+table(labels,historical)+"</details>")
        if annual:
            sections.append("<h5>首年综合评价</h5>"+table(labels,annual)+"<p>不重叠窗口复核</p>"+table(labels,independent))
        sections.append("</section>")
    history=[]
    timeline=list(all_rows)
    for old in read(Path("research_monitor/experiments/gold.json")):
        for f in old["forecasts"]:
            row=dict(f,model=old["model"],registered=old["registered"],origin=old["origin"],anchor=old["bar"]["close"])
            if "actual" in f:
                row["verification"]=outcome(row,dict(actual=f["actual"],observed=f["observed"]))
            timeline.append(row)
    for r in sorted(timeline,key=lambda r:(r["registered"],r["h"])):
        check=r.get("verification")
        status=(("正确" if check["direction_correct"] else "错误")+f'（预测{check["predicted_direction"]}，实际{check["actual_direction"]}）'
                if check else "待验证")
        history.append([r["registered"][:19].replace("T"," "),r["origin"],price(r["anchor"]),r["h"],r["model"],
                        price(r["point"]),f'{price(r["low"])}–{price(r["high"])}',r["target"],
                        check["observed"][:19].replace("T"," ") if check else "—",
                        price(check["actual"]) if check else "—",price(check["error"]) if check else "—",status])
    gaps="；".join(escape(f"{k} {v}") for k,v in sorted(state["gaps"].items())[-6:]) or "暂无已知缺口"
    return ('<article class="study gold-forecast" id="gold21"><h3>Au99.99 金价前瞻实验</h3>'
            '<p>单位为元/克，时间为北京时间。每周五收盘后登记。</p>'+''.join(sections)+
            '<h4>逐批预测与检验</h4><p>按登记时间从早到晚排列，误差为预测价减实际收盘价。</p>'+
            table(["登记时间","行情日","当时金价","交易日数","模型","预测价","80% 区间","预计验证日",
                   "实际检验时间","实际价","误差","方向判断"],history)+
            f'<p>数据缺口 · {gaps}</p><p>首年复评 {REVIEW}。21 日、63 日相邻周窗口共享行情，另按不重叠窗口复核。</p>'
            '<a href="research/gold21/ledger.json">完整登记与检验</a> · <a href="research/gold21/model.json">21 日冻结参数</a> · '
            '<a href="research/gold21/horizons.json">5、63 日冻结参数与历史成绩</a> · <a href="research/experiments/gold.json">早期区间回归实验记录</a></article>')


def launch(state,clock):
    # A one-time live launch, independent of the regular Friday window. Never accept
    # an origin or timestamp from the caller; require the latest confirmed close.
    if any("records" in b for b in state["batches"]):
        raise ValueError("三期限首批已经登记")
    now=clock()
    day=now.date()
    while not trading(day) or (day==now.date() and now.time()<time(15,30)):
        day-=timedelta(days=1)
    if any(b["origin"]==str(day) for b in state["batches"]):
        raise ValueError("行情日已有历史登记，禁止追补其他期限")
    data=inputs(day)
    locked=clock()
    if locked.date()!=now.date() or (trading(locked.date()) and day!=locked.date()):
        raise ValueError("登记时点已改变，需重新核实行情")
    state["batches"].append(register(day,data,locked,"启动日实时登记"))


def persist(previous,state):
    # Only append batches, first verifications and first settlements.
    batches=state["batches"]
    if len(batches)<len(previous["batches"]):
        raise ValueError("历史批次不可删除")
    for before,after in zip(previous["batches"],batches):
        if {k:v for k,v in before.items() if k!="records"}!={k:v for k,v in after.items() if k!="records"}:
            raise ValueError("历史批次不可修改")
        for old,new in zip(before.get("records",[]),after.get("records",[]),strict=True):
            allowed=() if "verification" in old else ("verification",)
            if old!={k:v for k,v in new.items() if k not in allowed}:
                raise ValueError("已登记的预测或检验结果不可修改")
    if any(state["settlements"].get(k)!=v for k,v in previous["settlements"].items()):
        raise ValueError("历史结算不可修改")
    if read(LEDGER)!=previous:
        raise RuntimeError("登记簿已更新，请重试")
    tmp=LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    tmp.replace(LEDGER)


if __name__=="__main__":
    import copy
    previous=read(LEDGER)
    state=copy.deepcopy(previous)
    clock=lambda: datetime.now(CN)
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--launch",action="store_true")
    if parser.parse_args().launch:
        launch(state,clock)
    update(state,clock(),clock)
    try:
        update_legacy(clock(), register_new=False)
        state["gaps"].pop("旧实验结算",None)
    except RuntimeError as exc:
        state["gaps"]["旧实验结算"]=str(exc)[:320]
    persist(previous,state)
