"""分析技能 — 模拟数据分析能力"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from .base_skill import BaseSkill, SkillResult


class AnalyzeSkill(BaseSkill):
    """分析技能：对输入数据进行统计分析"""

    def __init__(self):
        super().__init__(name="analyze", description="Data analysis and statistical computation")

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        data = params.get("data", [])
        if not data:
            return SkillResult(success=False, error="No data provided")

        await asyncio.sleep(random.uniform(0.2, 0.8))

        if not isinstance(data, list):
            data = [data]

        numeric = [x for x in data if isinstance(x, (int, float))]
        if not numeric:
            return SkillResult(
                success=True,
                data={
                    "type": "categorical",
                    "count": len(data),
                    "unique": len(set(str(x) for x in data)),
                },
            )

        return SkillResult(
            success=True,
            data={
                "type": "numeric",
                "count": len(numeric),
                "sum": sum(numeric),
                "mean": sum(numeric) / len(numeric),
                "min": min(numeric),
                "max": max(numeric),
                "range": max(numeric) - min(numeric),
            },
        )
