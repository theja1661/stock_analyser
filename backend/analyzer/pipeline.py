"""Ordered registry of pipeline stages, shared by the CLI and the web API."""
from __future__ import annotations

from typing import Any, Callable

from . import ingestion, llm_analysis, report, screener, sizing

# name -> callable(cfg, refresh: bool)
STAGES: list[tuple[str, Callable[[dict[str, Any], bool], Any]]] = [
    ("ingest", lambda cfg, refresh: ingestion.run(cfg, force=refresh)),
    ("screener", lambda cfg, refresh: screener.run(cfg)),
    ("llm", lambda cfg, refresh: llm_analysis.run(cfg)),
    ("sizing", lambda cfg, refresh: sizing.run(cfg)),
    ("report", lambda cfg, refresh: report.run(cfg)),
]
STAGE_NAMES: list[str] = [name for name, _ in STAGES]


def select(stage: str | None = None, from_stage: str | None = None) -> list[str]:
    """Stage names to run: one stage, a stage and everything after it, or all."""
    if stage:
        return [stage]
    if from_stage:
        return STAGE_NAMES[STAGE_NAMES.index(from_stage):]
    return list(STAGE_NAMES)
