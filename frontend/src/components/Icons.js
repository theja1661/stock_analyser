import { html } from "../lib/react.js";

const svg = (body, size) => html`<svg viewBox="0 0 24 24" width=${size} height=${size} fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const Icon = {
  picks: svg(html`<path d="M12 2l3 6.5 7 .9-5.1 4.8 1.3 7-6.2-3.4-6.2 3.4 1.3-7L2 9.4l7-.9z"/>`),
  stocks: svg(html`<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 6-7"/>`),
  docs: svg(html`<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M9 14h6M9 18h4"/>`),
  run: svg(html`<circle cx="12" cy="12" r="9"/><path d="M10 8l6 4-6 4z"/>`),
  settings: svg(html`<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>`),
  close: svg(html`<path d="M6 6l12 12M18 6L6 18"/>`, 22),
  refresh: svg(html`<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>`, 20),
};
