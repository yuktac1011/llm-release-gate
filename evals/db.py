import os, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("EVAL_DB", ROOT / "evals" / "results.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_version TEXT, model TEXT, mode TEXT, created_at TEXT,
  total INTEGER, passed INTEGER, pass_rate REAL, critical_failed INTEGER,
  avg_latency_ms REAL, prompt_tokens INTEGER, completion_tokens INTEGER
);
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER REFERENCES runs(id),
  case_id TEXT, category TEXT, critical INTEGER, question TEXT, answer TEXT,
  passed INTEGER, rules_passed INTEGER, rules_detail TEXT,
  similarity REAL, judge_verdict TEXT, judge_reason TEXT,
  latency_ms REAL, prompt_tokens INTEGER, completion_tokens INTEGER,
  error TEXT, from_cache INTEGER
);
CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY, value TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_run(conn, meta: dict, results: list[dict]) -> int:
    cur = conn.execute(
        """INSERT INTO runs (prompt_version, model, mode, created_at, total, passed, pass_rate,
           critical_failed, avg_latency_ms, prompt_tokens, completion_tokens)
           VALUES (:prompt_version, :model, :mode, :created_at, :total, :passed, :pass_rate,
           :critical_failed, :avg_latency_ms, :prompt_tokens, :completion_tokens)""", meta)
    run_id = cur.lastrowid
    conn.executemany(
        """INSERT INTO results (run_id, case_id, category, critical, question, answer, passed,
           rules_passed, rules_detail, similarity, judge_verdict, judge_reason, latency_ms,
           prompt_tokens, completion_tokens, error, from_cache)
           VALUES (:run_id, :case_id, :category, :critical, :question, :answer, :passed,
           :rules_passed, :rules_detail, :similarity, :judge_verdict, :judge_reason, :latency_ms,
           :prompt_tokens, :completion_tokens, :error, :from_cache)""",
        [{**r, "run_id": run_id} for r in results])
    conn.commit()
    return run_id