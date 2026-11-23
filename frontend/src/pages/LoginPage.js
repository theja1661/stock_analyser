// Shown when no (valid) access token is stored on this device.
import { api } from "../lib/api.js";
import { TOKEN_KEY, store } from "../lib/storage.js";
import { html, useState } from "../lib/react.js";

export function LoginPage({ onDone }) {
  const [t, setT] = useState("");
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    store(TOKEN_KEY, t.trim());
    try { await api("/api/config"); onDone(); } catch (x) { setErr(x.message); }
  }

  return html`<div class="app"><form class="card login" onSubmit=${submit}>
    <h2 style=${{ marginTop: 0 }}>Stock Analyzer</h2>
    <p class="muted small">Enter the access token printed when you started <code>python backend/server.py</code>
      on your PC (also saved in <code>data/.web_token</code>). Opening the printed link signs you in automatically.</p>
    <input class="input" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Access token"
      value=${t} onInput=${(e) => setT(e.target.value)} />
    ${err && html`<p class="neg small">${err}</p>`}
    <button class="btn primary block" style=${{ marginTop: 12 }} disabled=${!t.trim()}>Continue</button>
  </form></div>`;
}
