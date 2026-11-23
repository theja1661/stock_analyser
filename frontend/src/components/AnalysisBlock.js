// Thesis / risks / red flags / guidance for one stock, or why it's missing.
import { html } from "../lib/react.js";

const List = ({ items, cls = "", empty }) => items.length
  ? html`<ul class=${"plain " + cls}>${items.map((r, i) => html`<li key=${i}>${r}</li>`)}</ul>`
  : html`<p class="none">${empty}</p>`;

export function AnalysisBlock({ s }) {
  const a = s.analysis;
  if (!a) {
    return html`<p class="muted small" style=${{ margin: "8px 0 0" }}>
      No LLM analysis: thesis, risks and red flags are unavailable. Upload this quarter's documents
      for ${s.ticker} in the Docs tab and re-run.</p>`;
  }
  return html`<div>
    <div class="label">Thesis</div><p class="thesis">${a.thesis}</p>
    <div class="label">Risks</div><${List} items=${a.risks} empty="None listed" />
    <div class="label">Red flags</div><${List} items=${a.red_flags} cls="flags" empty="None identified" />
    <div class="label">Guidance</div><p style=${{ margin: 0 }}>${a.guidance_summary}</p>
    <div class="label">Sources</div><p class="muted small" style=${{ margin: 0 }}>${(s.documents_used || []).join(", ")}</p>
  </div>`;
}
