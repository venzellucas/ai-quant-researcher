from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _net_returns(prices: pd.DataFrame, weights: pd.DataFrame, cost_bps: float):
    """Daily net portfolio returns: yesterday's weights earn today's returns,
    minus turnover * cost. Returns (net_series, n_entries)."""
    prices = prices.sort_index()
    weights = weights.reindex(prices.index).reindex(columns=prices.columns).fillna(0.0)
    rets = prices.pct_change().fillna(0.0)
    gross = (weights.shift(1).fillna(0.0) * rets).sum(axis=1)
    turnover = (weights - weights.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = gross - turnover * (cost_bps / 1e4)
    entries = int(((weights > 0) & (weights.shift(1).fillna(0.0) <= 0)).sum().sum())
    return net, entries


def _sharpe_daily(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std())


def _ann(sr_daily: float) -> float:
    return sr_daily * np.sqrt(TRADING_DAYS)


def _max_drawdown(daily: pd.Series) -> float:
    curve = (1 + daily.fillna(0)).cumprod()
    return float((curve / curve.cummax() - 1).min())


def backtest(prices, weights, cost_bps: float = 5.0, oos_frac: float = 0.4) -> dict:
    """Transparent vectorized backtest. Reports both annualized Sharpe (for humans)
    and the per-period daily Sharpe + skew/kurtosis (for the Deflated Sharpe gate)."""
    net, entries = _net_returns(prices, weights, cost_bps)
    full = net.dropna()
    split = int(len(net) * (1 - oos_frac))
    sr_d = _sharpe_daily(net)
    return {
        "placeholder": False,
        "in_sample_sharpe": round(_ann(_sharpe_daily(net.iloc[:split])), 3),
        "oos_sharpe": round(_ann(_sharpe_daily(net.iloc[split:])), 3),
        "full_sharpe": round(_ann(sr_d), 3),
        "full_sharpe_daily": round(sr_d, 6),
        "skew": round(float(full.skew()), 4) if len(full) > 2 else 0.0,
        # pandas .kurtosis() is EXCESS kurtosis; PSR/DSR want raw (normal = 3)
        "kurtosis": round(float(full.kurtosis()) + 3.0, 4) if len(full) > 3 else 3.0,
        "trades": entries,
        "max_drawdown": round(_max_drawdown(net), 3),
        "n_obs": int(len(net)),
    }


def walk_forward(prices, weights, k: int = 5, cost_bps: float = 5.0) -> dict:
    """Split the net-return series into k contiguous folds and report per-fold
    Sharpe stability. The params are fixed up front (no per-fold fitting), so this
    measures robustness across regimes, not optimization."""
    net, _ = _net_returns(prices, weights, cost_bps)
    folds = [net.iloc[idx] for idx in np.array_split(np.arange(len(net)), k)]
    sharpes = [round(float(_ann(_sharpe_daily(f))), 3) for f in folds if len(f) > 20]
    if not sharpes:
        return {"fold_sharpes": [], "positive_fraction": 0.0, "mean_fold_sharpe": 0.0, "min_fold_sharpe": 0.0}
    pos = sum(1 for s in sharpes if s > 0)
    return {
        "fold_sharpes": sharpes,
        "positive_fraction": round(pos / len(sharpes), 3),
        "mean_fold_sharpe": round(float(np.mean(sharpes)), 3),
        "min_fold_sharpe": round(float(np.min(sharpes)), 3),
    }
