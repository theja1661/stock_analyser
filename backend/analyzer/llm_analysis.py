"""Stage 3: LLM review of the quarterly documents you drop into data/documents/<TICKER>/.

Provider-agnostic: analyze_stock() talks to an LLMProvider. GeminiProvider is
the only implementation today; add another class and register it in PROVIDERS
to switch via config.yaml (llm.provider).
"""
from __future__ import annotations

import hashlib
import json
import ssl
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import db
from .common import env_ca_hint, getenv_required, log, project_path, resolve_ca_bundle

DOC_EXTENSIONS = {".pdf", ".txt", ".md"}


class StockAnalysis(BaseModel):
    """Structured output every provider must return."""
    thesis: str = Field(description="Investment thesis, at most 3 short lines")
    risks: list[str] = Field(description="Key business/financial risks")
    red_flags: list[str] = Field(
        description="Governance, accounting or disclosure red flags; empty list if none")
    guidance_summary: str = Field(description="Management guidance/outlook, or 'No guidance given'")
    conviction: int = Field(description="1 (avoid) to 10 (very high conviction)")


class RetryableError(Exception):
    """Provider signals a transient error (rate limit / overload) worth retrying."""


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.model: str = cfg["llm"]["model"]

    @abstractmethod
    def generate(self, prompt: str, documents: list[Path]) -> dict[str, Any]:
        """Send prompt + documents, return a dict matching StockAnalysis.

        Raise RetryableError for rate limits/overload; anything else is fatal
        for this stock (but not for the run).
        """


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        from google import genai
        from google.genai import types

        self._types = types
        api_key = getenv_required(cfg["llm"].get("api_key_env", "GEMINI_API_KEY"))
        http_options = None
        bundle = resolve_ca_bundle(cfg)
        if bundle:
            ctx = ssl.create_default_context(cafile=bundle)
            http_options = types.HttpOptions(client_args={"verify": ctx})
        self.client = genai.Client(api_key=api_key, http_options=http_options)
        self.max_inline_bytes = int(float(cfg["llm"].get("max_inline_mb", 18)) * 1024 * 1024)

    def _parts(self, documents: list[Path]) -> tuple[list[Any], list[Any]]:
        """Build content parts. Returns (parts, uploaded_files_to_cleanup)."""
        types = self._types
        parts: list[Any] = []
        uploaded: list[Any] = []
        pdf_bytes = sum(p.stat().st_size for p in documents if p.suffix.lower() == ".pdf")
        use_files_api = pdf_bytes > self.max_inline_bytes
        for p in documents:
            if p.suffix.lower() == ".pdf":
                if use_files_api:
                    log.info("    uploading %s via Files API (%.1f MB)", p.name, p.stat().st_size / 1e6)
                    f = self.client.files.upload(file=str(p), config={"mime_type": "application/pdf"})
                    uploaded.append(f)
                    parts.append(f)
                else:
                    parts.append(types.Part.from_bytes(data=p.read_bytes(), mime_type="application/pdf"))
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
                parts.append(types.Part.from_text(text=f"--- Document: {p.name} ---\n{text}"))
        return parts, uploaded

    def generate(self, prompt: str, documents: list[Path]) -> dict[str, Any]:
        from google.genai import errors

        types = self._types
        uploaded: list[Any] = []
        try:
            parts, uploaded = self._parts(documents)
            resp = self.client.models.generate_content(
                model=self.model,
                contents=[*parts, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=StockAnalysis,
                    temperature=float(self.cfg["llm"].get("temperature", 0.2)),
                ),
            )
        except errors.APIError as e:
            if e.code in (429, 500, 503):
                raise RetryableError(f"HTTP {e.code}: {e.message}") from e
            raise
        finally:
            for f in uploaded:
                try:
                    self.client.files.delete(name=f.name)
                except Exception:
                    pass

        if getattr(resp, "parsed", None) is not None:
            parsed = resp.parsed
            return parsed.model_dump() if isinstance(parsed, BaseModel) else dict(parsed)
        if not resp.text:
            raise RuntimeError("empty response (possibly blocked by safety filters)")
        return json.loads(resp.text)


PROVIDERS: dict[str, type[LLMProvider]] = {"gemini": GeminiProvider}


def make_provider(cfg: dict[str, Any]) -> LLMProvider:
    name = cfg["llm"].get("provider", "gemini").lower()
    if name not in PROVIDERS:
        raise ValueError(f"Unknown llm.provider '{name}'. Available: {', '.join(PROVIDERS)}")
    return PROVIDERS[name](cfg)


# ------------------------------------------------------------------ helpers

def find_documents(documents_dir: Path, ticker: str) -> list[Path]:
    folder = documents_dir / ticker
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in DOC_EXTENSIONS)


def documents_hash(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: x.name):
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _fmt(v: float | None, kind: str) -> str:
    if v is None:
        return "not available"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "cr":
        return f"INR {v / 1e7:,.0f} Cr"
    return f"{v:.2f}"


def fundamentals_summary(f: dict[str, Any]) -> str:
    lines = [
        f"Company: {f.get('name') or f['ticker']} (NSE: {f['ticker']})",
        f"Sector: {f.get('sector') or 'not available'}",
        f"Price: {_fmt(f.get('price'), 'num')} INR",
        f"Trailing P/E: {_fmt(f.get('pe'), 'num')}",
        f"ROE: {_fmt(f.get('roe'), 'pct')}",
        f"Debt/Equity: {_fmt(f.get('debt_to_equity'), 'num')}",
        f"6-month price return: {_fmt(f.get('momentum_6m'), 'pct')}",
        "Quarterly results (newest first):",
    ]
    for q in f.get("quarters") or []:
        lines.append(f"  {q['period']}: revenue {_fmt(q['revenue'], 'cr')}, "
                     f"net profit {_fmt(q['net_profit'], 'cr')}")
    return "\n".join(lines)


PROMPT = """You are a skeptical equity analyst reviewing an Indian listed company for a
small retail investor's long-term portfolio.

Attached are the company's recent quarterly documents (results, investor
presentations and/or earnings call transcripts). Market data from Yahoo Finance:

{summary}

Using primarily the attached documents (and the data above for context):
- thesis: the investment case in at most 3 short lines.
- risks: the most important risks (2-5 items).
- red_flags: specific governance, accounting, related-party, pledging, auditor
  or disclosure concerns actually evidenced in the documents. Use an empty list
  if you find none. Do not speculate.
- guidance_summary: what management said about the outlook (growth, margins,
  capex). Write "No guidance given" if absent.
- conviction: integer 1-10 for buying now at the current price
  (1 = avoid, 5 = neutral, 10 = exceptional). Be calibrated; most stocks
  should land between 3 and 7.

If the documents contradict the market data, trust the documents and say so in risks."""


def _clean(result: dict[str, Any]) -> dict[str, Any]:
    thesis = str(result.get("thesis", "")).strip()
    thesis = "\n".join(thesis.splitlines()[:3])
    try:
        conviction = int(round(float(result.get("conviction", 0))))
    except (TypeError, ValueError):
        conviction = 1
    return {
        "thesis": thesis,
        "risks": [str(r) for r in (result.get("risks") or [])],
        "red_flags": [str(r) for r in (result.get("red_flags") or [])],
        "guidance_summary": str(result.get("guidance_summary", "")).strip(),
        "conviction": max(1, min(10, conviction)),
    }


def analyze_stock(ticker: str, document_paths: list[Path], fundamentals: dict[str, Any],
                  provider: LLMProvider | None = None,
                  cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyze one stock's documents. Retries transient errors with exponential backoff."""
    if provider is None:
        if cfg is None:
            raise ValueError("pass either provider or cfg")
        provider = make_provider(cfg)
    llm_cfg = provider.cfg["llm"]
    max_retries = int(llm_cfg.get("max_retries", 3))
    base = float(llm_cfg.get("backoff_base_seconds", 20))
    prompt = PROMPT.format(summary=fundamentals_summary(fundamentals))

    attempt = 0
    while True:
        try:
            return _clean(provider.generate(prompt, document_paths))
        except RetryableError as e:
            if attempt >= max_retries:
                raise RuntimeError(f"giving up after {max_retries} retries: {e}") from e
            wait = base * (2 ** attempt)
            attempt += 1
            log.warning("    %s: %s; retry %d/%d in %.0fs", ticker, e, attempt, max_retries, wait)
            time.sleep(wait)


# ------------------------------------------------------------------ stage

def run(cfg: dict[str, Any]) -> None:
    docs_dir = project_path(cfg, "documents_dir")
    delay = float(cfg["llm"].get("delay_seconds", 15))
    with db.connect(project_path(cfg, "database")) as conn:
        run_id = db.latest_screen_run(conn)
        if not run_id:
            log.error("No screener results. Run the screener stage first.")
            return
        screen = db.get_screen(conn, run_id)
        log.info("Analyzing %d screened stocks (screen run %s)", len(screen), run_id)

        provider: LLMProvider | None = None
        provider_error: str | None = None
        last_call = 0.0
        counts = {"cached": 0, "called": 0, "quant-only": 0, "error": 0}

        for row in screen:
            t = row["ticker"]
            docs = find_documents(docs_dir, t)
            names = [p.name for p in docs]
            if not docs:
                log.info("  %-12s no documents in data/documents/%s -> quant-only", t, t)
                db.set_analysis_status(conn, run_id, t, "quant-only", message="no documents")
                counts["quant-only"] += 1
                continue

            try:
                h = documents_hash(docs)
            except OSError as e:
                log.error("  %-12s cannot read documents: %s", t, e)
                db.set_analysis_status(conn, run_id, t, "error", documents=names, message=str(e))
                counts["error"] += 1
                continue

            if db.get_llm_cache(conn, t, h) is not None:
                log.info("  %-12s cached analysis (documents unchanged)", t)
                db.set_analysis_status(conn, run_id, t, "analyzed", h, names)
                counts["cached"] += 1
                continue

            if provider is None and provider_error is None:
                try:
                    provider = make_provider(cfg)
                    log.info("LLM provider: %s / %s", provider.name, provider.model)
                except Exception as e:
                    provider_error = str(e)
                    log.error("Cannot initialise LLM provider: %s", e)
            if provider is None:
                log.warning("  %-12s has documents but no LLM provider -> quant-only", t)
                db.set_analysis_status(conn, run_id, t, "error", h, names,
                                       f"LLM provider unavailable: {provider_error}")
                counts["error"] += 1
                continue

            wait = delay - (time.monotonic() - last_call)
            if last_call and wait > 0:
                log.info("    rate limit: sleeping %.0fs", wait)
                time.sleep(wait)

            fundamentals = db.get_fundamentals(conn, t) or {"ticker": t}
            log.info("  %-12s sending %d document(s) to %s: %s", t, len(docs), provider.model,
                     ", ".join(names))
            try:
                result = analyze_stock(t, docs, fundamentals, provider=provider)
                db.put_llm_cache(conn, t, h, provider.name, provider.model, result)
                db.set_analysis_status(conn, run_id, t, "analyzed", h, names)
                counts["called"] += 1
                log.info("  %-12s conviction %d/10, %d risk(s), %d red flag(s)", t,
                         result["conviction"], len(result["risks"]), len(result["red_flags"]))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                log.error("  %-12s analysis failed: %s", t, msg)
                if "CERTIFICATE_VERIFY" in msg.upper() or "SSL" in msg.upper():
                    log.error("  %s", env_ca_hint())
                db.set_analysis_status(conn, run_id, t, "error", h, names, msg[:500])
                counts["error"] += 1
            finally:
                last_call = time.monotonic()
                conn.commit()

    log.info("LLM stage done: %d new analyses, %d cached, %d quant-only, %d errors",
             counts["called"], counts["cached"], counts["quant-only"], counts["error"])
