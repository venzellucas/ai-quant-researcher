from __future__ import annotations

import time
from datetime import datetime, timedelta

from .model_router import QuotaExhausted


def run_forever(tenant, cfg) -> None:
    """Research loop. Honors operator /pause, sleeps until the daily reset on
    quota exhaustion, and backs off on errors instead of hot-looping."""
    print(f"[loop] starting; dry_run={cfg.dry_run}")
    while True:
        if tenant.state.is_paused():
            time.sleep(5)
            continue
        try:
            tenant.cycle()
        except QuotaExhausted as e:
            now = datetime.now()
            reset = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
            secs = (reset - now).total_seconds()
            print(f"[loop] {e}; sleeping {int(secs)}s until quota resets")
            time.sleep(secs)
            continue
        except KeyboardInterrupt:
            print("[loop] stopped by user")
            return
        except Exception as e:  # noqa: BLE001
            print(f"[loop] cycle error: {e}; backing off 60s")
            time.sleep(60)
            continue
        time.sleep(cfg.cycle_sleep_seconds)
