// Bottom sheet with everything about one stock.
import { api } from "../lib/api.js";
import { METRIC_LABELS, crore, inr, num, pct, when } from "../lib/format.js";
import { html, useEffect, useState } from "../lib/react.js";
import { AnalysisBlock } from "./AnalysisBlock.js";
import { Icon } from "./Icons.js";
import { Spinner, StatusBadge } from "./common.js";

const Metric = ({ k, v, small }) => html`<div class="metric"><div class="k">${k}</div><div class=${"v" + (small ? " small" : "")}>${v}</div></div>`;

export function StockSheet({ s, onClose, go }) {
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api("/api/stock/" + encodeURIComponent(s.ticker)).then(setF).catch((e) => setErr(e.message));
  }, [s.ticker]);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  const raw = s.raw || {}, sc = s.scores || {};
  const rawFmt = {
    valuation: raw.valuation == null ? num(null) : num(raw.valuation, 2) + "×",
    roe: pct(raw.roe, false), debt_to_equity: num(raw.debt_to_equity, 2),
    revenue_growth: pct(raw.revenue_growth), profit_growth: pct(raw.profit_growth), momentum: pct(raw.momentum),
  };

  return html`<div class="sheet-bg" onClick=${(e) => e.target === e.currentTarget && onClose()}>
    <div class="sheet" role="dialog" aria-modal="true" aria-label=${s.ticker}>
      <div class="grab"></div>
      <div class="row between">
        <div class="grow">
          <h2 style=${{ margin: 0, fontSize: 20 }}>${s.name || s.ticker}</h2>
          <div class="muted small">NSE: ${s.ticker} · ${s.sector || "sector missing"}</div>
        </div>
        <button class="icon-btn" aria-label="Close" onClick=${onClose}>${Icon.close}</button>
      </div>

      <div class="row wrap" style=${{ gap: 6, margin: "10px 0" }}>
        ${s.is_pick && html`<span class="badge pick">Pick #${s.rank}: buy ${s.quantity}</span>`}
        <${StatusBadge} s=${s} />
        <span class="badge">quant ${s.quant.toFixed(1)}</span>
        ${s.final_score != null && html`<span class="badge">final ${s.final_score.toFixed(1)}</span>`}
      </div>
      ${s.status === "error" && html`<p class="badge err" style=${{ whiteSpace: "normal" }}>${s.status_message}</p>`}

      <div class="metrics" style=${{ marginTop: 8 }}>
        <${Metric} k="Price" v=${inr(s.price)} />
        <${Metric} k="Trailing P/E" v=${num(s.pe, 1)} />
        <${Metric} k="ROE" v=${pct(s.roe, false)} />
        <${Metric} k="Debt / equity" v=${num(s.debt_to_equity, 2)} />
        <${Metric} k="6-month return" v=${pct(s.momentum_6m)} />
        <${Metric} k="Data fetched" v=${when(s.fetched_at)} small />
      </div>

      <div class="section-title">Quant scores (0–100, percentile)</div>
      <div class="card">
        ${Object.keys(METRIC_LABELS).map((m) => html`<div key=${m} style=${{ marginBottom: 10 }}>
          <div class="row between small">
            <span>${METRIC_LABELS[m]} <span class="muted">· ${rawFmt[m]}</span></span>
            <b class="num">${sc[m] != null ? sc[m].toFixed(0) : "0"}</b>
          </div>
          <div class="bar"><i style=${{ width: (sc[m] || 0) + "%" }}></i></div>
        </div>`)}
      </div>

      <div class="section-title">Quarterly results</div>
      <div class="card">
        ${err ? html`<p class="neg">${err}</p>`
          : !f ? html`<${Spinner} />`
          : f.quarters && f.quarters.length
            ? html`<table class="q">
                <thead><tr><th>Quarter</th><th>Revenue</th><th>Net profit</th></tr></thead>
                <tbody>${f.quarters.map((q) => html`<tr key=${q.period}><td>${q.period}</td><td>${crore(q.revenue)}</td><td>${crore(q.net_profit)}</td></tr>`)}</tbody>
              </table>`
            : html`<p class="na">No quarterly data</p>`}
        ${f && f.error && html`<p class="muted small" style=${{ marginBottom: 0 }}>Fetch notes: ${f.error}</p>`}
      </div>

      <div class="section-title">LLM analysis</div>
      <div class="card">
        <${AnalysisBlock} s=${s} />
        <p class="muted small" style=${{ marginBottom: 0 }}>Documents on disk now: ${s.documents_now.length ? s.documents_now.join(", ") : "none"}</p>
        <button class="btn sm" style=${{ marginTop: 10 }} onClick=${() => { onClose(); go("docs"); }}>Manage documents</button>
      </div>
    </div>
  </div>`;
}
