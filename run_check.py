import json, sys, shutil, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import config, data_fetcher, valuation_data, strategies

Path("data_cache").mkdir(exist_ok=True)
for seed in Path("seed").glob("*.csv"):
    target = Path("data_cache") / seed.name
    if not target.exists(): shutil.copy2(seed, target)
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
        if prices.attrs.get("stale_note") or not data_fetcher._cache_is_current(prices):
            raise ValueError("行情过期或使用过期缓存: " + date)
        enriched = valuation_data.attach_valuation(item, date)
        valuation = enriched.get("valuation")
        if valuation and (valuation.get("error") or valuation.get("warning")):
            valuation_errors.append(item["code"])
        if item.get("broad_strategy") == "pe_or_pb5_pe_exit" and (not enriched.get("pb_valuation_history") or enriched.get("pb_data_warning")):
            raise ValueError("PB 历史缺失或接口失败: " + str(enriched.get("pb_data_warning")))
        summary = strategies.analyze_asset(prices, enriched)
        results.append(summary)
        print(item["code"], "行情日期", date, "估值", json.dumps(enriched.get("valuation", {}), ensure_ascii=False), "缓存提示", prices.attrs.get("stale_note"))
    except Exception as exc:
        results.append({"symbol": item["code"], "status": "error", "error": str(exc)})
        print(item["code"], "失败", type(exc).__name__, str(exc))
Path("docs").mkdir(exist_ok=True)
versions = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path("data_cache").glob("valuation*.csv"))}
Path("docs/data-version.json").write_text(json.dumps(versions, indent=2), encoding="utf8")
Path("docs/index.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")
print("北京时间", datetime.now(timezone(timedelta(hours=8))).isoformat(), "结果数", len(results))
if valuation_errors or any(x.get("status") == "error" for x in results): sys.exit(1)

