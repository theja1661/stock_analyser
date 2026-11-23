"""Web server entry point (run from the project root or from backend/).

    python backend/server.py      # then open the printed URL on your phone or PC
"""
from __future__ import annotations

import socket

import uvicorn

from analyzer.common import load_config
from api.app import app
from api.auth import TOKEN, TOKEN_FILE


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # picks the outbound interface; no packets are sent
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    web = load_config().get("web") or {}
    host, port = web.get("host", "0.0.0.0"), int(web.get("port", 8000))
    print("\n  Stock Analyzer web UI")
    print(f"  On this PC:   http://127.0.0.1:{port}/?token={TOKEN}")
    if host in ("0.0.0.0", "::"):
        print(f"  On your phone (same Wi-Fi):  http://{lan_ip()}:{port}/?token={TOKEN}")
    print(f"  The token is saved in {TOKEN_FILE}. Delete that file to issue a new one.\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
