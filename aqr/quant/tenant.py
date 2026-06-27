from __future__ import annotations

from . import engine, gate, harness, ideator, redteam


class QuantResearcher:
    """Tenant #1. One cycle = ideate -> backtest -> walk-forward -> gate ->
    red-team -> (only survivors) notify. Everything is journaled either way."""

    def __init__(self, router, state, notifier, cfg):
        self.router = router
        self.state = state
        self.notifier = notifier
        self.cfg = cfg

    def cycle(self) -> None:
        spec = ideator.propose(self.router, self.state, self.cfg)
        hypo_id = spec["_id"]
        self.state.journal("ideate", f"#{hypo_id} {spec['name']} [{spec.get('template', '?')}] {spec.get('params', {})}")

        try:
            metrics = harness.run_backtest(spec, self.cfg)
            walk = (
                {"fold_sharpes": [], "positive_fraction": 1.0}
                if metrics.get("placeholder")
                else self._walk_forward(spec)
            )
        except Exception as e:
            self.state.set_hypothesis_status(hypo_id, "killed")
            self.state.journal("error", f"#{hypo_id} {spec['name']}: {e}")
            print(f"[cycle] #{hypo_id} {spec['name']} -> error: {e}")
            return

        prior = self.state.prior_sharpes()
        verdict = gate.evaluate(spec, metrics, walk, prior, self.state.trials_count())
        metrics_record = {**metrics, "dsr": verdict["dsr"], "walk_forward": walk}
        self.state.add_run(hypo_id, metrics_record)

        if not verdict["survived"]:
            self.state.set_hypothesis_status(hypo_id, "killed")
            self.state.journal("killed", f"#{hypo_id} {spec['name']}: {'; '.join(verdict['reasons'])}")
            print(f"[cycle] #{hypo_id} {spec['name']} -> killed: {'; '.join(verdict['reasons'])}")
            return

        # passed the statistical gate — now let the skeptic try to kill it
        rt = redteam.review(spec, metrics, walk, self.router, self.cfg)
        if rt["verdict"] == "kill":
            self.state.set_hypothesis_status(hypo_id, "redteam_killed")
            self.state.journal("redteam_killed", f"#{hypo_id} {spec['name']}: {rt['critique']}")
            print(f"[cycle] #{hypo_id} {spec['name']} -> red-team killed: {rt['critique']}")
            return

        self.state.set_hypothesis_status(hypo_id, "survived")
        self.notifier.send(
            f"✅ *Candidate finding* #{hypo_id} `{spec['name']}`\n"
            f"template: {spec.get('template')} | OOS Sharpe *{metrics['oos_sharpe']}* "
            f"(IS {metrics['in_sample_sharpe']})\n"
            f"DSR {verdict['dsr']} | walk-fwd {walk['positive_fraction']} positive | "
            f"trades {metrics['trades']} | maxDD {metrics['max_drawdown']}\n"
            f"_{spec.get('rationale', '')}_\n"
            f"🔴 red-team: {rt['critique']}"
        )
        self.state.journal("survived", f"#{hypo_id} {spec['name']} dsr={verdict['dsr']} {metrics}")
        print(f"[cycle] #{hypo_id} {spec['name']} -> SURVIVED (dsr {verdict['dsr']})")

    def _walk_forward(self, spec: dict) -> dict:
        from . import data as data_mod, strategies

        prices = data_mod.load_prices(
            universe=spec["universe"], provider=getattr(self.cfg, "data_provider", "yfinance")
        )
        weights = strategies.build_weights(spec.get("template", "xs_momentum"), prices, spec.get("params", {}))
        return engine.walk_forward(prices, weights, cost_bps=getattr(self.cfg, "cost_bps", 5.0))
