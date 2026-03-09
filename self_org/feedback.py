"""
反馈循环管理器 — 正反馈与负反馈的平衡。

自组织核心原理：反馈（Feedback）
- 正反馈：成功行为被放大（蚂蚁在好路径上放更多信息素）
- 负反馈：失败行为被抑制 + 自然衰减
- 两者平衡：避免系统陷入极端状态

实现：
- 追踪每个 Agent 和 Skill 的成功/失败历史
- 根据成功率动态调整任务分配权重
- 系统过热时触发负反馈（降温）
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from utils import get_logger, timestamp_now, clamp
from core.environment import SharedEnvironment

logger = get_logger("Feedback")


@dataclass
class FeedbackRecord:
    agent_id: str
    success: bool
    task_type: str
    duration: float
    timestamp: float = field(default_factory=timestamp_now)
    details: dict[str, Any] = field(default_factory=dict)


class FeedbackLoop:
    """
    反馈循环管理器。

    维护全局和每个 Agent 的反馈统计，
    通过正反馈放大优秀 Agent 的权重，通过负反馈抑制低效行为。
    """

    def __init__(self, environment: SharedEnvironment, window_size: int = 50):
        self._env = environment
        self._window = window_size
        self._records: dict[str, deque[FeedbackRecord]] = defaultdict(lambda: deque(maxlen=window_size))
        self._global_records: deque[FeedbackRecord] = deque(maxlen=window_size * 10)
        self._weights: dict[str, float] = defaultdict(lambda: 1.0)
        self._skill_success: dict[str, deque[bool]] = defaultdict(lambda: deque(maxlen=window_size))
        self._lock = asyncio.Lock()

    async def record(self, agent_id: str, success: bool, task_type: str,
                     duration: float, details: dict[str, Any] | None = None) -> None:
        """记录一次反馈"""
        fb = FeedbackRecord(
            agent_id=agent_id,
            success=success,
            task_type=task_type,
            duration=duration,
            details=details or {},
        )
        async with self._lock:
            self._records[agent_id].append(fb)
            self._global_records.append(fb)
            self._skill_success[task_type].append(success)

            self._update_weight(agent_id)

            trail_type = "success" if success else "failure"
            await self._env.deposit_pheromone(
                location=f"agent:{agent_id}",
                trail_type=trail_type,
                intensity=1.0 if success else 0.3,
                depositor="feedback_loop",
                data={"task_type": task_type, "duration": duration},
            )

    def _update_weight(self, agent_id: str) -> None:
        """正反馈 / 负反馈权重更新"""
        records = self._records[agent_id]
        if len(records) < 3:
            return

        recent = list(records)[-10:]
        success_rate = sum(1 for r in recent if r.success) / len(recent)

        old_weight = self._weights[agent_id]
        if success_rate > 0.7:
            self._weights[agent_id] = clamp(old_weight * 1.1, 0.1, 5.0)
        elif success_rate < 0.3:
            self._weights[agent_id] = clamp(old_weight * 0.85, 0.1, 5.0)

    async def get_weight(self, agent_id: str) -> float:
        async with self._lock:
            return self._weights[agent_id]

    async def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        async with self._lock:
            records = list(self._records.get(agent_id, []))
            if not records:
                return {"total": 0, "success_rate": 0, "avg_duration": 0, "weight": 1.0}

            successes = sum(1 for r in records if r.success)
            durations = [r.duration for r in records]
            return {
                "total": len(records),
                "success_rate": round(successes / len(records), 3),
                "avg_duration": round(sum(durations) / len(durations), 3),
                "weight": round(self._weights[agent_id], 3),
            }

    async def get_global_stats(self) -> dict[str, Any]:
        async with self._lock:
            records = list(self._global_records)
            if not records:
                return {"total": 0, "success_rate": 0, "avg_duration": 0}

            successes = sum(1 for r in records if r.success)
            durations = [r.duration for r in records]
            return {
                "total": len(records),
                "success_rate": round(successes / len(records), 3),
                "avg_duration": round(sum(durations) / len(durations), 3),
                "active_agents": len(self._records),
            }

    async def get_skill_success_rate(self, task_type: str) -> float:
        async with self._lock:
            records = list(self._skill_success.get(task_type, []))
            if not records:
                return 0.5
            return sum(records) / len(records)

    async def is_system_overheated(self, threshold: float = 0.3) -> bool:
        """检测系统是否过热（全局失败率高于阈值）"""
        stats = await self.get_global_stats()
        if stats["total"] < 5:
            return False
        return stats["success_rate"] < threshold

    async def apply_cooling(self) -> None:
        """负反馈：系统过热时降温"""
        logger.warning("System overheated — applying cooling (reducing all weights)")
        async with self._lock:
            for agent_id in self._weights:
                self._weights[agent_id] = clamp(self._weights[agent_id] * 0.7, 0.1, 5.0)

        await self._env.write_blackboard("system_overheated", True)
        await self._env.deposit_pheromone(
            location="global",
            trail_type="cooling_signal",
            intensity=2.0,
            depositor="feedback_loop",
        )
