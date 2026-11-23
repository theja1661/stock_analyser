"""Read-only views of pipeline output: summary, per-stock detail, HTML reports."""
from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from analyzer import db
from analyzer.common import load_config, project_path
from analyzer.llm_analysis import find_documents

from ..auth import AUTH
from ..jobs import job
from .documents import check_ticker

router = APIRouter(prefix="/api", dependencies=AUTH, tags=["results"])


def has_api_key(cfg: dict[str, Any]) -> bool:
    return bool(os.environ.get(cfg["llm"].get("api_key_env", "GEMINI_API_KEY"), "").strip())


def _brief(f: dict[str, Any]) -> dict[str, Any]:
    return {k: f.get(k) for k in ("name", "sector", "price", "pe", "roe", "debt_to_equity",
                                   "momentum_6m", "fetched_at")}


@router.get("/summary")
def summary() -> dict[str, Any]:
    """Everything the Picks and Stocks screens need, for the latest screen run."""
    cfg = load_config()
    db_path = project_path(cfg, "database")
    empty = {"run_id": None, "has_api_key": has_api_key(cfg), "job": job.status(include_lines=False)}
    if not db_path.exists():
        return empty
    with db.connect(db_path) as conn:
        run_id = db.latest_screen_run(conn)
        if not run_id:
            return empty
        screen = db.get_screen(conn, run_id)
        analysis = db.get_analysis(conn, run_id)
        final_rows, sizing = db.get_final(conn, run_id)
        funds = {r["ticker"]: db.get_fundamentals(conn, r["ticker"]) or {} for r in screen}
        n_funds = conn.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]

    final = {r["ticker"]: r for r in final_rows}
    docs_dir = project_path(cfg, "documents_dir")
    stocks = []
    for s in screen:
        t = s["ticker"]
        a = analysis.get(t, {})
        fr = final.get(t, {})
        stocks.append({
            "ticker": t,
            "screen_rank": s["rank"],
            "rank": fr.get("rank"),
            "quant": s["composite"],
            "scores": s["scores"],
            "raw": s["raw"],
            "final_score": fr.get("final_score"),
            "is_pick": bool(fr.get("is_pick")),
            "quantity": fr.get("quantity"),
            "cost": fr.get("cost"),
            "budget_pct": fr.get("budget_pct"),
            "status": a.get("status", "pending"),
            "status_message": a.get("message"),
            "analysis": a.get("analysis"),
            "documents_used": a.get("documents", []),
            "documents_now": [p.name for p in find_documents(docs_dir, t)],
            **_brief(funds[t]),
        })
    stocks.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0, x["screen_rank"]))
    fetched = [s["fetched_at"] for s in stocks if s["fetched_at"]]
    return {
        "run_id": run_id,
        "sized": bool(final_rows),
        "sizing": sizing,
        "budget": cfg.get("budget"),
        "universe_size": n_funds,
        "data_from": min(fetched) if fetched else None,
        "data_to": max(fetched) if fetched else None,
        "has_api_key": has_api_key(cfg),
        "stocks": stocks,
        "job": job.status(include_lines=False),
    }


@router.get("/stock/{ticker}")
def stock(ticker: str) -> dict[str, Any]:
    ticker = check_ticker(ticker)
    with db.connect(project_path(load_config(), "database")) as conn:
        f = db.get_fundamentals(conn, ticker)
    if not f:
        raise HTTPException(404, f"No data for {ticker}")
    return f


@router.get("/reports")
def list_reports() -> dict[str, Any]:
    d = project_path(load_config(), "reports_dir")
    files = sorted(d.glob("report_*.html"), reverse=True) if d.is_dir() else []
    return {"reports": [p.name for p in files]}


@router.get("/reports/{name}")
def get_report(name: str) -> FileResponse:
    if not re.fullmatch(r"report_\d{4}-\d{2}-\d{2}\.html", name):
        raise HTTPException(404, "Not found")
    p = project_path(load_config(), "reports_dir") / name
    if not p.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(p, media_type="text/html")
