# AI Quant Researcher

A 24/7 autonomous quant-research agent. It uses OpenRouter's **free/stealth**
models for the *thinking*, does all heavy compute locally for free, and pings you
on Telegram only when a finding survives a rigorous gate.

This repo is **just the code** — it runs in any always-on Python environment.
Provisioning, networking, and hardening live in your own infra layer, not here.

> The LLM is the orchestrator / hypothesis-generator / explainer — **not** the
> quant. The edge comes from the local data + backtest + statistics, and from the
> discipline that stops the agent from fooling itself.

## Hard restraints (by design)

1. **No code execution for the LLM.** The model only emits a structured
   hypothesis *spec*. A vetted local harness compiles and runs it. The model
   never gets a shell or `eval`. This is both a rigor guard (it can't peek at the
   holdout) and the strongest safety guard.
2. **Network isolation** *(an environment requirement, not app code)*: run it
   somewhere it can reach the internet only — no LAN, no host — enforced outside
   the app so the agent can't edit its own cage.
3. **Quota guards.** The router enforces the OpenRouter free-tier caps
   (20 rpm / 50-or-1000 per day) and sleeps until reset instead of hammering.
4. **Public data only.** Everything sent to a free/stealth endpoint is logged and
   used for training — never send proprietary/positions/client data.

## Anti-self-deception gate (the whole point)

An agent that tries thousands of ideas *will* manufacture "significance". So:
pre-register the hypothesis + success bar before running, test on a held-out set
the ideator can't read, apply the Deflated Sharpe Ratio over the running trial
count, charge realistic costs, and run a red-team LLM pass that tries to kill each
candidate before it reaches you.

## Architecture

```
runtime/  (reusable substrate)
  state.py         durable SQLite: quota ledger, call log, hypotheses, runs, journal, settings
  model_router.py  discovers live FREE models, ranks, auto-falls-back, enforces caps
  notify.py        Telegram push (Bot API, no library)
  commander.py     two-way Telegram control (long-poll)
  loop.py          research loop; honors /pause; sleeps on quota exhaustion
quant/    (tenant #1)
  ideator.py       LLM proposes ONE pre-registered hypothesis (template + params)
  strategies.py    strategy template registry (LLM picks; never writes code)
  data.py          price adapter (yfinance / synthetic), cached
  engine.py        transparent numpy/pandas backtest + walk-forward
  stats.py         Probabilistic / Deflated Sharpe Ratio
  gate.py          OOS + walk-forward + Deflated-Sharpe gate
  redteam.py       skeptical LLM second opinion
  tenant.py        ideate -> backtest -> walk-forward -> gate -> red-team -> notify
```

## Quickstart

```bash
python3 -m aqr.main --dry-run --once   # canned hypothesis, stdout "notify", no deps/secrets

cp .env.example .env                   # fill OPENROUTER_API_KEY + Telegram creds
pip install -e .[quant]                # httpx + numpy/pandas/yfinance for live runs
python3 scripts/list_free_models.py    # see what's free/stealth right now
python3 scripts/check_secrets.py --send-test   # verify creds without printing them
python3 -m aqr.main --once             # one real cycle
python3 -m aqr.main                    # run forever
```

## Talk to it (two-way Telegram)

The agent listens via **long polling** (outbound only — no webhook, no open port,
so it works behind an egress-only network). It obeys only your `chat_id`:

```
/status              what I'm doing + quota used today
/findings            surviving hypotheses
/journal [n]         recent log
/pause   /resume     control the loop
/focus crypto|etf|any   bias my next ideas
/kill <id>           blacklist a hypothesis
<anything else>      ask me a question (answered with journal context)
```

## Status

- **Phase 0–2 (done):** runtime (model router + fallback + quota, durable state,
  Telegram, loop), real numpy/pandas backtest engine + strategy templates + data
  adapter, two-way Telegram control, and the Deflated-Sharpe / walk-forward /
  red-team rigor gate.
- **Deployment & hardening:** handled in the infra layer, outside this repo.
