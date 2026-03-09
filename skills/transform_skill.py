"""转换技能 — 模拟数据转换能力"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from .base_skill import BaseSkill, SkillResult


class TransformSkill(BaseSkill):
    """转换技能：对输入数据进行各种变换"""

    def __init__(self):
        super().__init__(name="transform", description="Data transformation and processing")

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        data = params.get("data")
        operation = params.get("operation", "identity")

        if data is None:
            return SkillResult(success=False, error="No data provided")

        await asyncio.sleep(random.uniform(0.1, 0.4))

        try:
            result = self._apply_transform(data, operation)
            return SkillResult(success=True, data={"result": result, "operation": operation})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _apply_transform(self, data: Any, operation: str) -> Any:
        if operation == "identity":
            return data
        elif operation == "uppercase" and isinstance(data, str):
            return data.upper()
        elif operation == "lowercase" and isinstance(data, str):
            return data.lower()
        elif operation == "reverse" and isinstance(data, (str, list)):
            return data[::-1]
        elif operation == "sort" and isinstance(data, list):
            return sorted(data)
        elif operation == "double" and isinstance(data, (int, float)):
            return data * 2
        elif operation == "flatten" and isinstance(data, list):
            flat = []
            for item in data:
                if isinstance(item, list):
                    flat.extend(item)
                else:
                    flat.append(item)
            return flat
        else:
            return data
