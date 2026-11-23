"""Stage 1: fetch prices and fundamentals from Yahoo Finance (yfinance) into SQLite.

Only real fetched values are stored. Anything yfinance doesn't return is stored
as NULL and later scored 0 by the screener.
"""
from __future__ import annotations

import csv
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from . import db
from .common import env_ca_hint, log, project_path, resolve_ca_bundle

REVENUE_ROWS = ("Total Revenue", "Operating Revenue")
PROFIT_ROWS = ("Net Income", "Net Income Common Stockholders",
               "Net Income From Continuing Operation Net Minority Interest")


def load_universe(csv_path: Path) -> list[str]:
    tickers: list[str] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip().upper()
            if sym and not sym.startswith("#"):
                tickers.append(sym.removesuffix(".NS"))
    # de-duplicate, keep order
    return list(dict.fromkeys(tickers))


def _num(v: Any) -> float | None:
    """Coerce to float; NaN/inf/garbage -> None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _make_session(cfg: dict[str, Any]) -> Any | None:
    bundle = resolve_ca_bundle(cfg)
    if not bundle:
        return None
    try:
        from curl_cffi import requests as curl_requests

        return curl_requests.Session(impersonate="chrome", verify=bundle)
    except Exception as e:
        log.warning("Could not create custom HTTP session (%s); using yfinance default", e)
        return None


def _quarters(stmt: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Last 4 quarters (newest first) of revenue and net profit; missing -> None."""
    if stmt is None or stmt.empty:
        return []

    def pick_row(names: tuple[str, ...]) -> pd.Series | None:
        for n in names:
            if n in stmt.index:
                return stmt.loc[n]
        return None

    rev = pick_row(REVENUE_ROWS)
    prof = pick_row(PROFIT_ROWS)
    cols = sorted(stmt.columns, reverse=True)[:4]
    out = []
    for c in cols:
        out.append({
            "period": pd.Timestamp(c).date().isoformat(),
            "revenue": _num(rev[c]) if rev is not None else None,
            "net_profit": _num(prof[c]) if prof is not None else None,
        })
    return out


def fetch_ticker(symbol: str, cfg: dict[str, Any], session: Any | None) -> dict[str, Any]:
    """Fetch one ticker. Never raises; problems are recorded in rec['error']."""
    suffix = cfg["ingestion"].get("exchange_suffix", ".NS")
    yt = yf.Ticker(f"{symbol}{suffix}", session=session) if session else yf.Ticker(f"{symbol}{suffix}")
    errors: list[str] = []
    rec: dict[str, Any] = {
        "ticker": symbol, "name": None, "sector": None, "price": None, "pe": None,
        "roe": None, "debt_to_equity": None, "momentum_6m": None, "quarters": [],
        "quarters_available": 0, "fetched_at": db.utcnow_iso(), "error": None,
    }

    # --- summary info (price, ratios, sector)
    try:
        info = yt.info or {}
        rec["name"] = info.get("longName") or info.get("shortName")
        rec["sector"] = info.get("sector")
        rec["price"] = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
        pe = _num(info.get("trailingPE"))
        rec["pe"] = pe if pe is not None and pe > 0 else None  # negative/zero P/E is not meaningful
        rec["roe"] = _num(info.get("returnOnEquity"))
        de = _num(info.get("debtToEquity"))
        rec["debt_to_equity"] = de / 100.0 if de is not None else None  # Yahoo reports D/E in percent
        if not info or rec["name"] is None:
            errors.append("summary info empty")
    except Exception as e:
        errors.append(f"info: {type(e).__name__}: {e}")

    # --- price history -> 6-month momentum (and price fallback)
    try:
        hist = yt.history(period=cfg["ingestion"].get("momentum_period", "6mo"), auto_adjust=True)
        closes = hist["Close"].dropna() if not hist.empty else pd.Series(dtype=float)
        if len(closes) >= 2 and closes.iloc[0] > 0:
            rec["momentum_6m"] = float(closes.iloc[-1] / closes.iloc[0] - 1.0)
        if rec["price"] is None and len(closes):
            rec["price"] = float(closes.iloc[-1])
        if closes.empty:
            errors.append("no price history")
    except Exception as e:
        errors.append(f"history: {type(e).__name__}: {e}")

    # --- quarterly income statement
    try:
        rec["quarters"] = _quarters(yt.quarterly_financials)
        rec["quarters_available"] = sum(
            1 for q in rec["quarters"] if q["revenue"] is not None and q["net_profit"] is not None
        )
        if not rec["quarters"]:
            errors.append("no quarterly financials")
    except Exception as e:
        errors.append(f"quarterly: {type(e).__name__}: {e}")

    rec["error"] = "; ".join(errors) or None
    return rec


def _is_fresh(existing: dict[str, Any] | None, max_age: timedelta) -> bool:
    if not existing or existing.get("price") is None:
        return False
    try:
        fetched = datetime.fromisoformat(existing["fetched_at"])
    except (TypeError, ValueError):
        return False
    return datetime.now(timezone.utc) - fetched < max_age


def run(cfg: dict[str, Any], force: bool = False) -> None:
    universe = load_universe(project_path(cfg, "universe_csv"))
    log.info("Universe: %d tickers from %s", len(universe), cfg["paths"]["universe_csv"])
    max_age = timedelta(days=float(cfg["ingestion"].get("cache_days", 3)))
    delay = float(cfg["ingestion"].get("request_delay_seconds", 1.0))
    session = _make_session(cfg)

    fetched = cached = failed = 0
    with db.connect(project_path(cfg, "database")) as conn:
        for i, sym in enumerate(universe, 1):
            existing = db.get_fundamentals(conn, sym)
            if not force and _is_fresh(existing, max_age):
                cached += 1
                log.debug("[%d/%d] %s: cached (%s)", i, len(universe), sym, existing["fetched_at"])
                continue
            try:
                rec = fetch_ticker(sym, cfg, session)
            except Exception as e:  # belt and braces: one ticker must never kill the run
                log.error("[%d/%d] %s: unexpected failure: %s", i, len(universe), sym, e)
                failed += 1
                continue

            if rec["price"] is None and existing and existing.get("price") is not None:
                log.warning("[%d/%d] %s: fetch failed (%s); keeping older cached data",
                            i, len(universe), sym, rec["error"])
                failed += 1
                continue

            db.upsert_fundamentals(conn, rec)
            conn.commit()
            fetched += 1
            missing = [k for k in ("price", "pe", "roe", "debt_to_equity", "momentum_6m", "sector")
                       if rec[k] is None]
            level = log.warning if rec["price"] is None else log.info
            level("[%d/%d] %s: price=%s, quarters=%d/4%s%s", i, len(universe), sym,
                  f"{rec['price']:.2f}" if rec["price"] is not None else "MISSING",
                  rec["quarters_available"],
                  f", missing: {', '.join(missing)}" if missing else "",
                  f" ({rec['error']})" if rec["error"] else "")
            if rec["error"] and "CertificateVerify" in rec["error"]:
                log.warning(env_ca_hint())
            time.sleep(delay)

    log.info("Ingestion done: %d fetched, %d from cache (<%s days old), %d failed",
             fetched, cached, cfg["ingestion"].get("cache_days", 3), failed)
