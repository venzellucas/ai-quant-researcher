from __future__ import annotations

import math
from statistics import NormalDist

# Probabilistic & Deflated Sharpe Ratio (Bailey & López de Prado, 2014).
# Pure stdlib (NormalDist) — no scipy. All Sharpes here are PER-PERIOD (daily),
# matching T = number of observations.

_ND = NormalDist()
_EULER = 0.5772156649015329


def expected_max_sharpe(sr_std: float, n_trials: int) -> float:
    """Expected maximum Sharpe under the null of zero true skill, given that
    `n_trials` strategies were tried with cross-trial Sharpe dispersion `sr_std`.
    This is the bar a genuine finding must clear — and it RISES with n_trials,
    which is exactly the multiple-testing penalty."""
    if n_trials < 2 or sr_std <= 0:
        return 0.0
    a = (1 - _EULER) * _ND.inv_cdf(1 - 1.0 / n_trials)
    b = _EULER * _ND.inv_cdf(1 - 1.0 / (n_trials * math.e))
    return sr_std * (a + b)


def probabilistic_sharpe_ratio(sr: float, T: int, skew: float, kurt: float,
                               benchmark: float = 0.0) -> float:
    """P(true Sharpe > benchmark), correcting for sample length and the non-
    normality (skew/kurtosis) of returns."""
    if T < 2:
        return 0.0
    denom = 1 - skew * sr + ((kurt - 1) / 4.0) * sr * sr
    if denom <= 0:
        return 0.0
    z = (sr - benchmark) * math.sqrt(T - 1) / math.sqrt(denom)
    return _ND.cdf(z)


def deflated_sharpe_ratio(sr: float, T: int, skew: float, kurt: float,
                          sr_std: float, n_trials: int) -> float:
    """PSR measured against the selection-inflated benchmark expected_max_sharpe.
    A value > ~0.95 means the result is unlikely to be a multiple-testing fluke."""
    sr0 = expected_max_sharpe(sr_std, n_trials)
    return probabilistic_sharpe_ratio(sr, T, skew, kurt, benchmark=sr0)
