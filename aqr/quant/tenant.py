from __future__ import annotations

from . import gate, harness, ideator


class QuantResearcher:
    """Tenant #1 on the shared runtime. One cycle = one pre-registered hypothesis
    proposed, backtested, gated, journaled, and (only if it survives) pushed to you."""

    def __init__(self, router, state, notifier, cfg):
        self.router = router
        self.state = state
        self.notifier = notifier
        self.cfg = cfg

    def cycle(self) -> None:
        spec = ideator.propose(self.router, self.state, self.cfg)
        hypo_id = spec["_id"]
        self.state.journal(
            "ideate", f"#{hypo_id} {spec['name']} [{spec.get('template', '?')}] {spec.get('params', {})}"
        )

        try:
            metrics = harness.run_backtest(spec, self.cfg)
        except Exception as e:  # bad spec from the model, data failure, etc.
            self.state.set_hypothesis_status(hypo_id, "killed")
            self.state.journal("error", f"#{hypo_id} {spec['name']}: {e}")
            print(f"[cycle] #{hypo_id} {spec['name']} -> error: {e}")
            return

        self.state.add_run(hypo_id, metrics)
        verdict = gate.evaluate(spec, metrics, self.state.trials_count())

        if verdict["survived"]:
            self.state.set_hypothesis_status(hypo_id, "survived")
            self.notifier.send(
                f"✅ *Candidate finding* #{hypo_id} `{spec['name']}`\n"
                f"template: {spec.get('template')} | OOS Sharpe *{metrics['oos_sharpe']}* "
                f"(IS {metrics['in_sample_sharpe']}), trades {metrics['trades']}, "
                f"maxDD {metrics['max_drawdown']}\n"
                f"_{spec.get('rationale', '')}_"
            )
            self.state.journal("survived", f"#{hypo_id} {spec['name']} {metrics}")
            status = "SURVIVED"
        else:
            self.state.set_hypothesis_status(hypo_id, "killed")
            self.state.journal("killed", f"#{hypo_id} {spec['name']}: {'; '.join(verdict['reasons'])}")
            status = "killed: " + "; ".join(verdict["reasons"])

        print(f"[cycle] #{hypo_id} {spec['name']} -> {status}")
