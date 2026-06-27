from __future__ import annotations

import inspect
import re

import numpy as np
import pandas as pd

# Strategy templates. The LLM picks ONE template + params; it never writes code.
# Each returns a daily target-weight DataFrame (dates x tickers), long-only,
# rebalanced on a fixed cadence and forward-filled in between.


def _apply_rebalance(target: pd.DataFrame, every: int) -> pd.DataFrame:
    every = max(int(every), 1)
    keep = (np.arange(len(target.index)) % every) == 0
    cond = pd.DataFrame(
        np.repeat(keep[:, None], target.shape[1], axis=1), index=target.index, columns=target.columns
    )
    return target.where(cond).ffill().fillna(0.0)


def _normalize(mask: pd.DataFrame) -> pd.DataFrame:
    return mask.div(mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def xs_momentum(prices, lookback=126, skip=21, top_frac=0.25, rebalance=21):
    mom = prices.shift(skip) / prices.shift(lookback) - 1.0
    k = max(1, int(round(prices.shape[1] * float(top_frac))))
    chosen = mom.rank(axis=1, ascending=False).le(k).astype(float)
    return _apply_rebalance(_normalize(chosen), rebalance)


def ts_momentum(prices, lookback=126, rebalance=21):
    trail = prices / prices.shift(lookback) - 1.0
    return _apply_rebalance(_normalize((trail > 0).astype(float)), rebalance)


def mean_reversion(prices, lookback=20, entry_z=1.0, rebalance=5):
    z = (prices - prices.rolling(lookback).mean()) / prices.rolling(lookback).std()
    return _apply_rebalance(_normalize((z < -float(entry_z)).astype(float)), rebalance)


def ma_crossover(prices, fast=20, slow=100, rebalance=5):
    longs = (prices.rolling(int(fast)).mean() > prices.rolling(int(slow)).mean()).astype(float)
    return _apply_rebalance(_normalize(longs), rebalance)


REGISTRY = {
    "xs_momentum": xs_momentum,
    "ts_momentum": ts_momentum,
    "mean_reversion": mean_reversion,
    "ma_crossover": ma_crossover,
}


def _resolve_template(name: str) -> str | None:
    """Map a possibly-chatty model output (e.g. 'mean_reversion z-score reversion'
    or 'XS Momentum') to a known slug. Free/stealth models don't always return a
    clean slug, so normalize and substring-match rather than reject outright."""
    key = re.sub(r"[^a-z0-9]+", "_", (name or "").lower())
    if key in REGISTRY:
        return key
    return next((t for t in REGISTRY if t in key), None)


def build_weights(template: str, prices: pd.DataFrame, params: dict | None):
    key = _resolve_template(template)
    if key is None:
        raise ValueError(f"unknown template '{template}'; choices: {list(REGISTRY)}")
    fn = REGISTRY[key]
    valid = set(inspect.signature(fn).parameters)
    kw = {k: v for k, v in (params or {}).items() if k in valid}  # ignore junk params
    return fn(prices, **kw)
