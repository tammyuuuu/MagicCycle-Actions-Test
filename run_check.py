import json, sys, shutil, hashlib
from datetime import datetime, timezone, timedelta
from close_validation import validate_bar
from pathlib import Path
import config, data_fetcher, valuation_data, strategies

Path("data_cache").mkdir(exist_ok=True)
for seed in Path("seed").glob("*.csv"):
    target = Path("data_cache") / seed.name
    if not target.exists(): shutil.copy2(seed, target)
expected_date = data_fetcher._expected_latest_trade_date().isoformat()
print("最新已完成交易日:", expected_date)
results = []
valuation_errors = []
try:
    import akshare.stock_feature.stock_a_pe_and_pb
except Exception as exc:
    print("估值依赖检查:", repr(exc))
for item in config.TARGET_ETFS:
    try:
        prices = data_fetcher.fetch_etf_daily(item["code"], start="20100101", end="20500101")
        date = prices.index[-1].date().isoformat()
        valid, why = validate_bar(prices, prices.index[-1].date())
        if not valid:
            raise ValueError("行情日期或价格无效: " + why)
        if prices.attrs.get("update_state") == "error":
            raise ConnectionError("行情接口或校验失败，保留原页面: " + date)
        enriched = valuation_data.attach_valuation(item, date)
        valuation = enriched.get("valuation")
        if valuation and (valuation.get("error") or valuation.get("warning")):
            valuation_errors.append(item["code"])
        if item.get("broad_strategy") == "pe_or_pb5_pe_exit" and (not enriched.get("pb_valuation_history") or enriched.get("pb_data_warning")):
            raise ValueError("PB 历史缺失或接口失败: " + str(enriched.get("pb_data_warning")))
        summary = strategies.analyze_asset(prices, enriched)
        if summary.get("date") != date or float(summary["metrics"]["price"]) != float(prices.iloc[-1]["close"]):
            raise ValueError("提醒数据的日期或价格与行情不一致")
        summary["market_update"] = ("新数据尚未就绪，沿用历史数据" if prices.attrs.get("update_state") == "not_ready" else "历史交易日数据" if date != datetime.now(timezone(timedelta(hours=8))).date().isoformat() else "本交易日数据")
        results.append(summary)
        print(item["code"], "行情日期", date, "估值", json.dumps(enriched.get("valuation", {}), ensure_ascii=False), "缓存提示", prices.attrs.get("stale_note"))
    except Exception as exc:
        results.append({"symbol": item["code"], "status": "error", "error": str(exc)})
        print(item["code"], "失败", type(exc).__name__, str(exc))
Path("docs").mkdir(exist_ok=True)
versions = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path("data_cache").glob("valuation*.csv"))}
Path("docs/data-version.json").write_text(json.dumps(versions, indent=2), encoding="utf8")
Path("docs/index.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")
print("数据验证状态:", "失败" if valuation_errors or any(x.get("status") == "error" for x in results) else "成功", "目标行情日期:", expected_date)
print("北京时间", datetime.now(timezone(timedelta(hours=8))).isoformat(), "结果数", len(results))
if valuation_errors or any(x.get("status") == "error" for x in results): sys.exit(1)

