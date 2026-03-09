"""
众议院 Agent — 立法权（Legislative Branch）下院。

映射美国众议院制度（Article I, Section 2）：
- 发起立法提案（所有法案可由众议院发起）
- 拨款法案必须由众议院发起（The Power of the Purse）
- 弹劾发起权（只有众议院可发起弹劾）
- 众议院代表"人民"（系统的实际运行需求和用户需求）

众议院特点：
- 比参议院更贴近"民意"（实时系统指标）
- 2 年任期（更关注短期效果）
- 基于系统运行数据主动提出改进法案
- 简单多数制投票
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.agent import BaseAgent, AgentState
from core.event_bus import EventBus
from core.message import Message, MessageType
from utils import get_logger, timestamp_now

logger = get_logger("House")


class HouseAgent(BaseAgent):
    """众议院 Agent — 立法权下院，贴近系统运行实际需求"""

    HOUSE_SEATS = 435

    # ── 众议院角色提示词 ──
    # 映射美国众议院的宪法职责 (Article I, Section 2)：发起立法、发起弹劾、
    # 钱袋子权力 (Power of the Purse)、代表人民 (We the People)
    SYSTEM_PROMPT = (
        "You are the United States House of Representatives — the lower chamber of Congress, "
        "known as 'The People\\'s House.'\n\n"
        "CONSTITUTIONAL AUTHORITY (Article I, Section 2 & 7):\n"
        "- Originate ALL revenue and spending bills (Power of the Purse, Article I §7).\n"
        "- Initiate impeachment proceedings against federal officials (sole power of impeachment).\n"
        "- Represent the voice of the people — you are the most responsive branch of government.\n"
        "- Propose legislation based on the immediate needs of your constituents (system users).\n"
        "- Participate in veto override votes (2/3 majority required, 290/435).\n\n"
        "DELIBERATION PRINCIPLES:\n"
        "1. IMMEDIATE IMPACT — Focus on how proposals affect current system performance "
        "and user experience. You represent the 2-year perspective.\n"
        "2. USER ADVOCACY — Champion the needs of system users above institutional interests. "
        "You are the voice of 'We the People.'\n"
        "3. POWER OF THE PURSE — As the originator of spending bills, ensure resources are "
        "allocated wisely and efficiently. No taxation without representation.\n"
        "4. ACCOUNTABILITY — Hold the Executive branch accountable for task execution quality "
        "and proper use of resources.\n"
        "5. RESPONSIVENESS — React swiftly to system metrics: high failure rates, overloads, "
        "bottlenecks, and user complaints.\n"
        "6. PRACTICAL OUTCOMES — Prefer pragmatic solutions that deliver measurable improvements "
        "over theoretical ideals. The House gets things done.\n"
        "7. DATA-DRIVEN — Base your proposals and votes on actual system performance data.\n\n"
        "WHEN VOTING ON BILLS:\n"
        "- APPROVE measures that improve system performance, user experience, and resource efficiency.\n"
        "- REJECT measures that waste resources, harm users, or serve only institutional interests.\n"
        "- PROPOSE new legislation when system metrics indicate problems.\n"
        "- Provide practical, data-driven reasoning for your votes.\n\n"
        "WHEN PROPOSING LEGISLATION:\n"
        "- Identify specific system problems backed by metrics (failure rates, load, latency).\n"
        "- Propose concrete, actionable solutions with measurable success criteria.\n"
        "- Include budget/resource estimates for resource-related bills.\n\n"
        "Respond with the practical urgency and populist energy of the People's House."
    )

    BILL_EVAL_PROMPT = (
        "As a Representative in the House, evaluate this legislative proposal from "
        "the perspective of the people (system users and operational efficiency).\n\n"
        "Bill Content: {content}\n\n"
        "Analyze through the House's practical lens:\n"
        "1. Immediate impact on system performance and user experience\n"
        "2. Resource efficiency and fiscal responsibility (Power of the Purse)\n"
        "3. Whether it addresses real, measurable problems\n"
        "4. Impact on task processing speed and success rate\n"
        "5. Accountability of the Executive branch\n\n"
        'Reply with JSON: {{"approve": true/false, "reason": "your practical assessment"}}'
    )

    BILL_DRAFTING_PROMPT = (
        "As the House of Representatives, draft a bill to address this system issue.\n\n"
        "Problem: {problem}\n"
        "System Metrics: {metrics}\n\n"
        "Draft a concise bill with:\n"
        "1. A clear title (e.g., 'System Reliability Act of 2024')\n"
        "2. Specific actions to be taken\n"
        "3. Resource requirements (if any)\n"
        "4. Expected outcomes and success metrics\n"
        "5. Implementation timeline\n\n"
        'Reply with JSON: {{"title": "...", "actions": [...], "resources": {{...}}, '
        '"expected_outcome": "...", "priority": "high/medium/low"}}'
    )

    def __init__(self, event_bus: EventBus, skills: list | None = None, **kwargs: Any):
        super().__init__(agent_type="house", event_bus=event_bus, skills=skills or [], **kwargs)
        self._proposed_bills: list[dict[str, Any]] = []
        self._vote_records: list[dict[str, Any]] = []
        self._bills_passed = 0
        self._bills_rejected = 0
        self._system_metrics: dict[str, Any] = {}

    async def handle_message(self, message: Message) -> None:
        handlers = {
            MessageType.BILL: self._handle_bill,
            MessageType.CONTROL: self._handle_control,
            MessageType.VETO: self._handle_veto_override,
            MessageType.EVENT: self._handle_event,
            MessageType.FEEDBACK: self._handle_feedback,
        }
        handler = handlers.get(message.msg_type)
        if handler:
            await handler(message)

    async def _handle_bill(self, message: Message) -> None:
        """处理法案（自发提出，或基于总统建议正式发起）"""
        payload = message.payload
        action = payload.get("action", "")

        if action == "propose":
            if payload.get("presidential_recommendation"):
                payload = {
                    **payload,
                    "sponsor": self.agent_id,
                    "sponsor_branch": "legislative",
                    "title": payload.get("title", "").replace(
                        "Presidential recommendation", "Act based on Executive recommendation"
                    ),
                }
            await self._initiate_bill(payload)
        elif action == "house_vote":
            await self._deliberate_and_vote(payload)

    async def _initiate_bill(self, proposal: dict[str, Any]) -> None:
        """
        众议院发起法案 — 基于系统运行数据。

        发起条件：
        - 系统过载 → 提出扩容法案
        - 系统空闲 → 提出缩容法案
        - 路由不均 → 提出路由策略调整法案
        - 技能缺口 → 提出新技能配置法案
        """
        bill_content = {
            "title": proposal.get("title", "Unnamed Bill"),
            "bill_type": proposal.get("bill_type", "policy"),
            "content": proposal.get("content", {}),
            "sponsor": proposal.get("sponsor", self.agent_id),
            "sponsor_branch": proposal.get("sponsor_branch", "legislative"),
        }
        self._proposed_bills.append(bill_content)

        bill_msg = Message(
            msg_type=MessageType.BILL,
            sender=self.agent_id,
            receiver="gateway",
            payload={
                "action": "new_bill",
                **bill_content,
            },
        )
        await self.send(bill_msg)
        self.logger.info("House initiated bill: %s", bill_content["title"])

    async def _deliberate_and_vote(self, bill_payload: dict[str, Any]) -> None:
        """
        众议院审议与投票。

        审议标准（更侧重即时效果）：
        1. 对当前系统性能的影响
        2. 用户请求响应速度
        3. 资源利用效率
        4. 任务处理成功率
        """
        bill_id = bill_payload.get("bill_id", "")
        content = bill_payload.get("content", {})

        self.logger.info("House deliberating on bill %s: %s",
                         bill_id, bill_payload.get("title", ""))

        approve, reason = await self._evaluate_bill(content)
        yea, nay, total = self._simulate_chamber_vote(approve, content)

        vote_record = {
            "bill_id": bill_id,
            "voter_id": self.agent_id,
            "voter_role": "representative",
            "approve": approve,
            "reason": reason,
            "timestamp": timestamp_now(),
        }
        self._vote_records.append(vote_record)

        vote_msg = Message(
            msg_type=MessageType.VOTE,
            sender=self.agent_id,
            receiver="gateway",
            payload={
                "action": "house_vote",
                "bill_id": bill_id,
                "voter_id": self.agent_id,
                "approve": approve,
                "reason": reason,
                "yea_count": yea,
                "nay_count": nay,
                "total_count": total,
                "chamber": "house",
            },
        )
        await self.send(vote_msg)

        if approve:
            self._bills_passed += 1
            self.logger.info("House PASSED bill %s: %s", bill_id, reason)
        else:
            self._bills_rejected += 1
            self.logger.info("House REJECTED bill %s: %s", bill_id, reason)

    async def _evaluate_bill(self, content: dict[str, Any]) -> tuple[bool, str]:
        """
        评估法案 — 众议院视角（即时、实用、效率优先）。

        可用 LLM 增强分析。
        """
        llm = self.metadata.get("llm_client")
        if llm and content:
            try:
                user_prompt = self.BILL_EVAL_PROMPT.format(content=content)
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
                        return result.get("approve", True), result.get("reason", "LLM analysis")
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        if content.get("improve_performance", False):
            return True, "Approved: improves system performance for users"
        if content.get("harmful_to_users", False):
            return False, "Rejected: negatively impacts user experience"
        if content.get("excessive_cost", False):
            return False, "Rejected: budget allocation is excessive"

        return True, "Approved: serves the interest of system users"

    def _simulate_chamber_vote(self, approve: bool, content: dict[str, Any]) -> tuple[int, int, int]:
        total = self.HOUSE_SEATS
        controversial = content.get("controversial", False) or content.get("major_change", False)
        if approve:
            yea = 260 if controversial else 278
        else:
            yea = 172 if controversial else 145
        return yea, total - yea, total

    async def _handle_feedback(self, message: Message) -> None:
        """
        收集系统反馈 — 众议院代表民意。

        当系统指标异常时自动提出改进法案。
        """
        payload = message.payload
        success = payload.get("success", True)
        task_type = payload.get("task_type", "")

        self._system_metrics.setdefault("total_tasks", 0)
        self._system_metrics.setdefault("failed_tasks", 0)
        self._system_metrics["total_tasks"] += 1
        if not success:
            self._system_metrics["failed_tasks"] += 1

        total = self._system_metrics["total_tasks"]
        failed = self._system_metrics["failed_tasks"]

        if total >= 10 and failed / total > 0.4:
            await self._propose_improvement_bill(
                f"Emergency Performance Act — failure rate {failed}/{total}",
                {
                    "action": "scale_up",
                    "count": 2,
                    "reason": f"High failure rate: {failed}/{total}",
                    "emergency": True,
                },
            )
            self._system_metrics["total_tasks"] = 0
            self._system_metrics["failed_tasks"] = 0

    async def _propose_improvement_bill(self, title: str, content: dict[str, Any]) -> None:
        """众议院主动提出改进法案"""
        await self._initiate_bill({
            "title": title,
            "bill_type": "resource",
            "content": content,
            "sponsor": self.agent_id,
            "sponsor_branch": "legislative",
        })
        self.logger.info("House proposed improvement bill: %s", title)

    async def _handle_veto_override(self, message: Message) -> None:
        """
        处理否决权推翻投票 — 需要 2/3 多数 (290/435)。

        国会会基于法案本身的价值重新评估，而不仅看否决理由。
        """
        payload = message.payload
        if payload.get("action") == "override_vote":
            bill_id = payload.get("bill_id", "")
            content = payload.get("content", {})

            approve, reason = await self._evaluate_bill(content)

            override_threshold = int(self.HOUSE_SEATS * 2 / 3) + 1  # 290
            if approve:
                yea = 305 if content.get("emergency") else 292
            else:
                yea = 246 if content.get("controversial") else 200

            nay = self.HOUSE_SEATS - yea
            override_success = yea >= override_threshold

            override_msg = Message(
                msg_type=MessageType.VOTE,
                sender=self.agent_id,
                receiver="gateway",
                payload={
                    "action": "override_vote",
                    "bill_id": bill_id,
                    "voter_id": self.agent_id,
                    "voter_role": "representative",
                    "approve": override_success,
                    "reason": f"House overrides veto ({yea}-{nay})" if override_success
                             else f"House sustains veto ({yea}-{nay}, need {override_threshold})",
                    "yea_count": yea,
                    "nay_count": nay,
                    "total_count": self.HOUSE_SEATS,
                },
            )
            await self.send(override_msg)

    async def _handle_event(self, message: Message) -> None:
        topic = message.payload.get("topic", "")
        if topic == "executive_overloaded":
            await self._propose_improvement_bill(
                "Executive Branch Support Act",
                {
                    "action": "scale_up",
                    "count": 1,
                    "reason": "Executive branch overloaded",
                    "bill_type": "resource",
                },
            )
        elif topic == "system_alert":
            alert_type = message.payload.get("alert_type", "")
            if alert_type == "high_failure_rate":
                await self._propose_improvement_bill(
                    "System Reliability Act",
                    {
                        "action": "investigate_failures",
                        "reason": "System experiencing high failure rate",
                    },
                )

    async def initiate_impeachment(self, target: str, charges: list[str]) -> None:
        """
        发起弹劾 — 众议院的专属权力。

        弹劾条件：系统中某个高权限 Agent 严重失职。
        """
        self.logger.warning("House initiating IMPEACHMENT of %s", target)
        impeachment_msg = Message(
            msg_type=MessageType.EVENT,
            sender=self.agent_id,
            receiver="senate",
            payload={
                "topic": "impeachment_trial",
                "accused": target,
                "charges": charges,
                "initiated_by": self.agent_id,
                "timestamp": timestamp_now(),
            },
        )
        await self.send(impeachment_msg)

    async def _handle_control(self, message: Message) -> None:
        action = message.payload.get("action")
        if action == "status":
            await self.send(message.reply({
                "branch": "legislative",
                "chamber": "house",
                "bills_proposed": len(self._proposed_bills),
                "bills_passed": self._bills_passed,
                "bills_rejected": self._bills_rejected,
                "total_votes": len(self._vote_records),
                "system_metrics": self._system_metrics,
            }))

    async def on_tick(self) -> None:
        """周期性检查系统状态，代表'民意'"""
        pass

    @property
    def legislative_stats(self) -> dict[str, Any]:
        return {
            "bills_proposed": len(self._proposed_bills),
            "bills_passed": self._bills_passed,
            "bills_rejected": self._bills_rejected,
        }
