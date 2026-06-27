from __future__ import annotations

import math


def deflated_sharpe_ok(observed_sharpe: float, n_trials: int) -> bool:
    """Crude multiple-testing haircut: the more hypotheses tried, the higher the
    bar an observed Sharpe must clear to be believable. This is the whole point —
    an agent that tries thousands of ideas WILL find spurious 'significance'.

    Phase 2 replaces this with a proper Deflated Sharpe Ratio
    (Bailey & Lopez de Prado, 2014) plus walk-forward and a red-team LLM pass."""
    haircut = 0.5 * math.sqrt(math.log(max(n_trials, 1) + 1))
    return observed_sharpe > haircut


def evaluate(spec: dict, metrics: dict, n_trials: int) -> dict:
    bar = spec.get("success_bar", {})
    reasons: list[str] = []
    survived = True

    if metrics["oos_sharpe"] < bar.get("oos_sharpe_min", 0.5):
        survived = False
        reasons.append(f"OOS Sharpe {metrics['oos_sharpe']} < bar {bar.get('oos_sharpe_min', 0.5)}")
    if metrics["trades"] < bar.get("min_trades", 30):
        survived = False
        reasons.append(f"too few trades ({metrics['trades']})")
    if survived and not deflated_sharpe_ok(metrics["oos_sharpe"], n_trials):
        survived = False
        reasons.append(f"fails multiple-testing haircut after {n_trials} trials")

    return {"survived": survived, "reasons": reasons}
