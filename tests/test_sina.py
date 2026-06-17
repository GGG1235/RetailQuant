"""测试 Sina ETF 板块接口"""

import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app import app  # noqa: E402  (must run after stdout reconfigure)

client = app.test_client()

print("=" * 50)
print("测试 /api/boards?type=sector")
r = client.get("/api/boards?type=sector")
d = json.loads(r.data)
print(f"状态: {r.status_code}, 数量: {d['count']}")
for x in d["boards"][:8]:
    sign = "+" if x["change_pct"] >= 0 else ""
    print(f"  {x['name']:　<6s} {sign}{x['change_pct']:.2f}%")

print()
print("=" * 50)
print("测试 /api/boards?type=concept")
r = client.get("/api/boards?type=concept")
d = json.loads(r.data)
print(f"状态: {r.status_code}, 数量: {d['count']}")
for x in d["boards"][:8]:
    sign = "+" if x["change_pct"] >= 0 else ""
    print(f"  {x['name']:　<6s} {sign}{x['change_pct']:.2f}%")

print()
print("=" * 50)
print("测试 /api/board/sh512480/stocks")
r = client.get("/api/board/sh512480/stocks")
d = json.loads(r.data)
print(f"状态: {r.status_code}, 数量: {d['count']}")
for s in d["stocks"]:
    print(f"  {s['code']} {s['name']} {s['change_pct']:+.2f}%")
