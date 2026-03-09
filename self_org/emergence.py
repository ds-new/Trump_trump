"""
涌现引擎 — 从简单规则中产生复杂行为。

自组织核心原理：涌现（Emergence）
- 整体大于部分之和
- 宏观模式从微观交互中自发产生
- 无需中央编排，模式自然浮现

实现机制：
1. 模式检测：监控 Agent 集体行为，识别涌现模式
2. 领导者涌现：根据能力和信誉自动推选协调者
3. 集群形成：相似任务的 Agent 自发聚集
4. 负载均衡涌现：通过局部感知实现全局平衡
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from utils import get_logger, timestamp_now
from core.registry import AgentRegistry, AgentRecord
from core.environment import SharedEnvironment
from core.event_bus import EventBus
from core.message import Message, MessageType

logger = get_logger("Emergence")


class EmergenceEngine:
    """涌现引擎 — 检测并促进系统级别的涌现行为"""

    def __init__(
        self,
        registry: AgentRegistry,
        environment: SharedEnvironment,
        event_bus: EventBus,
        threshold: float = 0.6,
        min_agents: int = 2,
    ):
        self._registry = registry
        self._env = environment
        self._bus = event_bus
        self._threshold = threshold
        self._min_agents = min_agents
        self._patterns: list[dict[str, Any]] = []
        self._running = False
        self._leader_scores: dict[str, float] = {}
        self._current_leader: str | None = None

    async def detect_patterns(self) -> list[dict[str, Any]]:
        """
        模式检测：分析 Agent 群体行为，发现涌现模式。

        检测维度：
        - 负载分布模式（均匀/倾斜/过载）
        - 技能聚集模式（某类技能 Agent 是否自发集群）
        - 通信拓扑（星型/环型/全连接）
        """
        agents = self._registry.all_agents
        if not agents:
            return []

        patterns = []

        load_distribution = self._analyze_load(agents)
        patterns.append({"type": "load_distribution", **load_distribution})

        skill_clusters = self._analyze_skill_clusters(agents)
        if skill_clusters:
            patterns.append({"type": "skill_clustering", "clusters": skill_clusters})

        health_pattern = self._analyze_health(agents)
        patterns.append({"type": "system_health", **health_pattern})

        self._patterns = patterns
        return patterns

    def _analyze_load(self, agents: list[AgentRecord]) -> dict[str, Any]:
        loads = [a.load for a in agents]
        avg_load = sum(loads) / len(loads) if loads else 0
        max_load = max(loads) if loads else 0
        overloaded = sum(1 for l in loads if l > 0.8)

        if avg_load < 0.3:
            pattern = "underutilized"
        elif avg_load > 0.7:
            pattern = "saturated"
        elif max_load - min(loads) < 0.2:
            pattern = "balanced"
        else:
            pattern = "skewed"

        return {
            "pattern": pattern,
            "avg_load": round(avg_load, 3),
            "max_load": round(max_load, 3),
            "overloaded_count": overloaded,
            "agent_count": len(agents),
        }

    def _analyze_skill_clusters(self, agents: list[AgentRecord]) -> list[dict[str, Any]]:
        skill_agents: dict[str, list[str]] = {}
        for a in agents:
            for skill in a.skills:
                skill_agents.setdefault(skill, []).append(a.agent_id)

        clusters = []
        for skill, agent_ids in skill_agents.items():
            if len(agent_ids) >= 2:
                clusters.append({
                    "skill": skill,
                    "size": len(agent_ids),
                    "agents": agent_ids,
                })
        return clusters

    def _analyze_health(self, agents: list[AgentRecord]) -> dict[str, Any]:
        state_counts = Counter(a.state for a in agents)
        total = len(agents)
        healthy = state_counts.get("idle", 0) + state_counts.get("busy", 0)
        health_ratio = healthy / total if total > 0 else 0

        return {
            "health_ratio": round(health_ratio, 3),
            "states": dict(state_counts),
            "total": total,
        }

    async def elect_leader(self) -> str | None:
        """
        领导者涌现 — 不是指定，而是根据能力和信誉自然产生。

        评分标准：
        - 技能多样性（越多技能越适合协调）
        - 当前负载（负载低说明有余力）
        - 运行稳定性（不频繁下线）
        - 历史表现
        """
        agents = self._registry.all_agents
        if not agents:
            return None

        scores: dict[str, float] = {}
        for agent in agents:
            skill_score = len(agent.skills) * 0.3
            load_score = (1.0 - agent.load) * 0.3
            stability = min((timestamp_now() - agent.registered_at) / 60.0, 1.0) * 0.2
            history = self._leader_scores.get(agent.agent_id, 0.5) * 0.2
            scores[agent.agent_id] = skill_score + load_score + stability + history

        self._leader_scores = scores

        best_id = max(scores, key=lambda k: scores[k])

        await self._env.write_blackboard("current_leader", best_id)
        await self._env.deposit_pheromone(
            location="leadership",
            trail_type="leader_signal",
            intensity=scores[best_id],
            depositor=best_id,
            data={"scores": {k: round(v, 3) for k, v in scores.items()}},
        )

        if best_id != self._current_leader:
            logger.info("Leader emerged: %s (score=%.3f)", best_id, scores[best_id])
            self._current_leader = best_id
        else:
            logger.debug("Leader unchanged: %s (score=%.3f)", best_id, scores[best_id])
        return best_id

    async def suggest_scaling(self) -> dict[str, Any]:
        """根据涌现模式建议扩缩容"""
        patterns = await self.detect_patterns()
        suggestion = {"action": "none", "reason": ""}

        for p in patterns:
            if p["type"] == "load_distribution":
                if p["pattern"] == "saturated" or p.get("overloaded_count", 0) > 0:
                    suggestion = {
                        "action": "scale_up",
                        "reason": f"System saturated: avg_load={p['avg_load']}, overloaded={p['overloaded_count']}",
                        "recommended_count": max(1, p.get("overloaded_count", 1)),
                    }
                elif p["pattern"] == "underutilized" and p["agent_count"] > self._min_agents:
                    suggestion = {
                        "action": "scale_down",
                        "reason": f"Underutilized: avg_load={p['avg_load']}",
                        "recommended_count": max(1, p["agent_count"] // 3),
                    }
        return suggestion

    async def run(self, interval: float = 10.0) -> None:
        self._running = True
        logger.info("EmergenceEngine started (interval=%.1fs)", interval)
        while self._running:
            await asyncio.sleep(interval)
            try:
                patterns = await self.detect_patterns()
                await self.elect_leader()
                await self._env.write_blackboard("emergence_patterns", patterns)
            except Exception as e:
                logger.error("EmergenceEngine error: %s", e)

    async def stop(self) -> None:
        self._running = False
