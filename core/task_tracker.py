"""
任务追踪器 — 记录每个智能体的完整活动数据。

追踪内容：
- 所有活动类型：task（任务执行）、bill（法案处理）、vote（投票）、
  judicial_review（司法审查）、ruling（裁决）、executive_order（行政令）、veto（否决）
- 完成状态：success / failed / running
- Token 消耗：每个 Agent 的 prompt_tokens / completion_tokens / total_tokens
- 执行耗时：从活动开始到完成
- 效率指标：成功率、平均耗时、Token 效率
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from utils import get_logger, timestamp_now

logger = get_logger("TaskTracker")


@dataclass
class TaskRecord:
    task_id: str
    agent_id: str = ""
    agent_type: str = ""
    task_type: str = ""
    activity_type: str = "task"   # task / bill / vote / judicial_review / ruling / executive_order / veto
    skill_used: str = ""
    status: str = "pending"       # pending / running / success / failed / timeout
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error: str = ""
    department: str = ""
    detail: str = ""


class TaskTracker:
    """
    集中式任务追踪器。

    追踪所有智能体的所有活动类型（任务、法案、投票、司法审查等），
    并在面板上展示完整的三权分立工作情况。
    """

    def __init__(self, max_records: int = 500):
        self._records: list[TaskRecord] = []
        self._max_records = max_records
        self._agent_tokens: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0}
        )
        self._agent_meta: dict[str, dict[str, str]] = {}
        self._registered_agents: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    def register_agent(self, agent_id: str, agent_type: str,
                       department: str = "", branch: str = "") -> None:
        """Agent 创建时注册，确保面板能看到所有 Agent"""
        self._registered_agents[agent_id] = {
            "agent_type": agent_type,
            "department": department,
            "branch": branch,
        }
        self._agent_meta[agent_id] = {
            "agent_type": agent_type,
            "department": department,
        }

    async def on_task_dispatched(
        self, task_id: str, agent_id: str, agent_type: str,
        task_type: str, department: str = "",
        activity_type: str = "task",
    ) -> None:
        async with self._lock:
            record = TaskRecord(
                task_id=task_id,
                agent_id=agent_id,
                agent_type=agent_type,
                task_type=task_type,
                activity_type=activity_type,
                department=department,
                status="running",
                start_time=timestamp_now(),
            )
            self._records.append(record)
            self._agent_meta[agent_id] = {
                "agent_type": agent_type,
                "department": department,
            }
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

    async def on_task_completed(
        self, task_id: str, agent_id: str, success: bool,
        duration: float = 0.0, skill_used: str = "",
        usage: dict[str, int] | None = None, error: str = "",
    ) -> None:
        async with self._lock:
            record = self._find_record(task_id)
            if record:
                record.status = "success" if success else "failed"
                record.end_time = timestamp_now()
                record.duration = duration or (record.end_time - record.start_time)
                record.skill_used = skill_used
                record.error = error
                if usage:
                    record.prompt_tokens = usage.get("prompt_tokens", 0)
                    record.completion_tokens = usage.get("completion_tokens", 0)
                    record.total_tokens = usage.get("total_tokens", 0)
            else:
                record = TaskRecord(
                    task_id=task_id,
                    agent_id=agent_id,
                    status="success" if success else "failed",
                    end_time=timestamp_now(),
                    duration=duration,
                    skill_used=skill_used,
                    error=error,
                )
                if usage:
                    record.prompt_tokens = usage.get("prompt_tokens", 0)
                    record.completion_tokens = usage.get("completion_tokens", 0)
                    record.total_tokens = usage.get("total_tokens", 0)
                self._records.append(record)

            if usage and agent_id:
                tokens = self._agent_tokens[agent_id]
                tokens["prompt_tokens"] += usage.get("prompt_tokens", 0)
                tokens["completion_tokens"] += usage.get("completion_tokens", 0)
                tokens["total_tokens"] += usage.get("total_tokens", 0)
                tokens["call_count"] += 1

    async def on_activity(
        self, activity_id: str, agent_id: str, agent_type: str,
        activity_type: str, detail: str = "", success: bool = True,
        duration: float = 0.0, department: str = "",
    ) -> None:
        """记录非 TASK 类型的活动（法案、投票、司法审查等）"""
        async with self._lock:
            record = TaskRecord(
                task_id=activity_id,
                agent_id=agent_id,
                agent_type=agent_type,
                task_type=activity_type,
                activity_type=activity_type,
                department=department,
                status="success" if success else "failed",
                start_time=timestamp_now(),
                end_time=timestamp_now(),
                duration=duration,
                detail=detail,
            )
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

    def _find_record(self, task_id: str) -> TaskRecord | None:
        for r in reversed(self._records):
            if r.task_id == task_id:
                return r
        return None

    async def get_overview(self) -> dict[str, Any]:
        async with self._lock:
            total = len(self._records)
            success = sum(1 for r in self._records if r.status == "success")
            failed = sum(1 for r in self._records if r.status == "failed")
            running = sum(1 for r in self._records if r.status == "running")

            completed = [r for r in self._records if r.status in ("success", "failed")]
            total_duration = sum(r.duration for r in completed)
            avg_duration = (total_duration / len(completed)) if completed else 0

            total_tokens = sum(r.total_tokens for r in self._records)
            total_prompt = sum(r.prompt_tokens for r in self._records)
            total_completion = sum(r.completion_tokens for r in self._records)

            activity_counts = defaultdict(int)
            for r in self._records:
                activity_counts[r.activity_type] += 1

            return {
                "total_tasks": total,
                "success": success,
                "failed": failed,
                "running": running,
                "success_rate": round(success / max(total - running, 1), 4),
                "avg_duration": round(avg_duration, 3),
                "total_tokens": total_tokens,
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "tokens_per_task": round(total_tokens / max(len(completed), 1), 1),
                "activity_counts": dict(activity_counts),
                "registered_agents": len(self._registered_agents),
            }

    async def get_agent_stats(self) -> list[dict[str, Any]]:
        async with self._lock:
            agents: dict[str, dict[str, Any]] = {}

            for agent_id, meta in self._registered_agents.items():
                agents[agent_id] = {
                    "agent_id": agent_id,
                    "agent_type": meta.get("agent_type", ""),
                    "department": meta.get("department", ""),
                    "branch": meta.get("branch", ""),
                    "total_tasks": 0,
                    "success": 0,
                    "failed": 0,
                    "running": 0,
                    "total_duration": 0.0,
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "activities": defaultdict(int),
                }

            for r in self._records:
                if not r.agent_id:
                    continue
                if r.agent_id not in agents:
                    meta = self._agent_meta.get(r.agent_id, {})
                    agents[r.agent_id] = {
                        "agent_id": r.agent_id,
                        "agent_type": meta.get("agent_type", r.agent_type),
                        "department": meta.get("department", r.department),
                        "branch": "",
                        "total_tasks": 0,
                        "success": 0,
                        "failed": 0,
                        "running": 0,
                        "total_duration": 0.0,
                        "total_tokens": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "activities": defaultdict(int),
                    }
                a = agents[r.agent_id]
                a["total_tasks"] += 1
                if r.status == "success":
                    a["success"] += 1
                elif r.status == "failed":
                    a["failed"] += 1
                elif r.status == "running":
                    a["running"] += 1
                a["total_duration"] += r.duration
                a["total_tokens"] += r.total_tokens
                a["prompt_tokens"] += r.prompt_tokens
                a["completion_tokens"] += r.completion_tokens
                a["activities"][r.activity_type] += 1

            result = []
            for a in agents.values():
                done = a["success"] + a["failed"]
                a["success_rate"] = round(a["success"] / max(done, 1), 4)
                a["avg_duration"] = round(a["total_duration"] / max(done, 1), 3)
                a["tokens_per_task"] = round(a["total_tokens"] / max(done, 1), 1)
                token_info = self._agent_tokens.get(a["agent_id"], {})
                a["llm_calls"] = token_info.get("call_count", 0)
                a["activities"] = dict(a["activities"])
                result.append(a)

            branch_order = {"executive": 0, "legislative": 1, "judicial": 2, "": 3}
            type_order = {"president": 0, "worker": 1, "house": 2, "senate": 3, "supreme_court": 4}
            result.sort(key=lambda x: (
                branch_order.get(x.get("branch", ""), 3),
                type_order.get(x.get("agent_type", ""), 5),
            ))
            return result

    async def get_task_history(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        async with self._lock:
            records = list(reversed(self._records))
            page = records[offset: offset + limit]
            return [
                {
                    "task_id": r.task_id,
                    "agent_id": r.agent_id,
                    "agent_type": r.agent_type,
                    "department": r.department,
                    "task_type": r.task_type,
                    "activity_type": r.activity_type,
                    "skill_used": r.skill_used,
                    "status": r.status,
                    "duration": round(r.duration, 3),
                    "total_tokens": r.total_tokens,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "error": r.error,
                    "detail": r.detail,
                }
                for r in page
            ]

    async def get_token_stats(self) -> dict[str, Any]:
        """按 Agent 分组的 Token 消耗统计"""
        async with self._lock:
            per_agent = {}
            for agent_id, tokens in self._agent_tokens.items():
                meta = self._agent_meta.get(agent_id, {})
                per_agent[agent_id] = {
                    **tokens,
                    "agent_type": meta.get("agent_type", ""),
                    "department": meta.get("department", ""),
                }
            total = {
                "prompt_tokens": sum(t["prompt_tokens"] for t in self._agent_tokens.values()),
                "completion_tokens": sum(t["completion_tokens"] for t in self._agent_tokens.values()),
                "total_tokens": sum(t["total_tokens"] for t in self._agent_tokens.values()),
                "total_calls": sum(t["call_count"] for t in self._agent_tokens.values()),
            }
            return {"total": total, "per_agent": per_agent}

    async def get_monitor_data(self) -> dict[str, Any]:
        """面板所需的全部数据"""
        overview = await self.get_overview()
        agent_stats = await self.get_agent_stats()
        task_history = await self.get_task_history(limit=100)
        token_stats = await self.get_token_stats()
        return {
            "timestamp": timestamp_now(),
            "overview": overview,
            "agent_stats": agent_stats,
            "task_history": task_history,
            "token_stats": token_stats,
        }
