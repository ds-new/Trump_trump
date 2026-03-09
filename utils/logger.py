"""统一日志模块"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(name)

    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)-7s %(name)-20s │ %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logging.root.addHandler(handler)
        logging.root.setLevel(getattr(logging, level.upper(), logging.INFO))
        _CONFIGURED = True

    return logger
