// Edit config.yaml values, open past reports, install hints.
import { api, token } from "../lib/api.js";
import { METRIC_LABELS } from "../lib/format.js";
import { html, useEffect, useState } from "../lib/react.js";
import { Loading, Spinner } from "../components/common.js";

function NumberField({ label, hint, value, onChange, ...attrs }) {
  return html`<label class="field">
    <span>${label} ${hint && html`<small>· ${hint}</small>`}</span>
    <input class="input" type="number" inputmode="decimal" value=${value} onInput=${(e) => onChange(e.target.value)} ...${attrs} />
  </label>`;
}

function WeightSlider({ name, value, total, onChange }) {
  return html`<label class="field" style=${{ marginBottom: 8 }}>
    <div class="row between weight-label">
      <span>${METRIC_LABELS[name] || name}</span>
      <span class="num">${value}${total > 0 ? html` <small>(${Math.round((value / total) * 100)}%)</small>` : ""}</span>
    </div>
    <input type="range" min="0" max="50" step="1" value=${value} onInput=${(e) => onChange(Number(e.target.value))} />
  </label>`;
}

function toPayload(cfg) {
  return {
    budget: Number(cfg.budget), max_price: Number(cfg.max_price), top_n: Number(cfg.top_n),
    num_picks: Number(cfg.num_picks), topup_leftover: !!cfg.topup_leftover,
    max_position_pct: Number(cfg.max_position_pct), model: cfg.model,
    weights: Object.fromEntries(Object.entries(cfg.weights).map(([k, v]) => [k, Number(v)])),
  };
}

export function SettingsPage({ toast, refresh, logout }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [reports, setReports] = useState([]);

  useEffect(() => {
    api("/api/config").then(setCfg).catch((e) => toast(e.message));
    api("/api/reports").then((r) => setReports(r.reports)).catch(() => {});
  }, []);
  if (!cfg) return html`<${Loading} />`;

  const set = (k) => (v) => setCfg(Object.assign({}, cfg, { [k]: v }));
  const setWeight = (k) => (v) => setCfg(Object.assign({}, cfg, { weights: Object.assign({}, cfg.weights, { [k]: v }) }));
  const totalW = Object.values(cfg.weights).reduce((a, b) => a + Number(b), 0);

  async function save() {
    setSaving(true);
    try {
      setCfg(await api("/api/config", { method: "PUT", json: toPayload(cfg) }));
      toast("Saved. Re-screen or re-size to apply.");
      refresh();
    } catch (e) { toast(e.message); } finally { setSaving(false); }
  }

  return html`<div>
    <div class="section-title" style=${{ marginTop: 0 }}>Budget & sizing</div>
    <div class="card">
      <${NumberField} label="Budget (₹)" hint="amount to invest" value=${cfg.budget} onChange=${set("budget")} min="100" step="100" />
      <${NumberField} label="Number of picks" value=${cfg.num_picks} onChange=${set("num_picks")} min="1" max="10" step="1" />
      <label class="switch field">
        <span>Spend leftover on extra shares<br/><small>adds to the smallest position first</small></span>
        <input type="checkbox" checked=${!!cfg.topup_leftover} onChange=${(e) => set("topup_leftover")(e.target.checked)} />
      </label>
      <${NumberField} label="Max position size (% of budget)" value=${cfg.max_position_pct} onChange=${set("max_position_pct")} min="10" max="100" step="1" />
    </div>

    <div class="section-title">Screener</div>
    <div class="card">
      <${NumberField} label="Max share price (₹)" hint="hard filter" value=${cfg.max_price} onChange=${set("max_price")} min="1" step="50" />
      <${NumberField} label="Stocks to shortlist" hint="sent to the LLM" value=${cfg.top_n} onChange=${set("top_n")} min="3" max="50" step="1" />
      <div class="label" style=${{ marginTop: 0 }}>Metric weights <span class="plain-case">(total ${totalW})</span></div>
      ${Object.keys(cfg.weights).map((k) => html`<${WeightSlider} key=${k} name=${k} value=${cfg.weights[k]} total=${totalW} onChange=${setWeight(k)} />`)}
    </div>

    <div class="section-title">LLM</div>
    <div class="card">
      <label class="field"><span>Gemini model</span>
        <input class="input" value=${cfg.model} onInput=${(e) => set("model")(e.target.value.trim())} /></label>
      <div class="small">API key (${cfg.api_key_env}): ${cfg.has_api_key
        ? html`<span class="badge ok">set on PC</span>` : html`<span class="badge warn">not set</span>`}</div>
    </div>
    <button class="btn primary block" disabled=${saving || totalW <= 0} onClick=${save}>${saving ? html`<${Spinner} />` : "Save settings"}</button>

    <div class="section-title">Past reports</div>
    <div class="card">
      ${reports.length ? reports.map((r) => html`<div class="file" key=${r}>
        <div class="grow">${r.replace("report_", "").replace(".html", "")}</div>
        <a class="btn sm" href=${`/api/reports/${r}?token=${encodeURIComponent(token())}`} target="_blank" rel="noopener">Open</a>
      </div>`) : html`<p class="muted small" style=${{ margin: 0 }}>No reports yet.</p>`}
    </div>

    <div class="section-title">Install on your phone</div>
    <div class="card small muted">
      <b>Android (Chrome):</b> ⋮ menu → <i>Add to Home screen</i>.<br/>
      <b>iPhone (Safari):</b> Share → <i>Add to Home Screen</i>.<br/>
      The PC must be on and running <code>python backend/server.py</code>.
    </div>
    <button class="btn block" style=${{ marginTop: 4 }} onClick=${logout}>Forget access token on this device</button>
    <p class="muted small" style=${{ textAlign: "center" }}>Personal research tool. Not investment advice.</p>
  </div>`;
}
