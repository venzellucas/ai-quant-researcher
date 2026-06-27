from __future__ import annotations

import json
import random

TEMPLATES_DOC = """Choose exactly ONE strategy template and its params:
- xs_momentum    cross-sectional momentum   params: lookback, skip, top_frac, rebalance
- ts_momentum    time-series (absolute) mom  params: lookback, rebalance
- mean_reversion z-score reversion           params: lookback, entry_z, rebalance
- ma_crossover   moving-average crossover    params: fast, slow, rebalance"""

SYSTEM = f"""You are a careful quantitative researcher. Propose ONE concrete, \
falsifiable, long-only hypothesis to test on PUBLIC daily price data.

{TEMPLATES_DOC}

Return ONLY minified JSON with keys:
  "name": short slug,
  "template": one of the template names above,
  "universe": list of liquid tickers (US ETFs like SPY/QQQ/TLT, or crypto like BTC-USD),
  "params": object with that template's params,
  "rationale": the economic reason it might work,
  "success_bar": {{"oos_sharpe_min": number, "min_trades": int}}

The success_bar is PRE-REGISTERED — you commit to it BEFORE seeing any result. \
Do not re-propose anything already marked killed in the journal."""

ETF_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "HYG", "LQD", "XLK", "XLE", "XLF"]
CRYPTO_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD"]


def _canned(focus: str) -> dict:
    universe = CRYPTO_UNIVERSE if focus == "crypto" else ETF_UNIVERSE
    return {
        "name": f"xs_mom_{random.randint(1000, 9999)}",
        "template": "xs_momentum",
        "universe": universe,
        "params": {"lookback": 126, "skip": 21, "top_frac": 0.3, "rebalance": 21},
        "rationale": "cross-sectional momentum is a long-documented risk premium",
        "success_bar": {"oos_sharpe_min": 0.5, "min_trades": 30},
    }


def propose(router, state, cfg) -> dict:
    focus = state.get_setting("focus", "")
    if cfg.dry_run or not cfg.openrouter_api_key:
        spec = _canned(focus)
    else:
        journal = "\n".join(state.recent_journal(20))
        focus_line = f"Operator focus: {focus or 'any asset class'}."
        c = router.complete(
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"{focus_line}\nRecent journal:\n{journal}\n\nPropose the next hypothesis."},
            ],
            max_tokens=600,
            temperature=0.9,
            response_format={"type": "json_object"},
        )
        spec = json.loads(c.text)

    hypo_id = state.add_hypothesis(
        spec=spec, rationale=spec.get("rationale", ""), success_bar=spec.get("success_bar", {})
    )
    spec["_id"] = hypo_id
    return spec
