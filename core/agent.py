"""
Agent 基类 — 自组织系统的基本单元。

设计理念（映射自组织原理）：
- 自治性：每个 Agent 独立运行事件循环，自主决策
- 局部交互：Agent 通过消息与邻近 Agent 通信
- 简单规则：每个 Agent 遵循简单行为规则，复杂行为从整体涌现
- 适应性：Agent 根据反馈动态调整行为参数

参考 OpenClaw 的 Pi Agent Runtime：
- RPC 模式 + 工具流式调用
- 技能（Skills）可挂载
- 会话隔离
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from utils import get_logger, generate_id, timestamp_now
from .message import Message, MessageType
from .event_bus import EventBus


class AgentState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    OVERLOADED = "overloaded"
    DEAD = "dead"
    SPAWNING = "spawning"


class BaseAgent(ABC):
    """
    所有 Agent 的抽象基类。

    每个 Agent 具备：
    - 唯一身份标识
    - 技能列表
    - 独立事件循环
    - 收件箱（异步队列）
    - 生命周期钩子
    """

    def __init__(
        self,
        agent_type: str,
        event_bus: EventBus,
        agent_id: str | None = None,
        skills: list | None = None,
    ):
        self.agent_id = agent_id or generate_id(agent_type)
        self.agent_type = agent_type
        self.event_bus = event_bus
        self.skills: list = skills or []
        self.state = AgentState.IDLE
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._running = False
        self._task_count = 0
        self._max_tasks = 5
        self._performance: list[float] = []
        self._created_at = timestamp_now()
        self.logger = get_logger(f"Agent:{self.agent_id}")
        self.metadata: dict[str, Any] = {}

    @property
    def load(self) -> float:
        if self._max_tasks == 0:
            return 1.0
        return self._task_count / self._max_tasks

    @property
    def uptime(self) -> float:
        return timestamp_now() - self._created_at

    @property
    def avg_performance(self) -> float:
        if not self._performance:
            return 0.0
        return sum(self._performance) / len(self._performance)

    async def receive(self, message: Message) -> None:
        await self._inbox.put(message)

    async def send(self, message: Message) -> None:
        await self.event_bus.publish(message)

    async def broadcast(self, payload: dict[str, Any], msg_type: MessageType = MessageType.EVENT) -> None:
        msg = Message(msg_type=msg_type, sender=self.agent_id, receiver="*", payload=payload)
        await self.send(msg)

    def record_performance(self, score: float) -> None:
        self._performance.append(score)
        if len(self._performance) > 100:
            self._performance = self._performance[-50:]

    @abstractmethod
    async def handle_message(self, message: Message) -> None:
        """处理收到的消息 — 子类实现具体逻辑"""
        ...

    async def on_start(self) -> None:
        """生命周期：启动时"""
        self.logger.info("Agent started [type=%s, skills=%s]", self.agent_type, [s.name for s in self.skills])

    async def on_stop(self) -> None:
        """生命周期：停止时"""
        self.logger.info("Agent stopped (uptime=%.1fs, avg_perf=%.2f)", self.uptime, self.avg_performance)

    async def on_tick(self) -> None:
        """周期性自检 — 可用于自适应行为"""
        pass

    async def run(self) -> None:
        self._running = True
        self.state = AgentState.IDLE
        await self.on_start()

        tick_interval = 2.0

        while self._running:
            try:
                try:
                    message = await asyncio.wait_for(self._inbox.get(), timeout=tick_interval)
                    self.state = AgentState.BUSY
                    self._task_count += 1
                    start = timestamp_now()

                    await self.handle_message(message)

                    elapsed = timestamp_now() - start
                    self.record_performance(1.0 / max(elapsed, 0.001))
                    self._task_count -= 1
                except asyncio.TimeoutError:
                    pass

                if self._task_count == 0:
                    self.state = AgentState.IDLE
                elif self.load >= 0.8:
                    self.state = AgentState.OVERLOADED

                await self.on_tick()

            except Exception as e:
                self.logger.error("Error in run loop: %s", e)

        self.state = AgentState.DEAD
        await self.on_stop()

    async def stop(self) -> None:
        self._running = False
