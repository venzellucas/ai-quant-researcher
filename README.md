# AI Quant Researcher

A 24/7 autonomous quant-research agent that runs on a hardened Proxmox LXC, uses
OpenRouter's **free/stealth** models for the *thinking*, does all heavy compute
locally for free, and pings you on Telegram only when a finding survives a
rigorous gate.

> The LLM is the orchestrator / hypothesis-generator / explainer — **not** the
> quant. The edge comes from the local data + backtest + statistics, and from the
> discipline that stops the agent from fooling itself.

## Hard restraints (by design)

1. **No code execution for the LLM.** The model only emits a structured
   hypothesis *spec*. A vetted local harness compiles and runs it. The model
   never gets a shell or `eval`. This is both a rigor guard (it can't peek at the
   holdout) and the strongest safety guard.
2. **Network isolation** (see `deploy/proxmox/`): the container can reach the
   internet only — no other containers, no LAN, no Proxmox host. Enforced
   host-side so the agent can't edit its own cage.
3. **Quota guards.** The router enforces the OpenRouter free-tier caps
   (20 rpm / 50-or-1000 per day) and sleeps until reset instead of hammering.
4. **Public data only.** Everything sent to a free/stealth endpoint is logged and
   used for training — never send proprietary/positions/client data.

## Anti-self-deception gate (the whole point)

An agent that tries thousands of ideas *will* manufacture "significance". So:
pre-register the hypothesis + success bar before running, test on a held-out set
the ideator can't read, apply a multiple-testing haircut (Phase 2: Deflated
Sharpe / FDR over the running trial count), charge realistic costs, and run a
red-team LLM pass that tries to kill each candidate before it reaches you.

## Architecture

```
runtime/  (reusable substrate)
  state.py         durable SQLite: quota ledger, call log, hypotheses, runs, journal
  model_router.py  discovers live FREE models, ranks, auto-falls-back, enforces caps
  notify.py        Telegram push (Bot API, no library)
  loop.py          event loop; sleeps during compute / on quota exhaustion
quant/    (tenant #1)
  ideator.py       LLM proposes ONE pre-registered, falsifiable hypothesis
  harness.py       backtest (Phase 0 = placeholder; Phase 1 = vectorbt, owns data)
  gate.py          OOS + multiple-testing gate
  tenant.py        wires ideate -> run -> gate -> notify -> journal
```

## Quickstart (Phase 0 plumbing, no secrets needed)

```bash
python3 -m aqr.main --dry-run --once   # canned hypothesis, stdout "notify"
```

Then wire it up:

```bash
cp .env.example .env          # fill OPENROUTER_API_KEY + Telegram creds
python3 scripts/list_free_models.py            # see what's free/stealth right now
TELEGRAM_BOT_TOKEN=xxx python3 scripts/get_telegram_chat_id.py
pip install -e .              # installs httpx for live runs
python3 -m aqr.main --once    # one real cycle
python3 -m aqr.main           # run forever
```

## Talk to it (two-way Telegram)

The agent listens via **long polling** (outbound 443 only — no webhook, no open
port, fits the egress-only firewall). It obeys only your `chat_id`. Commands:

```
/status              what I'm doing + quota used today
/findings            surviving hypotheses
/journal [n]         recent log
/pause   /resume     control the loop
/focus crypto|etf|any   bias my next ideas
/kill <id>           blacklist a hypothesis
<anything else>      ask me a question (answered with journal context)
```

## Roadmap

- **Phase 0 (done):** runtime plumbing — router+fallback+quota, state, Telegram, loop.
- **Phase 1 (done):** transparent numpy/pandas backtest engine + strategy template
  registry (the LLM picks a template + params, never writes code) + data adapter
  (yfinance for ETFs & crypto, synthetic for offline tests) + two-way Telegram control.
- **Phase 2 (done):** Deflated Sharpe Ratio gate (stdlib, no scipy) + walk-forward
  fold stability + a red-team LLM pass that must clear a candidate before it pings you.
- **Phase 3:** deploy to the hardened LXC (systemd + firewall) + tiny dashboard.
- **Phase 4 (fun):** agent-civilization tenant on the same runtime.
