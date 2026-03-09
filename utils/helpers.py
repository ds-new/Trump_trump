"""通用工具函数"""

from __future__ import annotations

import time
import uuid


def generate_id(prefix: str = "agent") -> str:
    short = uuid.uuid4().hex[:8]
    return f"{prefix}-{short}"


def timestamp_now() -> float:
    return time.time()


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
