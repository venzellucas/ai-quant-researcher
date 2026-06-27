from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path

from aqr.config import Config
from aqr.quant.tenant import QuantResearcher
from aqr.runtime.loop import run_forever
from aqr.runtime.model_router import ModelRouter
from aqr.runtime.notify import TelegramNotifier
from aqr.runtime.state import State

_CRASH_THROTTLE_SEC = 1800  # at most one crash alert per 30 min


def _crash_alert(notifier: TelegramNotifier, cfg: Config, exc: BaseException) -> None:
    """Best-effort Telegram alert on an unhandled crash, throttled so a crash loop
    (under systemd's exponential backoff) doesn't spam you."""
    marker = Path(cfg.db_path).parent / ".last_crash_alert"
    try:
        if marker.exists() and (time.time() - marker.stat().st_mtime) < _CRASH_THROTTLE_SEC:
            return
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time()))
    except Exception:  # noqa: BLE001
        pass
    notifier.send(
        f"🛑 *AQR crashed*\n`{type(exc).__name__}: {str(exc)[:200]}`\n"
        "systemd will restart it (with backoff)."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Quant Researcher")
    ap.add_argument("--dry-run", action="store_true", help="no network: canned hypothesis + stdout notify")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = ap.parse_args()

    cfg = Config.load()
    if args.dry_run:
        cfg.dry_run = True

    # As a service, WAIT for the OpenRouter key rather than crash-looping if .env
    # isn't set up yet. Keeps systemd 'active' (no restart backoff) and picks the
    # key up within ~10s of setup_secrets.py creating .env.
    if not cfg.dry_run and not args.once:
        while not cfg.openrouter_api_key:
            print("[main] waiting for OPENROUTER_API_KEY in .env …", flush=True)
            time.sleep(10)
            cfg = Config.load()

    notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)
    try:
        state = State(cfg.db_path)
        router = ModelRouter(cfg, state)
        tenant = QuantResearcher(router, state, notifier, cfg)

        if args.once:
            tenant.cycle()
            return

        if notifier.enabled:
            from aqr.runtime.commander import Commander

            threading.Thread(target=lambda: Commander(cfg).run(), daemon=True).start()

        print("[main] starting research loop", flush=True)
        run_forever(tenant, cfg)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001 — last-ditch alert before systemd restarts us
        _crash_alert(notifier, cfg, exc)
        raise


if __name__ == "__main__":
    main()
