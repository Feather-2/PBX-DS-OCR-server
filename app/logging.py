from __future__ import annotations

import logging
import os


def setup_logging(level: str | int = "INFO") -> logging.Logger:
    lvl = level
    if isinstance(level, str):
        lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
    )
    logger = logging.getLogger("dsocr-service")
    return logger
