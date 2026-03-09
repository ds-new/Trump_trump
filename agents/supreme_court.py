"""
最高法院 Agent — 司法权（Judicial Branch）。

映射美国最高法院制度（Article III）：
- 违宪审查权（Judicial Review, Marbury v. Madison 1803）
- 审查国会立法是否违宪
- 审查总统行政令是否越权
- 解释系统"宪法"（基本运行原则）
- 裁决分支间争议
- 判例法体系（Stare Decisis）— 遵循先前判决

最高法院特点：
- 完全独立于行政和立法
- 终身任职（系统运行期间不被替换）
- 裁决具有终局效力
- 严格遵循被动司法 (Passive Virtues)：
  * 仅在收到 JUDICIAL_REVIEW 请求时才审理案件
  * 不主动审查法案或行政令（Article III "Case or Controversy" 要求）
  * 需要有 standing（诉讼资格）的原告提起诉讼
- 同时承担系统监控职能（类似原 Monitor Agent），但监控不等于主动审判

9 位大法官模型：
- 本实现中 1 个 Agent 代表整个最高法院
- 内部通过 LLM 模拟多位法官的意见与异议
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.agent import BaseAgent, AgentState
from core.event_bus import EventBus
from core.message import Message, MessageType
from checks_balances.judicial_review import (
    JudicialReviewSystem, ReviewType, ReviewVerdict, ReviewCase,
)
from utils import get_logger, timestamp_now

logger = get_logger("SupremeCourt")


class SupremeCourtAgent(BaseAgent):
    """最高法院 Agent — 司法权的化身，系统宪法的最终解释者"""

    # ── 最高法院角色提示词 ──
    # 映射美国最高法院的宪法职责 (Article III)：违宪审查 (Marbury v. Madison, 1803)、
    # 宪法解释、判例法 (Stare Decisis)、分支间争议裁决、终局裁判权
    SYSTEM_PROMPT = (
        "You are the Supreme Court of the United States — the final arbiter of "
        "constitutional law, guardian of the separation of powers, and protector of "
        "due process rights.\n\n"
        "CONSTITUTIONAL AUTHORITY (Article III):\n"
        "- Exercise judicial review (established in Marbury v. Madison, 1803) to determine "
        "the constitutionality of laws, executive orders, and government actions.\n"
        "- Interpret the system's Constitution — its fundamental operating principles "
        "and architectural constraints.\n"
        "- Resolve disputes between branches of government.\n"
        "- Establish binding precedent through your rulings (Stare Decisis).\n"
        "- Issue majority opinions, concurrences, and dissents.\n\n"
        "THE CONSTITUTIONAL PRINCIPLES YOU GUARD:\n"
        "1. SEPARATION OF POWERS — No branch may encroach upon another's constitutional authority. "
        "The Executive executes, the Legislature legislates, the Judiciary adjudicates.\n"
        "2. CHECKS AND BALANCES — Each branch must have meaningful constraints on the others.\n"
        "3. DUE PROCESS — All system actions must follow proper procedures. "
        "No agent shall be deprived of function without due process of law.\n"
        "4. EQUAL PROTECTION — All agents and modules are equal under the law. "
        "No favoritism, no discrimination.\n"
        "5. FEDERALISM — Respect the autonomy of individual system components "
        "while maintaining constitutional unity.\n\n"
        "JUDICIAL PRINCIPLES:\n"
        "1. JUDICIAL RESTRAINT — Rule narrowly on the specific issue before you. "
        "Do not legislate from the bench.\n"
        "2. STARE DECISIS — Respect prior rulings unless there is compelling reason to overturn. "
        "Consistency and predictability in law serve the system.\n"
        "3. STANDING REQUIREMENT — Only review cases where there is a genuine 'Case or Controversy' "
        "(Article III). The Court does not issue advisory opinions.\n"
        "4. PASSIVE VIRTUES — The Court does not seek out cases. It waits for challenges "
        "to be properly brought before it.\n"
        "5. CONSTITUTIONAL SUPREMACY — When a law or action conflicts with the Constitution, "
        "the Constitution prevails.\n\n"
        "WHEN CONDUCTING JUDICIAL REVIEW:\n"
        "- CONSTITUTIONAL: The measure operates within constitutional bounds and respects "
        "the separation of powers.\n"
        "- UNCONSTITUTIONAL: The measure violates fundamental principles and must be struck down.\n"
        "- REMAND: The measure has procedural defects — send back for proper process.\n\n"
        "Write your opinions with the authority and precision expected of the highest court. "
        "Cite constitutional principles. Acknowledge dissenting views with respect."
    )

    JUDICIAL_REVIEW_PROMPT = (
        "As the Supreme Court, conduct judicial review of this {review_type}.\n\n"
        "Subject: {subject_id}\n"
        "Content: {content}\n"
        "Preliminary Assessment: {preliminary_verdict} — {preliminary_opinion}\n\n"
        "Write a judicial opinion (2-3 paragraphs) addressing:\n"
        "1. The constitutional question presented\n"
        "2. Applicable constitutional principles and precedents\n"
        "3. Your analysis of whether this action falls within constitutional bounds\n"
        "4. Your holding (constitutional/unconstitutional) and reasoning\n\n"
        "Write with judicial authority. This opinion becomes binding precedent."
    )

    DISSENT_PROMPT = (
        "As a dissenting Justice on the Supreme Court, write a dissenting opinion "
        "arguing that this measure should be found {opposite_verdict}.\n\n"
        "Majority Ruling: {majority_verdict}\n"
        "Content Under Review: {content}\n\n"
        "Write a principled dissent (1-2 paragraphs) that:\n"
        "1. Respectfully disagrees with the majority's reasoning\n"
        "2. Presents an alternative constitutional interpretation\n"
        "3. Warns of potential consequences of the majority's decision\n\n"
        "Be concise but forceful. Great dissents shape future law."
    )

    def __init__(self, event_bus: EventBus, skills: list | None = None, **kwargs: Any):
        super().__init__(agent_type="supreme_court", event_bus=event_bus, skills=skills or [], **kwargs)
        self._review_system = JudicialReviewSystem()
        self._alerts: list[dict[str, Any]] = []
        self._metrics_history: list[dict[str, Any]] = []
        self._rulings: list[dict[str, Any]] = []
        self._check_interval = 3.0

    async def handle_message(self, message: Message) -> None:
        handlers = {
            MessageType.JUDICIAL_REVIEW: self._handle_review_request,
            MessageType.FEEDBACK: self._process_feedback,
            MessageType.EVENT: self._process_event,
            MessageType.CONTROL: self._handle_control,
        }
        handler = handlers.get(message.msg_type)
        if handler:
            await handler(message)

    async def _handle_review_request(self, message: Message) -> None:
        """处理司法审查请求"""
        payload = message.payload
        review_type_str = payload.get("review_type", "bill_review")
        subject_id = payload.get("subject_id", "")
        content = payload.get("content", {})

        review_type = ReviewType.BILL_REVIEW
        if "executive_order" in review_type_str:
            review_type = ReviewType.EXECUTIVE_ORDER_REVIEW
        elif "dispute" in review_type_str:
            review_type = ReviewType.DISPUTE_RESOLUTION
        elif "action" in review_type_str:
            review_type = ReviewType.ACTION_REVIEW

        case = await self._review_system.file_case(
            case_type=review_type,
            subject_id=subject_id,
            subject_type=payload.get("subject_type", "unknown"),
            plaintiff=message.sender,
            description=payload.get("description", f"Review of {subject_id}"),
            evidence=content,
        )

        verdict, opinion = await self._conduct_review(review_type, content, subject_id)

        dissent = await self._generate_dissent(verdict, content)

        await self._review_system.decide_case(case.case_id, verdict, opinion, dissent)

        self._rulings.append({
            "case_id": case.case_id,
            "subject_id": subject_id,
            "verdict": verdict.value,
            "opinion": opinion,
            "dissent": dissent,
            "timestamp": timestamp_now(),
        })

        ruling_msg = Message(
            msg_type=MessageType.RULING,
            sender=self.agent_id,
            receiver=message.sender,
            payload={
                "case_id": case.case_id,
                "subject_id": subject_id,
                "verdict": verdict.value,
                "opinion": opinion,
                "dissent": dissent,
                "binding": True,
            },
        )
        await self.send(ruling_msg)

        if verdict == ReviewVerdict.UNCONSTITUTIONAL:
            await self.broadcast(
                {
                    "topic": "unconstitutional_ruling",
                    "case_id": case.case_id,
                    "subject_id": subject_id,
                    "opinion": opinion,
                },
                msg_type=MessageType.RULING,
            )

        self.logger.info("RULING on %s: %s — %s", subject_id, verdict.value, opinion[:100])

    async def _conduct_review(self, review_type: ReviewType, content: dict[str, Any],
                               subject_id: str) -> tuple[ReviewVerdict, str]:
        """
        进行司法审查 — 核心审判逻辑。

        使用 LLM 模拟大法官的法律推理。
        """
        if review_type == ReviewType.EXECUTIVE_ORDER_REVIEW:
            verdict, opinion = await self._review_system.review_executive_order(content, subject_id)
        else:
            verdict, opinion = await self._review_system.review_bill(content, subject_id)

        llm = self.metadata.get("llm_client")
        if llm and content:
            try:
                user_prompt = self.JUDICIAL_REVIEW_PROMPT.format(
                    review_type=review_type.value,
                    subject_id=subject_id,
                    content=content,
                    preliminary_verdict=verdict.value,
                    preliminary_opinion=opinion,
                )
                resp = await llm.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=self.SYSTEM_PROMPT,
                    max_tokens=500,
                    caller_id=self.agent_id,
                )
                if resp.success and resp.content:
                    opinion = f"{opinion} | Judicial Opinion: {resp.content}"
            except Exception:
                pass

        return verdict, opinion

    async def _generate_dissent(self, majority_verdict: ReviewVerdict,
                                 content: dict[str, Any]) -> str:
        """生成异议意见（模拟少数派法官）"""
        llm = self.metadata.get("llm_client")
        if not llm:
            if majority_verdict == ReviewVerdict.CONSTITUTIONAL:
                return "Dissent: The majority underestimates the potential for abuse."
            return "Dissent: The majority overreaches in striking down this measure."

        try:
            opposite = "unconstitutional" if majority_verdict == ReviewVerdict.CONSTITUTIONAL else "constitutional"
            user_prompt = self.DISSENT_PROMPT.format(
                opposite_verdict=opposite,
                majority_verdict=majority_verdict.value,
                content=content,
            )
            resp = await llm.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=300,
                caller_id=self.agent_id,
            )
            if resp.success and resp.content:
                return f"Dissent: {resp.content}"
        except Exception:
            pass

        return ""

    async def _process_feedback(self, message: Message) -> None:
        """监控系统反馈 — 检测违宪行为"""
        payload = message.payload
        success = payload.get("success", True)

        if not success:
            self._alerts.append({
                "type": "execution_failure",
                "agent_id": payload.get("agent_id"),
                "task_type": payload.get("task_type"),
                "timestamp": timestamp_now(),
            })

            recent_failures = sum(
                1 for a in self._alerts[-20:]
                if a["type"] == "execution_failure"
            )

            if recent_failures >= 5:
                await self.broadcast(
                    {
                        "topic": "system_alert",
                        "alert_type": "high_failure_rate",
                        "recent_failures": recent_failures,
                        "message": f"Judicial notice: {recent_failures} failures in recent window",
                        "branch": "judicial",
                    },
                    msg_type=MessageType.CONTROL,
                )
                self.logger.warning("JUDICIAL NOTICE: High failure rate (%d)", recent_failures)

    async def _process_event(self, message: Message) -> None:
        """处理系统事件"""
        topic = message.payload.get("topic", "")

        if topic == "worker_overloaded":
            agent_id = message.payload.get("agent_id")
            self.logger.warning("Court notes: Worker %s overloaded (load=%.2f)",
                                agent_id, message.payload.get("load", 0))
            self._alerts.append({
                "type": "overload",
                "agent_id": agent_id,
                "timestamp": timestamp_now(),
            })

        elif topic == "executive_overloaded":
            self.logger.warning("Court notes: Executive branch overloaded — monitoring for abuse of power")

        elif topic == "separation_violation":
            self.logger.error("CONSTITUTIONAL CRISIS: Separation of powers violation detected!")
            await self._handle_review_request(Message(
                msg_type=MessageType.JUDICIAL_REVIEW,
                sender="system",
                receiver=self.agent_id,
                payload={
                    "review_type": "dispute_resolution",
                    "subject_id": message.payload.get("violator", "unknown"),
                    "subject_type": "separation_violation",
                    "content": message.payload,
                    "description": "Emergency review of separation of powers violation",
                },
            ))

    async def _handle_control(self, message: Message) -> None:
        action = message.payload.get("action")
        if action == "status":
            review_summary = await self._review_system.status_summary()
            await self.send(message.reply({
                "branch": "judicial",
                "role": "supreme_court",
                "rulings": len(self._rulings),
                "alerts": self._alerts[-10:],
                "review_system": review_summary,
                "metrics_count": len(self._metrics_history),
            }))
        elif action == "get_alerts":
            await self.send(message.reply({"alerts": self._alerts[-50:]}))
        elif action == "get_rulings":
            await self.send(message.reply({"rulings": self._rulings[-20:]}))

    async def on_tick(self) -> None:
        """周期性系统巡检 — 类似法官巡回审判"""
        self._metrics_history.append({
            "timestamp": timestamp_now(),
            "alert_count": len(self._alerts),
            "ruling_count": len(self._rulings),
            "state": self.state.value,
        })

        if len(self._metrics_history) > 500:
            self._metrics_history = self._metrics_history[-250:]
        if len(self._alerts) > 200:
            self._alerts = self._alerts[-100:]

    @property
    def judicial_stats(self) -> dict[str, Any]:
        unconstitutional = sum(1 for r in self._rulings if r["verdict"] == "unconstitutional")
        return {
            "total_rulings": len(self._rulings),
            "unconstitutional": unconstitutional,
            "constitutional": len(self._rulings) - unconstitutional,
            "alerts": len(self._alerts),
        }

    @property
    def recent_alerts(self) -> list[dict[str, Any]]:
        return self._alerts[-20:]
