from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _sharpe(daily: pd.Series) -> float:
    r = daily.dropna()
    if len(r) < 20 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS))


def _max_drawdown(daily: pd.Series) -> float:
    curve = (1 + daily.fillna(0)).cumprod()
    return float((curve / curve.cummax() - 1).min())


def backtest(prices: pd.DataFrame, weights: pd.DataFrame, cost_bps: float = 5.0,
             oos_frac: float = 0.4) -> dict:
    """Transparent vectorized backtest (no black box). Yesterday's weights earn
    today's returns; turnover is charged at cost_bps. Reports in-sample and a
    held-out out-of-sample Sharpe. The OOS tail is never seen at ideation time —
    the LLM commits params up front — so this split is honest."""
    prices = prices.sort_index()
    weights = weights.reindex(prices.index).reindex(columns=prices.columns).fillna(0.0)
    rets = prices.pct_change().fillna(0.0)

    gross = (weights.shift(1).fillna(0.0) * rets).sum(axis=1)
    turnover = (weights - weights.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = gross - turnover * (cost_bps / 1e4)

    entries = int(((weights > 0) & (weights.shift(1).fillna(0.0) <= 0)).sum().sum())

    split = int(len(net) * (1 - oos_frac))
    return {
        "placeholder": False,
        "in_sample_sharpe": round(_sharpe(net.iloc[:split]), 3),
        "oos_sharpe": round(_sharpe(net.iloc[split:]), 3),
        "full_sharpe": round(_sharpe(net), 3),
        "trades": entries,
        "max_drawdown": round(_max_drawdown(net), 3),
        "n_obs": int(len(net)),
    }
