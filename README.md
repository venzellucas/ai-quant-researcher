# AI Quant Researcher

A 24/7 autonomous quant-research agent. It uses OpenRouter's **free/stealth**
models for the *thinking*, does all heavy compute locally for free, and pings you
on Telegram only when a finding survives a rigorous gate.

> **Archived — unmaintained.** This ran exactly once, for 23 hours, in June 2026.
> It generated **951 hypotheses and killed all 951**. The machine it lived on has
> been destroyed. It is published because the *negative result* and the reason
> behind it are more useful than the code — see [Results](#results). Take the
> harness, take the lessons, don't expect support.

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

The gate worked. It worked *too well* — see below.

## Results

One continuous run, **2026-06-27 16:47 → 2026-06-28 15:47 UTC (23h)**:

| | |
|---|---|
| Hypotheses proposed | 951 |
| Backtests executed | 950 |
| LLM calls | 1,818 |
| Survivors reaching the user | **0** |
| Killed at the statistical gate | 949 |
| Killed by the red-team pass | 2 |

Search space actually covered — 847 distinct tickers (yfinance, 2015–2026),
universes ranging from 1 to 530 assets, centred on liquid US ETFs
(TLT ×473, SPY ×443, QQQ ×355, GLD ×317, the XL* sector suite, IWM, BTC-USD ×192):

| Strategy template | Hypotheses |
|---|---|
| `xs_momentum` (cross-sectional momentum) | 375 |
| `ts_momentum` (absolute / time-series trend) | 308 |
| `mean_reversion` (z-score) | 175 |
| `ma_crossover` | 93 |

### Finding 1 — the gate made itself unsatisfiable

This is the interesting one, and it is a **design bug, not a market result**.

The Deflated Sharpe Ratio penalises by the *cumulative* number of trials. The loop
held a fixed bar of `DSR ≥ 0.95` while its own global trial counter grew without
bound. The best DSR achievable therefore decayed monotonically:

| Trials | Max DSR reached |
|---|---|
| 1–50 | **1.000** |
| 51–100 | 0.861 |
| 101–150 | 0.700 |
| 151–200 | 0.464 |
| 501–550 | 0.707 |
| 901–950 | 0.330 |

**All six hypotheses that ever cleared DSR ≥ 0.95 were ids #2, #3, #5, #8, #19 and
#40 — every one inside the first 40 trials.** After roughly trial 50 a survivor was
arithmetically impossible. The agent then spent ~900 further hypotheses — 21 of its
23 hours and ~1,700 LLM calls — on a search that could not, by construction,
produce a result. It was racing its own ruler.

The multiple-testing correction is right in principle. Applying it against a single
eternal counter is not. See [TODO #1](#todo).

### Finding 2 — raw Sharpe is theatre

The highest *raw* out-of-sample Sharpes in the whole run, with their DSR:

| id | Strategy | OOS Sharpe | DSR |
|---|---|---|---|
| 659 | `xsm_multi_asset_mr_far_skip63_top33_rebal21` | **1.397** | 0.464 |
| 132 | `xs_mom_12etf_252d_skip21_top25_rebal5` | **1.234** | 0.357 |
| 329 | `mr_sector_rotation_rev_40d_z15_rebal5` | **1.233** | 0.054 |

An ungated agent reports these three as discoveries. They are noise. If you build
one of these systems and it never shows you a number like the DSR column, it is
lying to you — and so is any backtest post you read that quotes only the left column.

### Finding 3 — the two that reached the red-team

Both were killed, and both critiques were correct.

**#40 `ts_momentum_multiasset_12m_trend`** — 12-month absolute trend, long-only,
SPY / QQQ / TLT / GLD / BTC-USD, monthly rebalance.
IS 1.519 · **OOS 0.863** · DSR 0.974 · 66 trades · max DD −24.5% · kurtosis 15.15 ·
walk-forward folds `[1.463, 1.705, 1.386, 0.768, 0.947]` — **5 of 5 positive**.

> *"66 trades across 5 assets over ~16 years is far too few independent signals —
> most of the OOS Sharpe is likely driven by a handful of regime-dependent bets
> (e.g. 2020–2021 BTC/SPY trends), and the 15.15 kurtosis with 0.86 skew reveals
> extreme tail concentration that makes the 0.86 OOS Sharpe fragile."*

**#2 `xs_momentum_gold_bonds_dollar`** — cross-sectional momentum on
GLD / TLT / UUP / SPY / DBA / EEM.
IS 0.601 · OOS 0.505 · DSR 0.97 · 113 trades · max DD −25.3% · kurtosis 7.77 ·
folds `[-0.721, 0.819, 1.385, -0.353, 1.085]` — 3 of 5 positive.

> *"Walk-forward fold Sharpe ranges from −0.72 to +1.39 with only 60% positive
> folds — this is a lottery ticket, not a strategy."*

### Finding 4 — operational envelope

Free-tier OpenRouter sustained **~984 calls on day one, 782 on day two** before the
daily cap bit, at roughly **40 hypotheses/hour** end-to-end (ideate → backtest →
walk-forward → gate → red-team). Local compute was never the bottleneck; the
free-tier quota was.

### The honest conclusion

Nothing here is evidence that momentum or mean-reversion don't work. It is evidence
that **standard textbook factors on liquid US ETFs do not survive an honest
multiple-testing correction**, which is exactly what the literature already says.
The value of the run is the harness and the two findings above, not alpha.

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

The `runtime/` half is tenant-agnostic — free-model routing with fallback, a quota
ledger, durable SQLite state, and two-way Telegram control. If you want to build an
autonomous agent on free models for something *other* than quant research, that half
is the reusable part.

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

## TODO

Ordered by how much they matter. Nobody is working on these.

1. **Fix the trial-counter — nothing else matters until this is done.**
   Budget trials per pre-registered hypothesis *family*, and deflate within the
   family, instead of deflating against one global counter that grows forever.
   Alternatives: a fixed trial budget declared up front; a
   family-wise-error-rate or FDR scheme across families; or resetting the
   deflation basis whenever the ideator moves to a genuinely new hypothesis class.
   As shipped, the loop is unsatisfiable after ~50 trials.
2. **Optimise for a report a human will read, not for throughput.**
   The real reason this project died was not compute or code — it was that nobody
   had time to read 951 hypotheses and 1,902 journal rows. The gate was so tight
   it never sent a single Telegram notification, so an agent ran 24/7 and never
   spoke. A successor should emit *one page a week* — what was tried, what was
   killed and why, what is worth a human's attention — and treat silence as a bug.
3. **Re-test #40 without BTC-USD, on a wider universe.**
   If the 12-month trend premium survives removal of the 2020–21 crypto regime and
   extends to more assets, it is the well-documented (public, not proprietary) CTA
   time-series-momentum effect. If it doesn't, the red-team was right. Either
   answer is worth having; it is the only candidate in 951 that earned a follow-up.
4. **Widen the strategy registry.** Four templates — cross-sectional momentum,
   absolute trend, z-score mean reversion, MA crossover — is a narrow prior. The
   ideator can only pick from the registry (by design), so the registry *is* the
   ceiling on what can ever be discovered. Carry/value/vol-targeting are absent.
5. **Constrain the ideator's template field.** It repeatedly emitted chatty,
   non-canonical names (`"mean_reversion z-score reversion"` appears in 71 specs);
   hypothesis #1 died outright with `unknown template`. The last commit papered
   over this with tolerant resolution. Enum-constrain the field at emit time instead.
6. **Audit the cost model.** The gate charges costs, but the assumptions were never
   validated against real fills — spread, slippage and borrow on a monthly rebalance
   of sector ETFs are forgiving; on anything thinner they are not.
7. **Address survivorship and data quality.** Universes were hand-picked live
   tickers from yfinance, so they inherit survivorship bias, and delisted names
   surfaced as warnings mid-run (`['SUGAR']: possibly delisted`). Point-in-time
   constituent data would change results.
8. **Persist and reuse the kill ledger.** 951 dead hypotheses are in SQLite and
   nothing reads them back — the ideator can and did re-propose near-duplicates.

## Status

- **Phase 0–2 (done):** runtime (model router + fallback + quota, durable state,
  Telegram, loop), real numpy/pandas backtest engine + strategy templates + data
  adapter, two-way Telegram control, and the Deflated-Sharpe / walk-forward /
  red-team rigor gate.
- **Deployment & hardening:** handled in the infra layer, outside this repo.
- **Maintenance:** none. Archived June 2026, published August 2026.
