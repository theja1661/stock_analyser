"""SQLite helpers. One file (data.db) holds the cache and every stage's output."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker            TEXT PRIMARY KEY,
    name              TEXT,
    sector            TEXT,
    price             REAL,
    pe                REAL,
    roe               REAL,      -- fraction, e.g. 0.18 = 18%
    debt_to_equity    REAL,      -- ratio, e.g. 0.45
    momentum_6m       REAL,      -- fraction, e.g. 0.12 = +12%
    quarters_json     TEXT,      -- [{"period": "2026-09-30", "revenue": .., "net_profit": ..}, ...] newest first
    quarters_available INTEGER,  -- quarters (of last 4) with both revenue and net profit
    fetched_at        TEXT NOT NULL,
    error             TEXT       -- last fetch problem, if any
);

CREATE TABLE IF NOT EXISTS screen_results (
    run_id          TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    ticker          TEXT NOT NULL,
    composite       REAL NOT NULL,
    scores_json     TEXT NOT NULL,   -- per-metric 0-100 scores
    raw_json        TEXT NOT NULL,   -- raw metric values used
    PRIMARY KEY (run_id, ticker)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    ticker      TEXT NOT NULL,
    doc_hash    TEXT NOT NULL,
    provider    TEXT,
    model       TEXT,
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (ticker, doc_hash)
);

-- Which analysis applies to each screened stock in a given screen run.
CREATE TABLE IF NOT EXISTS analysis_status (
    run_id    TEXT NOT NULL,
    ticker    TEXT NOT NULL,
    status    TEXT NOT NULL,   -- analyzed | quant-only | error
    doc_hash  TEXT,
    documents TEXT,            -- JSON list of file names
    message   TEXT,
    PRIMARY KEY (run_id, ticker)
);

CREATE TABLE IF NOT EXISTS final_ranking (
    run_id        TEXT NOT NULL,
    rank          INTEGER NOT NULL,
    ticker        TEXT NOT NULL,
    final_score   REAL,
    is_pick       INTEGER NOT NULL DEFAULT 0,
    quantity      INTEGER,
    cost          REAL,
    budget_pct    REAL,
    PRIMARY KEY (run_id, ticker)
);

CREATE TABLE IF NOT EXISTS sizing_summary (
    run_id    TEXT PRIMARY KEY,
    budget    REAL NOT NULL,
    invested  REAL NOT NULL,
    leftover  REAL NOT NULL,
    notes     TEXT
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- fundamentals

def get_fundamentals(conn: sqlite3.Connection, ticker: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM fundamentals WHERE ticker = ?", (ticker,)).fetchone()
    return _fund_row(row) if row else None


def all_fundamentals(conn: sqlite3.Connection, tickers: list[str] | None = None) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM fundamentals ORDER BY ticker").fetchall()
    out = [_fund_row(r) for r in rows]
    if tickers is not None:
        wanted = set(tickers)
        out = [r for r in out if r["ticker"] in wanted]
    return out


def _fund_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["quarters"] = json.loads(d.pop("quarters_json") or "[]")
    return d


def upsert_fundamentals(conn: sqlite3.Connection, rec: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO fundamentals (ticker, name, sector, price, pe, roe, debt_to_equity,
            momentum_6m, quarters_json, quarters_available, fetched_at, error)
        VALUES (:ticker, :name, :sector, :price, :pe, :roe, :debt_to_equity,
            :momentum_6m, :quarters_json, :quarters_available, :fetched_at, :error)
        ON CONFLICT(ticker) DO UPDATE SET
            name=excluded.name, sector=excluded.sector, price=excluded.price, pe=excluded.pe,
            roe=excluded.roe, debt_to_equity=excluded.debt_to_equity,
            momentum_6m=excluded.momentum_6m, quarters_json=excluded.quarters_json,
            quarters_available=excluded.quarters_available, fetched_at=excluded.fetched_at,
            error=excluded.error
        """,
        {**rec, "quarters_json": json.dumps(rec.get("quarters") or [])},
    )


# ---------------------------------------------------------------- screener

def save_screen(conn: sqlite3.Connection, run_id: str, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        "INSERT INTO screen_results (run_id, rank, ticker, composite, scores_json, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (run_id, r["rank"], r["ticker"], r["composite"], json.dumps(r["scores"]), json.dumps(r["raw"]))
            for r in rows
        ],
    )


def latest_screen_run(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(run_id) AS r FROM screen_results").fetchone()
    return row["r"] if row else None


def get_screen(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM screen_results WHERE run_id = ? ORDER BY rank", (run_id,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["scores"] = json.loads(d.pop("scores_json"))
        d["raw"] = json.loads(d.pop("raw_json"))
        out.append(d)
    return out


# ---------------------------------------------------------------- LLM

def get_llm_cache(conn: sqlite3.Connection, ticker: str, doc_hash: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT result_json FROM llm_cache WHERE ticker = ? AND doc_hash = ?", (ticker, doc_hash)
    ).fetchone()
    return json.loads(row["result_json"]) if row else None


def put_llm_cache(conn: sqlite3.Connection, ticker: str, doc_hash: str, provider: str,
                  model: str, result: dict[str, Any]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache (ticker, doc_hash, provider, model, result_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, doc_hash, provider, model, json.dumps(result), utcnow_iso()),
    )
    conn.commit()  # persist immediately so a crash later doesn't waste the API call


def set_analysis_status(conn: sqlite3.Connection, run_id: str, ticker: str, status: str,
                        doc_hash: str | None = None, documents: list[str] | None = None,
                        message: str | None = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO analysis_status (run_id, ticker, status, doc_hash, documents, message) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, ticker, status, doc_hash, json.dumps(documents or []), message),
    )


def get_analysis(conn: sqlite3.Connection, run_id: str) -> dict[str, dict[str, Any]]:
    """ticker -> {status, documents, message, analysis (dict or None)}"""
    rows = conn.execute("SELECT * FROM analysis_status WHERE run_id = ?", (run_id,)).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = dict(r)
        d["documents"] = json.loads(d["documents"] or "[]")
        d["analysis"] = get_llm_cache(conn, d["ticker"], d["doc_hash"]) if d["doc_hash"] else None
        if d["status"] == "analyzed" and d["analysis"] is None:
            d["status"] = "error"
            d["message"] = "cached analysis missing"
        out[d["ticker"]] = d
    return out


# ---------------------------------------------------------------- sizing

def save_final(conn: sqlite3.Connection, run_id: str, rows: list[dict[str, Any]],
               summary: dict[str, Any]) -> None:
    conn.execute("DELETE FROM final_ranking WHERE run_id = ?", (run_id,))
    conn.executemany(
        "INSERT INTO final_ranking (run_id, rank, ticker, final_score, is_pick, quantity, cost, budget_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (run_id, r["rank"], r["ticker"], r["final_score"], int(r["is_pick"]),
             r.get("quantity"), r.get("cost"), r.get("budget_pct"))
            for r in rows
        ],
    )
    conn.execute(
        "INSERT OR REPLACE INTO sizing_summary (run_id, budget, invested, leftover, notes) VALUES (?, ?, ?, ?, ?)",
        (run_id, summary["budget"], summary["invested"], summary["leftover"], json.dumps(summary.get("notes", []))),
    )


def get_final(conn: sqlite3.Connection, run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM final_ranking WHERE run_id = ? ORDER BY rank", (run_id,)
    ).fetchall()]
    s = conn.execute("SELECT * FROM sizing_summary WHERE run_id = ?", (run_id,)).fetchone()
    summary = None
    if s:
        summary = dict(s)
        summary["notes"] = json.loads(summary["notes"] or "[]")
    return rows, summary
