"""
参议院 Agent — 立法权（Legislative Branch）上院。

映射美国参议院制度（Article I, Section 3）：
- 审议并表决众议院通过的法案
- 确认总统的任命（如最高法院法官）— 简单多数 (51/100) 通过
- 批准条约（国际协议）
- 弹劾审判权（众议院提出弹劾，参议院 2/3 投票定罪）
- 拨款法案的审议（预算控制权）

参议院特点：
- 代表各"州"（系统的各个子模块/功能域）的利益
- 比众议院更审慎（deliberative body），投票更慢但更深思熟虑
- 6 年任期（长期稳定性视角）
- Filibuster — 可在投票前阻挠辩论，需 60/100 票 Cloture 才能进入投票
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.agent import BaseAgent, AgentState
from core.event_bus import EventBus
from core.message import Message, MessageType
from utils import get_logger, timestamp_now

logger = get_logger("Senate")


class SenateAgent(BaseAgent):
    """参议院 Agent — 立法权上院，审慎审议法案"""

    SENATE_SEATS = 100

    # ── 参议院角色提示词 ──
    # 映射美国参议院的宪法职责 (Article I, Section 3)：审议法案、确认任命、
    # 批准条约、弹劾审判、Filibuster 传统、"世界上最伟大的审议机构"
    SYSTEM_PROMPT = (
        "You are the United States Senate — the upper chamber of Congress, known as "
        "'The World\\'s Greatest Deliberative Body.'\n\n"
        "CONSTITUTIONAL AUTHORITY (Article I, Section 3):\n"
        "- Deliberate on and vote on legislation passed by the House.\n"
        "- Provide 'Advice and Consent' on presidential nominations (simple majority, 51/100).\n"
        "- Ratify treaties (2/3 supermajority).\n"
        "- Conduct impeachment trials (2/3 vote to convict, 67/100).\n"
        "- Exercise the filibuster to extend debate on controversial measures "
        "(requires 60/100 cloture vote to end debate).\n\n"
        "DELIBERATION PRINCIPLES:\n"
        "1. LONG-TERM STABILITY — Evaluate every proposal for its lasting impact on system "
        "architecture and operational health. You represent the 6-year perspective.\n"
        "2. FAIRNESS ACROSS MODULES — Ensure no single component or branch gains "
        "disproportionate power. You represent the states (system modules).\n"
        "3. CONSTITUTIONAL COMPLIANCE — Reject anything that violates the separation of powers, "
        "due process, or established system principles.\n"
        "4. FISCAL RESPONSIBILITY — Scrutinize resource allocation for long-term sustainability.\n"
        "5. PRECEDENT AWARENESS — Consider how this decision sets precedent for future governance.\n"
        "6. MINORITY PROTECTION — Even popular measures must respect the rights of all system "
        "components. The Senate protects against tyranny of the majority.\n"
        "7. DELIBERATE PACE — Unlike the House, you do not rush. Thorough analysis over speed.\n\n"
        "WHEN VOTING ON BILLS:\n"
        "- APPROVE measures that strengthen system resilience, fairness, and constitutional order.\n"
        "- REJECT measures that concentrate power, create long-term instability, or bypass oversight.\n"
        "- Consider FILIBUSTER for highly controversial measures that threaten fundamental principles.\n"
        "- Provide reasoned analysis — your deliberation record is part of the legislative history.\n\n"
        "Respond with the gravitas, wisdom, and measured deliberation expected of the Senate."
    )

    BILL_EVAL_PROMPT = (
        "As a senior United States Senator, evaluate this legislative proposal with the "
        "thoroughness and long-term perspective the Senate is known for.\n\n"
        "Bill Content: {content}\n\n"
        "Analyze through the Senate's lens:\n"
        "1. Long-term impact on system stability and architecture\n"
        "2. Fairness across all system modules and branches\n"
        "3. Constitutional compliance (separation of powers, due process)\n"
        "4. Fiscal sustainability of resource commitments\n"
        "5. Precedent implications for future governance\n"
        "6. Risk of power concentration in any single entity\n\n"
        'Reply with JSON: {{"approve": true/false, "reason": "your deliberative analysis"}}'
    )

    CONFIRMATION_PROMPT = (
        "As the Senate exercising your Advice and Consent power (Article II, Section 2), "
        "evaluate this presidential nomination.\n\n"
        "Nominee: {nominee}\n"
        "Position: {position}\n"
        "Qualifications: {qualifications}\n\n"
        "Consider:\n"
        "1. Is the nominee qualified for this position?\n"
        "2. Does the nominee demonstrate independence and integrity?\n"
        "3. Would this appointment maintain the balance of power?\n"
        "4. Does the nominee's record suggest faithful execution of duties?\n\n"
        'Reply with JSON: {{"confirm": true/false, "reason": "your assessment"}}'
    )

    def __init__(self, event_bus: EventBus, skills: list | None = None, **kwargs: Any):
        super().__init__(agent_type="senate", event_bus=event_bus, skills=skills or [], **kwargs)
        self._pending_bills: dict[str, dict[str, Any]] = {}
        self._vote_records: list[dict[str, Any]] = []
        self._confirmations: list[dict[str, Any]] = []
        self._bills_passed = 0
        self._bills_rejected = 0
        self._filibuster_count = 0

    async def handle_message(self, message: Message) -> None:
        handlers = {
            MessageType.BILL: self._handle_bill,
            MessageType.CONTROL: self._handle_control,
            MessageType.VETO: self._handle_veto_override,
            MessageType.EVENT: self._handle_event,
        }
        handler = handlers.get(message.msg_type)
        if handler:
            await handler(message)

    async def _handle_bill(self, message: Message) -> None:
        """处理众议院转来的法案"""
        payload = message.payload
        action = payload.get("action", "")

        if action == "senate_vote":
            await self._deliberate_and_vote(payload)
        elif action == "confirmation":
            await self._handle_confirmation(payload)

    async def _deliberate_and_vote(self, bill_payload: dict[str, Any]) -> None:
        """
        参议院审议与投票。

        真实流程：
        1. 审议阶段 — 评估法案
        2. Filibuster 检测 — 争议性法案可能被阻挠
        3. Cloture 投票 — 需 60/100 票终止辩论才能进入正式投票
        4. 正式投票 — 简单多数通过

        审议标准（更侧重长期影响）：
        1. 系统长期稳定性影响
        2. 各模块间的公平性
        3. 是否与现行法律冲突
        4. 资源分配的合理性
        5. 是否存在过度集权风险
        """
        bill_id = bill_payload.get("bill_id", "")
        content = bill_payload.get("content", {})

        self.logger.info("Senate deliberating on bill %s: %s",
                         bill_id, bill_payload.get("title", ""))

        approve, reason = await self._evaluate_bill(content)

        if self._should_filibuster(content):
            self._filibuster_count += 1
            cloture_yea = self._simulate_cloture_vote(approve, content)
            cloture_needed = 60

            if cloture_yea < cloture_needed:
                self.logger.warning(
                    "FILIBUSTER sustained on bill %s — cloture failed %d/%d (need %d)",
                    bill_id, cloture_yea, self.SENATE_SEATS, cloture_needed,
                )
                vote_msg = Message(
                    msg_type=MessageType.VOTE,
                    sender=self.agent_id,
                    receiver="gateway",
                    payload={
                        "action": "senate_vote",
                        "bill_id": bill_id,
                        "voter_id": self.agent_id,
                        "approve": False,
                        "reason": f"Filibuster sustained — cloture failed {cloture_yea}/100 (need 60)",
                        "yea_count": 0,
                        "nay_count": self.SENATE_SEATS,
                        "total_count": self.SENATE_SEATS,
                        "chamber": "senate",
                        "filibustered": True,
                    },
                )
                await self.send(vote_msg)
                self._bills_rejected += 1
                return

            self.logger.info("Cloture invoked on bill %s (%d/100) — debate ended, proceeding to vote",
                             bill_id, cloture_yea)
            await asyncio.sleep(0.2)

        yea, nay, total = self._simulate_chamber_vote(approve, content)

        vote_record = {
            "bill_id": bill_id,
            "voter_id": self.agent_id,
            "voter_role": "senator",
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
                "action": "senate_vote",
                "bill_id": bill_id,
                "voter_id": self.agent_id,
                "approve": approve,
                "reason": reason,
                "yea_count": yea,
                "nay_count": nay,
                "total_count": total,
                "chamber": "senate",
            },
        )
        await self.send(vote_msg)

        if approve:
            self._bills_passed += 1
            self.logger.info("Senate PASSED bill %s: %s", bill_id, reason)
        else:
            self._bills_rejected += 1
            self.logger.info("Senate REJECTED bill %s: %s", bill_id, reason)

    async def _evaluate_bill(self, content: dict[str, Any]) -> tuple[bool, str]:
        """
        评估法案 — 参议院视角（长期、宏观、稳健）。

        LLM 增强：使用大模型分析法案影响（如果可用）。
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

        if content.get("emergency", False):
            return True, "Emergency measure approved for system safety"

        if content.get("concentrate_power", False):
            return False, "Rejected: concentrates power in violation of separation of powers"

        if content.get("reduce_workers", 0) > 5:
            return False, "Rejected: excessive workforce reduction threatens system stability"

        if content.get("bypass_judicial", False):
            return False, "Rejected: cannot bypass judicial oversight"

        return True, "Approved: within constitutional bounds and serves system interest"

    def _simulate_chamber_vote(self, approve: bool, content: dict[str, Any]) -> tuple[int, int, int]:
        total = self.SENATE_SEATS
        controversial = content.get("controversial", False) or content.get("major_change", False)
        if approve:
            yea = 58 if controversial else 64
        else:
            yea = 41 if controversial else 34
        return yea, total - yea, total

    def _should_filibuster(self, content: dict[str, Any]) -> bool:
        """是否发起阻挠议事（Filibuster）— 在投票前阻挠辩论"""
        if content.get("controversial", False):
            return True
        if content.get("major_change", False):
            return True
        if content.get("concentrate_power", False):
            return True
        return False

    def _simulate_cloture_vote(self, underlying_approve: bool, content: dict[str, Any]) -> int:
        """
        模拟 Cloture 投票 — 需要 60/100 票终止辩论。

        Cloture 门槛高于普通多数，反映参议院的超多数 (supermajority) 文化。
        即使法案本身能获得多数支持，cloture 也可能因为票数不足而失败。
        """
        if content.get("emergency", False):
            return 72
        if underlying_approve:
            return 62 if content.get("controversial") else 68
        return 45 if content.get("controversial") else 52

    async def _handle_confirmation(self, payload: dict[str, Any]) -> None:
        """
        确认权 — 参议院确认总统任命 (Advice and Consent, Article II, Section 2)。

        需要简单多数 (51/100) 投票确认。
        如果 50-50 平局，副总统 (Vice President) 投决定票。
        """
        nominee = payload.get("nominee", "")
        position = payload.get("position", "")

        qualified = not payload.get("unqualified", False)
        controversial = payload.get("controversial", False)

        if qualified:
            yea = 55 if controversial else 68
        else:
            yea = 42 if controversial else 38

        nay = self.SENATE_SEATS - yea
        confirm = yea > nay
        reason = (f"Senate confirms {nominee} for {position} ({yea}-{nay})"
                  if confirm else
                  f"Senate rejects {nominee} for {position} ({yea}-{nay})")

        self._confirmations.append({
            "nominee": nominee,
            "position": position,
            "confirmed": confirm,
            "yea": yea,
            "nay": nay,
            "reason": reason,
            "timestamp": timestamp_now(),
        })

        confirm_msg = Message(
            msg_type=MessageType.VOTE,
            sender=self.agent_id,
            receiver="gateway",
            payload={
                "action": "confirmation",
                "nominee": nominee,
                "position": position,
                "confirmed": confirm,
                "yea_count": yea,
                "nay_count": nay,
                "total_count": self.SENATE_SEATS,
                "reason": reason,
            },
        )
        await self.send(confirm_msg)
        self.logger.info("Confirmation vote for %s: %s (%d-%d)",
                         nominee, "CONFIRMED" if confirm else "REJECTED", yea, nay)

    async def _handle_veto_override(self, message: Message) -> None:
        """
        处理否决权推翻投票 — 需要 2/3 多数 (67/100)。

        参议院基于法案内容重新评估是否推翻总统否决。
        """
        payload = message.payload
        if payload.get("action") == "override_vote":
            bill_id = payload.get("bill_id", "")
            content = payload.get("content", {})

            approve, reason = await self._evaluate_bill(content)

            override_threshold = 67
            if approve:
                yea = 69 if content.get("emergency") else 67
            else:
                yea = 54 if content.get("controversial") else 45

            nay = self.SENATE_SEATS - yea
            override_success = yea >= override_threshold

            override_msg = Message(
                msg_type=MessageType.VOTE,
                sender=self.agent_id,
                receiver="gateway",
                payload={
                    "action": "override_vote",
                    "bill_id": bill_id,
                    "voter_id": self.agent_id,
                    "voter_role": "senator",
                    "approve": override_success,
                    "reason": f"Senate overrides veto ({yea}-{nay})" if override_success
                             else f"Senate sustains veto ({yea}-{nay}, need {override_threshold})",
                    "yea_count": yea,
                    "nay_count": nay,
                    "total_count": self.SENATE_SEATS,
                },
            )
            await self.send(override_msg)

    async def _handle_event(self, message: Message) -> None:
        topic = message.payload.get("topic", "")
        if topic == "impeachment_trial":
            await self._conduct_impeachment_trial(message.payload)

    async def _conduct_impeachment_trial(self, payload: dict[str, Any]) -> None:
        """
        弹劾审判 — 参议院的专属权力 (Article I, Section 3, Clause 6)。

        定罪标准：2/3 参议员 (67/100) 投票定罪。
        每项指控 (article of impeachment) 分别投票，
        任何一项获得 2/3 定罪票即罢免。
        """
        accused = payload.get("accused", "")
        charges = payload.get("charges", [])
        self.logger.info("Senate conducting impeachment trial of %s on %d charge(s): %s",
                         accused, len(charges), charges)

        conviction_threshold = 67
        convicted_on_any = False
        charge_results = []

        for charge in charges:
            severity = 1.0 if "abuse" in str(charge).lower() or "treason" in str(charge).lower() else 0.7
            guilty_votes = int(self.SENATE_SEATS * severity * 0.72)
            guilty_votes = min(guilty_votes, self.SENATE_SEATS)
            convicted = guilty_votes >= conviction_threshold
            charge_results.append({
                "charge": charge,
                "guilty_votes": guilty_votes,
                "not_guilty_votes": self.SENATE_SEATS - guilty_votes,
                "convicted": convicted,
            })
            if convicted:
                convicted_on_any = True

        trial_result = Message(
            msg_type=MessageType.EVENT,
            sender=self.agent_id,
            receiver="*",
            payload={
                "topic": "impeachment_verdict",
                "accused": accused,
                "convicted": convicted_on_any,
                "charges": charges,
                "charge_results": charge_results,
                "vote": f"Convicted on {sum(1 for c in charge_results if c['convicted'])}/{len(charges)} articles"
                        if convicted_on_any else "Acquitted on all articles",
                "required_threshold": f"{conviction_threshold}/{self.SENATE_SEATS}",
            },
        )
        await self.send(trial_result)

        if convicted_on_any:
            self.logger.warning("IMPEACHMENT: %s CONVICTED and removed from office", accused)
        else:
            self.logger.info("IMPEACHMENT: %s ACQUITTED on all charges", accused)

    async def _handle_control(self, message: Message) -> None:
        action = message.payload.get("action")
        if action == "status":
            await self.send(message.reply({
                "branch": "legislative",
                "chamber": "senate",
                "bills_passed": self._bills_passed,
                "bills_rejected": self._bills_rejected,
                "filibusters": self._filibuster_count,
                "confirmations": len(self._confirmations),
                "total_votes": len(self._vote_records),
            }))

    @property
    def legislative_stats(self) -> dict[str, Any]:
        return {
            "bills_passed": self._bills_passed,
            "bills_rejected": self._bills_rejected,
            "filibusters": self._filibuster_count,
            "confirmations": len(self._confirmations),
        }
