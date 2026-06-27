from __future__ import annotations

import json
import sqlite3
import time
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS quota (
    day TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    model TEXT,
    ok INTEGER NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    error TEXT
);
CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    spec TEXT NOT NULL,
    rationale TEXT,
    success_bar TEXT,
    status TEXT NOT NULL DEFAULT 'proposed'  -- proposed | survived | killed
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hypo_id INTEGER NOT NULL,
    ts REAL NOT NULL,
    metrics TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class State:
    """Durable SQLite state, safe to open from multiple threads (WAL mode + one
    connection per thread). Holds the quota ledger, call log, hypotheses, runs,
    journal, and operator settings (pause / focus)."""

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- quota ledger -----------------------------------------------------
    def quota_today(self) -> int:
        row = self.db.execute("SELECT count FROM quota WHERE day=?", (date.today().isoformat(),)).fetchone()
        return row["count"] if row else 0

    def incr_quota(self, n: int = 1) -> None:
        self.db.execute(
            "INSERT INTO quota(day,count) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET count=count+?",
            (date.today().isoformat(), n, n),
        )
        self.db.commit()

    # --- settings (operator control) -------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?",
            (key, value, value),
        )
        self.db.commit()

    def is_paused(self) -> bool:
        return self.get_setting("paused", "0") == "1"

    # --- research bookkeeping --------------------------------------------
    def trials_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) AS c FROM hypotheses").fetchone()["c"]

    def record_call(self, model, ok, pt=0, ct=0, error=None) -> None:
        self.db.execute(
            "INSERT INTO llm_calls(ts,model,ok,prompt_tokens,completion_tokens,error) VALUES(?,?,?,?,?,?)",
            (time.time(), model, int(ok), pt, ct, error),
        )
        self.db.commit()

    def add_hypothesis(self, spec, rationale, success_bar) -> int:
        cur = self.db.execute(
            "INSERT INTO hypotheses(ts,spec,rationale,success_bar) VALUES(?,?,?,?)",
            (time.time(), json.dumps(spec), rationale, json.dumps(success_bar)),
        )
        self.db.commit()
        return cur.lastrowid

    def set_hypothesis_status(self, hypo_id, status) -> None:
        self.db.execute("UPDATE hypotheses SET status=? WHERE id=?", (status, hypo_id))
        self.db.commit()

    def kill_hypothesis(self, hypo_id: int) -> None:
        self.set_hypothesis_status(hypo_id, "killed")
        self.journal("kill", f"#{hypo_id} manually killed by operator")

    def add_run(self, hypo_id, metrics) -> None:
        self.db.execute(
            "INSERT INTO runs(hypo_id,ts,metrics) VALUES(?,?,?)", (hypo_id, time.time(), json.dumps(metrics))
        )
        self.db.commit()

    def journal(self, kind, text) -> None:
        self.db.execute("INSERT INTO journal(ts,kind,text) VALUES(?,?,?)", (time.time(), kind, text))
        self.db.commit()

    def recent_journal(self, limit: int = 20) -> list[str]:
        rows = self.db.execute("SELECT kind,text FROM journal ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [f"[{r['kind']}] {r['text']}" for r in rows]

    def prior_sharpes(self) -> list[float]:
        """Per-period (daily) Sharpes of all prior runs — the cross-trial
        dispersion the Deflated Sharpe Ratio needs to penalize multiple testing."""
        out = []
        for r in self.db.execute("SELECT metrics FROM runs").fetchall():
            try:
                m = json.loads(r["metrics"])
                if "full_sharpe_daily" in m:
                    out.append(float(m["full_sharpe_daily"]))
            except Exception:
                pass
        return out

    # --- summaries for the Telegram commander ----------------------------
    def summary(self) -> dict:
        def n(where=""):
            return self.db.execute(f"SELECT COUNT(*) c FROM hypotheses {where}").fetchone()["c"]

        return {
            "total": n(),
            "survived": n("WHERE status='survived'"),
            "killed": n("WHERE status='killed'"),
            "quota": self.quota_today(),
            "paused": self.is_paused(),
            "focus": self.get_setting("focus", ""),
        }

    def findings(self, limit: int = 10) -> list[str]:
        rows = self.db.execute(
            "SELECT id,spec FROM hypotheses WHERE status='survived' ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            try:
                name = json.loads(r["spec"]).get("name", "?")
            except Exception:
                name = "?"
            out.append(f"#{r['id']} {name}")
        return out
