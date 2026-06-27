"""Print the chat id(s) that have messaged your bot.

Usage:
  1. Create a bot with @BotFather, copy the token.
  2. Send any message to your new bot from your Telegram account.
  3. TELEGRAM_BOT_TOKEN=xxx python scripts/get_telegram_chat_id.py
"""

import json
import os
import sys
import urllib.request

token = os.environ.get("TELEGRAM_BOT_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not token:
    sys.exit("set TELEGRAM_BOT_TOKEN or pass the token as arg1")

with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates") as r:
    data = json.load(r)

if not data.get("result"):
    print("No updates yet. Send a message to your bot first, then re-run.")
else:
    for u in data["result"]:
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat", {})
        print(f"chat_id={chat.get('id')}  type={chat.get('type')}  "
              f"name={chat.get('first_name') or chat.get('title')}")
