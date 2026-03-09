"""
事件总线 — 去中心化的消息分发机制。

自组织原理：
- 没有中央调度器，通过发布-订阅模式实现松耦合
- 支持事件过滤与优先级队列
- 广播机制模拟自然系统中的信号扩散
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, Awaitable

from utils import get_logger
from .message import Message, MessageType

logger = get_logger("EventBus")

Listener = Callable[[Message], Awaitable[None]]


class EventBus:
    """异步事件总线，支持主题订阅与消息广播"""

    def __init__(self, queue_size: int = 1000):
        self._subscribers: dict[str, list[Listener]] = defaultdict(list)
        self._type_subscribers: dict[MessageType, list[Listener]] = defaultdict(list)
        self._queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=queue_size)
        self._running = False
        self._stats: dict[str, int] = defaultdict(int)

    def subscribe(self, topic: str, listener: Listener) -> None:
        self._subscribers[topic].append(listener)

    def subscribe_type(self, msg_type: MessageType, listener: Listener) -> None:
        self._type_subscribers[msg_type].append(listener)

    def unsubscribe(self, topic: str, listener: Listener) -> None:
        if listener in self._subscribers[topic]:
            self._subscribers[topic].remove(listener)

    def unsubscribe_type(self, msg_type: MessageType, listener: Listener) -> None:
        if listener in self._type_subscribers[msg_type]:
            self._type_subscribers[msg_type].remove(listener)

    async def publish(self, message: Message, topic: str | None = None) -> None:
        await self._queue.put(message)
        self._stats["published"] += 1

        if topic:
            self._stats[f"topic:{topic}"] += 1

    async def _dispatch(self, message: Message, topic: str | None = None) -> None:
        tasks = []

        for listener in self._type_subscribers.get(message.msg_type, []):
            tasks.append(asyncio.create_task(self._safe_call(listener, message)))

        if topic:
            for listener in self._subscribers.get(topic, []):
                tasks.append(asyncio.create_task(self._safe_call(listener, message)))

        if message.is_broadcast:
            for listener in self._subscribers.get("*", []):
                tasks.append(asyncio.create_task(self._safe_call(listener, message)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self._stats["dispatched"] += len(tasks)

    @staticmethod
    async def _safe_call(listener: Listener, message: Message) -> None:
        try:
            await listener(message)
        except Exception as e:
            logger.error("Listener error: %s — %s", listener, e)

    async def start(self) -> None:
        self._running = True
        logger.info("EventBus started")
        while self._running:
            try:
                message = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                topic = message.payload.get("topic")
                await self._dispatch(message, topic)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("EventBus loop error: %s", e)

    async def stop(self) -> None:
        self._running = False
        logger.info("EventBus stopped — stats: %s", dict(self._stats))

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)
