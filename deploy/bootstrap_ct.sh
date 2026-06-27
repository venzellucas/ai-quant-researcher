#!/usr/bin/env bash
# Phase 3 (final) — run INSIDE the container (after `pct enter <CTID>`), from
# /opt/ai-quant-researcher. Prompts SILENTLY for your secrets, writes .env (never
# echoed, never leaves the container), verifies them, and starts the service.
set -euo pipefail

APP_DIR="/opt/ai-quant-researcher"
ENV_FILE="${APP_DIR}/.env"
PY="${APP_DIR}/.venv/bin/python"

[ -d "$APP_DIR" ] || { echo "run this inside the container, from $APP_DIR"; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "run as root (you are, after 'pct enter')"; exit 1; }
cd "$APP_DIR"

echo "Enter your secrets — input is hidden, not echoed, and never stored in history."
read -rsp "OpenRouter API key: " OR; echo
read -rsp "Telegram bot token (from @BotFather): " TG; echo

echo
echo "Now open Telegram and send any message to your bot (so it can learn your chat id)."
read -rp "Press Enter once you've messaged the bot… " _
CHAT="$(TELEGRAM_BOT_TOKEN="$TG" "$PY" "${APP_DIR}/scripts/get_telegram_chat_id.py" 2>/dev/null \
        | sed -n 's/.*chat_id=\(-\{0,1\}[0-9]\{1,\}\).*/\1/p' | head -1 || true)"
if [ -n "$CHAT" ]; then
  read -rp "Detected chat_id ${CHAT} — use it? [Y/n] " yn; [ "${yn:-Y}" = n ] && CHAT=""
fi
[ -n "$CHAT" ] || read -rp "Enter your TELEGRAM_CHAT_ID: " CHAT

umask 077
cat > "$ENV_FILE" <<EOF
OPENROUTER_API_KEY=${OR}
TELEGRAM_BOT_TOKEN=${TG}
TELEGRAM_CHAT_ID=${CHAT}
AQR_DAILY_LIMIT=1000
AQR_DB_PATH=${APP_DIR}/data/aqr.sqlite3
AQR_DATA_PROVIDER=yfinance
EOF
chmod 600 "$ENV_FILE"; chown root:root "$ENV_FILE"
unset OR TG

echo
echo "==> verifying secrets (masked) and sending a test Telegram message"
set -a; . "$ENV_FILE"; set +a
"$PY" "${APP_DIR}/scripts/check_secrets.py" --send-test || {
  echo "Secrets incomplete/invalid — fix $ENV_FILE and re-run scripts/check_secrets.py"; exit 1; }

echo "==> enabling + starting the service"
systemctl enable --now ai-quant-researcher

cat <<EOF

✅ Live. Watch it think:
     journalctl -u ai-quant-researcher -f
Or just message your bot:  /status
EOF
