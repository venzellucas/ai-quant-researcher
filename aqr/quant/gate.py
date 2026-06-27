from __future__ import annotations

import statistics

from . import stats

DSR_THRESHOLD = 0.95       # Deflated Sharpe prob a finding must clear
WF_POS_FRACTION = 0.6      # fraction of walk-forward folds that must be positive
MIN_TRIALS_FOR_DSR = 5     # need a few trials before the selection variance is meaningful


def evaluate(spec: dict, metrics: dict, walk: dict, prior_daily_sharpes: list[float],
             n_trials: int) -> dict:
    """Survive only if it clears the PRE-REGISTERED OOS bar, has enough trades, is
    stable across walk-forward folds, AND beats the Deflated Sharpe bar (which
    rises with the number of hypotheses tried). This is what stops the agent from
    fooling itself."""
    bar = spec.get("success_bar", {})
    reasons: list[str] = []
    survived = True

    if metrics["oos_sharpe"] < bar.get("oos_sharpe_min", 0.5):
        survived = False
        reasons.append(f"OOS Sharpe {metrics['oos_sharpe']} < bar {bar.get('oos_sharpe_min', 0.5)}")
    if metrics["trades"] < bar.get("min_trades", 30):
        survived = False
        reasons.append(f"too few trades ({metrics['trades']})")
    if walk["positive_fraction"] < WF_POS_FRACTION:
        survived = False
        reasons.append(f"walk-forward unstable ({walk['positive_fraction']} of folds positive)")

    sr_std = statistics.pstdev(prior_daily_sharpes) if len(prior_daily_sharpes) >= 2 else 0.0
    dsr = stats.deflated_sharpe_ratio(
        sr=metrics["full_sharpe_daily"], T=metrics["n_obs"],
        skew=metrics.get("skew", 0.0), kurt=metrics.get("kurtosis", 3.0),
        sr_std=sr_std, n_trials=max(n_trials, 1),
    )
    if len(prior_daily_sharpes) < MIN_TRIALS_FOR_DSR:
        reasons.append(f"DSR provisional ({dsr:.2f}; needs >={MIN_TRIALS_FOR_DSR} prior trials)")
    elif dsr < DSR_THRESHOLD:
        survived = False
        reasons.append(f"Deflated Sharpe {dsr:.2f} < {DSR_THRESHOLD} after {n_trials} trials")

    return {"survived": survived, "reasons": reasons, "dsr": round(dsr, 3), "sr_std": round(sr_std, 4)}
