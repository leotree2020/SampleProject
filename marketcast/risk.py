"""风险管理：基于 ATR 的止损止盈与仓位计算。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .data import FOREX


@dataclass
class RiskConfig:
    capital: float = 100_000.0     # 账户资金
    risk_pct: float = 0.01         # 单笔最多亏损资金的比例（1%）
    atr_stop_mult: float = 2.0     # 止损距离 = N 倍 ATR
    reward_risk: float = 2.0       # 止盈距离 / 止损距离
    lot_size: Optional[float] = None    # 最小交易单位（None 时按品种自动推断）
    max_leverage: Optional[float] = None  # 最大杠杆（None 时按品种自动推断）


@dataclass
class RiskPlan:
    direction: str          # long / short
    entry: float
    stop_loss: float
    take_profit: float
    atr: float
    units: float            # 建议数量（股 / 外汇基础货币单位）
    position_value: float   # 名义市值
    risk_amount: float      # 触发止损时的预计亏损
    leverage: float
    note: str


def default_lot_size(symbol: str, asset_type: str) -> float:
    if asset_type == FOREX:
        return 1000.0  # 微型手
    if symbol.upper().endswith((".SS", ".SZ")):
        return 100.0   # A 股一手 100 股
    return 1.0


def default_max_leverage(asset_type: str) -> float:
    return 10.0 if asset_type == FOREX else 1.0


def build_risk_plan(
    symbol: str,
    asset_type: str,
    price: float,
    atr: float,
    direction: str,
    cfg: RiskConfig | None = None,
) -> Optional[RiskPlan]:
    """direction 为 long/short，返回止损止盈与仓位建议；无法计算时返回 None。"""
    cfg = cfg or RiskConfig()
    if direction not in ("long", "short") or not np.isfinite(atr) or atr <= 0 or price <= 0:
        return None

    lot = cfg.lot_size or default_lot_size(symbol, asset_type)
    max_lev = cfg.max_leverage or default_max_leverage(asset_type)
    stop_dist = atr * cfg.atr_stop_mult
    sign = 1 if direction == "long" else -1
    stop = price - sign * stop_dist
    target = price + sign * stop_dist * cfg.reward_risk

    risk_budget = cfg.capital * cfg.risk_pct
    units = risk_budget / stop_dist
    notes = []
    max_units = cfg.capital * max_lev / price
    if units > max_units:
        units = max_units
        notes.append(f"受最大杠杆 {max_lev:g} 倍限制，仓位已下调")
    units = np.floor(units / lot) * lot
    if units <= 0:
        notes.append(f"资金不足一个交易单位（{lot:g}），建议降低风险或增加资金")
        units = 0.0

    value = units * price
    return RiskPlan(
        direction=direction,
        entry=price,
        stop_loss=stop,
        take_profit=target,
        atr=atr,
        units=float(units),
        position_value=float(value),
        risk_amount=float(units * stop_dist),
        leverage=float(value / cfg.capital) if cfg.capital else float("nan"),
        note="；".join(notes),
    )


def price_decimals(price: float, asset_type: str) -> int:
    """根据价格量级决定显示的小数位（外汇 EURUSD 5 位，USDJPY 3 位）。"""
    if asset_type == FOREX:
        return 3 if price >= 20 else 5
    if price < 1:
        return 4
    return 2
