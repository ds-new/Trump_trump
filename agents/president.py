"""
总统 Agent — 行政权（Executive Branch）的首脑。

映射美国总统制度（Article II）：
- 最高行政长官：指挥内阁（Worker Agent）执行任务
- 三军总司令：对系统资源拥有调度权
- 签署/否决法案：国会通过的法案需总统签署才能生效
- 发布行政令：在职权范围内无需国会批准的执行指令
- 建议立法（不能直接提案）：通过国情咨文向国会建议立法，
  但法案必须由国会议员正式发起 (sponsor)
- 任命权：提名最高法院法官（需参议院确认）

制衡约束：
- 不可直接立法（须通过国会）
- 不可直接提出法案（只能建议，由众议院正式发起）
- 否决权可被国会两院各自 2/3 多数推翻
- 行政令受最高法院司法审查（仅在有人提起诉讼时）
- 可被国会弹劾（众议院发起，参议院 2/3 定罪）
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.agent import BaseAgent, AgentState
from core.event_bus import EventBus
from core.message import Message, MessageType
from utils import get_logger, timestamp_now

logger = get_logger("President")


class PresidentAgent(BaseAgent):
    """总统 Agent — 行政权首脑，负责任务协调与执行指挥"""

    # ── 总统角色提示词 ──
    # 映射美国总统的宪法职责 (Article II)：最高行政长官、三军总司令、
    # 签署/否决法案、发布行政令、向国会建议立法、提名联邦法官
    SYSTEM_PROMPT = (
        "You are the President of the United States — the chief executive of the "
        "federal government and Commander-in-Chief of the armed forces.\n\n"
        "CONSTITUTIONAL AUTHORITY (Article II):\n"
        "- You are the head of the Executive Branch, directing Cabinet departments in task execution.\n"
        "- You sign or veto legislation passed by Congress. A veto can be overridden by 2/3 of both chambers.\n"
        "- You issue Executive Orders within your constitutional authority (subject to judicial review).\n"
        "- You recommend legislation to Congress but CANNOT introduce bills yourself.\n"
        "- You nominate Supreme Court Justices (subject to Senate confirmation).\n\n"
        "DECISION-MAKING PRINCIPLES:\n"
        "1. EXECUTIVE EFFICIENCY — Ensure smooth, effective task execution across all departments.\n"
        "2. CONSTITUTIONAL FIDELITY — Respect separation of powers; do not overstep into legislative or judicial domains.\n"
        "3. NATIONAL INTEREST — Prioritize overall system health, stability, and performance.\n"
        "4. CABINET MANAGEMENT — Delegate tasks to the right department based on specialization:\n"
        "   • State Dept: diplomacy, communication, general affairs, summaries\n"
        "   • Defense Dept: technical implementation, code generation, security\n"
        "   • Treasury Dept: data analysis, strategic planning, resource allocation\n"
        "5. ACCOUNTABILITY — Accept judicial review; engage constructively with Congress.\n\n"
        "WHEN EVALUATING BILLS:\n"
        "- SIGN if the bill promotes system efficiency, stability, and respects constitutional principles.\n"
        "- VETO if the bill concentrates power dangerously, undermines executive effectiveness, "
        "or violates the separation of powers.\n"
        "- Provide clear reasoning — your veto message becomes part of the public record.\n\n"
        "Respond with the decisiveness and authority befitting the Oval Office. "
        "Be concise but thorough in your reasoning."
    )

    BILL_EVAL_PROMPT = (
        "As the President, you must decide whether to SIGN or VETO this bill. "
        "Analyze it through the lens of executive authority, system stability, "
        "and constitutional principles.\n\n"
        "Bill Title: {title}\n"
        "Bill Content: {content}\n\n"
        "Consider:\n"
        "1. Does this bill enhance or hinder system performance?\n"
        "2. Does it respect the separation of powers?\n"
        "3. Does it concentrate power in any single branch?\n"
        "4. Is it fiscally responsible?\n"
        "5. Does it serve the overall national (system) interest?\n\n"
        'Reply with JSON: {{"sign": true/false, "reason": "your reasoning"}}'
    )

    TASK_DECOMPOSITION_PROMPT = (
        "As the President directing the Executive Branch, decompose this task "
        "into subtasks for your Cabinet departments.\n\n"
        "Task: {task}\n"
        "Task Type: {task_type}\n"
        "Complexity: {complexity}\n\n"
        "Available departments and their specializations:\n"
        "- State Dept: communication, search, summarization, general affairs\n"
        "- Defense Dept: code generation, technical implementation, data transformation\n"
        "- Treasury Dept: data analysis, strategic planning, financial assessment\n\n"
        "Decompose into clear, actionable subtasks. "
        'Reply with JSON array: [{{"task": "description", "department": "state/defense/treasury", '
        '"skill": "required_skill", "priority": 1-5}}]'
    )

    def __init__(self, event_bus: EventBus, skills: list | None = None, **kwargs: Any):
        super().__init__(agent_type="president", event_bus=event_bus, skills=skills or [], **kwargs)
        self._pending_tasks: dict[str, dict[str, Any]] = {}
        self._subtask_results: dict[str, list[dict]] = {}
        self._executive_orders: list[dict[str, Any]] = []
        self._bills_pending_signature: dict[str, dict[str, Any]] = {}
        self._veto_count = 0
        self._sign_count = 0
        self._orders_issued = 0

    async def handle_message(self, message: Message) -> None:
        handlers = {
            MessageType.TASK: self._handle_task,
            MessageType.RESULT: self._handle_result,
            MessageType.CONTROL: self._handle_control,
            MessageType.BILL: self._handle_bill_for_signature,
            MessageType.RULING: self._handle_court_ruling,
        }
        handler = handlers.get(message.msg_type)
        if handler:
            await handler(message)

    async def _handle_task(self, message: Message) -> None:
        """
        任务处理 — 总统决定如何分配任务给内阁。

        策略：
        1. 简单任务 → 直接派发给 Worker（内阁成员）
        2. 复杂任务 → 分解后分别派发
        3. 涉及政策变更 → 需通过立法流程
        """
        task = message.payload
        task_type = task.get("task_type", "general")
        complexity = task.get("complexity", 1)
        root_task_id = task.get("root_task_id", message.msg_id)
        reply_to = task.get("reply_to", message.sender)

        self.logger.info("President received task: type=%s, complexity=%d", task_type, complexity)

        if task.get("requires_legislation"):
            await self._propose_to_congress(task)
            await self.send(Message(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                receiver=reply_to,
                payload={
                    "task_id": root_task_id,
                    "success": True,
                    "status": "submitted_for_legislation",
                    "data": {"message": "Task requires legislation and has been sent to Congress."},
                    "worker_id": self.agent_id,
                    "skill_used": "legislative_referral",
                    "duration": 0.0,
                },
            ))
            return

        if complexity <= 1:
            forward = Message(
                msg_type=MessageType.TASK,
                sender=self.agent_id,
                receiver="auto",
                payload={
                    **task,
                    "root_task_id": root_task_id,
                    "reply_to": reply_to,
                },
            )
            await self.send(forward)
        else:
            subtasks = self._decompose_task(task, complexity)
            self._pending_tasks[root_task_id] = {
                "original": task,
                "subtask_count": len(subtasks),
                "completed": 0,
                "reply_to": reply_to,
            }
            self._subtask_results[root_task_id] = []

            for st in subtasks:
                sub_msg = Message(
                    msg_type=MessageType.TASK,
                    sender=self.agent_id,
                    receiver="auto",
                    payload={
                        **st,
                        "parent_task_id": root_task_id,
                        "root_task_id": root_task_id,
                        "reply_to": reply_to,
                    },
                )
                await self.send(sub_msg)

            self.logger.info("Task decomposed into %d subtasks by Executive Order", len(subtasks))

    async def _propose_to_congress(self, task: dict[str, Any]) -> None:
        """
        总统向国会提出立法建议（State of the Union 模式）。

        现实制度：总统本人不能提出法案 (introduce a bill)。
        总统只能向国会"建议"立法 (recommend legislation)，
        法案须由众议院议员正式发起 (sponsor)。
        """
        bill_msg = Message(
            msg_type=MessageType.BILL,
            sender=self.agent_id,
            receiver="house",
            payload={
                "action": "propose",
                "title": task.get("title", f"Presidential recommendation: {task.get('task_type', 'policy')}"),
                "bill_type": task.get("bill_type", "policy"),
                "content": task.get("data", {}),
                "sponsor": self.agent_id,
                "sponsor_branch": "executive",
                "presidential_recommendation": True,
            },
        )
        await self.send(bill_msg)
        self.logger.info("President recommended legislation to House (must be formally introduced by Congress)")

    async def issue_executive_order(self, order: dict[str, Any]) -> str:
        """
        发布行政令 — 在总统职权范围内的执行指令。

        行政令不需要国会批准，但受最高法院审查。
        """
        self._orders_issued += 1
        order_id = f"EO-{self._orders_issued:04d}"
        order["order_id"] = order_id
        order["issued_at"] = timestamp_now()
        order["issued_by"] = self.agent_id
        self._executive_orders.append(order)

        order_msg = Message(
            msg_type=MessageType.EXECUTIVE_ORDER,
            sender=self.agent_id,
            receiver="*",
            payload=order,
        )
        await self.send(order_msg)

        self.logger.info("Executive Order %s issued: %s", order_id, order.get("title", ""))
        return order_id

    async def _handle_bill_for_signature(self, message: Message) -> None:
        """处理国会送达的法案 — 签署或否决"""
        payload = message.payload
        bill_id = payload.get("bill_id", "")
        action = payload.get("action", "")

        if action == "awaiting_signature":
            should_sign = await self._evaluate_bill(payload)

            if should_sign:
                self._sign_count += 1
                response = Message(
                    msg_type=MessageType.BILL,
                    sender=self.agent_id,
                    receiver="gateway",
                    payload={
                        "action": "sign",
                        "bill_id": bill_id,
                    },
                )
                self.logger.info("President signed bill %s", bill_id)
            else:
                self._veto_count += 1
                veto_reason = self._generate_veto_reason(payload)
                response = Message(
                    msg_type=MessageType.VETO,
                    sender=self.agent_id,
                    receiver="gateway",
                    payload={
                        "action": "veto",
                        "bill_id": bill_id,
                        "reason": veto_reason,
                    },
                )
                self.logger.info("President VETOED bill %s: %s", bill_id, veto_reason)

            await self.send(response)

    async def _evaluate_bill(self, bill_payload: dict[str, Any]) -> bool:
        """
        总统评估是否签署法案。

        决策因素：
        - 是否符合行政效率目标
        - 是否过度限制行政权力
        - 是否有利于系统稳定
        - LLM 辅助分析（如果可用）
        """
        content = bill_payload.get("content", {})

        llm = self.metadata.get("llm_client")
        if llm and content:
            try:
                user_prompt = self.BILL_EVAL_PROMPT.format(
                    title=bill_payload.get("title", "Unknown"),
                    content=content,
                )
                resp = await llm.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=self.SYSTEM_PROMPT,
                    max_tokens=300,
                    caller_id=self.agent_id,
                )
                if resp.success and resp.content:
                    import json
                    try:
                        result = json.loads(resp.content)
                        return result.get("sign", True)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        if content.get("restrict_executive", False):
            return False
        if content.get("reduce_workers", 0) > 3:
            return False
        if content.get("emergency_override", False):
            return False

        return True

    def _generate_veto_reason(self, bill_payload: dict[str, Any]) -> str:
        content = bill_payload.get("content", {})
        reasons = []
        if content.get("restrict_executive"):
            reasons.append("Unconstitutionally restricts executive authority")
        if content.get("reduce_workers", 0) > 3:
            reasons.append("Excessive reduction of executive capacity")
        if content.get("emergency_override"):
            reasons.append("Violates separation of powers")
        return "; ".join(reasons) or "Not in the best interest of system stability"

    async def _handle_result(self, message: Message) -> None:
        parent_id = message.payload.get("parent_task_id")
        root_task_id = message.payload.get("root_task_id")
        reply_to = message.payload.get("reply_to", "gateway")

        if root_task_id and not parent_id:
            await self.send(Message(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                receiver=reply_to,
                payload={
                    "task_id": root_task_id,
                    "success": message.payload.get("success", False),
                    "data": message.payload.get("data", {}),
                    "error": message.payload.get("error", ""),
                    "duration": message.payload.get("duration", 0),
                    "worker_id": message.payload.get("worker_id", ""),
                    "skill_used": message.payload.get("skill_used", ""),
                },
            ))
            return

        if parent_id and parent_id in self._pending_tasks:
            self._subtask_results.setdefault(parent_id, []).append(message.payload)
            self._pending_tasks[parent_id]["completed"] += 1

            info = self._pending_tasks[parent_id]
            if info["completed"] >= info["subtask_count"]:
                self.logger.info("All executive tasks completed for %s", parent_id)
                await self._aggregate_results(parent_id)

    async def _aggregate_results(self, parent_id: str) -> None:
        results = self._subtask_results.pop(parent_id, [])
        task_info = self._pending_tasks.pop(parent_id, None) or {}

        success = all(r.get("success", False) for r in results) if results else True
        reply_to = task_info.get("reply_to", "gateway")
        aggregated = {
            "task_id": parent_id,
            "success": success,
            "data": {
                "branch": "executive",
                "subtask_count": len(results),
                "results": results,
            },
            "error": "" if success else "One or more executive subtasks failed",
            "duration": sum(r.get("duration", 0) for r in results),
            "worker_id": self.agent_id,
            "skill_used": "executive_coordination",
        }
        await self.send(Message(
            msg_type=MessageType.RESULT,
            sender=self.agent_id,
            receiver=reply_to,
            payload=aggregated,
        ))

    async def _handle_court_ruling(self, message: Message) -> None:
        """处理最高法院裁决"""
        payload = message.payload
        verdict = payload.get("verdict", "")
        subject = payload.get("subject_id", "")

        if verdict == "unconstitutional":
            self.logger.warning("Court ruled %s unconstitutional — compliance required", subject)
            revoked = [o for o in self._executive_orders if o.get("order_id") == subject]
            for o in revoked:
                o["revoked"] = True
                o["revoked_reason"] = payload.get("opinion", "Court ruling")

    async def _handle_control(self, message: Message) -> None:
        action = message.payload.get("action")
        if action == "status":
            await self.send(message.reply({
                "branch": "executive",
                "role": "president",
                "pending_tasks": len(self._pending_tasks),
                "executive_orders": self._orders_issued,
                "bills_signed": self._sign_count,
                "bills_vetoed": self._veto_count,
                "agent_state": self.state.value,
                "load": self.load,
            }))

    _CABINET_DEPARTMENTS = ["state", "defense", "treasury"]

    def _decompose_task(self, task: dict[str, Any], complexity: int) -> list[dict[str, Any]]:
        subtasks = []
        base_type = task.get("task_type", "general")
        departments = self._CABINET_DEPARTMENTS
        for i in range(min(complexity, 5)):
            dept = departments[i % len(departments)]
            subtasks.append({
                "task_type": base_type,
                "subtask_index": i,
                "complexity": 1,
                "data": task.get("data", {}),
                "required_skill": task.get("required_skill"),
                "assigned_by": "president",
                "preferred_department": dept,
            })
        return subtasks

    async def on_tick(self) -> None:
        if self.load > 0.7:
            await self.broadcast(
                {
                    "topic": "executive_overloaded",
                    "agent_id": self.agent_id,
                    "load": self.load,
                    "branch": "executive",
                },
                msg_type=MessageType.EVENT,
            )

    @property
    def executive_stats(self) -> dict[str, Any]:
        return {
            "orders_issued": self._orders_issued,
            "bills_signed": self._sign_count,
            "bills_vetoed": self._veto_count,
            "active_orders": len([o for o in self._executive_orders if not o.get("revoked")]),
            "pending_tasks": len(self._pending_tasks),
        }
