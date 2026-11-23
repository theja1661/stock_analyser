"""Read and update the user-tunable parts of backend/config.yaml (comments preserved)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from analyzer.common import CONFIG_FILE, load_config

from ..auth import AUTH
from ..jobs import job
from .results import has_api_key

router = APIRouter(prefix="/api/config", dependencies=AUTH, tags=["settings"])


class Settings(BaseModel):
    budget: float = Field(ge=100, le=100_000_000)
    max_price: float = Field(ge=1, le=1_000_000)
    top_n: int = Field(ge=3, le=50)
    num_picks: int = Field(ge=1, le=10)
    topup_leftover: bool
    max_position_pct: float = Field(ge=10, le=100)
    weights: dict[str, float]
    model: str = Field(pattern=r"^[A-Za-z0-9._\-/]{1,80}$")


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _num(v: float) -> int | float:
    return int(v) if float(v).is_integer() else v


@router.get("")
def get_config() -> dict[str, Any]:
    cfg = load_config()
    return {
        "budget": cfg["budget"],
        "max_price": cfg["screener"]["max_price"],
        "top_n": cfg["screener"]["top_n"],
        "num_picks": cfg["sizing"]["num_picks"],
        "topup_leftover": cfg["sizing"].get("topup_leftover", True),
        "max_position_pct": cfg["sizing"].get("max_position_pct", 45),
        "weights": cfg["screener"]["weights"],
        "model": cfg["llm"]["model"],
        "api_key_env": cfg["llm"].get("api_key_env", "GEMINI_API_KEY"),
        "has_api_key": has_api_key(cfg),
    }


@router.put("")
def put_config(s: Settings) -> dict[str, Any]:
    if job.running:
        raise HTTPException(409, "Wait for the current run to finish before changing settings")
    y = _yaml()
    with open(CONFIG_FILE, encoding="utf-8") as f:
        data = y.load(f)
    known = set(data["screener"]["weights"])
    if set(s.weights) != known or any(not 0 <= v <= 100 for v in s.weights.values()):
        raise HTTPException(400, f"Weights must be exactly {sorted(known)}, each 0-100")
    if sum(s.weights.values()) <= 0:
        raise HTTPException(400, "At least one weight must be above 0")

    data["budget"] = _num(s.budget)
    data["screener"]["max_price"] = _num(s.max_price)
    data["screener"]["top_n"] = s.top_n
    for k, v in s.weights.items():
        data["screener"]["weights"][k] = _num(v)
    data["sizing"]["num_picks"] = s.num_picks
    data["sizing"]["topup_leftover"] = s.topup_leftover
    data["sizing"]["max_position_pct"] = _num(s.max_position_pct)
    data["llm"]["model"] = s.model

    tmp = CONFIG_FILE.with_suffix(".yaml.tmp")
    newline = "\r\n" if b"\r\n" in CONFIG_FILE.read_bytes() else "\n"  # keep original line endings
    with open(tmp, "w", encoding="utf-8", newline=newline) as f:
        y.dump(data, f)
    load_config(tmp)  # make sure it still parses before replacing
    tmp.replace(CONFIG_FILE)
    return get_config()
