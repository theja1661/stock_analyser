// The screened shortlist; tap a row for the detail sheet.
import { inr, num, pct } from "../lib/format.js";
import { html, useState } from "../lib/react.js";
import { Loading, StatusBadge, scoreOf } from "../components/common.js";

const FILTERS = {
  all: { label: (d) => "All " + d.stocks.length, keep: () => true },
  analyzed: { label: () => "Analyzed", keep: (s) => s.status === "analyzed" },
  needs: { label: () => "Need docs", keep: (s) => !s.documents_now.length },
};

function StockRow({ s, onOpen }) {
  const score = scoreOf(s);
  return html`<div class="card tap" onClick=${() => onOpen(s)}>
    <div class="stock-row">
      <div class=${"rank" + (s.is_pick ? " pick" : "")}>${s.rank || s.screen_rank}</div>
      <div class="grow">
        <div class="row" style=${{ gap: 6 }}><b>${s.ticker}</b> <${StatusBadge} s=${s} /></div>
        <div class="muted small ellipsis">${s.name || ""}</div>
        <div class="mini num">
          <span>${inr(s.price)}</span><span>P/E ${num(s.pe, 1)}</span>
          <span>ROE ${pct(s.roe, false)}</span><span>6m ${pct(s.momentum_6m)}</span>
        </div>
      </div>
      <div class="scorebox"><b>${score.value}</b><span class="muted small">${score.label}</span></div>
    </div>
  </div>`;
}

export function StocksPage({ data, onOpen }) {
  const [filter, setFilter] = useState("all");
  if (!data) return html`<${Loading} />`;
  if (!data.run_id) return html`<div class="card empty"><h3>No screen yet</h3><p>Run the pipeline first.</p></div>`;

  const list = data.stocks.filter(FILTERS[filter].keep);
  return html`<div>
    <div class="row wrap" style=${{ gap: 6, marginBottom: 10 }}>
      ${Object.entries(FILTERS).map(([k, f]) => html`<button key=${k}
        class=${"btn sm" + (filter === k ? " primary" : "")} onClick=${() => setFilter(k)}>${f.label(data)}</button>`)}
    </div>
    ${list.map((s) => html`<${StockRow} key=${s.ticker} s=${s} onOpen=${onOpen} />`)}
    ${!list.length && html`<div class="card empty">Nothing here.</div>`}
  </div>`;
}
