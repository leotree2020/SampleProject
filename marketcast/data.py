"""行情数据获取与标准化。

支持三种来源：
- Yahoo Finance（通过 yfinance，覆盖美股、A股、港股、外汇等）
- 本地 CSV 文件（兼容常见英文 / 中文列名）
- 合成数据（离线演示与测试用）

所有来源最终都会被标准化为：以 DatetimeIndex 为索引、
包含 open / high / low / close / volume 五列的 DataFrame。
"""

from __future__ import annotations

import datetime as _dt
import re
import zlib
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]

STOCK = "stock"
FOREX = "forex"

_COLUMN_ALIASES = {
    "date": "date",
    "datetime": "date",
    "time": "date",
    "timestamp": "date",
    "日期": "date",
    "时间": "date",
    "交易日期": "date",
    "open": "open",
    "开盘": "open",
    "开盘价": "open",
    "high": "high",
    "最高": "high",
    "最高价": "high",
    "low": "low",
    "最低": "low",
    "最低价": "low",
    "close": "close",
    "收盘": "close",
    "收盘价": "close",
    "price": "close",
    "adj close": "adj_close",
    "adj_close": "adj_close",
    "volume": "volume",
    "vol": "volume",
    "成交量": "volume",
}

_FOREX_CODES = {
    "USD", "EUR", "JPY", "GBP", "AUD", "NZD", "CAD", "CHF", "CNY", "CNH",
    "HKD", "SGD", "SEK", "NOK", "DKK", "MXN", "ZAR", "TRY", "KRW", "INR",
    "THB", "PLN", "XAU", "XAG",
}

MIN_BARS = 150


class DataError(RuntimeError):
    """数据获取或校验失败。"""


def normalize_symbol(symbol: str, asset_type: str = "auto") -> Tuple[str, str]:
    """把用户输入的代码转换成 Yahoo Finance 代码，并推断资产类型。

    示例::

        normalize_symbol("EURUSD")   -> ("EURUSD=X", "forex")
        normalize_symbol("EUR/USD")  -> ("EURUSD=X", "forex")
        normalize_symbol("600519")   -> ("600519.SS", "stock")  # 沪市
        normalize_symbol("000001")   -> ("000001.SZ", "stock")  # 深市
        normalize_symbol("700")      -> ("0700.HK", "stock")    # 港股
        normalize_symbol("AAPL")     -> ("AAPL", "stock")
    """
    s = symbol.strip().upper().replace(" ", "")
    if not s:
        raise ValueError("代码不能为空")

    if s.endswith("=X"):
        return s, FOREX

    pair = re.fullmatch(r"([A-Z]{3})[/\-_]?([A-Z]{3})", s)
    if pair and pair.group(1) in _FOREX_CODES and pair.group(2) in _FOREX_CODES:
        return f"{pair.group(1)}{pair.group(2)}=X", FOREX

    if asset_type == FOREX:
        return f"{s}=X", FOREX

    if re.fullmatch(r"\d{6}", s):
        if s[0] in "569":
            return f"{s}.SS", STOCK
        if s[0] in "0123":
            return f"{s}.SZ", STOCK
        return s, STOCK

    if re.fullmatch(r"\d{1,5}", s):
        return f"{int(s):04d}.HK", STOCK

    return s, STOCK


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    """把任意来源的行情表整理为标准 OHLCV 格式。"""
    if df is None or df.empty:
        raise DataError("行情数据为空")

    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    out.columns = [_COLUMN_ALIASES.get(str(c).strip().lower(), str(c).strip().lower()) for c in out.columns]

    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"])
        out = out.set_index("date")
    if not isinstance(out.index, pd.DatetimeIndex):
        try:
            out.index = pd.to_datetime(out.index)
        except (TypeError, ValueError) as exc:
            raise DataError("无法识别日期列，请提供 date / 日期 列") from exc
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index.name = "date"

    if "close" not in out.columns and "adj_close" in out.columns:
        out["close"] = out["adj_close"]
    if "close" not in out.columns:
        raise DataError("缺少收盘价列（close / 收盘）")
    for col in ("open", "high", "low"):
        if col not in out.columns:
            out[col] = out["close"]
    if "volume" not in out.columns:
        out["volume"] = 0.0

    out = out[OHLCV].apply(pd.to_numeric, errors="coerce")
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out.dropna(subset=["close"])
    out["volume"] = out["volume"].fillna(0.0)
    out[["open", "high", "low"]] = out[["open", "high", "low"]].apply(lambda c: c.fillna(out["close"]))
    # 确保 high/low 包住 open/close，修正个别脏数据
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    out = out[out["close"] > 0]
    if out.empty:
        raise DataError("清洗后没有有效数据")
    return out


def load_csv(path: str | Path) -> pd.DataFrame:
    """读取本地 CSV，自动尝试 utf-8 / utf-8-sig / gbk 编码。"""
    path = Path(path)
    if not path.exists():
        raise DataError(f"文件不存在: {path}")
    last_err: Optional[Exception] = None
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return standardize(pd.read_csv(path, encoding=enc))
        except UnicodeDecodeError as exc:
            last_err = exc
    raise DataError(f"无法解码文件 {path}: {last_err}")


def fetch_yahoo(
    yahoo_symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: str = "5y",
    interval: str = "1d",
    cache_dir: Optional[str | Path] = None,
) -> pd.DataFrame:
    """从 Yahoo Finance 下载行情（自动复权）。

    ``cache_dir`` 不为空时，会按「代码 + 参数 + 当天日期」缓存为 CSV，
    当天重复调用直接读缓存，避免触发限流。
    """
    cache_file: Optional[Path] = None
    if cache_dir:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", yahoo_symbol)
        span = f"{start or period}_{end or 'now'}"
        cache_file = Path(cache_dir) / f"{safe}_{interval}_{span}_{_dt.date.today():%Y%m%d}.csv"
        if cache_file.exists():
            return load_csv(cache_file)

    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - 依赖缺失时提示
        raise DataError("未安装 yfinance，请先 pip install yfinance") from exc

    ticker = yf.Ticker(yahoo_symbol)
    try:
        if start:
            raw = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
        else:
            raw = ticker.history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:  # yfinance 会抛出多种网络异常
        raise DataError(f"下载 {yahoo_symbol} 失败: {exc}") from exc

    if raw is None or raw.empty:
        raise DataError(f"没有获取到 {yahoo_symbol} 的数据，请检查代码是否正确或稍后重试")

    df = standardize(raw)
    if yahoo_symbol.endswith("=X"):
        df = fix_yahoo_fx_bars(df)
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_file)
    return df


def fix_yahoo_fx_bars(df: pd.DataFrame) -> pd.DataFrame:
    """修正 Yahoo 外汇日线的前视偏差。

    Yahoo 外汇日线的 close 实际上是当天开盘附近的快照（close≈open），
    而 high/low 却覆盖了全天。直接使用会让「收盘在日内位置」等特征偷看到
    收盘之后的价格（实测与次日收益相关系数约 -0.7，真实市场应接近 0）。

    修正方法：第 t 根K线的 high/low 改用第 t-1 天（在 t 的快照时刻已完整结束）
    的 high/low，并与前后两个收盘价合并；open 用前一收盘价。
    这样每根K线只包含收盘时刻之前已知的信息。
    """
    if len(df) < 3:
        return df
    hist = df.iloc[:-1]  # 最新一根通常是盘中实时价，不参与判断
    rng = (hist["high"] - hist["low"]).replace(0, np.nan)
    close_is_open = ((hist["close"] - hist["open"]).abs() / rng).median()
    if not (close_is_open < 0.05):  # 数据格式已改变则不处理
        return df
    out = df.copy()
    c, prev_c = out["close"], out["close"].shift(1)
    out["open"] = prev_c
    out["high"] = pd.concat([df["high"].shift(1), prev_c, c], axis=1).max(axis=1)
    out["low"] = pd.concat([df["low"].shift(1), prev_c, c], axis=1).min(axis=1)
    return out.iloc[1:]


def data_quality_warnings(df: pd.DataFrame) -> list:
    """常见数据问题检查，返回中文提示列表。"""
    warns = []
    c, h, l = df["close"], df["high"], df["low"]
    rng = (h - l).replace(0, np.nan)
    pos = (c - l) / rng
    nxt = c.shift(-1) / c - 1
    corr = pos.corr(nxt)
    if pd.notna(corr) and abs(corr) > 0.3:
        warns.append(
            f"数据疑似存在前视偏差：K线收盘位置与下一期收益的相关系数为 {corr:.2f}（正常应接近 0），"
            "可能是 high/low 包含了收盘之后的价格，机器学习与回测结果会被严重高估"
        )
    stale = float((c.diff() == 0).mean())
    if stale > 0.1:
        warns.append(f"有 {stale:.0%} 的K线收盘价与前一根相同，数据可能存在停牌或缺失")
    if float(rng.isna().mean()) > 0.2:
        warns.append("大量K线最高价等于最低价，可能缺少 high/low 数据，ATR 等指标会失真")
    return warns


def generate_synthetic(
    n: int = 1500,
    seed: int = 42,
    start_price: float = 100.0,
    asset_type: str = STOCK,
    end: str = "2025-12-31",
) -> pd.DataFrame:
    """生成带趋势切换与波动聚集的合成行情，用于离线演示和测试。"""
    rng = np.random.default_rng(seed)
    if asset_type == FOREX:
        base_vol, drift_scale, start_price = 0.005, 0.0002, 1.10 if start_price == 100.0 else start_price
    else:
        base_vol, drift_scale = 0.015, 0.0006

    # 趋势状态：每隔一段随机长度切换一次
    drift = np.empty(n)
    i = 0
    while i < n:
        length = int(rng.integers(40, 160))
        drift[i : i + length] = rng.normal(0, drift_scale * 1.5)
        i += length

    # GARCH(1,1) 风格的波动聚集
    vol = np.empty(n)
    rets = np.empty(n)
    var = base_vol**2
    omega, alpha, beta = base_vol**2 * 0.05, 0.08, 0.87
    prev = 0.0
    for t in range(n):
        var = omega + alpha * prev**2 + beta * var
        vol[t] = np.sqrt(var)
        prev = rng.standard_t(5) / np.sqrt(5 / 3) * vol[t]
        rets[t] = drift[t] + prev

    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]]) * np.exp(rng.normal(0, vol * 0.2))
    spread = np.abs(rng.normal(0, vol * 0.6, size=n)) * close
    high = np.maximum(open_, close) + spread
    low = np.maximum(np.minimum(open_, close) - spread, 1e-6)

    if asset_type == FOREX:
        volume = np.zeros(n)
    else:
        volume = rng.lognormal(mean=13, sigma=0.35, size=n) * (1 + 20 * np.abs(rets))

    idx = pd.bdate_range(end=end, periods=n, name="date")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )


def load_data(
    symbol: Optional[str] = None,
    asset_type: str = "auto",
    csv: Optional[str | Path] = None,
    demo: bool = False,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: str = "5y",
    interval: str = "1d",
    cache_dir: Optional[str | Path] = None,
) -> Tuple[pd.DataFrame, str, str]:
    """统一入口，返回 ``(df, 数据代码, 资产类型)``。"""
    if demo:
        at = FOREX if asset_type == FOREX else STOCK
        seed = zlib.crc32(symbol.encode("utf-8")) if symbol else 42
        df = generate_synthetic(seed=seed, asset_type=at)
        name = symbol or "DEMO"
    elif csv:
        df = load_csv(csv)
        name = symbol or Path(csv).stem
        at = asset_type if asset_type in (STOCK, FOREX) else STOCK
    else:
        if not symbol:
            raise ValueError("请提供股票/外汇代码，或使用 csv / demo 数据源")
        name, inferred = normalize_symbol(symbol, asset_type)
        at = asset_type if asset_type in (STOCK, FOREX) else inferred
        df = fetch_yahoo(name, start=start, end=end, period=period, interval=interval, cache_dir=cache_dir)

    if len(df) < MIN_BARS:
        raise DataError(f"数据量太少（{len(df)} 根K线），至少需要 {MIN_BARS} 根，请拉长时间范围")
    return df, name, at
