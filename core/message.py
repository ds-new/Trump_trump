"""
消息协议 — 三权分立 Agent System 的通信基础。

消息类型映射美国政治制度：
- TASK / RESULT: 行政执行（Executive Branch）的任务下发与结果回传
- BILL: 立法提案（由众议院发起或总统提议）
- VOTE: 国会投票（参议院 / 众议院对法案的表决）
- VETO: 总统否决权
- EXECUTIVE_ORDER: 总统行政令（无需立法的执行指令）
- JUDICIAL_REVIEW: 司法审查请求（最高法院审查法案或行政令合宪性）
- RULING: 司法裁决（最高法院的最终裁定）
- EVENT / HEARTBEAT / CONTROL / FEEDBACK / PHEROMONE / DISCOVERY: 基础设施消息
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Any

from utils import generate_id, timestamp_now


class MessageType(Enum):
    TASK = auto()
    RESULT = auto()
    EVENT = auto()
    HEARTBEAT = auto()
    CONTROL = auto()
    FEEDBACK = auto()
    PHEROMONE = auto()
    DISCOVERY = auto()
    BILL = auto()
    VOTE = auto()
    VETO = auto()
    EXECUTIVE_ORDER = auto()
    JUDICIAL_REVIEW = auto()
    RULING = auto()


@dataclass
class Message:
    msg_type: MessageType
    sender: str
    receiver: str  # "*" = broadcast
    payload: dict[str, Any] = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: generate_id("msg"))
    timestamp: float = field(default_factory=timestamp_now)
    priority: int = 0
    ttl: int = 10  # max hop count

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["msg_type"] = self.msg_type.name
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        data["msg_type"] = MessageType[data["msg_type"]]
        return cls(**data)

    @property
    def is_broadcast(self) -> bool:
        return self.receiver == "*"

    def reply(self, payload: dict[str, Any], msg_type: MessageType | None = None) -> Message:
        return Message(
            msg_type=msg_type or MessageType.RESULT,
            sender=self.receiver,
            receiver=self.sender,
            payload=payload,
            priority=self.priority,
        )
