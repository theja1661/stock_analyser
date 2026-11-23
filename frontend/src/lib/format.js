// Display helpers. Missing values are always shown as "missing", never as 0.
import { html } from "./react.js";

export const MISSING = html`<span class="na">missing</span>`;

const fixed = (v, d) => Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

export const inr = (v, d = 2) => (v == null ? MISSING : "₹" + fixed(v, d));
export const num = (v, d = 2) => (v == null ? MISSING : fixed(v, d));
export const crore = (v) => (v == null ? MISSING : "₹" + (v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 0 }) + " Cr");

/** Fraction -> percent. signed=true colours it green/red and adds a "+". */
export function pct(v, signed = true) {
  if (v == null) return MISSING;
  const s = (signed && v > 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
  return signed ? html`<span class=${v > 0 ? "pos" : v < 0 ? "neg" : ""}>${s}</span>` : s;
}

export function when(iso) {
  if (!iso) return "never";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export const METRIC_LABELS = {
  valuation: "Valuation (P/E ÷ sector)",
  roe: "ROE",
  debt_to_equity: "Debt / equity",
  revenue_growth: "Revenue growth",
  profit_growth: "Profit growth",
  momentum: "6-month return",
};
