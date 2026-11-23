// Start pipeline runs and stream the log.
import { api } from "../lib/api.js";
import { when } from "../lib/format.js";
import { html, useEffect, useRef, useState } from "../lib/react.js";
import { Spinner } from "../components/common.js";

const RUNS = [
  { key: "full", label: "Full weekly run", body: {}, desc: "Fetch data → screen → LLM → size → report", primary: true },
  { key: "analyze", label: "Analyze & report", body: { from_stage: "llm" }, desc: "After uploading documents" },
  { key: "rescreen", label: "Re-screen", body: { from_stage: "screener" }, desc: "After changing weights or budget" },
  { key: "resize", label: "Re-size only", body: { from_stage: "sizing" }, desc: "After changing budget / picks" },
];

const lineClass = (l) => (/ERROR/.test(l) ? "e" : /WARNING/.test(l) ? "w" : /STAGE:/.test(l) ? "s" : "");

/** Polls /api/job and accumulates log lines. */
function useJobLog(setJob) {
  const [lines, setLines] = useState([]);
  const next = useRef(0);
  useEffect(() => {
    let alive = true, timer;
    async function poll() {
      try {
        const j = await api("/api/job?since=" + next.current);
        if (!alive) return;
        if (next.current > j.next) { next.current = 0; setLines([]); }  // a new run replaced the old log
        if (j.lines.length) setLines((l) => l.concat(j.lines).slice(-3000));
        next.current = j.next;
        setJob(j);
        timer = setTimeout(poll, j.running ? 1200 : 4000);
      } catch (e) { if (alive) timer = setTimeout(poll, 5000); }
    }
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, []);
  const reset = () => { next.current = 0; setLines([]); };
  return [lines, reset];
}

export function RunPage({ job, setJob, data, toast }) {
  const [refreshData, setRefreshData] = useState(false);
  const [lines, resetLog] = useJobLog(setJob);
  const logRef = useRef(null);
  const stick = useRef(true);

  useEffect(() => {
    if (stick.current && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  async function start(body) {
    try {
      const j = await api("/api/run", { method: "POST", json: Object.assign({}, body, { refresh: refreshData }) });
      resetLog(); setJob(j); toast("Pipeline started");
    } catch (e) { toast(e.message); }
  }
  async function cancel() {
    try { setJob(await api("/api/job/cancel", { method: "POST" })); } catch (e) { toast(e.message); }
  }

  const running = job && job.running;
  const status = running ? html`<span><${Spinner} /> running since ${when(job.started)}</span>`
    : job && job.finished ? html`<span class=${job.exit_code === 0 ? "pos" : "neg"}>
        ${job.exit_code === 0 ? "finished" : "failed (exit " + job.exit_code + ")"} ${when(job.finished)}</span>`
    : "idle";

  return html`<div>
    ${data && !data.has_api_key && html`<div class="card notice">
      <b>No Gemini API key on the PC.</b>
      <div class="small">Stocks will be quant-only. Set GEMINI_API_KEY on the PC and restart the server (see README).</div>
    </div>`}
    <div class="btn-grid">
      ${RUNS.map((r) => html`<button key=${r.key} class=${"btn run-btn" + (r.primary ? " primary" : "")} disabled=${running}
        onClick=${() => start(r.body)}><div>${r.label}</div><div class="small">${r.desc}</div></button>`)}
    </div>
    <label class="switch card" style=${{ marginTop: 10 }}>
      <span><b>Force fresh market data</b><div class="muted small">Ignore the 3-day cache (full run only, slower)</div></span>
      <input type="checkbox" checked=${refreshData} onChange=${(e) => setRefreshData(e.target.checked)} />
    </label>
    <div class="row between" style=${{ margin: "16px 2px 8px" }}>
      <div class="section-title" style=${{ margin: 0 }}>Log</div>
      <div class="small muted">${status}</div>
    </div>
    <div class="log" ref=${logRef} onScroll=${(e) => { const el = e.target; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; }}>
      ${lines.length ? lines.map((l, i) => html`<div key=${i} class=${lineClass(l)}>${l}</div>`)
        : html`<span style=${{ opacity: 0.6 }}>No output yet. The LLM stage waits 15 s between API calls, so a full run with documents can take several minutes.</span>`}
    </div>
    ${running && html`<button class="btn danger block" style=${{ marginTop: 10 }} onClick=${cancel}>Stop run</button>`}
  </div>`;
}
