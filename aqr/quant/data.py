from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Data adapter. The harness (not the LLM) owns all data access. Prices are cached
# so repeated backtests don't re-hit the network or the free-tier quota.


def _synthetic(universe, start, end) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    out = {}
    for t in universe:
        rng = np.random.default_rng(abs(hash(t)) % (2**32))
        rets = rng.normal(0.0003, 0.012, len(idx))
        out[t] = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame(out, index=idx)


def _yfinance(universe, start, end) -> pd.DataFrame:
    import yfinance as yf  # lazy: only needed for live data

    df = yf.download(list(universe), start=start, end=end, auto_adjust=True, progress=False)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df
    if isinstance(close, pd.Series):
        close = close.to_frame(universe[0])
    return close.dropna(how="all")


def load_prices(universe, start="2015-01-01", end=None, provider="yfinance",
                cache_dir="data/prices") -> pd.DataFrame:
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    key = f"{provider}_{'-'.join(sorted(universe))}_{start}_{end}".replace("/", "_")[:180]
    cache = Path(cache_dir) / f"{key}.csv"
    if cache.exists():
        return pd.read_csv(cache, index_col=0, parse_dates=True)

    if provider == "synthetic":
        px = _synthetic(universe, start, end)
    elif provider == "yfinance":
        px = _yfinance(universe, start, end)
    else:
        raise ValueError(f"unknown data provider '{provider}'")

    px = px.dropna(how="all")
    px.to_csv(cache)
    return px
