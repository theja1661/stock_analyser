// Small shared UI pieces.
import { html } from "../lib/react.js";

export const Spinner = () => html`<span class="spin" aria-label="Loading"></span>`;
export const Loading = () => html`<div class="empty"><${Spinner} /></div>`;

export function StatusBadge({ s }) {
  if (s.status === "analyzed") return html`<span class="badge ok">LLM analyzed</span>`;
  if (s.status === "error") return html`<span class="badge err" title=${s.status_message || ""}>LLM failed</span>`;
  if (s.status === "pending") return html`<span class="badge">not analyzed yet</span>`;
  return html`<span class="badge">quant-only</span>`;
}

/** The big number on a card: final score when LLM-analyzed, otherwise the quant score. */
export function scoreOf(s) {
  return s.final_score != null
    ? { value: s.final_score.toFixed(1), label: "final" }
    : { value: s.quant.toFixed(1), label: "quant" };
}
