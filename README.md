# MarketCast · 股票与外汇预测辅助系统

一个**辅助决策**工具：把技术指标评分、机器学习方向预测、历史回测和风控建议整合成一份可读的分析报告，帮助你更系统地看待行情。

> ⚠️ 本系统输出仅为基于历史数据的统计分析，**不构成任何投资建议**。金融市场接近随机游走，任何模型都无法稳定预测价格。系统会如实展示模型在样本外是否真的优于「瞎猜」，请据此判断信号的参考价值。

## 功能

| 模块 | 说明 |
|---|---|
| 数据获取 | Yahoo Finance 在线行情（美股、A股、港股、外汇），本地 CSV（兼容中英文列名、GBK 编码），离线演示数据 |
| 技术指标 | MA、EMA、RSI、MACD、布林带、ATR、KDJ、ADX、OBV（纯 pandas 实现，无未来函数） |
| 技术面评分 | 7 个维度各自打分并加权合成 -100 ~ +100 的综合分，每项附中文解读 |
| 机器学习预测 | 30+ 个特征，逻辑回归 / 随机森林 / 梯度提升 / 集成模型，预测未来 N 根K线上涨概率 |
| 严格验证 | 时间顺序的滚动验证，训练集与测试集之间留出间隔防止信息泄露，并与朴素基准对比 |
| 综合结论 | 技术面与模型加权；模型没有预测力时自动降低其权重并给出提示 |
| 风控建议 | 基于 ATR 的止损止盈、按风险比例计算仓位（A股 100 股一手、外汇 1000 单位微型手、杠杆上限） |
| 历史回测 | 技术评分策略、机器学习策略（仅样本外），含交易成本，与买入持有对比 |
| 数据质量检查 | 自动检测前视偏差、停牌/缺失、缺少高低价等问题 |
| 交互界面 | 命令行（文本 / Markdown / JSON 报告、批量扫描）+ Streamlit 可视化面板 |

## 安装

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 命令行用法

```bash
# 单个品种完整分析
python -m marketcast analyze AAPL                 # 美股
python -m marketcast analyze 600519               # A股（自动识别为 600519.SS）
python -m marketcast analyze 000001               # 深市（000001.SZ）
python -m marketcast analyze 0700                 # 港股（0700.HK）
python -m marketcast analyze EURUSD               # 外汇（EURUSD=X），也可写 EUR/USD

# 常用参数
python -m marketcast analyze USDJPY --horizon 3 --model logistic
python -m marketcast analyze 600519 --start 2015-01-01 --capital 500000 --risk-pct 0.005
python -m marketcast analyze AAPL --format markdown -o reports/aapl.md
python -m marketcast analyze AAPL --format json

# 使用本地 CSV / 离线演示
python -m marketcast analyze 示例股票 --csv examples/sample_ohlcv.csv
python -m marketcast analyze DEMO --demo

# 批量扫描自选列表（按综合分排序）
python -m marketcast scan AAPL MSFT NVDA 600519 0700 EURUSD USDJPY GBPUSD
```

主要参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--horizon` | 5 | 预测未来多少根K线 |
| `--model` | ensemble | `ensemble` / `logistic` / `random_forest` / `gradient_boosting` |
| `--period` / `--start` / `--end` | 5y | 历史数据范围 |
| `--type` | auto | 强制指定 `stock` / `forex` |
| `--allow-short` / `--long-only` | 外汇允许、股票不允许 | 是否允许做空 |
| `--capital` `--risk-pct` `--atr-mult` `--rr` `--lot-size` | 100000 / 1% / 2 / 2 / 自动 | 风控参数 |
| `--no-cache` | | 默认会把当天下载的行情缓存在 `.marketcast_cache/` |

### 报告示例（节选）

```
【综合结论】看空   综合分 -31.6   置信度：中等
【操作参考】可考虑轻仓做空，严格设置止损
【未来5根K线约90%波动区间】1.10868 ~ 1.13082

一、技术面评分：-33.2（偏空）
  - 均线趋势     -1.00 ×0.25  价格位于 MA20 下方、MA60 下方，MA20 在 MA60 之下（空头排列）
  - ADX趋势强度  -1.00 ×0.15  ADX=35.8，趋势明显，空方占优
  ...
二、机器学习预测（未来5根K线）
  上涨概率：37.5%
  样本外验证：准确率 49.6% | AUC 0.507 | 朴素基准 46.7% | 测试样本 1025 | 预测力不足
三、风控建议
  方向：做空   止损：1.13202   止盈：1.09504   建议数量：81,000 单位
四、历史回测（含交易成本，不代表未来表现）
  ...
⚠ 提示
  - 模型样本外准确率 49.6%、AUC 0.507，未明显优于朴素基准（46.7%），机器学习信号权重已下调，仅供参考
```

## 可视化面板

```bash
streamlit run app.py
```

浏览器打开后在左侧选择数据源、代码和参数，点击「开始分析」。面板包含：

- 概览：收盘价、综合结论、技术分、上涨概率、置信度、风险提示
- 行情图表：K线 + 均线 + 布林带、成交量、RSI、MACD、历史技术评分（共用时间轴）
- 技术信号：各指标得分与解读
- 机器学习：样本外准确率 / AUC / 基准对比、各折表现、特征重要性
- 历史回测：净值曲线与绩效指标
- 风控建议：止损止盈与仓位
- 支持「红涨绿跌 / 绿涨红跌 / 红涨蓝跌（色盲友好）」配色切换，可下载 Markdown 报告

## CSV 格式

至少需要日期和收盘价列，推荐包含开高低收和成交量。列名支持：

| 字段 | 可识别的列名 |
|---|---|
| 日期 | `date` `datetime` `time` `日期` `时间` `交易日期` |
| 开盘 | `open` `开盘` `开盘价` |
| 最高 | `high` `最高` `最高价` |
| 最低 | `low` `最低` `最低价` |
| 收盘 | `close` `price` `adj close` `收盘` `收盘价` |
| 成交量 | `volume` `vol` `成交量`（外汇可省略） |

参考 `examples/sample_ohlcv.csv`。

## 作为 Python 库使用

```python
from marketcast import analyze, load_data, AnalysisConfig
from marketcast.report import render_text

df, symbol, asset_type = load_data("600519", period="10y")
result = analyze(df, symbol, asset_type, AnalysisConfig(horizon=10))
print(render_text(result))
print(result.ml_proba_up, result.combined_label, result.risk_plan)
```

## 项目结构

```
marketcast/
  data.py        数据获取、代码识别、标准化、数据质量检查
  indicators.py  技术指标
  signals.py     技术面评分与中文解读
  features.py    机器学习特征与预测目标
  models.py      模型、滚动验证、最新预测
  backtest.py    向量化回测与绩效指标
  risk.py        ATR 止损止盈与仓位计算
  analysis.py    分析总入口（整合以上模块）
  report.py      文本 / Markdown / JSON 报告
  cli.py         命令行
app.py           Streamlit 可视化面板
tests/           单元测试（全部离线运行）
examples/        示例数据
```

运行测试：

```bash
python -m pytest
```

## 设计原则与已知局限

**如何避免「看起来很准」的假象：**

- 所有指标与特征都只用当期及以前的数据，测试中会截断未来数据验证结果不变
- 预测目标是未来 N 根K线收益，滚动验证时训练集和测试集之间留出 N 根K线的间隔
- ML 回测只在样本外区间进行
- 准确率总是与「始终猜训练集中更常见的方向」的朴素基准对比
- **Yahoo 外汇日线存在前视偏差**：它的 close 实际是当天开盘附近的快照，而 high/low 覆盖全天。直接使用时「收盘在日内位置」与次日收益的相关系数约为 -0.7（真实市场应接近 0），会让模型虚假地达到 60%+ 准确率。系统会自动修正这类数据，并对任何来源的数据做同样的检查

**局限：**

- 回测按收盘价成交，未考虑滑点、涨跌停、A股 T+1、停牌、外汇隔夜利息（swap）等
- Yahoo 的 A股/港股数据可能有延迟或缺失；外汇最新一根K线是盘中实时价
- 技术评分的权重与阈值是经验设定，不同市场、不同品种的有效性差别很大
- 对大部分流动性好的品种，模型样本外表现接近 50%，这是市场有效性的正常体现

## 后续可扩展方向

- 接入 akshare / tushare 等国内数据源，加入基本面与资金流数据
- 新闻 / 公告情绪分析
- 多品种组合优化与相关性分析
- 定时扫描与消息推送（邮件、企业微信、Telegram）
- 分钟级数据与日内策略
