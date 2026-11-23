"""Stage 2: hard filters + 6-metric quant score.

Each metric is normalized to 0-100 by percentile rank across the filtered
universe, so a single extreme outlier can't squash everyone else's score.
Stocks missing a metric get 0 for it.
"""
from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

import pandas as pd

from . import db
from .common import log, project_path
from .ingestion import load_universe

# metric -> True if higher raw value is better
METRICS: dict[str, bool] = {
    "valuation": False,       # P/E relative to sector median
    "roe": True,
    "debt_to_equity": False,
    "revenue_growth": True,
    "profit_growth": True,
    "momentum": True,
}


def growth(quarters: list[dict[str, Any]], key: str) -> float | None:
    """Change from the oldest to the newest available value in the last 4 quarters."""
    vals = [q[key] for q in quarters if q.get(key) is not None]  # newest first
    if len(vals) < 2:
        return None
    newest, oldest = vals[0], vals[-1]
    if oldest == 0:
        return None
    return (newest - oldest) / abs(oldest)


def percentile_scores(values: pd.Series, higher_is_better: bool) -> pd.Series:
    """Map values to 0-100 (best=100). NaN -> 0."""
    present = values.dropna()
    scores = pd.Series(0.0, index=values.index)
    if present.empty:
        return scores
    if len(present) == 1:
        scores[present.index] = 100.0
        return scores
    ranks = present.rank(method="average", ascending=higher_is_better)  # 1 = worst
    scores[present.index] = (ranks - 1) / (len(present) - 1) * 100.0
    return scores


def score_universe(funds: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    scfg = cfg["screener"]
    max_price = float(scfg.get("max_price", 2000))
    min_q = int(scfg.get("min_quarters", 3))

    # Sector medians use every stock with a valid P/E, not just the filtered set,
    # so the benchmark is as broad as possible.
    by_sector: dict[str, list[float]] = {}
    for f in funds:
        if f["sector"] and f["pe"] is not None:
            by_sector.setdefault(f["sector"], []).append(f["pe"])
    sector_median = {s: median(v) for s, v in by_sector.items()}

    passed: list[dict[str, Any]] = []
    for f in funds:
        if f["price"] is None:
            log.info("  drop %-12s price missing", f["ticker"])
        elif f["price"] > max_price:
            log.info("  drop %-12s price %.0f > %.0f", f["ticker"], f["price"], max_price)
        elif (f["quarters_available"] or 0) < min_q:
            log.info("  drop %-12s only %d/4 quarters of data", f["ticker"], f["quarters_available"] or 0)
        else:
            passed.append(f)
    log.info("Hard filters: %d of %d stocks pass", len(passed), len(funds))
    if not passed:
        return []

    raw = pd.DataFrame(
        {
            "valuation": [
                (f["pe"] / sector_median[f["sector"]])
                if f["pe"] is not None and f["sector"] in sector_median else None
                for f in passed
            ],
            "roe": [f["roe"] for f in passed],
            "debt_to_equity": [f["debt_to_equity"] for f in passed],
            "revenue_growth": [growth(f["quarters"], "revenue") for f in passed],
            "profit_growth": [growth(f["quarters"], "net_profit") for f in passed],
            "momentum": [f["momentum_6m"] for f in passed],
        },
        index=[f["ticker"] for f in passed],
        dtype="float64",
    )

    weights = {m: float(scfg["weights"].get(m, 0)) for m in METRICS}
    total_w = sum(weights.values()) or 1.0
    scores = pd.DataFrame({m: percentile_scores(raw[m], hib) for m, hib in METRICS.items()})
    composite = sum(scores[m] * weights[m] for m in METRICS) / total_w

    rows = []
    for t in raw.index:
        rows.append({
            "ticker": t,
            "composite": round(float(composite[t]), 2),
            "scores": {m: round(float(scores.at[t, m]), 1) for m in METRICS},
            "raw": {m: (None if pd.isna(raw.at[t, m]) else float(raw.at[t, m])) for m in METRICS},
        })
    rows.sort(key=lambda r: r["composite"], reverse=True)
    return rows


def run(cfg: dict[str, Any]) -> str | None:
    universe = load_universe(project_path(cfg, "universe_csv"))
    with db.connect(project_path(cfg, "database")) as conn:
        funds = db.all_fundamentals(conn, universe)
        if not funds:
            log.error("No fundamentals in the database. Run the ingest stage first.")
            return None
        rows = score_universe(funds, cfg)
        if not rows:
            log.error("No stocks survived the hard filters; nothing to rank.")
            return None
        top = rows[: int(cfg["screener"].get("top_n", 15))]
        for i, r in enumerate(top, 1):
            r["rank"] = i
        run_id = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        db.save_screen(conn, run_id, top)

    log.info("Top %d by composite quant score (run %s):", len(top), run_id)
    for r in top:
        missing = [m for m, v in r["raw"].items() if v is None]
        log.info("  %2d. %-12s %5.1f%s", r["rank"], r["ticker"], r["composite"],
                 f"  (missing: {', '.join(missing)})" if missing else "")
    return run_id
