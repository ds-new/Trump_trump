"""
信息素管理器 — 间接协调的高级抽象。

Stigmergy（希腊语 στίγμα + ἔργον = "标记" + "工作"）
- 最初描述白蚁筑巢行为：无中央指挥，通过在环境中留痕来间接协调
- 在本系统中：Agent 通过在共享环境中留下「任务线索」来引导其他 Agent

高级信息素类型：
- task_trail: 任务路径信息素（哪些任务频繁出现在哪些位置）
- skill_demand: 技能需求信号（哪些技能被需要）
- success_path: 成功路径（历史上哪些 Agent 组合解决了类似问题）
- warning_signal: 警告信号（哪些路径容易失败）
"""

from __future__ import annotations

import asyncio
from typing import Any

from utils import get_logger, timestamp_now
from core.environment import SharedEnvironment

logger = get_logger("Stigmergy")


class StigmergyManager:
    """
    高级信息素管理，在 SharedEnvironment 基础上提供语义化的信息素操作。
    """

    TRAIL_TYPES = ("task_trail", "skill_demand", "success_path", "warning_signal")

    def __init__(self, environment: SharedEnvironment):
        self._env = environment

    async def mark_task(self, task_type: str, agent_id: str, success: bool) -> None:
        """标记任务路径 — 成功的路径信息素增强，失败的路径添加警告"""
        intensity = 2.0 if success else 0.5
        trail = "success_path" if success else "warning_signal"

        await self._env.deposit_pheromone(
            location=f"task:{task_type}",
            trail_type=trail,
            intensity=intensity,
            depositor=agent_id,
            data={"success": success, "task_type": task_type},
        )

        await self._env.deposit_pheromone(
            location=f"task:{task_type}",
            trail_type="task_trail",
            intensity=1.0,
            depositor=agent_id,
        )

    async def signal_skill_demand(self, skill_name: str, urgency: float = 1.0) -> None:
        """发出技能需求信号 — 告知系统需要某种技能"""
        await self._env.deposit_pheromone(
            location="skill_market",
            trail_type="skill_demand",
            intensity=urgency,
            depositor="system",
            data={"skill": skill_name},
        )

        demand = await self._env.read_blackboard("skill_demand", {})
        demand[skill_name] = demand.get(skill_name, 0) + urgency
        await self._env.write_blackboard("skill_demand", demand)

    async def find_best_agent_for_task(self, task_type: str) -> str | None:
        """根据信息素找到最适合处理某任务的 Agent"""
        trails = await self._env.read_pheromones(f"task:{task_type}", "success_path")
        if not trails:
            return None

        best = max(trails, key=lambda p: p.intensity)
        return best.depositor

    async def get_task_risk(self, task_type: str) -> float:
        """获取任务风险评估（基于警告信息素）"""
        warnings = await self._env.read_pheromones(f"task:{task_type}", "warning_signal")
        successes = await self._env.read_pheromones(f"task:{task_type}", "success_path")

        warning_total = sum(p.intensity for p in warnings)
        success_total = sum(p.intensity for p in successes)
        total = warning_total + success_total

        if total == 0:
            return 0.5
        return warning_total / total

    async def get_skill_demand_ranking(self) -> list[tuple[str, float]]:
        """获取技能需求排行"""
        demand = await self._env.read_blackboard("skill_demand", {})
        return sorted(demand.items(), key=lambda x: x[1], reverse=True)

    async def decay_cycle(self) -> int:
        """执行一次全局信息素衰减"""
        removed = await self._env.evaporate()
        if removed > 0:
            logger.debug("Pheromone decay: removed %d trails", removed)
        return removed

    async def run(self, interval: float = 5.0) -> None:
        """持续运行信息素衰减循环"""
        logger.info("StigmergyManager started (decay_interval=%.1fs)", interval)
        while True:
            await asyncio.sleep(interval)
            try:
                await self.decay_cycle()
            except Exception as e:
                logger.error("Stigmergy decay error: %s", e)
