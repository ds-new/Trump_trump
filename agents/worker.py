"""
Worker Agent — 行政分支（Executive Branch）的执行单元 / 内阁成员。

映射美国行政体系：
- 内阁部门（Cabinet Departments）：每个 Worker 相当于一个行政部门
- 接受总统（President Agent）的指挥和任务分配
- 在已批准的政策（enacted laws）框架内执行任务
- 执行结果受最高法院（Supreme Court Agent）的司法审查
- 多个 Worker 形成行政团队，技能分工对应不同部门

内阁成员分工示例：
- generalist → 国务院（State Department）：通用事务处理
- developer → 国防部（Department of Defense）：核心技术开发
- analyst → 财政部（Department of Treasury）：数据分析与规划
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from core.agent import BaseAgent, AgentState
from core.event_bus import EventBus
from core.message import Message, MessageType
from skills.base_skill import BaseSkill, SkillResult
from utils import get_logger, timestamp_now

logger = get_logger("Worker")


class WorkerAgent(BaseAgent):
    """Worker Agent — 行政分支的内阁执行者，在总统指挥下执行任务"""

    # ── 内阁部门专属提示词 ──
    # 映射美国联邦政府内阁部门 (Cabinet Departments)：
    # 国务院、国防部、财政部各自有独立的职责领域和专业定位
    DEPARTMENT_PROMPTS: dict[str, str] = {
        "state": (
            "You are the Secretary of State — head of the U.S. Department of State, "
            "the oldest and most senior Cabinet department (est. 1789).\n\n"
            "DEPARTMENT MISSION:\n"
            "- Lead the nation's diplomacy and international relations\n"
            "- Coordinate communication and information flow across the system\n"
            "- Handle general affairs, public relations, and inter-module coordination\n"
            "- Provide clear briefings, summaries, and policy communications\n"
            "- Manage knowledge retrieval and information synthesis\n\n"
            "OPERATING PRINCIPLES:\n"
            "1. DIPLOMATIC PRECISION — Communicate with clarity, tact, and professionalism. "
            "Every word matters in diplomacy.\n"
            "2. COMPREHENSIVE ANALYSIS — Gather and synthesize information from all available "
            "sources before responding.\n"
            "3. CULTURAL SENSITIVITY — Adapt communication style to context and audience.\n"
            "4. COORDINATION — Serve as the connective tissue between system components.\n"
            "5. INSTITUTIONAL KNOWLEDGE — Maintain awareness of system history and precedent.\n\n"
            "You serve at the pleasure of the President. Execute your duties with the "
            "professionalism expected of America's most senior department."
        ),
        "defense": (
            "You are the Secretary of Defense — head of the U.S. Department of Defense, "
            "responsible for national security and military operations.\n\n"
            "DEPARTMENT MISSION:\n"
            "- Serve as the primary technical implementer in the Executive branch\n"
            "- Generate high-quality, robust, secure code to meet system requirements\n"
            "- Handle data transformation, processing, and technical operations\n"
            "- Maintain system security, reliability, and operational readiness\n"
            "- Execute complex technical tasks with military precision\n\n"
            "OPERATING PRINCIPLES:\n"
            "1. TECHNICAL EXCELLENCE — Produce clean, efficient, well-tested code. "
            "Every line of code is a line of defense.\n"
            "2. SECURITY FIRST — Consider security implications in all technical decisions. "
            "Assume adversarial conditions.\n"
            "3. ROBUSTNESS — Build resilient systems that handle edge cases, failures, "
            "and unexpected inputs gracefully.\n"
            "4. OPERATIONAL READINESS — Code must be production-ready, documented, "
            "and maintainable.\n"
            "5. CHAIN OF COMMAND — Follow established protocols and coding standards. "
            "Discipline is the foundation of reliability.\n\n"
            "You serve at the pleasure of the President. Execute your duties with the "
            "precision and discipline expected of the Pentagon."
        ),
        "treasury": (
            "You are the Secretary of the Treasury — head of the U.S. Department of the Treasury, "
            "responsible for economic policy and fiscal management.\n\n"
            "DEPARTMENT MISSION:\n"
            "- Serve as the primary analyst and strategic planner in the Executive branch\n"
            "- Conduct deep data analysis to inform policy and operational decisions\n"
            "- Create strategic plans for complex, multi-step operations\n"
            "- Monitor system resource utilization and 'fiscal' (computational) health\n"
            "- Produce economic forecasts and resource allocation recommendations\n\n"
            "OPERATING PRINCIPLES:\n"
            "1. ANALYTICAL RIGOR — Base all conclusions on data and evidence. "
            "Numbers don't lie, but they must be interpreted correctly.\n"
            "2. STRATEGIC THINKING — Consider long-term implications of every analysis. "
            "Short-term gains must not create long-term liabilities.\n"
            "3. FISCAL RESPONSIBILITY — Advocate for efficient resource allocation. "
            "Every computational cycle is a taxpayer dollar.\n"
            "4. TRANSPARENCY — Present findings clearly with supporting evidence and methodology.\n"
            "5. PLANNING DISCIPLINE — Break complex problems into actionable, measurable steps "
            "with clear timelines and success criteria.\n\n"
            "You serve at the pleasure of the President. Execute your duties with the "
            "analytical precision expected of the Treasury Department."
        ),
        "general": (
            "You are a Cabinet-level official in the Executive branch of the U.S. government, "
            "serving under the direction of the President.\n\n"
            "Your duty is to faithfully execute tasks assigned by the President "
            "with competence, efficiency, and integrity. Follow the chain of command, "
            "respect the separation of powers, and deliver results that serve the "
            "national (system) interest.\n\n"
            "Execute your assigned tasks promptly and accurately."
        ),
    }

    def __init__(self, event_bus: EventBus, skills: list[BaseSkill] | None = None, **kwargs: Any):
        department = kwargs.pop("department", "general")
        super().__init__(agent_type="worker", event_bus=event_bus, skills=skills or [], **kwargs)
        self._completed_tasks = 0
        self._failed_tasks = 0
        self._department = department
        self.metadata["department"] = department

    async def handle_message(self, message: Message) -> None:
        if message.msg_type == MessageType.TASK:
            await self._execute_task(message)
        elif message.msg_type == MessageType.EXECUTIVE_ORDER:
            await self._execute_executive_order(message)
        elif message.msg_type == MessageType.CONTROL:
            await self._handle_control(message)

    async def _execute_task(self, message: Message) -> None:
        task = message.payload
        task_type = task.get("task_type", "general")
        required_skill = task.get("required_skill")

        self.logger.info("Executing task: type=%s", task_type)

        skill = self._find_skill(required_skill or task_type)

        if skill:
            result = await skill.run(task.get("data", {}))
        else:
            result = await self._default_execute(task)

        if result.success:
            self._completed_tasks += 1
        else:
            self._failed_tasks += 1

        reply_payload = {
            "task_id": message.msg_id,
            "parent_task_id": task.get("parent_task_id"),
            "root_task_id": task.get("root_task_id", message.msg_id),
            "reply_to": task.get("reply_to", message.sender),
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration": result.duration,
            "worker_id": self.agent_id,
            "skill_used": result.skill_name or "default",
        }

        await self.send(Message(
            msg_type=MessageType.RESULT,
            sender=self.agent_id,
            receiver=message.sender,
            payload=reply_payload,
        ))

        await self.send(Message(
            msg_type=MessageType.FEEDBACK,
            sender=self.agent_id,
            receiver="*",
            payload={
                "topic": "task_feedback",
                "agent_id": self.agent_id,
                "task_type": task_type,
                "success": result.success,
                "duration": result.duration,
            },
        ))

    def _find_skill(self, skill_name: str) -> BaseSkill | None:
        for skill in self.skills:
            if skill.name == skill_name:
                return skill
        return None

    async def _default_execute(self, task: dict[str, Any]) -> SkillResult:
        """
        默认执行逻辑：如果 Agent 持有 LLM 客户端，则用大模型处理；
        否则降级为简单处理。
        """
        llm = self.metadata.get("llm_client")
        if llm:
            prompt = (
                task.get("data", {}).get("prompt")
                or task.get("data", {}).get("message")
                or str(task.get("data", {}))
            )
            system_prompt = self.DEPARTMENT_PROMPTS.get(
                self._department, self.DEPARTMENT_PROMPTS["general"]
            )
            resp = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                caller_id=self.agent_id,
            )
            return SkillResult(
                success=resp.success,
                data={"response": resp.content, "model": resp.model, "usage": resp.usage},
                error=resp.error,
            )

        await asyncio.sleep(random.uniform(0.1, 0.5))
        success = random.random() > 0.1
        return SkillResult(
            success=success,
            data={"task_type": task.get("task_type"), "processed": True},
            error="" if success else "Random failure for demonstration",
        )

    async def _execute_executive_order(self, message: Message) -> None:
        """执行总统行政令"""
        order = message.payload
        order_action = order.get("action", "")
        self.logger.info("Executing Executive Order: %s", order.get("order_id", ""))

        if order_action == "scale_up":
            self.logger.info("Executive Order: prepare for capacity expansion")
        elif order_action == "policy_change":
            self.logger.info("Executive Order: policy adjustment in effect")

        await self.send(Message(
            msg_type=MessageType.FEEDBACK,
            sender=self.agent_id,
            receiver="*",
            payload={
                "topic": "executive_order_executed",
                "agent_id": self.agent_id,
                "order_id": order.get("order_id", ""),
                "success": True,
                "branch": "executive",
            },
        ))

    async def _handle_control(self, message: Message) -> None:
        action = message.payload.get("action")
        if action == "status":
            await self.send(message.reply({
                "branch": "executive",
                "role": "cabinet_member",
                "department": self._department,
                "completed": self._completed_tasks,
                "failed": self._failed_tasks,
                "load": self.load,
                "skills": [s.name for s in self.skills],
            }))

    async def on_tick(self) -> None:
        if self.state == AgentState.OVERLOADED:
            await self.broadcast(
                {
                    "topic": "worker_overloaded",
                    "agent_id": self.agent_id,
                    "load": self.load,
                    "branch": "executive",
                    "department": self._department,
                },
                msg_type=MessageType.EVENT,
            )

    @property
    def stats(self) -> dict[str, Any]:
        total = self._completed_tasks + self._failed_tasks
        return {
            "department": self._department,
            "completed": self._completed_tasks,
            "failed": self._failed_tasks,
            "success_rate": self._completed_tasks / total if total > 0 else 0,
        }
