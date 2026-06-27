from __future__ import annotations

import time

from .model_router import ModelRouter
from .notify import TelegramNotifier
from .state import State

HELP = (
    "*AI Quant Researcher*\n"
    "/status — what I'm doing + quota\n"
    "/findings — surviving hypotheses\n"
    "/journal [n] — recent log\n"
    "/pause · /resume — control the loop\n"
    "/focus crypto|etf|any — bias my ideas\n"
    "/kill <id> — blacklist a hypothesis\n"
    "…or just ask me a question."
)


class Commander:
    """Two-way Telegram control via LONG POLLING (outbound 443 only — fits the
    egress-only firewall, no inbound webhook). Runs in its own thread with its
    own SQLite connection. Only the configured chat_id is obeyed."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.state = State(cfg.db_path)
        self.router = ModelRouter(cfg, self.state)
        self.notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)
        self.allowed = str(cfg.telegram_chat_id)

    # --- command handling -------------------------------------------------
    def handle(self, text: str) -> None:
        low = text.strip().lower()
        if low in ("/start", "/help"):
            return self.notifier.send(HELP)
        if low.startswith("/status"):
            s = self.state.summary()
            return self.notifier.send(
                f"{'⏸ *paused*' if s['paused'] else '▶ *running*'} | focus: {s['focus'] or 'any'}\n"
                f"trials {s['total']} · survived {s['survived']} · killed {s['killed']}\n"
                f"quota today {s['quota']}/{self.cfg.daily_request_limit}"
            )
        if low.startswith("/findings"):
            f = self.state.findings(10)
            return self.notifier.send("*Survivors:*\n" + ("\n".join(f) if f else "none yet"))
        if low.startswith("/journal"):
            parts = text.split()
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
            return self.notifier.send("\n".join(self.state.recent_journal(n)) or "empty")
        if low.startswith("/pause"):
            self.state.set_setting("paused", "1")
            return self.notifier.send("⏸ paused")
        if low.startswith("/resume"):
            self.state.set_setting("paused", "0")
            return self.notifier.send("▶ resumed")
        if low.startswith("/focus"):
            parts = text.split()
            val = parts[1].lower() if len(parts) > 1 else "any"
            self.state.set_setting("focus", "" if val == "any" else val)
            return self.notifier.send(f"focus → {val}")
        if low.startswith("/kill"):
            parts = text.split()
            if len(parts) > 1 and parts[1].isdigit():
                self.state.kill_hypothesis(int(parts[1]))
                return self.notifier.send(f"killed #{parts[1]}")
            return self.notifier.send("usage: /kill <id>")
        return self._ask(text)  # free-form → chat with the researcher (costs quota)

    def _ask(self, question: str) -> None:
        ctx = "\n".join(self.state.recent_journal(15))
        try:
            c = self.router.complete(
                messages=[
                    {"role": "system", "content": "You are the autonomous quant researcher. "
                     "Answer the operator briefly, using the research journal as context."},
                    {"role": "user", "content": f"Journal:\n{ctx}\n\nQuestion: {question}"},
                ],
                max_tokens=400,
                temperature=0.4,
            )
            self.notifier.send(c.text)
        except Exception as e:  # noqa: BLE001
            self.notifier.send(f"(can't answer right now: {e})")

    # --- long-poll loop ---------------------------------------------------
    def run(self) -> None:
        if not self.notifier.enabled:
            print("[commander] no Telegram creds; command listener disabled")
            return
        import httpx

        print("[commander] listening (long-poll)")
        offset = None
        while True:
            try:
                r = httpx.get(
                    f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/getUpdates",
                    params={"timeout": 30, "offset": offset},
                    timeout=40,
                )
                for upd in r.json().get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    if str((msg.get("chat") or {}).get("id")) != self.allowed:
                        continue  # ignore anyone who isn't you
                    if msg.get("text"):
                        self.handle(msg["text"])
            except Exception as e:  # noqa: BLE001
                print(f"[commander] poll error: {e}; retry in 5s")
                time.sleep(5)
