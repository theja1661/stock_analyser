"""Shared helpers: config loading, logging, and TLS CA-bundle resolution."""
from __future__ import annotations

import logging
import os
import ssl
import sys
from pathlib import Path
from typing import Any

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]   # stock_analyzer/backend
ROOT_DIR = BACKEND_DIR.parent                        # stock_analyzer/
DATA_DIR = ROOT_DIR / "data"                         # runtime state (db, documents, reports, secrets)
FRONTEND_DIR = ROOT_DIR / "frontend"
CONFIG_FILE = BACKEND_DIR / "config.yaml"
log = logging.getLogger("stock_analyzer")


def load_config(path: str | Path = CONFIG_FILE) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


def resolve(p: str | Path) -> Path:
    """Paths in config.yaml are relative to the project root."""
    p = Path(p)
    return p if p.is_absolute() else ROOT_DIR / p


def project_path(cfg: dict[str, Any], key: str) -> Path:
    """Resolve a path from cfg['paths']."""
    return resolve(cfg["paths"][key])


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    # yfinance is chatty about transient failures we already handle.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)


_ca_bundle_cache: str | None | bool = False  # False = not resolved yet


def resolve_ca_bundle(cfg: dict[str, Any]) -> str | None:
    """Return a CA bundle path to verify TLS against, or None for library defaults.

    'auto' on Windows exports the Windows certificate store (which includes any
    corporate proxy root CA) plus certifi's bundle into data/.certs/ca_bundle.pem.
    """
    global _ca_bundle_cache
    if _ca_bundle_cache is not False:
        return _ca_bundle_cache  # type: ignore[return-value]

    setting = (cfg.get("network") or {}).get("ca_bundle")
    result: str | None = None
    if setting and setting != "auto":
        p = resolve(setting)
        if p.exists():
            result = str(p)
        else:
            log.warning("Configured ca_bundle %s not found; using library defaults", p)
    elif setting == "auto" and sys.platform == "win32":
        try:
            pems: list[str] = []
            for store in ("ROOT", "CA"):
                for cert, encoding, _trust in ssl.enum_certificates(store):  # type: ignore[attr-defined]
                    if encoding == "x509_asn":
                        pems.append(ssl.DER_cert_to_PEM_cert(cert))
            try:
                import certifi

                pems.append(Path(certifi.where()).read_text(encoding="ascii"))
            except Exception:  # certifi is optional here
                pass
            out = DATA_DIR / ".certs" / "ca_bundle.pem"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(pems), encoding="ascii")
            result = str(out)
            log.debug("Built CA bundle from Windows store: %s (%d certs)", out, len(pems))
        except Exception as e:
            log.warning("Could not build CA bundle from Windows store (%s); using defaults", e)

    _ca_bundle_cache = result
    return result


def env_ca_hint() -> str:
    return (
        "If you are behind a corporate proxy, set network.ca_bundle in config.yaml "
        "('auto' on Windows, or a path to your company's root CA PEM)."
    )


def getenv_required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Environment variable {name} is not set")
    return val
