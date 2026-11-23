"""List, upload and delete the quarterly documents in data/documents/<TICKER>/."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from analyzer.common import load_config, project_path
from analyzer.llm_analysis import DOC_EXTENSIONS, find_documents

from ..auth import AUTH

router = APIRouter(prefix="/api/documents", dependencies=AUTH, tags=["documents"])

TICKER_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")  # NSE symbols, e.g. M&M, BAJAJ-AUTO
MAX_UPLOAD_MB = 50


def check_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not TICKER_RE.match(t):
        raise HTTPException(400, "Invalid ticker")
    return t


def safe_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    stem, suffix = Path(base).stem, Path(base).suffix.lower()
    if suffix not in DOC_EXTENSIONS:
        raise HTTPException(400, f"Only {', '.join(sorted(DOC_EXTENSIONS))} files are accepted")
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .") or "document"
    return f"{stem[:100]}{suffix}"


def _docs_dir() -> Path:
    return project_path(load_config(), "documents_dir")


@router.get("")
def list_documents() -> dict[str, Any]:
    docs_dir = _docs_dir()
    out: dict[str, list[dict[str, Any]]] = {}
    if docs_dir.is_dir():
        for folder in sorted(p for p in docs_dir.iterdir() if p.is_dir()):
            out[folder.name] = [
                {"name": p.name, "size": p.stat().st_size,
                 "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
                for p in find_documents(docs_dir, folder.name)
            ]
    return {"documents": out}


@router.post("/{ticker}")
async def upload_documents(ticker: str, files: list[UploadFile] = File(...)) -> dict[str, Any]:
    t = check_ticker(ticker)
    folder = _docs_dir() / t
    limit = MAX_UPLOAD_MB * 1024 * 1024
    pending: list[tuple[str, bytes]] = []
    for up in files:  # validate everything before writing anything
        name = safe_filename(up.filename or "document.pdf")
        data = await up.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"{name} is larger than {MAX_UPLOAD_MB} MB")
        if name.endswith(".pdf") and not data.startswith(b"%PDF"):
            raise HTTPException(400, f"{name} does not look like a PDF")
        pending.append((name, data))
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in pending:
        (folder / name).write_bytes(data)
    return {"ticker": t, "saved": [n for n, _ in pending]}


@router.delete("/{ticker}/{filename}")
def delete_document(ticker: str, filename: str) -> dict[str, Any]:
    t = check_ticker(ticker)
    folder = _docs_dir() / t
    target = folder / Path(filename).name
    if target.parent != folder or not target.is_file():
        raise HTTPException(404, "File not found")
    target.unlink()
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return {"deleted": target.name}
