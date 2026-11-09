"""机器学习方向预测：滚动（walk-forward）验证 + 最新一期预测。

金融时间序列的信噪比很低，因此这里刻意：
- 使用强正则化的简单模型（逻辑回归 / 浅层随机森林 / 浅层梯度提升）
- 只做时间顺序上的滚动验证，并在训练集与测试集之间留出 ``horizon``
  根K线的间隔，防止标签重叠造成信息泄露
- 始终与「朴素基准」对比，让使用者看到模型是否真的有增量价值
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import Dataset

MODEL_FACTORIES: Dict[str, Callable[[], object]] = {
    "logistic": lambda: Pipeline(
        [("scaler", StandardScaler()), ("clf", LogisticRegression(C=0.1, max_iter=2000))]
    ),
    "random_forest": lambda: RandomForestClassifier(
        n_estimators=200, max_depth=4, min_samples_leaf=30, max_features="sqrt", random_state=0, n_jobs=-1
    ),
    "gradient_boosting": lambda: HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=40, l2_regularization=1.0, random_state=0
    ),
}

ENSEMBLE = "ensemble"
MODEL_CHOICES = [ENSEMBLE, *MODEL_FACTORIES]


def _members(model: str) -> List[str]:
    if model == ENSEMBLE:
        return list(MODEL_FACTORIES)
    if model not in MODEL_FACTORIES:
        raise ValueError(f"未知模型 {model}，可选：{', '.join(MODEL_CHOICES)}")
    return [model]


def _fit_predict(model: str, X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame) -> np.ndarray:
    """训练并返回测试集上涨概率；集成模型取各成员平均。"""
    if y_train.nunique() < 2:  # 训练集只有一个类别时无法训练，退化为该类别的频率
        return np.full(len(X_test), float(y_train.iloc[0]))
    probs = []
    for name in _members(model):
        est = MODEL_FACTORIES[name]()
        est.fit(X_train, y_train)
        probs.append(est.predict_proba(X_test)[:, 1])
    return np.mean(probs, axis=0)


@dataclass
class ValidationResult:
    oof_proba: pd.Series                 # 样本外预测概率（未参与测试的行为 NaN）
    accuracy: float
    auc: float
    brier: float
    baseline_accuracy: float             # 朴素基准：始终预测训练集中更常见的方向
    up_rate: float                       # 测试期实际上涨比例
    n_test: int
    folds: List[Dict[str, float]] = field(default_factory=list)

    @property
    def has_edge(self) -> bool:
        """模型样本外是否明显优于朴素基准（经验阈值）。"""
        return (
            not np.isnan(self.auc)
            and self.auc >= 0.53
            and self.accuracy >= self.baseline_accuracy + 0.01
        )


def walk_forward(ds: Dataset, model: str = ENSEMBLE, n_splits: int = 5) -> ValidationResult:
    """扩展窗口的滚动验证。"""
    X, y = ds.X, ds.y
    n_splits = max(2, min(n_splits, len(X) // 100))
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=ds.horizon)
    oof = pd.Series(np.nan, index=X.index, name="proba_up")
    folds: List[Dict[str, float]] = []
    baseline_hits = 0
    for train_idx, test_idx in tscv.split(X):
        X_tr, y_tr = X.iloc[train_idx], y.iloc[train_idx]
        X_te, y_te = X.iloc[test_idx], y.iloc[test_idx]
        p = _fit_predict(model, X_tr, y_tr, X_te)
        oof.iloc[test_idx] = p
        majority = int(y_tr.mean() >= 0.5)
        baseline_hits += int((y_te == majority).sum())
        folds.append(
            {
                "start": str(X_te.index[0].date()),
                "end": str(X_te.index[-1].date()),
                "accuracy": float(accuracy_score(y_te, p >= 0.5)),
                "auc": float(roc_auc_score(y_te, p)) if y_te.nunique() > 1 else float("nan"),
                "n": int(len(test_idx)),
            }
        )

    mask = oof.notna()
    y_t, p_t = y[mask], oof[mask]
    return ValidationResult(
        oof_proba=oof,
        accuracy=float(accuracy_score(y_t, p_t >= 0.5)),
        auc=float(roc_auc_score(y_t, p_t)) if y_t.nunique() > 1 else float("nan"),
        brier=float(brier_score_loss(y_t, p_t)),
        baseline_accuracy=baseline_hits / int(mask.sum()),
        up_rate=float(y_t.mean()),
        n_test=int(mask.sum()),
        folds=folds,
    )


@dataclass
class Forecast:
    proba_up: float
    top_features: List[tuple]   # [(特征名, 重要性), ...]


def predict_latest(ds: Dataset, model: str = ENSEMBLE, top_k: int = 6) -> Forecast:
    """用全部有标签数据训练，预测最新一根K线之后 horizon 期上涨的概率。"""
    proba = float(_fit_predict(model, ds.X, ds.y, ds.X_latest)[0])

    # 用随机森林的特征重要性做可解释性参考
    rf = MODEL_FACTORIES["random_forest"]()
    rf.fit(ds.X, ds.y)
    imp = sorted(zip(ds.X.columns, rf.feature_importances_), key=lambda t: t[1], reverse=True)
    return Forecast(proba_up=proba, top_features=[(n, float(v)) for n, v in imp[:top_k]])


FEATURE_NAMES_CN = {
    "ret_1": "1日涨跌幅", "ret_3": "3日涨跌幅", "ret_5": "5日涨跌幅", "ret_10": "10日涨跌幅",
    "ret_20": "20日涨跌幅", "ret_60": "60日涨跌幅",
    "vol_10": "10日波动率", "vol_20": "20日波动率", "vol_ratio": "短/长期波动率比",
    "close_sma5": "价格偏离MA5", "close_sma10": "价格偏离MA10", "close_sma20": "价格偏离MA20",
    "close_sma60": "价格偏离MA60", "sma5_sma20": "MA5/MA20", "sma20_sma60": "MA20/MA60",
    "rsi_6": "RSI(6)", "rsi_14": "RSI(14)", "macd": "MACD(DIF)", "macd_hist": "MACD柱",
    "macd_hist_chg": "MACD柱变化", "bb_pct_b": "布林%b", "bb_width": "布林带宽",
    "atr_pct": "ATR占比", "kdj_k": "KDJ-K", "kdj_j": "KDJ-J", "kdj_kd": "K-D差值",
    "adx": "ADX趋势强度", "di_diff": "+DI与-DI差", "hl_range": "当日振幅",
    "close_pos": "收盘在日内位置", "gap": "跳空幅度", "dist_high_20": "距20日高点",
    "dist_low_20": "距20日低点", "volume_z": "成交量Z值", "volume_ratio_5_20": "5日/20日量比",
    "obv_slope": "OBV斜率",
}
