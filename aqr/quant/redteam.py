from __future__ import annotations

import json

SYSTEM = """You are a SKEPTICAL quant reviewer. Your job is to try to KILL the \
candidate strategy below before it reaches the operator. Consider: lookahead / \
data-snooping, regime dependence, too few independent trades, implausible \
turnover or transaction costs, overfit parameters, survivorship bias, and whether \
the economic rationale is post-hoc storytelling. Be harsh but fair.

Respond ONLY with minified JSON: {"verdict":"keep"|"kill","critique":"<=2 sentences"}."""

_SPEC_KEYS = ("name", "template", "universe", "params", "rationale", "success_bar")


def review(spec: dict, metrics: dict, walk: dict, router, cfg) -> dict:
    """Second-opinion LLM pass. A candidate must survive this to notify you.
    Skipped (auto-keep, clearly flagged) when no model is configured."""
    if cfg.dry_run or not cfg.openrouter_api_key:
        return {"verdict": "keep", "critique": "red-team skipped (no model configured)"}

    payload = json.dumps({
        "spec": {k: spec[k] for k in _SPEC_KEYS if k in spec},
        "metrics": metrics,
        "walk_forward": walk,
    })
    try:
        c = router.complete(
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": payload}],
            max_tokens=300, temperature=0.2, response_format={"type": "json_object"},
        )
        out = json.loads(c.text)
        verdict = "kill" if str(out.get("verdict", "")).lower().startswith("kill") else "keep"
        return {"verdict": verdict, "critique": str(out.get("critique", ""))[:300]}
    except Exception as e:  # noqa: BLE001 — fail open, but say so loudly in the alert
        return {"verdict": "keep", "critique": f"⚠️ red-team unavailable ({e})"}
