"""
消息路由器 — 智能化的消息分发。

参考 OpenClaw 的路由策略：
- multi-agent routing: 根据渠道/账户/对等体路由到隔离的 Agent
- session isolation: 每个会话独立上下文
- channel routing: 多通道收件箱

自组织增强：
- 路由决策受信息素影响（成功路径被强化）
- 负载感知路由（避免将消息发给过载 Agent）
- 能力匹配路由（根据技能要求匹配 Agent）
"""

from __future__ import annotations

import random
from typing import Any

from utils import get_logger
from core.registry import AgentRegistry, AgentRecord
from core.environment import SharedEnvironment
from core.message import Message, MessageType
from self_org.feedback import FeedbackLoop
from self_org.stigmergy import StigmergyManager

logger = get_logger("Router")


class MessageRouter:
    """自适应消息路由器"""

    def __init__(
        self,
        registry: AgentRegistry,
        environment: SharedEnvironment,
        feedback: FeedbackLoop,
        stigmergy: StigmergyManager,
        strategy: str = "adaptive",
    ):
        self._registry = registry
        self._env = environment
        self._feedback = feedback
        self._stigmergy = stigmergy
        self._strategy = strategy
        self._route_count = 0

    async def route(self, message: Message) -> str | None:
        """
        路由消息到最合适的 Agent。

        策略优先级：
        1. 如果指定了接收者且不是广播 → 直接路由
        2. adaptive: 综合信息素 + 负载 + 能力匹配 + 部门偏好
        3. round_robin: 轮询
        4. random: 随机
        """
        if not message.is_broadcast and message.receiver != "auto":
            return message.receiver

        task_type = message.payload.get("task_type", "general")
        required_skill = message.payload.get("required_skill")
        allowed_agent_types = message.payload.get("allowed_agent_types")
        preferred_department = message.payload.get("preferred_department")

        if allowed_agent_types is None and message.msg_type == MessageType.TASK:
            allowed_agent_types = ["worker"]

        if self._strategy == "adaptive":
            return await self._adaptive_route(
                task_type, required_skill, allowed_agent_types, preferred_department,
            )
        elif self._strategy == "round_robin":
            return await self._round_robin_route(required_skill, allowed_agent_types)
        else:
            return await self._random_route(required_skill, allowed_agent_types)

    def _filter_candidates(
        self,
        candidates: list[AgentRecord],
        allowed_agent_types: list[str] | None,
    ) -> list[AgentRecord]:
        if not allowed_agent_types:
            return [a for a in candidates if a.state != "dead"]
        allowed = set(allowed_agent_types)
        return [a for a in candidates if a.state != "dead" and a.agent_type in allowed]

    async def _adaptive_route(
        self,
        task_type: str,
        required_skill: str | None,
        allowed_agent_types: list[str] | None,
        preferred_department: str | None = None,
    ) -> str | None:
        """
        自适应路由 — 综合多个信号做出决策。

        权重因子：
        - 信息素推荐 (0.3): 历史上谁擅长这类任务
        - 负载均衡 (0.3): 谁最空闲
        - 反馈权重 (0.2): 谁的历史表现最好
        - 技能匹配 (0.2): 谁具备所需技能
        - 部门偏好 (0.25): 优先匹配 preferred_department 对应的 Worker

        当多个候选者得分相同时，使用轮询避免总是选同一个。
        """
        candidates = self._filter_candidates(self._registry.all_agents, allowed_agent_types)
        if not candidates:
            return None

        if required_skill:
            skill_agents = self._filter_candidates(
                await self._registry.find_by_skill(required_skill),
                allowed_agent_types,
            )
            if skill_agents:
                candidates = skill_agents

        scores: dict[str, float] = {}

        stigmergy_pick = await self._stigmergy.find_best_agent_for_task(task_type)

        for agent in candidates:
            if agent.state == "dead":
                continue

            load_score = (1.0 - agent.load) * 0.3
            feedback_weight = await self._feedback.get_weight(agent.agent_id)
            fb_score = min(feedback_weight / 3.0, 1.0) * 0.2
            stig_score = 0.3 if agent.agent_id == stigmergy_pick else 0.0
            skill_score = 0.2 if required_skill and required_skill in agent.skills else 0.0

            dept_score = 0.0
            if preferred_department:
                agent_dept = getattr(agent, "department", None) or agent.metadata.get("department", "")
                if agent_dept == preferred_department:
                    dept_score = 0.25

            scores[agent.agent_id] = load_score + fb_score + stig_score + skill_score + dept_score

        if not scores:
            return None

        best_score = max(scores.values())
        tied = [aid for aid, s in scores.items() if abs(s - best_score) < 0.01]

        if len(tied) > 1:
            best = tied[self._route_count % len(tied)]
        else:
            best = tied[0]

        self._route_count += 1
        logger.debug("Routed to %s (score=%.3f, total_routes=%d)", best, scores[best], self._route_count)
        return best

    async def _round_robin_route(
        self,
        required_skill: str | None,
        allowed_agent_types: list[str] | None,
    ) -> str | None:
        if required_skill:
            agents = self._filter_candidates(
                await self._registry.find_by_skill(required_skill),
                allowed_agent_types,
            )
        else:
            agents = self._filter_candidates(self._registry.all_agents, allowed_agent_types)

        if not agents:
            return None

        idx = self._route_count % len(agents)
        self._route_count += 1
        return agents[idx].agent_id

    async def _random_route(
        self,
        required_skill: str | None,
        allowed_agent_types: list[str] | None,
    ) -> str | None:
        if required_skill:
            agents = self._filter_candidates(
                await self._registry.find_by_skill(required_skill),
                allowed_agent_types,
            )
        else:
            agents = self._filter_candidates(self._registry.all_agents, allowed_agent_types)

        if not agents:
            return None

        return random.choice(agents).agent_id

    @property
    def total_routes(self) -> int:
        return self._route_count
