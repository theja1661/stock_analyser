"""Stage 5: standalone HTML report (inline CSS, no external resources)."""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from . import db
from .common import log, project_path

MISSING = '<span class="na">missing</span>'

CSS = """
:root { --ink:#1d2330; --muted:#667085; --line:#e4e7ec; --bg:#f7f8fa; --card:#fff;
        --accent:#1f5fbf; --good:#147a4b; --bad:#b42318; --warn-bg:#fff6e5; --warn:#8a5a00; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width:1180px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:24px; margin:0 0 4px; }
h2 { font-size:18px; margin:32px 0 12px; }
h3 { font-size:17px; margin:0; }
.sub { color:var(--muted); margin:0 0 16px; }
.disclaimer { background:var(--warn-bg); color:var(--warn); border:1px solid #f3d9a4;
              border-radius:8px; padding:10px 14px; font-weight:600; margin-bottom:20px; }
.summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.stat .k { color:var(--muted); font-size:13px; }
.stat .v { font-size:22px; font-weight:650; font-variant-numeric:tabular-nums; }
.notes { margin:12px 0 0; padding-left:20px; color:var(--muted); }
.picks { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px; }
.card .head { display:flex; justify-content:space-between; gap:12px; align-items:baseline; }
.card .meta { color:var(--muted); font-size:13px; margin:2px 0 12px; }
.score { font-size:26px; font-weight:700; color:var(--accent); font-variant-numeric:tabular-nums; }
.score small { font-size:12px; color:var(--muted); font-weight:500; display:block; text-align:right; }
.buy { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; background:var(--bg);
       border-radius:8px; padding:10px; margin-bottom:12px; font-variant-numeric:tabular-nums; }
.buy div span { display:block; color:var(--muted); font-size:12px; }
.buy div b { font-size:16px; }
.label { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted);
         margin:12px 0 4px; font-weight:600; }
.thesis { white-space:pre-line; margin:0; }
ul { margin:0; padding-left:20px; }
.flags li { color:var(--bad); }
.none { color:var(--good); }
.badge { display:inline-block; font-size:12px; padding:1px 8px; border-radius:999px;
         border:1px solid var(--line); color:var(--muted); background:var(--bg); white-space:nowrap; }
.badge.ok { color:var(--good); border-color:#b7e0c8; background:#eefaf3; }
.badge.err { color:var(--bad); border-color:#f5c2bd; background:#fdf1f0; }
.tablewrap { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:12px; }
table { border-collapse:collapse; width:100%; font-size:13.5px; }
th, td { padding:8px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
th { background:#f0f2f5; font-weight:600; color:#344054; position:sticky; top:0; }
td.l, th.l { text-align:left; }
tr:last-child td { border-bottom:none; }
tr.pick td { background:#f2f7ff; }
td { font-variant-numeric:tabular-nums; }
.na { color:#98a2b3; font-style:italic; }
.pos { color:var(--good); } .neg { color:var(--bad); }
footer { color:var(--muted); font-size:12.5px; margin-top:28px; }
"""


def _e(v: Any) -> str:
    return escape(str(v)) if v is not None else ""


def _num(v: float | None, digits: int = 2) -> str:
    return MISSING if v is None else f"{v:,.{digits}f}"


def _pct(v: float | None, signed: bool = True) -> str:
    if v is None:
        return MISSING
    cls = "pos" if v > 0 else "neg" if v < 0 else ""
    txt = f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"
    return f'<span class="{cls}">{txt}</span>' if signed else txt


def _status_badge(status: str, message: str | None = None) -> str:
    if status == "analyzed":
        return '<span class="badge ok">LLM analyzed</span>'
    if status == "error":
        return f'<span class="badge err" title="{_e(message)}">LLM failed (quant-only)</span>'
    return '<span class="badge">quant-only</span>'


def _list(items: list[str], cls: str = "", empty: str = "None") -> str:
    if not items:
        return f'<p class="none" style="margin:0">{escape(empty)}</p>'
    return f'<ul class="{cls}">' + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"


def _pick_card(r: dict[str, Any], f: dict[str, Any], a: dict[str, Any]) -> str:
    an = a.get("analysis")
    if r["final_score"] is not None:
        score = f'{r["final_score"]:.1f}<small>final score</small>'
    else:
        score = f'{r["quant"]:.1f}<small>quant score only</small>'
    body = ""
    if an:
        body = (
            f'<div class="label">Thesis</div><p class="thesis">{_e(an["thesis"])}</p>'
            f'<div class="label">Risks</div>{_list(an["risks"])}'
            f'<div class="label">Red flags</div>{_list(an["red_flags"], "flags", "None identified")}'
            f'<div class="label">Guidance</div><p style="margin:0">{_e(an["guidance_summary"])}</p>'
            f'<div class="label">Sources</div><p class="meta" style="margin:0">'
            f'{_e(", ".join(a.get("documents") or []))}</p>'
        )
    else:
        body = ('<p class="meta">No LLM analysis: thesis, risks and red flags are unavailable. '
                f'Drop quarterly documents into <code>data/documents/{_e(r["ticker"])}/</code> and re-run.</p>')
    conv = f' · conviction {an["conviction"]}/10' if an else ""
    return f"""
<article class="card">
  <div class="head">
    <div><h3>{_e(f.get("name") or r["ticker"])}</h3>
      <div class="meta">NSE: {_e(r["ticker"])} · {_e(f.get("sector") or "sector missing")}
        · quant {r["quant"]:.1f}{conv} · {_status_badge(r["status"], a.get("message"))}</div></div>
    <div class="score">{score}</div>
  </div>
  <div class="buy">
    <div><span>Quantity</span><b>{r["quantity"]}</b> @ ₹{r["price"]:,.2f}</div>
    <div><span>Cost</span><b>₹{r["cost"]:,.2f}</b></div>
    <div><span>% of budget</span><b>{r["budget_pct"]:.1f}%</b></div>
  </div>
  {body}
</article>"""


def build_html(cfg: dict[str, Any], run_id: str, ranked: list[dict[str, Any]],
               summary: dict[str, Any], screen: dict[str, dict[str, Any]],
               funds: dict[str, dict[str, Any]], analysis: dict[str, dict[str, Any]]) -> str:
    today = date.today().isoformat()
    picks = [r for r in ranked if r["is_pick"]]
    for p in picks:
        p["price"] = funds.get(p["ticker"], {}).get("price")

    fetched = [f["fetched_at"] for f in funds.values() if f.get("fetched_at")]
    freshness = (f"{min(fetched)[:10]} to {max(fetched)[:10]}" if fetched else "unknown")

    cards = "".join(_pick_card(p, funds.get(p["ticker"], {}), analysis.get(p["ticker"], {}))
                    for p in picks) or '<p class="meta">No picks could be made this week.</p>'
    notes = "".join(f"<li>{escape(n)}</li>" for n in summary.get("notes", []))

    rows_html = []
    for r in ranked:
        t = r["ticker"]
        f = funds.get(t, {})
        raw = screen.get(t, {}).get("raw", {})
        a = analysis.get(t, {})
        conv = (a.get("analysis") or {}).get("conviction")
        rows_html.append(f"""
<tr class="{"pick" if r["is_pick"] else ""}">
  <td>{r["rank"]}</td>
  <td class="l"><b>{_e(t)}</b>{" ★" if r["is_pick"] else ""}<br><span class="meta">{_e(f.get("name") or "")}</span></td>
  <td class="l">{_e(f.get("sector")) or MISSING}</td>
  <td>{_num(f.get("price"))}</td>
  <td>{_num(f.get("pe"), 1)}</td>
  <td>{_num(raw.get("valuation"), 2)}</td>
  <td>{_pct(f.get("roe"), signed=False)}</td>
  <td>{_num(f.get("debt_to_equity"), 2)}</td>
  <td>{_pct(raw.get("revenue_growth"))}</td>
  <td>{_pct(raw.get("profit_growth"))}</td>
  <td>{_pct(f.get("momentum_6m"))}</td>
  <td><b>{r["quant"]:.1f}</b></td>
  <td>{conv if conv is not None else "—"}</td>
  <td><b>{f'{r["final_score"]:.1f}' if r["final_score"] is not None else "—"}</b></td>
  <td class="l">{_status_badge(r["status"], a.get("message"))}</td>
</tr>""")

    w = cfg["screener"]["weights"]
    weights_txt = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in w.items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stock Picks {today}</title>
<style>{CSS}</style></head>
<body><main>
<div class="disclaimer">Personal research tool. Not investment advice.</div>
<h1>Weekly NSE stock report</h1>
<p class="sub">Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} · screen run {escape(run_id)}
  · market data fetched {escape(freshness)} (Yahoo Finance)</p>

<section class="summary">
  <div class="stat"><div class="k">Budget</div><div class="v">₹{summary["budget"]:,.0f}</div></div>
  <div class="stat"><div class="k">Invested</div><div class="v">₹{summary["invested"]:,.2f}</div></div>
  <div class="stat"><div class="k">Leftover cash</div><div class="v">₹{summary["leftover"]:,.2f}</div></div>
  <div class="stat"><div class="k">Picks</div><div class="v">{len(picks)}</div></div>
</section>
{f'<ul class="notes">{notes}</ul>' if notes else ""}

<h2>Suggested picks</h2>
<section class="picks">{cards}</section>

<h2>All screened stocks (top {len(ranked)} by quant score)</h2>
<div class="tablewrap"><table>
<thead><tr>
  <th>#</th><th class="l">Stock</th><th class="l">Sector</th><th>Price ₹</th><th>P/E</th>
  <th title="P/E divided by sector median">P/E ÷ sector</th><th>ROE</th><th>D/E</th>
  <th>Rev growth</th><th>Profit growth</th><th>6m return</th><th>Quant</th>
  <th>Conviction</th><th>Final</th><th class="l">Analysis</th>
</tr></thead>
<tbody>{"".join(rows_html)}</tbody></table></div>

<footer>
  <p>Final score = {cfg["sizing"].get("quant_weight", 0.5)} × quant score + {cfg["sizing"].get("llm_weight", 0.5)} × (conviction × 10).
  Stocks without LLM analysis are ranked after analyzed ones by quant score.
  Quant score is a weighted average of percentile ranks (0-100) within the filtered universe
  ({escape(weights_txt)}); a missing metric scores 0. Growth compares the newest of the last 4
  quarters with the oldest. Hard filters: price ≤ ₹{cfg["screener"].get("max_price", 2000):,}
  and ≥ {cfg["screener"].get("min_quarters", 3)} of 4 quarters of data.</p>
  <p>Data from Yahoo Finance can be incomplete or delayed; verify figures against exchange filings before acting.</p>
</footer>
</main></body></html>
"""


def run(cfg: dict[str, Any]) -> Path | None:
    with db.connect(project_path(cfg, "database")) as conn:
        run_id = db.latest_screen_run(conn)
        if not run_id:
            log.error("No screener results. Run the pipeline first.")
            return None
        ranked_rows, summary = db.get_final(conn, run_id)
        if not ranked_rows or summary is None:
            log.error("No sizing results for screen run %s. Run the sizing stage first.", run_id)
            return None
        screen = {r["ticker"]: r for r in db.get_screen(conn, run_id)}
        analysis = db.get_analysis(conn, run_id)
        funds = {t: (db.get_fundamentals(conn, t) or {}) for t in screen}

    ranked = []
    for r in ranked_rows:
        a = analysis.get(r["ticker"], {})
        status = a.get("status", "quant-only")
        ranked.append({**r, "is_pick": bool(r["is_pick"]), "quant": screen[r["ticker"]]["composite"],
                       "status": status})

    html = build_html(cfg, run_id, ranked, summary, screen, funds, analysis)
    out_dir = project_path(cfg, "reports_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"report_{date.today().isoformat()}.html"
    out.write_text(html, encoding="utf-8")
    log.info("Report written: %s", out)
    return out
