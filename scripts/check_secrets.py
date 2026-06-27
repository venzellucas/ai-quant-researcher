"""Verify .env secrets WITHOUT revealing them.

Reads OPENROUTER_API_KEY / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from .env (or the
environment) and prints ONLY non-secret confirmation: whether each one works, the
bot's @username, your OpenRouter usage/limit. It never prints a secret value, so
it is safe for someone else to run and read the output.

Usage:
  python3 scripts/check_secrets.py              # verify only
  python3 scripts/check_secrets.py --send-test  # also send a test Telegram message
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def masked(v: str) -> str:
    return f"present (len={len(v)})" if v else "MISSING"


def _get(url: str, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> int:
    load_env()
    ork = os.environ.get("OPENROUTER_API_KEY", "")
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cid = os.environ.get("TELEGRAM_CHAT_ID", "")
    ok = True

    print("OPENROUTER_API_KEY:", masked(ork))
    if ork:
        try:
            d = _get("https://openrouter.ai/api/v1/key", {"Authorization": f"Bearer {ork}"}).get("data", {})
            print(f"   -> valid ✓  usage={d.get('usage')}  limit={d.get('limit')}  free_tier={d.get('is_free_tier')}")
        except urllib.error.HTTPError as e:
            ok = False
            print(f"   -> INVALID ✗ (HTTP {e.code}) — regenerate the key" if e.code == 401
                  else f"   -> could not verify (HTTP {e.code}); key may still be fine")
        except Exception as e:  # noqa: BLE001
            print(f"   -> could not verify ({e})")

    print("TELEGRAM_BOT_TOKEN:", masked(tok))
    if tok:
        try:
            me = _get(f"https://api.telegram.org/bot{tok}/getMe").get("result", {})
            print(f"   -> valid ✓  bot=@{me.get('username')}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"   -> INVALID ✗ ({e})")

    # chat_id is just your numeric Telegram id (not a credential)
    print("TELEGRAM_CHAT_ID:", cid or "MISSING (run scripts/get_telegram_chat_id.py)")

    if "--send-test" in sys.argv and tok and cid:
        try:
            data = json.dumps({"chat_id": cid, "text": "✅ AQR secrets verified — connection works."}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage", data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=20)
            print("Sent a test message to your Telegram — check your phone.")
        except Exception as e:  # noqa: BLE001
            print(f"test message failed: {e}")

    complete = ok and ork and tok and cid
    print("\nRESULT:", "ALL GOOD ✓" if complete else "incomplete — fix the MISSING/INVALID items in .env")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
