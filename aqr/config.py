from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (stdlib only, so --dry-run needs no dependencies)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Config:
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    db_path: str = "data/aqr.sqlite3"

    # quota guards (OpenRouter free tier)
    daily_request_limit: int = 1000  # 50 without credits, 1000 once you've bought >= $10
    requests_per_minute: int = 20

    # model selection: substrings matched (lowercase) against model ids, best first.
    # "alpha" catches whatever stealth frontier checkpoint is live this week.
    preferred_models: list[str] = field(default_factory=lambda: ["alpha", "deepseek", "qwen", "llama"])

    # backtest
    data_provider: str = "yfinance"  # "yfinance" (ETFs + crypto) or "synthetic" (offline tests)
    cost_bps: float = 5.0

    cycle_sleep_seconds: int = 60
    dry_run: bool = False

    @classmethod
    def load(cls, env_file: str = ".env") -> "Config":
        _load_dotenv(Path(env_file))
        return cls(
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            db_path=os.environ.get("AQR_DB_PATH", "data/aqr.sqlite3"),
            daily_request_limit=int(os.environ.get("AQR_DAILY_LIMIT", "1000")),
            data_provider=os.environ.get("AQR_DATA_PROVIDER", "yfinance"),
            cost_bps=float(os.environ.get("AQR_COST_BPS", "5")),
            dry_run=os.environ.get("AQR_DRY_RUN", "").lower() in ("1", "true", "yes"),
        )
