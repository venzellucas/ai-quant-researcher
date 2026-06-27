from __future__ import annotations


class TelegramNotifier:
    """Push-only Telegram notifier via the Bot API (no library needed).
    Falls back to stdout when no token/chat is configured (e.g. --dry-run)."""

    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            print(f"[notify:stdout] {text}")
            return
        import httpx

        try:
            httpx.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[notify:error] {e}\n{text}")
