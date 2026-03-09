"""
自组织 Agent System 全局配置。

受 OpenClaw 架构启发：
- Gateway 作为控制平面
- 技能系统（Skills）可插拔
- Agent 间通信协议
- 自组织参数（涌现、反馈、适应阈值）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class LLMConfig:
    """大模型配置"""
    api_key: str = field(default_factory=lambda: os.getenv(
       ))
    base_url: str = field(default_factory=lambda: os.getenv())
    model: str = field(default_factory=lambda: os.getenv())

    max_tokens: int = field(default_factory=lambda: int(os.getenv('MAX_TOKEN', '12000')))
    temperature: float = 0.7
    timeout: float = 120.0
    max_retries: int = 2


@dataclass
class SelfOrgConfig:
    """自组织行为参数"""
    pheromone_decay: float = 0.05
    pheromone_amplify: float = 1.5
    emergence_threshold: float = 0.6
    feedback_window: int = 50
    adaptation_rate: float = 0.1
    max_agents: int = 20
    min_agents: int = 2
    leader_election_interval: float = 10.0
    health_check_interval: float = 5.0


@dataclass
class GatewayConfig:
    """网关配置（参考 OpenClaw Gateway）"""
    host: str = "127.0.0.1"
    port: int = 18790
    max_connections: int = 100
    heartbeat_interval: float = 5.0
    message_queue_size: int = 1000
    routing_strategy: str = "adaptive"


@dataclass
class AgentConfig:
    """单个 Agent 配置"""
    agent_id: str = ""
    agent_type: str = "worker"
    skills: list[str] = field(default_factory=list)
    max_tasks: int = 5
    priority: int = 0
    auto_scale: bool = True
    sandbox_mode: bool = False


@dataclass
class SystemConfig:
    """系统全局配置"""
    workspace: str = str(Path.home() / ".agent_system" / "workspace")
    log_level: str = "INFO"
    llm: LLMConfig = field(default_factory=LLMConfig)
    self_org: SelfOrgConfig = field(default_factory=SelfOrgConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    default_agent: AgentConfig = field(default_factory=AgentConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: str | Path) -> SystemConfig:
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text())
        return cls(
            workspace=data.get("workspace", cls.workspace),
            log_level=data.get("log_level", "INFO"),
            llm=LLMConfig(**data.get("llm", {})),
            self_org=SelfOrgConfig(**data.get("self_org", {})),
            gateway=GatewayConfig(**data.get("gateway", {})),
            default_agent=AgentConfig(**data.get("default_agent", {})),
        )
