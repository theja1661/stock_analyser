// Upload / delete quarterly documents per ticker.
import { api } from "../lib/api.js";
import { when } from "../lib/format.js";
import { html, useCallback, useEffect, useRef, useState } from "../lib/react.js";
import { Loading, Spinner } from "../components/common.js";

const sameFiles = (a, b) => [...a].sort().join("|") === [...b].sort().join("|");

function TickerFolder({ ticker, files, stock, busy, onUpload, onDelete }) {
  const inputRef = useRef(null);
  const stale = stock && stock.status === "analyzed" && !sameFiles(files.map((f) => f.name), stock.documents_used || []);
  return html`<div class="card">
    <div class="row between">
      <div class="grow">
        <b>${ticker}</b> ${stock && html`<span class="muted small">#${stock.screen_rank} by quant</span>`}
        <div class="row wrap" style=${{ gap: 6, marginTop: 4 }}>
          ${files.length ? html`<span class="badge ok">${files.length} file(s)</span>` : html`<span class="badge warn">needs documents</span>`}
          ${stale && html`<span class="badge">changed: re-run LLM</span>`}
          ${!stock && html`<span class="badge">not in current top list</span>`}
        </div>
      </div>
      <input ref=${inputRef} type="file" accept=".pdf,.txt,.md,application/pdf,text/plain" multiple hidden
        onChange=${(e) => { onUpload(ticker, e.target.files); e.target.value = ""; }} />
      <button class="btn sm primary" disabled=${busy} onClick=${() => inputRef.current && inputRef.current.click()}>
        ${busy ? html`<${Spinner} />` : "Upload"}</button>
    </div>
    ${files.length > 0 && html`<div style=${{ marginTop: 8 }}>
      ${files.map((f) => html`<div class="file" key=${f.name}>
        <div class="grow">
          <div class="ellipsis">${f.name}</div>
          <div class="muted small">${(f.size / 1e6).toFixed(2)} MB · ${when(f.modified)}</div>
        </div>
        <button class="btn sm danger" onClick=${() => onDelete(ticker, f.name)}>Delete</button>
      </div>`)}
    </div>`}
  </div>`;
}

export function DocsPage({ data, toast, refresh }) {
  const [docs, setDocs] = useState(null);
  const [busy, setBusy] = useState(null);
  const [extra, setExtra] = useState("");

  const reload = useCallback(() => api("/api/documents").then((d) => setDocs(d.documents)).catch((e) => toast(e.message)), []);
  useEffect(() => { reload(); }, []);

  async function upload(ticker, fileList) {
    if (!fileList || !fileList.length) return;
    const fd = new FormData();
    for (const f of fileList) fd.append("files", f, f.name);
    setBusy(ticker);
    try {
      const r = await api("/api/documents/" + encodeURIComponent(ticker), { method: "POST", body: fd });
      toast(`Saved ${r.saved.length} file(s) for ${r.ticker}`);
      await reload(); refresh();
    } catch (e) { toast(e.message); } finally { setBusy(null); }
  }

  async function remove(ticker, name) {
    if (!confirm(`Delete ${name} from ${ticker}?`)) return;
    try {
      await api(`/api/documents/${encodeURIComponent(ticker)}/${encodeURIComponent(name)}`, { method: "DELETE" });
      await reload(); refresh();
    } catch (e) { toast(e.message); }
  }

  if (!docs) return html`<${Loading} />`;
  const stocks = (data && data.stocks) || [];
  const screened = stocks.map((s) => s.ticker);
  const tickers = [...screened, ...Object.keys(docs).filter((t) => !screened.includes(t))];
  const missing = screened.filter((t) => !(docs[t] || []).length).length;

  return html`<div>
    <p class="muted small" style=${{ marginTop: 0 }}>
      Upload quarterly results, investor presentations or call transcripts (PDF, TXT or MD) for the screened stocks.
      ${screened.length ? ` ${missing} of ${screened.length} still need documents.` : ""}
      After uploading, go to Run and choose <b>Analyze & report</b>.</p>
    ${tickers.map((t) => html`<${TickerFolder} key=${t} ticker=${t} files=${docs[t] || []}
      stock=${stocks.find((s) => s.ticker === t)} busy=${busy === t} onUpload=${upload} onDelete=${remove} />`)}
    <div class="card">
      <div class="label" style=${{ marginTop: 0 }}>Another ticker</div>
      <div class="row">
        <input class="input grow" placeholder="NSE symbol, e.g. TATAPOWER" value=${extra}
          onInput=${(e) => setExtra(e.target.value.toUpperCase().replace(/[^A-Z0-9&-]/g, ""))} />
        <button class="btn" disabled=${!extra} onClick=${() => { setDocs(Object.assign({ [extra]: [] }, docs)); setExtra(""); }}>Add</button>
      </div>
    </div>
  </div>`;
}
