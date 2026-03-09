"""
Agent 注册中心 — 去中心化的服务发现。

自组织原理：
- 类似蚁群中的「气味标记」：Agent 注册后向环境广播存在信息
- 支持按能力（skill）、状态、负载发现 Agent
- 自动清理失联 Agent（自愈）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from utils import get_logger, timestamp_now

if TYPE_CHECKING:
    from .agent import BaseAgent

logger = get_logger("Registry")


@dataclass
class AgentRecord:
    agent_id: str
    agent_type: str
    skills: list[str]
    state: str
    load: float  # 0.0 ~ 1.0
    registered_at: float
    last_heartbeat: float
    metadata: dict = field(default_factory=dict)


class AgentRegistry:
    """Agent 注册与发现中心"""

    def __init__(self, heartbeat_timeout: float = 15.0):
        self._agents: dict[str, AgentRecord] = {}
        self._heartbeat_timeout = heartbeat_timeout
        self._lock = asyncio.Lock()

    async def register(self, agent: BaseAgent) -> None:
        async with self._lock:
            now = timestamp_now()
            record = AgentRecord(
                agent_id=agent.agent_id,
                agent_type=agent.agent_type,
                skills=[s.name for s in agent.skills],
                state=agent.state.value,
                load=agent.load,
                registered_at=now,
                last_heartbeat=now,
                metadata=dict(getattr(agent, "metadata", {})),
            )
            self._agents[agent.agent_id] = record
            logger.info("Registered: %s [%s] skills=%s", agent.agent_id, agent.agent_type, record.skills)

    async def unregister(self, agent_id: str) -> None:
        async with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                logger.info("Unregistered: %s", agent_id)

    async def heartbeat(self, agent_id: str, load: float = 0.0, state: str = "idle") -> None:
        async with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].last_heartbeat = timestamp_now()
                self._agents[agent_id].load = load
                self._agents[agent_id].state = state

    async def find_by_skill(self, skill_name: str) -> list[AgentRecord]:
        async with self._lock:
            return [
                r for r in self._agents.values()
                if skill_name in r.skills and r.state != "dead"
            ]

    async def find_by_type(self, agent_type: str) -> list[AgentRecord]:
        async with self._lock:
            return [
                r for r in self._agents.values()
                if r.agent_type == agent_type and r.state != "dead"
            ]

    async def find_least_loaded(self, agent_type: str | None = None) -> AgentRecord | None:
        async with self._lock:
            candidates = [
                r for r in self._agents.values()
                if r.state in ("idle", "busy") and (agent_type is None or r.agent_type == agent_type)
            ]
            if not candidates:
                return None
            return min(candidates, key=lambda r: r.load)

    async def cleanup_stale(self) -> list[str]:
        """清理超时未响应的 Agent（自愈机制）"""
        now = timestamp_now()
        stale = []
        async with self._lock:
            for agent_id, record in list(self._agents.items()):
                if now - record.last_heartbeat > self._heartbeat_timeout:
                    stale.append(agent_id)
                    del self._agents[agent_id]
                    logger.warning("Cleaned stale agent: %s (silent %.1fs)", agent_id, now - record.last_heartbeat)
        return stale

    @property
    def all_agents(self) -> list[AgentRecord]:
        return list(self._agents.values())

    @property
    def count(self) -> int:
        return len(self._agents)
