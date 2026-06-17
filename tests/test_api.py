"""测试 nufm.dfcfw.com 板块接口（备选数据源，尚未启用）"""

import json

import requests

url = (
    "https://nufm.dfcfw.com/EM_Finance2014NumericApplication/JS.aspx"
    "?type=CT&cmd=C._BKHY&sty=DCRRBK&st=(ChangePercent)&sr=-1"
    "&p=1&ps=8&token=7bc05d0d4c3c22ef9fca8c2a912d779c"
)

r = requests.get(
    url,
    timeout=10,
    headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    },
)

print("status:", r.status_code, "len:", len(r.text))
raw = r.content  # bytes
print("starts with:", repr(raw[:50]))
print("ends with:", repr(raw[-50:]))

text = raw.decode("utf-8-sig", errors="replace")
# 格式可能是: var xxx= 或直接 eval(
for line in text.split("\n")[:3]:
    print("line:", line[:120])

idx = text.find('["')
if idx >= 0:
    print("found data at byte", idx, ":", text[idx : idx + 200])
elif text.startswith("eval("):
    inner = text[5:-1]
    data = json.loads(inner)
    print("count:", len(data))
    for item in data[:5]:
        parts = item.split(",")
        print(f"  {parts[1]} {parts[2]} 涨跌:{parts[3]}% 代码:{parts[0]}")
else:
    print("raw sample:", repr(raw[:500]))
