// App shell: auth gate, header, bottom tab bar, shared data + run status.
import { api, setUnauthorizedHandler } from "./lib/api.js";
import { when } from "./lib/format.js";
import { html, useCallback, useEffect, useRef, useState } from "./lib/react.js";
import { TAB_KEY, TOKEN_KEY, load, store } from "./lib/storage.js";
import { Icon } from "./components/Icons.js";
import { StockSheet } from "./components/StockSheet.js";
import { Spinner } from "./components/common.js";
import { DocsPage } from "./pages/DocsPage.js";
import { LoginPage } from "./pages/LoginPage.js";
import { PicksPage } from "./pages/PicksPage.js";
import { RunPage } from "./pages/RunPage.js";
import { SettingsPage } from "./pages/SettingsPage.js";
import { StocksPage } from "./pages/StocksPage.js";

const TABS = [
  { key: "picks", label: "Picks", title: "This week's picks" },
  { key: "stocks", label: "Stocks", title: "Shortlist" },
  { key: "docs", label: "Docs", title: "Documents" },
  { key: "run", label: "Run", title: "Run pipeline" },
  { key: "settings", label: "Settings", title: "Settings" },
];

function initialTab() {
  const h = location.hash.slice(1);
  const saved = load(TAB_KEY);
  return TABS.some((t) => t.key === h) ? h : TABS.some((t) => t.key === saved) ? saved : "picks";
}

function useToast() {
  const [msg, setMsg] = useState(null);
  const timer = useRef(null);
  const toast = useCallback((m) => {
    setMsg(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 3500);
  }, []);
  return [msg, toast];
}

export function App() {
  const [authed, setAuthed] = useState(!!load(TOKEN_KEY));
  const [tab, setTab] = useState(initialTab);
  const [data, setData] = useState(null);
  const [job, setJob] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [loading, setLoading] = useState(false);
  const [msg, toast] = useToast();

  const logout = useCallback(() => { store(TOKEN_KEY, null); setAuthed(false); }, []);
  setUnauthorizedHandler(logout);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api("/api/summary");
      setData(d);
      if (d.job) setJob(d.job);
    } catch (e) { toast(e.message); } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (authed) refresh(); }, [authed]);
  useEffect(() => { store(TAB_KEY, tab); history.replaceState(null, "", "#" + tab); scrollTo(0, 0); }, [tab]);

  // While a run is in progress, poll its status from any tab; reload results when it ends.
  const wasRunning = useRef(false);
  useEffect(() => {
    const running = !!(job && job.running);
    if (wasRunning.current && !running) {
      refresh();
      toast(job && job.exit_code === 0 ? "Run finished" : "Run ended with errors (see Run tab)");
    }
    wasRunning.current = running;
    if (!running) return;
    const t = setInterval(() => api("/api/job?lines=false").then(setJob).catch(() => {}), 3000);
    return () => clearInterval(t);
  }, [job && job.running]);

  // Keep an open detail sheet in sync with refreshed data.
  useEffect(() => {
    if (!sheet || !data || !data.stocks) return;
    const s = data.stocks.find((x) => x.ticker === sheet.ticker);
    if (s && s !== sheet) setSheet(s);
  }, [data]);

  if (!authed) return html`<${LoginPage} onDone=${() => setAuthed(true)} />`;

  const running = !!(job && job.running);
  const current = TABS.find((t) => t.key === tab);
  const pages = {
    picks: () => html`<div class="disclaimer">Personal research tool. Not investment advice.</div>
      <${PicksPage} data=${data} onOpen=${setSheet} go=${setTab} />`,
    stocks: () => html`<${StocksPage} data=${data} onOpen=${setSheet} />`,
    docs: () => html`<${DocsPage} data=${data} toast=${toast} refresh=${refresh} />`,
    run: () => html`<${RunPage} job=${job} setJob=${setJob} data=${data} toast=${toast} />`,
    settings: () => html`<${SettingsPage} toast=${toast} refresh=${refresh} logout=${logout} />`,
  };

  return html`<div>
    <div class="app">
      <header class="top">
        <div>
          <h1>${current.title}</h1>
          <div class="sub">${data && data.run_id ? "Screen " + when(data.run_id) : "Stock Analyzer"}${running ? " · run in progress" : ""}</div>
        </div>
        <button class="icon-btn" aria-label="Refresh" onClick=${refresh}>${loading ? html`<${Spinner} />` : Icon.refresh}</button>
      </header>
      ${pages[tab]()}
    </div>

    <nav class="tabs"><div class="in">
      ${TABS.map((t) => html`<button key=${t.key} class=${tab === t.key ? "on" : ""} onClick=${() => setTab(t.key)}
        aria-current=${tab === t.key ? "page" : undefined}>
        ${Icon[t.key]}<span>${t.label}</span>${t.key === "run" && running && html`<i class="dot"></i>`}
      </button>`)}
    </div></nav>

    ${sheet && html`<${StockSheet} s=${sheet} onClose=${() => setSheet(null)} go=${setTab} />`}
    ${msg && html`<div class="toast" role="status">${msg}</div>`}
  </div>`;
}
