"""
自适应策略 — Agent 行为的动态调整。

自组织核心原理：适应（Adaptation）
- 个体适应：Agent 根据自身历史表现调整策略
- 群体适应：系统整体根据涌现模式调整结构
- 环境适应：根据任务流量和复杂度动态扩缩容

类比自然界：
- 蜂群中蜜蜂会根据食物源质量改变舞蹈频率
- 鱼群中个体根据邻居行为调整游动方向
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

from utils import get_logger, clamp
from core.registry import AgentRegistry
from core.environment import SharedEnvironment
from .feedback import FeedbackLoop

logger = get_logger("Adaptation")


class AdaptationAction(Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    REBALANCE = "rebalance"
    SKILL_SHIFT = "skill_shift"
    COOLDOWN = "cooldown"
    NONE = "none"


class AdaptationStrategy:
    """
    自适应策略引擎。

    持续监控系统状态，生成适应性动作建议。
    不直接执行动作，而是输出建议由上层（Gateway/Coordinator）执行。
    """

    def __init__(
        self,
        registry: AgentRegistry,
        environment: SharedEnvironment,
        feedback: FeedbackLoop,
        adaptation_rate: float = 0.1,
        min_agents: int = 2,
        max_agents: int = 20,
    ):
        self._registry = registry
        self._env = environment
        self._feedback = feedback
        self._rate = adaptation_rate
        self._min_agents = min_agents
        self._max_agents = max_agents
        self._history: list[dict[str, Any]] = []
        self._last_action: str = "none"

    async def evaluate(self) -> dict[str, Any]:
        """
        评估当前系统状态，生成适应性建议。

        决策逻辑：
        1. 如果系统过热 → 降温
        2. 如果 Agent 不足 → 扩容
        3. 如果 Agent 过剩 → 缩容
        4. 如果负载不均 → 重平衡
        5. 如果某技能需求激增 → 技能迁移
        """
        agents = self._registry.all_agents
        agent_count = len(agents)
        global_stats = await self._feedback.get_global_stats()

        if await self._feedback.is_system_overheated():
            action = self._build_action(AdaptationAction.COOLDOWN, "System failure rate too high")
            self._history.append(action)
            return action

        if agent_count > 0:
            avg_load = sum(a.load for a in agents) / agent_count
            overloaded = sum(1 for a in agents if a.load > 0.8)

            if overloaded > agent_count * 0.5 and agent_count < self._max_agents:
                needed = min(overloaded, self._max_agents - agent_count)
                action = self._build_action(
                    AdaptationAction.SCALE_UP,
                    f"{overloaded}/{agent_count} agents overloaded",
                    count=needed,
                )
                self._history.append(action)
                return action

            if avg_load < 0.15 and agent_count > self._min_agents:
                removable = max(1, (agent_count - self._min_agents) // 2)
                action = self._build_action(
                    AdaptationAction.SCALE_DOWN,
                    f"Avg load {avg_load:.2f}, system underutilized",
                    count=removable,
                )
                self._history.append(action)
                return action

            loads = [a.load for a in agents]
            if loads:
                variance = sum((l - avg_load) ** 2 for l in loads) / len(loads)
                if variance > 0.1:
                    action = self._build_action(
                        AdaptationAction.REBALANCE,
                        f"Load variance {variance:.3f} too high",
                    )
                    self._history.append(action)
                    return action

        skill_demand = await self._env.read_blackboard("skill_demand", {})
        if skill_demand:
            highest = max(skill_demand, key=skill_demand.get)
            providers = await self._registry.find_by_skill(highest)
            if len(providers) == 0:
                action = self._build_action(
                    AdaptationAction.SKILL_SHIFT,
                    f"No providers for high-demand skill: {highest}",
                    target_skill=highest,
                )
                self._history.append(action)
                return action

        return self._build_action(AdaptationAction.NONE, "System stable")

    def _build_action(self, action: AdaptationAction, reason: str, **kwargs: Any) -> dict[str, Any]:
        return {"action": action.value, "reason": reason, **kwargs}

    async def run(self, interval: float = 8.0) -> None:
        logger.info("AdaptationStrategy started (interval=%.1fs)", interval)
        while True:
            await asyncio.sleep(interval)
            try:
                result = await self.evaluate()
                action = result["action"]
                if action != "none" and action != self._last_action:
                    logger.info("Adaptation: %s — %s", action, result["reason"])
                self._last_action = action
                if action != "none":
                    await self._env.write_blackboard("adaptation_action", result)
            except Exception as e:
                logger.error("Adaptation error: %s", e)

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)
