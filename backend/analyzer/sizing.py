"""Stage 4: blend quant + LLM scores, pick the top N, size whole-share positions."""
from __future__ import annotations

import math
from typing import Any

from . import db
from .common import log, project_path


def rank_candidates(screen: list[dict[str, Any]], analysis: dict[str, dict[str, Any]],
                    cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyzed stocks ranked by final score, then the rest by quant score."""
    s = cfg["sizing"]
    qw, lw = float(s.get("quant_weight", 0.5)), float(s.get("llm_weight", 0.5))
    analyzed, others = [], []
    for row in screen:
        a = analysis.get(row["ticker"], {})
        item = {
            "ticker": row["ticker"],
            "quant": row["composite"],     # already 0-100 (weighted mean of 0-100 scores)
            "status": a.get("status", "quant-only"),
            "conviction": None,
            "final_score": None,
        }
        if item["status"] == "analyzed" and a.get("analysis"):
            item["conviction"] = a["analysis"]["conviction"]
            item["final_score"] = round(qw * item["quant"] + lw * item["conviction"] * 10, 2)
            analyzed.append(item)
        else:
            others.append(item)
    analyzed.sort(key=lambda x: x["final_score"], reverse=True)
    others.sort(key=lambda x: x["quant"], reverse=True)
    ranked = analyzed + others
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def allocate(ranked: list[dict[str, Any]], prices: dict[str, float | None],
             cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    s = cfg["sizing"]
    budget = float(cfg.get("budget", 6000))
    n = int(s.get("num_picks", 3))
    min_analyzed = int(s.get("min_analyzed_for_picks", 3))
    notes: list[str] = []

    n_analyzed = sum(1 for r in ranked if r["status"] == "analyzed")
    eligible = [r for r in ranked if r["status"] == "analyzed"]
    if n_analyzed < min_analyzed:
        eligible = ranked  # analyzed first, then quant-only by quant score
        notes.append(f"Only {n_analyzed} stock(s) had LLM analysis, so quant-only stocks were "
                     f"allowed into the picks.")

    per_pick = budget / n
    picks: list[dict[str, Any]] = []
    for r in eligible:
        if len(picks) == n:
            break
        price = prices.get(r["ticker"])
        if not price:
            notes.append(f"{r['ticker']} skipped: no current price.")
            continue
        qty = math.floor(per_pick / price)
        if qty == 0:
            notes.append(f"{r['ticker']} skipped: one share (INR {price:,.2f}) exceeds the "
                         f"INR {per_pick:,.0f} allocation.")
            continue
        r.update(is_pick=True, price=price, quantity=qty)
        picks.append(r)

    if len(picks) < n:
        notes.append(f"Only {len(picks)} pick(s) could be made out of {n} wanted.")

    # Optional top-up: spend leftover on extra whole shares, always adding to the
    # currently smallest position (keeps weights close to equal), and never letting
    # a position exceed max_position_pct of the budget.
    if s.get("topup_leftover", True) and picks:
        cap = budget * float(s.get("max_position_pct", 45)) / 100.0
        leftover = budget - sum(p["price"] * p["quantity"] for p in picks)
        while True:
            options = [p for p in picks
                       if p["price"] <= leftover + 1e-9 and p["price"] * (p["quantity"] + 1) <= cap]
            if not options:
                break
            p = min(options, key=lambda x: x["price"] * x["quantity"])
            p["quantity"] += 1
            leftover -= p["price"]

    for r in ranked:
        r.setdefault("is_pick", False)
        if r["is_pick"]:
            r["cost"] = round(r["price"] * r["quantity"], 2)
            r["budget_pct"] = round(r["cost"] / budget * 100, 2)
        else:
            r["quantity"] = r["cost"] = r["budget_pct"] = None

    invested = round(sum(p["cost"] for p in picks), 2)
    summary = {"budget": budget, "invested": invested,
               "leftover": round(budget - invested, 2), "notes": notes}
    return ranked, summary


def run(cfg: dict[str, Any]) -> None:
    with db.connect(project_path(cfg, "database")) as conn:
        run_id = db.latest_screen_run(conn)
        if not run_id:
            log.error("No screener results. Run the screener stage first.")
            return
        screen = db.get_screen(conn, run_id)
        analysis = db.get_analysis(conn, run_id)
        if not analysis:
            log.warning("No LLM stage results for this screen run; treating all as quant-only.")
        prices = {r["ticker"]: (db.get_fundamentals(conn, r["ticker"]) or {}).get("price") for r in screen}

        ranked = rank_candidates(screen, analysis, cfg)
        ranked, summary = allocate(ranked, prices, cfg)
        db.save_final(conn, run_id, ranked, summary)

    log.info("Picks (budget INR %.0f):", summary["budget"])
    for r in ranked:
        if r["is_pick"]:
            score = f"final {r['final_score']:.1f}" if r["final_score"] is not None else f"quant {r['quant']:.1f} (quant-only)"
            log.info("  %-12s %s  x%d @ %.2f = INR %.2f (%.1f%%)", r["ticker"], score,
                     r["quantity"], r["price"], r["cost"], r["budget_pct"])
    log.info("Invested INR %.2f, leftover cash INR %.2f", summary["invested"], summary["leftover"])
    for n in summary["notes"]:
        log.info("  note: %s", n)
