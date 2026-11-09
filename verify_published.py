import json, time, urllib.request
from pathlib import Path

base = "https://tammyuuuu.github.io/MagicCycle-Actions-Test/"
expected = json.loads(Path("docs/index.json").read_text(encoding="utf8"))
for attempt in range(12):
    try:
        with urllib.request.urlopen(base + "index.json?run=" + str(time.time_ns()), timeout=15) as response:
            actual = json.load(response)
        with urllib.request.urlopen(base + "?run=" + str(time.time_ns()), timeout=15) as response:
            page = response.read().decode("utf8")
        if actual == expected and all(row["date"] in page for row in expected) and page.count('<article class="card">') == len(expected):
            print("线上页面和数据验证成功；行情日期:", sorted({r["date"] for r in actual}))
            break
    except Exception as exc:
        print("等待线上更新:", type(exc).__name__, str(exc))
    if attempt < 11: time.sleep(10)
else:
    raise SystemExit("发布后线上数据核对失败；请查看页面和部署日志")
