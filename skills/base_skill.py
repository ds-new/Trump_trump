"""
技能基类 — 参考 OpenClaw Skills Platform。

OpenClaw 的技能系统：
- bundled skills（内置技能）
- managed skills（通过 ClawHub 管理）
- workspace skills（用户自定义）

本系统的技能：
- 每个技能是一个独立可执行单元
- 技能可以被动态挂载到 Agent 上
- 技能执行结果产生反馈，影响信息素
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from utils import generate_id, timestamp_now


@dataclass
class SkillResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration: float = 0.0
    skill_name: str = ""
    timestamp: float = field(default_factory=timestamp_now)


class BaseSkill(ABC):
    """技能抽象基类"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.skill_id = generate_id("skill")
        self._execution_count = 0
        self._success_count = 0

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> SkillResult:
        """执行技能"""
        ...

    @property
    def success_rate(self) -> float:
        if self._execution_count == 0:
            return 0.0
        return self._success_count / self._execution_count

    async def run(self, params: dict[str, Any]) -> SkillResult:
        """带统计的执行包装"""
        start = timestamp_now()
        try:
            result = await self.execute(params)
            result.duration = timestamp_now() - start
            result.skill_name = self.name
            self._execution_count += 1
            if result.success:
                self._success_count += 1
            return result
        except Exception as e:
            self._execution_count += 1
            return SkillResult(
                success=False,
                error=str(e),
                duration=timestamp_now() - start,
                skill_name=self.name,
            )

    def __repr__(self) -> str:
        return f"<Skill:{self.name} rate={self.success_rate:.0%}>"
