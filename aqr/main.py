from __future__ import annotations

import argparse
import threading

from aqr.config import Config
from aqr.quant.tenant import QuantResearcher
from aqr.runtime.loop import run_forever
from aqr.runtime.model_router import ModelRouter
from aqr.runtime.notify import TelegramNotifier
from aqr.runtime.state import State


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Quant Researcher")
    ap.add_argument("--dry-run", action="store_true", help="no network: canned hypothesis + stdout notify")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = ap.parse_args()

    cfg = Config.load()
    if args.dry_run:
        cfg.dry_run = True

    state = State(cfg.db_path)
    router = ModelRouter(cfg, state)
    notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)
    tenant = QuantResearcher(router, state, notifier, cfg)

    if args.once:
        tenant.cycle()
        return

    # two-way Telegram control in a background thread (long-poll, outbound only)
    if not cfg.dry_run and notifier.enabled:
        from aqr.runtime.commander import Commander

        threading.Thread(target=lambda: Commander(cfg).run(), daemon=True).start()

    run_forever(tenant, cfg)


if __name__ == "__main__":
    main()
