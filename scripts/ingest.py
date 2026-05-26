#!/usr/bin/env python3
"""One-shot ingest: MinerU parse -> structure -> index."""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.orchestrator import ingest
from src.config.settings import get_settings

logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ingest")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest PDF into vector + BM25 index")
    parser.add_argument("--session-id", default=None, help="Usage log session id")
    args = parser.parse_args()
    sid = args.session_id or f"ingest-{uuid.uuid4().hex[:8]}"
    try:
        result = ingest(session_id=sid)
        logger.info("Ingest OK: %s", result)
        print(result)
        return 0
    except Exception as e:
        logger.exception("Ingest failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
