"""CLI entry point (run from the project root or from backend/).

    python backend/main.py run                    # full weekly pipeline
    python backend/main.py run --stage screener   # one stage
    python backend/main.py run --from llm         # a stage and everything after it
"""
from __future__ import annotations

import argparse
import sys
import time

from analyzer.common import load_config, log, setup_logging
from analyzer.pipeline import STAGE_NAMES, STAGES, select


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Weekly NSE stock screener + LLM document analysis")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run the pipeline")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--stage", choices=STAGE_NAMES, help="run only this stage")
    g.add_argument("--from", dest="from_stage", choices=STAGE_NAMES,
                   help="run this stage and all later ones")
    r.add_argument("--refresh", action="store_true", help="ignore the 3-day price/fundamentals cache")
    r.add_argument("--config", default=None, help="path to config.yaml")
    r.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    setup_logging(args.verbose)
    try:
        cfg = load_config(args.config) if args.config else load_config()
    except Exception as e:
        log.error("Cannot load config: %s", e)
        return 2

    selected = select(args.stage, args.from_stage)
    for name, fn in STAGES:
        if name not in selected:
            continue
        log.info("=" * 60)
        log.info("STAGE: %s", name.upper())
        log.info("=" * 60)
        t0 = time.monotonic()
        try:
            fn(cfg, args.refresh)
        except KeyboardInterrupt:
            log.error("Interrupted.")
            return 130
        except Exception:
            log.exception("Stage '%s' failed", name)
            return 1
        log.info("Stage %s finished in %.1fs", name, time.monotonic() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
