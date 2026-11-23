// This week's picks: budget summary + one card per pick.
import { inr, when } from "../lib/format.js";
import { html, useState } from "../lib/react.js";
import { AnalysisBlock } from "../components/AnalysisBlock.js";
import { Loading, StatusBadge, scoreOf } from "../components/common.js";

function PickCard({ s, onOpen }) {
  const [open, setOpen] = useState(false);
  const score = scoreOf(s);
  return html`<div class="card">
    <div class="pick-head">
      <div class="grow">
        <h3 class="ellipsis">${s.name || s.ticker}</h3>
        <div class="muted small">${s.ticker} · ${s.sector || "sector missing"}</div>
        <div class="row wrap" style=${{ marginTop: 6, gap: 6 }}>
          <${StatusBadge} s=${s} />
          ${s.analysis && html`<span class="badge pick">conviction ${s.analysis.conviction}/10</span>`}
        </div>
      </div>
      <div class="score">${score.value}<small>${score.label === "final" ? "final score" : "quant only"}</small></div>
    </div>
    <div class="buy">
      <div><span>Buy</span><b>${s.quantity}</b> <span style=${{ display: "inline" }}>@ ${inr(s.price)}</span></div>
      <div><span>Cost</span><b>${inr(s.cost)}</b></div>
      <div><span>% of budget</span><b>${s.budget_pct != null ? s.budget_pct.toFixed(1) + "%" : "—"}</b></div>
    </div>
    ${open ? html`<${AnalysisBlock} s=${s} />`
      : s.analysis ? html`<p class="thesis small" style=${{ marginTop: 10 }}>${s.analysis.thesis}</p>` : null}
    <div class="row" style=${{ marginTop: 12, gap: 8 }}>
      <button class="btn sm" onClick=${() => setOpen(!open)}>${open ? "Show less" : "Thesis, risks & flags"}</button>
      <button class="btn sm" onClick=${() => onOpen(s)}>Details</button>
    </div>
  </div>`;
}

const EmptyState = ({ title, text, go }) => html`<div class="card empty">
  <h3>${title}</h3><p>${text}</p>
  <button class="btn primary" onClick=${() => go("run")}>Go to Run</button>
</div>`;

export function PicksPage({ data, onOpen, go }) {
  if (!data) return html`<${Loading} />`;
  if (!data.run_id) return html`<${EmptyState} go=${go} title="No results yet"
    text="Run the pipeline to fetch data, screen stocks and size positions." />`;
  if (!data.sized) return html`<${EmptyState} go=${go} title="Screen done, not sized yet"
    text=${`The latest screen (${when(data.run_id)}) has no picks yet. Run the LLM, sizing and report stages.`} />`;

  const picks = data.stocks.filter((s) => s.is_pick).sort((a, b) => a.rank - b.rank);
  const z = data.sizing;
  return html`<div>
    <div class="stats">
      <div class="stat"><div class="k">Budget</div><div class="v">${inr(z.budget, 0)}</div></div>
      <div class="stat"><div class="k">Invested</div><div class="v">${inr(z.invested, 0)}</div></div>
      <div class="stat"><div class="k">Leftover</div><div class="v">${inr(z.leftover, 0)}</div></div>
    </div>
    ${z.budget !== data.budget && html`<p class="badge warn" style=${{ margin: "4px 0" }}>Budget changed to ${inr(data.budget, 0)}; re-size to apply</p>`}
    ${z.notes && z.notes.length ? html`<ul class="notes">${z.notes.map((n, i) => html`<li key=${i}>${n}</li>`)}</ul>` : null}
    <div class="section-title">Suggested picks</div>
    ${picks.length ? picks.map((s) => html`<${PickCard} key=${s.ticker} s=${s} onOpen=${onOpen} />`)
      : html`<div class="card empty">No picks could be made.</div>`}
    <p class="muted small">Screen run ${when(data.run_id)} · market data ${when(data.data_to)} (Yahoo Finance).
      Verify figures against exchange filings before acting.</p>
  </div>`;
}
