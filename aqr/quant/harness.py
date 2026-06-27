from __future__ import annotations

import random


def _placeholder(spec: dict) -> dict:
    """Dependency-free synthetic metric for --dry-run (no pandas, no network).
    Must carry the SAME keys the real engine emits so the Phase 2 gate accepts it."""
    rng = random.Random(spec.get("name", "x"))
    is_s = rng.gauss(0.2, 0.6)
    oos = is_s - abs(rng.gauss(0.3, 0.3))
    full = (is_s + oos) / 2
    return {
        "placeholder": True,
        "in_sample_sharpe": round(is_s, 3),
        "oos_sharpe": round(oos, 3),
        "full_sharpe": round(full, 3),
        "full_sharpe_daily": round(full / (252 ** 0.5), 6),
        "skew": 0.0,
        "kurtosis": 3.0,
        "trades": rng.randint(20, 200),
        "max_drawdown": round(-abs(rng.gauss(0.15, 0.1)), 3),
        "n_obs": 1500,
    }


def run_backtest(spec: dict, cfg) -> dict:
    if cfg.dry_run:
        return _placeholder(spec)

    # real path (Phase 1). Heavy imports are lazy so --dry-run stays dep-free.
    from . import data as data_mod, engine, strategies

    prices = data_mod.load_prices(
        universe=spec["universe"],
        provider=getattr(cfg, "data_provider", "yfinance"),
    )
    weights = strategies.build_weights(
        spec.get("template", "xs_momentum"), prices, spec.get("params", {})
    )
    return engine.backtest(prices, weights, cost_bps=getattr(cfg, "cost_bps", 5.0))
