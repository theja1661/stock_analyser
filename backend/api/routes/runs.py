"""Start, watch and cancel pipeline runs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from analyzer.pipeline import STAGE_NAMES

from ..auth import AUTH
from ..jobs import job

router = APIRouter(prefix="/api", dependencies=AUTH, tags=["runs"])


class RunRequest(BaseModel):
    stage: str | None = None
    from_stage: str | None = None
    refresh: bool = False


@router.post("/run")
def run(req: RunRequest) -> dict[str, Any]:
    if req.stage and req.from_stage:
        raise HTTPException(400, "Use either stage or from_stage")
    args: list[str] = []
    for value, flag in ((req.stage, "--stage"), (req.from_stage, "--from")):
        if value:
            if value not in STAGE_NAMES:
                raise HTTPException(400, f"Unknown stage {value}")
            args += [flag, value]
    if req.refresh:
        args.append("--refresh")
    job.start(args)
    return job.status()


@router.get("/job")
def job_status(since: int = 0, lines: bool = True) -> dict[str, Any]:
    return job.status(since, include_lines=lines)


@router.post("/job/cancel")
def job_cancel() -> dict[str, Any]:
    job.cancel()
    return job.status(include_lines=False)
