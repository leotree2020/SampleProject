import numpy as np
import pandas as pd
import pytest

from marketcast import models
from marketcast.features import build_features, forward_return, make_dataset


def test_forward_return_alignment():
    close = pd.Series([100.0, 110, 121, 133.1])
    fr = forward_return(close, 1)
    assert fr.iloc[0] == pytest.approx(0.1)
    assert np.isnan(fr.iloc[-1])


def test_features_have_no_lookahead(stock_df):
    full = build_features(stock_df)
    cut = build_features(stock_df.iloc[:500])
    pd.testing.assert_frame_equal(full.iloc[:500], cut)


def test_make_dataset_shapes(stock_df):
    ds = make_dataset(stock_df, horizon=5)
    assert len(ds.X) == len(ds.y) == len(ds.fwd_ret)
    assert ds.X_latest.index[0] == stock_df.index[-1]
    # 最后 horizon 行没有标签
    assert ds.X.index[-1] == stock_df.index[-6]
    assert not ds.X.isna().any().any()
    assert set(ds.y.unique()) <= {0, 1}


def test_walk_forward_has_gap_and_valid_metrics(stock_df):
    ds = make_dataset(stock_df, horizon=5)
    val = models.walk_forward(ds, "logistic", n_splits=4)
    assert 0 <= val.accuracy <= 1 and 0 <= val.auc <= 1
    assert val.n_test == int(val.oof_proba.notna().sum())
    assert len(val.folds) == 4
    p = val.oof_proba.dropna()
    assert ((p >= 0) & (p <= 1)).all()


def test_model_detects_real_signal():
    """构造一个下期收益可由特征预测的序列，模型应当识别出预测力。"""
    rng = np.random.default_rng(0)
    n = 1200
    rets = np.zeros(n)
    noise = rng.normal(0, 0.01, n)
    for t in range(1, n):
        rets[t] = -0.6 * rets[t - 1] + noise[t]  # 强均值回复
    close = 100 * np.exp(np.cumsum(rets))
    idx = pd.bdate_range("2015-01-01", periods=n)
    df = pd.DataFrame({"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 0.0}, index=idx)
    ds = make_dataset(df, horizon=1)
    val = models.walk_forward(ds, "logistic")
    assert val.auc > 0.6
    assert val.has_edge


def test_random_walk_has_no_edge():
    rng = np.random.default_rng(3)
    n = 1200
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    idx = pd.bdate_range("2015-01-01", periods=n)
    df = pd.DataFrame({"open": close, "high": close * 1.002, "low": close * 0.998, "close": close, "volume": 0.0}, index=idx)
    val = models.walk_forward(make_dataset(df, horizon=5), "logistic")
    assert val.auc < 0.6


def test_predict_latest(stock_df):
    ds = make_dataset(stock_df, horizon=5)
    fc = models.predict_latest(ds, "ensemble")
    assert 0 <= fc.proba_up <= 1
    assert len(fc.top_features) == 6


def test_unknown_model(stock_df):
    with pytest.raises(ValueError):
        models.walk_forward(make_dataset(stock_df), "nope")
