"""Shared-secret access token. Every /api call must present it."""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, Request

from analyzer.common import DATA_DIR

TOKEN_FILE = DATA_DIR / ".web_token"


def load_token() -> str:
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tok = secrets.token_urlsafe(18)
    TOKEN_FILE.write_text(tok, encoding="utf-8")
    return tok


TOKEN = load_token()


def require_token(request: Request) -> None:
    """Accept `Authorization: Bearer <token>`, or `?token=` for links opened in a new tab."""
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    supplied = supplied or request.query_params.get("token", "")
    if not supplied or not secrets.compare_digest(supplied, TOKEN):
        raise HTTPException(status_code=401, detail="Missing or wrong access token")


AUTH = [Depends(require_token)]
