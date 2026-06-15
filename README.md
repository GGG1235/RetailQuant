# RetailQuant



- ✅ 缠论近似（MA5>MA20 站上买入）
- ✅ Buy & Hold 近似（低位吸筹）
- ✅ 止损/止盈信号
- ✅ Flask + 看板
- ✅ 加仓/减仓/删除
- ✅ 资金曲线快照

## 启动

```bash
cd /Users/ggg1235/Downloads/rQuant
pip install -r requirements.txt
python3 -m waitress --host=0.0.0.0 --port=5060 app:app
# 浏览器访问 http://localhost:5060
```

## 文件

```
rQuant/
├── app.py              # Flask 主程序
├── data.py             # Sina 拉数 + JSON 缓存
├── strategy.py         # 缠论近似 + BuyHold
├── portfolio.py        # 持仓管理（JSON 存储）
├── requirements.txt    # flask / waitress / pandas / requests
├── templates/
│   ├── index.html      # 看板
│   └── error.html
├── static/
│   └── style.css
└── data/               # K 线 JSON 缓存（自动生成）
```

## 注意

- 第一次访问会触发 Sina 拉数，沙箱环境可能慢
- 数据每 5 天自动刷新（应付周末/节假日）
- 持仓在 `data/portfolio.json`，删除 = 清空
