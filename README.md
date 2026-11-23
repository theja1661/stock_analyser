# NSE Stock Analyzer (personal)

A weekly pipeline for Indian equities, run from the command line or a phone-friendly web app. It screens NSE stocks on fundamentals, has an LLM (Gemini) read the quarterly documents you supply, and suggests picks with whole-share quantities for your budget.

> Personal research tool. Not investment advice.

## Project layout

```
stock_analyzer/
├── backend/                     Python: pipeline + web API
│   ├── main.py                  CLI entry       → python backend/main.py run
│   ├── server.py                Web entry       → python backend/server.py
│   ├── config.yaml              all settings (budget, weights, model, paths, ...)
│   ├── universe.csv             tickers to screen
│   ├── requirements.txt
│   ├── analyzer/                the pipeline (no web code)
│   │   ├── pipeline.py          ordered stage registry used by CLI and API
│   │   ├── ingestion.py         stage 1: yfinance prices + fundamentals
│   │   ├── screener.py          stage 2: hard filters + 6-metric quant score
│   │   ├── llm_analysis.py      stage 3: provider-agnostic LLM document review
│   │   ├── sizing.py            stage 4: final score, picks, whole-share sizing
│   │   ├── report.py            stage 5: standalone HTML report
│   │   ├── db.py                SQLite helpers
│   │   └── common.py            config, paths, logging, CA bundle
│   └── api/                     FastAPI layer over the pipeline
│       ├── app.py               app factory; serves frontend/ at /
│       ├── auth.py              access-token check
│       ├── jobs.py              background pipeline runner + live log
│       └── routes/              results.py · runs.py · documents.py · settings.py
├── frontend/                    React app (no build step)
│   ├── index.html · manifest.json
│   ├── css/styles.css
│   ├── assets/icon.svg
│   ├── vendor/                  React 18 + htm (local copies, no CDN)
│   └── src/
│       ├── main.js · App.js     entry + app shell (tabs, auth, run status)
│       ├── lib/                 api.js · format.js · storage.js · react.js
│       ├── components/          StockSheet · AnalysisBlock · Icons · common
│       └── pages/               Picks · Stocks · Docs · Run · Settings · Login
└── data/                        runtime state, git-ignored
    ├── data.db                  cache + every stage's output
    ├── documents/<TICKER>/      your quarterly PDFs / transcripts
    ├── reports/                 report_YYYY-MM-DD.html
    ├── .web_token               web access token
    └── .certs/                  auto-built CA bundle
```

- **Backend:** `analyzer/` is the whole pipeline and knows nothing about the web. `api/` is a thin layer that calls it.
- **Frontend:** talks to the backend only through `/api/...`.
- **Data:** everything the app generates lives in `data/`. Delete that folder to start fresh.

## Setup

Requires Python 3.10+. Run these from the project root:

```powershell
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Gemini API key

Get a key from Google AI Studio (https://aistudio.google.com/apikey). Set it as an environment variable only, never in `config.yaml` or the code:

```powershell
$env:GEMINI_API_KEY = "your-key"        # current PowerShell session
setx GEMINI_API_KEY "your-key"          # future sessions (open a new terminal afterwards)
```

Without a key everything still runs, and every stock is treated as quant-only. The default model, `gemini-flash-latest`, is Google's alias for its current Flash model. Change `llm.model` to pin a specific version.

### OpenRouter

The default remains Gemini. To switch to OpenRouter, set `OPENROUTER_API_KEY` in the project root `.env` file or in the process environment, then change `backend/config.yaml` to:

```yaml
llm:
  provider: openrouter
  model: openrouter/free
  api_key_env: OPENROUTER_API_KEY
```

The application loads `<project root>/.env` automatically before provider initialization without replacing existing process environment variables. The provider uses OpenRouter's OpenAI-compatible API and requests JSON output. If a model rejects `response_format={"type":"json_object"}`, the provider retries once without that parameter and relies on the prompt plus Pydantic validation. PDF files are text-extracted locally with `pypdf`; image-only/scanned PDFs require OCR before they can be analysed.

### Corporate network / TLS errors

You may see `CertificateVerifyError` or `CERTIFICATE_VERIFY_FAILED`. That means your network re-signs HTTPS traffic. The default `network.ca_bundle: auto` handles this on Windows by building a CA bundle from the Windows certificate store into `data/.certs/`. On other systems, set it to the path of your company's root-CA PEM file.

## Using it

### Command line

```powershell
python backend/main.py run                      # full pipeline
python backend/main.py run --stage screener     # one stage: ingest | screener | llm | sizing | report
python backend/main.py run --from llm           # a stage and everything after it
python backend/main.py run --refresh            # ignore the 3-day data cache
python backend/main.py run -v                   # debug logging
```

Open `data/reports/report_YYYY-MM-DD.html` for the result. The commands also work from inside `backend/`, as `python main.py run`.

### Web app (phone or desktop)

```powershell
python backend/server.py
```

It prints a link for this PC and one for your phone, each with an access token. Open a link once and the token is remembered. On a phone, use *Add to Home screen* for an app icon: the ⋮ menu in Chrome on Android, or Share in Safari on iPhone.

| Tab | What you can do |
|---|---|
| **Picks** | This week's picks with quantity, cost, % of budget and leftover cash. Expand a pick for its thesis, risks and red flags. |
| **Stocks** | The top-15 shortlist. Tap a stock for its score breakdown, quarterly numbers and analysis. |
| **Docs** | Upload quarterly PDFs or transcripts from your phone, and see which stocks still need them. |
| **Run** | *Full weekly run*, *Analyze & report*, *Re-screen* or *Re-size*, with a live log. |
| **Settings** | Change budget, picks, price filter, weights and model. Changes are saved to `config.yaml` with comments kept. Past reports are here too. |

How the server works:

- It runs the same `backend/main.py` commands in the background, so the CLI and the web app always agree.
- The API key stays on the PC. If you set or change `GEMINI_API_KEY`, restart the server.
- To revoke all devices, delete `data/.web_token` and restart the server.

**Reaching it from your phone.** The phone and PC must be on the same network, and the network must allow device-to-device traffic. That usually works on home Wi-Fi and usually doesn't on office or guest Wi-Fi.

- When Windows asks, allow Python on *Private* networks, and mark your home Wi-Fi as *Private*.
- To reach the server from anywhere, use Tailscale (https://tailscale.com) on both devices.
- Don't port-forward it to the open internet. It uses plain HTTP.
- To keep it on this PC only, set `web.host: 127.0.0.1`.

### Suggested weekly routine

1. Run **Re-screen**, or **Full weekly run** if your data is more than 3 days old, to see this week's top 15.
2. Upload recent quarterly results, presentations and call transcripts for those stocks. Use the **Docs** tab, or copy them into `data/documents/<TICKER>/`, where the folder is named after the NSE symbol, e.g. `data/documents/ITC/`. Accepted formats are `.pdf`, `.txt` and `.md`.
3. Run **Analyze & report**. Stocks whose documents haven't changed reuse their cached analysis, so there's no extra API cost.
4. Read the picks.

Stocks with no documents are **quant-only**. They only enter the picks when fewer than 3 stocks have LLM analysis.

## Configuration (`backend/config.yaml`)

Paths in `paths:` are relative to the project root.

- `budget`: amount to invest (default 6000).
- `paths.universe_csv`: the ticker list. The starter `backend/universe.csv` has 34 large caps. Add symbols without `.NS` under the `symbol` header. For the full Nifty 500, NSE publishes `ind_nifty500list.csv` on niftyindices.com; rename its `Symbol` header to `symbol`.
- `screener`: `weights` (default 20/20/15/20/20/5), `max_price`, `min_quarters`, `top_n`.
- `llm`: `provider`, `model`, `delay_seconds` (15), `max_retries` (3) and backoff.
- `sizing`:
  - `num_picks`, the blend weights, and `min_analyzed_for_picks`.
  - `topup_leftover`: spends leftover cash on extra shares, adding to the smallest position first. No position goes above `max_position_pct` (45%) of the budget.
- `web`: `host` and `port` for the web server.

## Scoring details

- **Valuation**: trailing P/E ÷ sector median P/E, with the median taken over the whole fetched universe. Lower is better. Missing, zero or negative P/E scores 0.
- **ROE**: higher is better.
- **Debt/equity**: lower is better. Yahoo reports it in %; it is converted to a ratio. Yahoo gives no value for banks.
- **Revenue / profit growth**: newest of the last 4 quarters vs the oldest, as (new − old) / |old|. These are sequential quarters, so seasonal businesses look noisy.
- **Momentum**: 6-month price return.
- Each metric is a percentile rank (0 = worst, 100 = best) among stocks that passed the hard filters. A missing metric scores 0. The composite is the weighted average.
- **Final score** = 0.5 × quant + 0.5 × (conviction × 10).

Missing data is never filled in. It is stored as NULL and shown as *missing*.

## Extending

- **Another LLM provider:** in `backend/analyzer/llm_analysis.py`, subclass `LLMProvider` and implement `generate(prompt, documents) -> dict`. Raise `RetryableError` on rate limits, register the class in `PROVIDERS`, then set `llm.provider`.
- **A new API endpoint:** add a router module in `backend/api/routes/` and list it in `routes/__init__.py`.
- **A new screen:** add `frontend/src/pages/YourPage.js` and register it in the `TABS` / `pages` maps in `frontend/src/App.js`. Files are plain ES modules, so just reload the browser.
