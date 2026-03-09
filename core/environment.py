"""
共享环境 — 信息素（Stigmergy）的载体。

自组织核心机制：
- 信息素沉积与蒸发：Agent 在环境中留下信息标记（类似蚂蚁在路径上留下信息素）
- 间接协调：Agent 不需要直接通信，通过读取环境中的信号来协调行为
- 正反馈循环：成功路径的信息素增强，引导更多 Agent 走同样的路
- 负反馈循环：信息素自然衰减，避免系统锁死在旧模式中
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from utils import get_logger, timestamp_now

logger = get_logger("Environment")


@dataclass
class Pheromone:
    """信息素标记"""
    trail_type: str
    intensity: float
    depositor: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=timestamp_now)
    updated_at: float = field(default_factory=timestamp_now)


class SharedEnvironment:
    """
    共享环境 — 所有 Agent 的公共知识空间。

    功能：
    - 信息素沉积/读取/蒸发
    - 共享黑板（Blackboard）用于任务发布
    - 全局状态统计
    """

    def __init__(self, decay_rate: float = 0.05, amplify_factor: float = 1.5):
        self._pheromones: dict[str, list[Pheromone]] = defaultdict(list)
        self._blackboard: dict[str, Any] = {}
        self._decay_rate = decay_rate
        self._amplify_factor = amplify_factor
        self._lock = asyncio.Lock()
        self._stats: dict[str, float] = defaultdict(float)

    async def deposit_pheromone(self, location: str, trail_type: str, intensity: float,
                                  depositor: str, data: dict[str, Any] | None = None) -> None:
        """在某个位置沉积信息素"""
        async with self._lock:
            existing = None
            for p in self._pheromones[location]:
                if p.trail_type == trail_type and p.depositor == depositor:
                    existing = p
                    break

            if existing:
                existing.intensity = min(existing.intensity + intensity * self._amplify_factor, 10.0)
                existing.updated_at = timestamp_now()
                if data:
                    existing.data.update(data)
            else:
                self._pheromones[location].append(
                    Pheromone(trail_type=trail_type, intensity=intensity, depositor=depositor, data=data or {})
                )

            self._stats["deposits"] += 1

    async def read_pheromones(self, location: str, trail_type: str | None = None) -> list[Pheromone]:
        """读取某个位置的信息素"""
        async with self._lock:
            trails = self._pheromones.get(location, [])
            if trail_type:
                return [p for p in trails if p.trail_type == trail_type]
            return list(trails)

    async def get_strongest_trail(self, location: str, trail_type: str) -> Pheromone | None:
        """获取某位置最强的信息素路径"""
        trails = await self.read_pheromones(location, trail_type)
        if not trails:
            return None
        return max(trails, key=lambda p: p.intensity)

    async def evaporate(self) -> int:
        """全局信息素蒸发（模拟自然衰减）"""
        removed = 0
        async with self._lock:
            for location in list(self._pheromones.keys()):
                surviving = []
                for p in self._pheromones[location]:
                    p.intensity *= (1 - self._decay_rate)
                    if p.intensity > 0.01:
                        surviving.append(p)
                    else:
                        removed += 1
                self._pheromones[location] = surviving
                if not surviving:
                    del self._pheromones[location]
        self._stats["evaporated"] += removed
        return removed

    async def write_blackboard(self, key: str, value: Any) -> None:
        async with self._lock:
            self._blackboard[key] = value

    async def read_blackboard(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._blackboard.get(key, default)

    async def list_blackboard(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._blackboard)

    @property
    def pheromone_count(self) -> int:
        return sum(len(v) for v in self._pheromones.values())

    @property
    def stats(self) -> dict[str, float]:
        return dict(self._stats)
