"""Runs one pipeline subprocess at a time and keeps its log in memory."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from analyzer.common import BACKEND_DIR, ROOT_DIR

MAX_LOG_LINES = 3000
MAIN_SCRIPT = BACKEND_DIR / "main.py"


class JobRunner:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[str] | None = None
        self.lines: list[str] = []
        self.dropped = 0
        self.args: list[str] = []
        self.started: str | None = None
        self.finished: str | None = None
        self.exit_code: int | None = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, args: list[str]) -> None:
        with self.lock:
            if self.running:
                raise HTTPException(status_code=409, detail="A pipeline run is already in progress")
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            self.proc = subprocess.Popen(
                [sys.executable, "-u", str(MAIN_SCRIPT), "run", *args],
                cwd=ROOT_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            self.lines, self.dropped, self.args = [], 0, args
            self.started = datetime.now().isoformat(timespec="seconds")
            self.finished, self.exit_code = None, None
            threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()

    def _pump(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            with self.lock:
                self.lines.append(line.rstrip("\n"))
                if len(self.lines) > MAX_LOG_LINES:
                    self.lines.pop(0)
                    self.dropped += 1
        code = proc.wait()
        with self.lock:
            self.exit_code = code
            self.finished = datetime.now().isoformat(timespec="seconds")

    def cancel(self) -> None:
        with self.lock:
            if self.running and self.proc:
                self.proc.terminate()

    def status(self, since: int = 0, include_lines: bool = True) -> dict[str, Any]:
        with self.lock:
            out: dict[str, Any] = {
                "running": self.running,
                "args": self.args,
                "started": self.started,
                "finished": self.finished,
                "exit_code": self.exit_code,
                "next": self.dropped + len(self.lines),
            }
            if include_lines:
                out["lines"] = self.lines[max(0, since - self.dropped):]
            return out


job = JobRunner()
