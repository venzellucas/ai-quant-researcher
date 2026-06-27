from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from .state import State


class QuotaExhausted(Exception):
    """Daily free-tier request cap hit; caller should sleep until reset."""


class NoModelAvailable(Exception):
    """Every candidate free model failed this cycle."""


@dataclass
class Completion:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ModelRouter:
    """Wraps OpenRouter. Discovers FREE models live, ranks them by preference,
    and auto-falls-back across them on error. Enforces the 20 rpm / daily caps
    so an unattended loop can't blow the quota. Every attempt is logged.

    Stealth/alpha models are ephemeral — they vanish or flip to paid without
    notice (Quasar->GPT-4.1, Polaris->GPT-5.1, Sherlock->Grok4.1). So we never
    hard-depend on one: we rediscover what's free on each refresh and degrade.
    """

    _STATIC_FALLBACK = [
        "deepseek/deepseek-chat-v3:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]

    def __init__(self, cfg, state: State):
        self.cfg = cfg
        self.state = state
        self._rpm: deque[float] = deque()
        self._cooldown: dict[str, float] = {}
        self._models: list[str] = []
        self._fetched_at = 0.0

    # --- model discovery --------------------------------------------------
    def _refresh_models(self, force: bool = False) -> None:
        if not force and self._models and (time.time() - self._fetched_at) < 900:
            return
        try:
            import httpx

            r = httpx.get(f"{self.cfg.openrouter_base_url}/models", timeout=30)
            r.raise_for_status()
            free = [
                m["id"]
                for m in r.json()["data"]
                if float(m.get("pricing", {}).get("prompt", 1)) == 0
                and float(m.get("pricing", {}).get("completion", 1)) == 0
            ]
            self._models = self._rank(free or self._STATIC_FALLBACK)
            self._fetched_at = time.time()
        except Exception:
            if not self._models:
                self._models = self._rank(self._STATIC_FALLBACK)

    def _rank(self, ids: list[str]) -> list[str]:
        def score(mid: str) -> int:
            low = mid.lower()
            for i, pref in enumerate(self.cfg.preferred_models):
                if pref in low:
                    return i
            return len(self.cfg.preferred_models) + 1

        return sorted(set(ids), key=score)

    def candidates(self) -> list[str]:
        self._refresh_models()
        now = time.time()
        return [m for m in self._models if self._cooldown.get(m, 0) < now]

    # --- quota guards -----------------------------------------------------
    def _respect_rpm(self) -> None:
        now = time.time()
        while self._rpm and now - self._rpm[0] > 60:
            self._rpm.popleft()
        if len(self._rpm) >= self.cfg.requests_per_minute:
            time.sleep(max(0.0, 60 - (now - self._rpm[0]) + 0.1))
        self._rpm.append(time.time())

    def _check_daily(self) -> None:
        if self.state.quota_today() >= self.cfg.daily_request_limit:
            raise QuotaExhausted(f"daily limit {self.cfg.daily_request_limit} reached")

    # --- completion -------------------------------------------------------
    def complete(self, messages, max_tokens=1024, temperature=0.7, response_format=None) -> Completion:
        self._check_daily()
        import httpx

        last_err = None
        for model in self.candidates():
            self._respect_rpm()
            self.state.incr_quota(1)  # failed attempts count toward the cap too
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format:
                payload["response_format"] = response_format
            try:
                r = httpx.post(
                    f"{self.cfg.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.cfg.openrouter_api_key}",
                        "HTTP-Referer": "https://github.com/venzellucas/ai-quant-researcher",
                        "X-Title": "ai-quant-researcher",
                    },
                    json=payload,
                    timeout=120,
                )
                if r.status_code in (429, 500, 502, 503, 520, 524):
                    self._cooldown[model] = time.time() + 120
                    self.state.record_call(model, ok=False, error=f"http {r.status_code}")
                    last_err = f"{model}: http {r.status_code}"
                    continue
                r.raise_for_status()
                data = r.json()
                usage = data.get("usage", {})
                self.state.record_call(
                    model, ok=True,
                    pt=usage.get("prompt_tokens", 0),
                    ct=usage.get("completion_tokens", 0),
                )
                return Completion(
                    text=data["choices"][0]["message"]["content"],
                    model=model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )
            except Exception as e:  # noqa: BLE001
                self._cooldown[model] = time.time() + 120
                self.state.record_call(model, ok=False, error=str(e)[:200])
                last_err = f"{model}: {e}"
                continue
        raise NoModelAvailable(last_err or "no free models available")
