"""
立法管理系统 — 法案的完整生命周期。

映射美国立法流程（Article I）：
1. 法案由国会议员正式发起（总统只能建议，不能直接提案）
2. 众议院辩论与投票（简单多数通过）
3. 参议院辩论与投票（简单多数通过；争议性法案可能遭遇 Filibuster，需 60 票 Cloture）
4. 总统签署或否决
5. 若总统否决，国会可以两院各自 2/3 多数推翻否决
6. 最高法院仅在有人提起诉讼时才进行违宪审查（被动司法）

法案类型：
- POLICY: 系统策略（路由策略、负载均衡规则）
- RESOURCE: 资源分配（Agent 扩缩容）— 必须由众议院发起（Origination Clause）
- BUDGET: 预算分配（计算资源配额）— 必须由众议院发起（Origination Clause）
- AMENDMENT: 对已有法案的修正
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from utils import get_logger, generate_id, timestamp_now

logger = get_logger("Legislation")


class BillStatus(Enum):
    DRAFTED = "drafted"
    HOUSE_VOTING = "house_voting"
    HOUSE_PASSED = "house_passed"
    HOUSE_REJECTED = "house_rejected"
    SENATE_VOTING = "senate_voting"
    SENATE_PASSED = "senate_passed"
    SENATE_REJECTED = "senate_rejected"
    AWAITING_SIGNATURE = "awaiting_signature"
    SIGNED = "signed"
    VETOED = "vetoed"
    VETO_OVERRIDE_VOTING = "veto_override_voting"
    VETO_OVERRIDDEN = "veto_overridden"
    ENACTED = "enacted"
    UNCONSTITUTIONAL = "unconstitutional"
    EXPIRED = "expired"


class BillType(Enum):
    POLICY = "policy"
    RESOURCE = "resource"
    BUDGET = "budget"
    AMENDMENT = "amendment"
    EMERGENCY = "emergency"


@dataclass
class Vote:
    voter_id: str
    voter_role: str  # "senator" / "representative"
    approve: bool
    reason: str = ""
    yea_count: int = 0
    nay_count: int = 0
    total_count: int = 0
    timestamp: float = field(default_factory=timestamp_now)


@dataclass
class Bill:
    bill_id: str = field(default_factory=lambda: generate_id("bill"))
    title: str = ""
    bill_type: BillType = BillType.POLICY
    sponsor: str = ""
    sponsor_branch: str = ""
    content: dict[str, Any] = field(default_factory=dict)
    status: BillStatus = BillStatus.DRAFTED
    house_votes: list[Vote] = field(default_factory=list)
    senate_votes: list[Vote] = field(default_factory=list)
    override_votes: list[Vote] = field(default_factory=list)
    veto_reason: str = ""
    judicial_review_result: str | None = None
    created_at: float = field(default_factory=timestamp_now)
    enacted_at: float | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def _log(self, action: str, detail: str = "") -> None:
        self.history.append({
            "action": action,
            "detail": detail,
            "timestamp": timestamp_now(),
            "status": self.status.value,
        })

    @property
    def house_result(self) -> dict[str, Any]:
        if not self.house_votes:
            return {"yea": 0, "nay": 0, "total": 0, "passed": False}
        yea = sum(v.yea_count or (1 if v.approve else 0) for v in self.house_votes)
        nay = sum(v.nay_count or (0 if v.approve else 1) for v in self.house_votes)
        total = sum(v.total_count or 1 for v in self.house_votes)
        return {"yea": yea, "nay": nay, "total": total, "passed": yea > nay}

    @property
    def senate_result(self) -> dict[str, Any]:
        if not self.senate_votes:
            return {"yea": 0, "nay": 0, "total": 0, "passed": False}
        yea = sum(v.yea_count or (1 if v.approve else 0) for v in self.senate_votes)
        nay = sum(v.nay_count or (0 if v.approve else 1) for v in self.senate_votes)
        total = sum(v.total_count or 1 for v in self.senate_votes)
        return {"yea": yea, "nay": nay, "total": total, "passed": yea > nay}

    @property
    def override_result(self) -> dict[str, Any]:
        if not self.override_votes:
            return {
                "house": {"yea": 0, "nay": 0, "total": 0, "overridden": False},
                "senate": {"yea": 0, "nay": 0, "total": 0, "overridden": False},
                "overridden": False,
            }

        def chamber_result(role: str) -> dict[str, Any]:
            votes = [v for v in self.override_votes if v.voter_role == role]
            if not votes:
                return {"yea": 0, "nay": 0, "total": 0, "overridden": False}
            yea = sum(v.yea_count or (1 if v.approve else 0) for v in votes)
            nay = sum(v.nay_count or (0 if v.approve else 1) for v in votes)
            total = sum(v.total_count or 1 for v in votes)
            overridden = total > 0 and yea / total >= 2 / 3
            return {"yea": yea, "nay": nay, "total": total, "overridden": overridden}

        house = chamber_result("representative")
        senate = chamber_result("senator")
        return {
            "house": house,
            "senate": senate,
            "overridden": house["overridden"] and senate["overridden"],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "bill_id": self.bill_id,
            "title": self.title,
            "type": self.bill_type.value,
            "sponsor": self.sponsor,
            "sponsor_branch": self.sponsor_branch,
            "status": self.status.value,
            "content": self.content,
            "house_result": self.house_result,
            "senate_result": self.senate_result,
            "override_result": self.override_result,
            "veto_reason": self.veto_reason,
            "judicial_review": self.judicial_review_result,
            "created_at": self.created_at,
            "enacted_at": self.enacted_at,
            "history_count": len(self.history),
        }


class LegislationManager:
    """
    立法管理器 — 管理法案从提出到生效的完整流程。

    核心规则（映射美国宪法）：
    - 众议院先投票，简单多数通过
    - 参议院再投票，简单多数通过
    - 总统签署后成为法律；否决后需 2/3 国会多数推翻
    - 紧急法案可走快速通道（仅需总统签署）
    """

    def __init__(self) -> None:
        self._bills: dict[str, Bill] = {}
        self._enacted_laws: dict[str, Bill] = {}
        self._lock = asyncio.Lock()

    async def propose_bill(self, title: str, bill_type: BillType, sponsor: str,
                           sponsor_branch: str, content: dict[str, Any]) -> Bill:
        async with self._lock:
            bill = Bill(
                title=title,
                bill_type=bill_type,
                sponsor=sponsor,
                sponsor_branch=sponsor_branch,
                content=content,
            )
            bill.status = BillStatus.HOUSE_VOTING
            bill._log("proposed", f"By {sponsor} ({sponsor_branch})")
            self._bills[bill.bill_id] = bill
            logger.info("Bill proposed: [%s] %s by %s", bill.bill_id, title, sponsor)
            return bill

    async def cast_house_vote(self, bill_id: str, voter_id: str, approve: bool,
                               reason: str = "", yea_count: int = 0,
                               nay_count: int = 0, total_count: int = 0) -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id)
            if not bill or bill.status != BillStatus.HOUSE_VOTING:
                return None

            bill.house_votes.append(Vote(
                voter_id=voter_id, voter_role="representative",
                approve=approve, reason=reason,
                yea_count=yea_count, nay_count=nay_count, total_count=total_count,
            ))
            bill._log("house_vote", f"{voter_id}: {'Yea' if approve else 'Nay'}")
            return bill

    async def finalize_house_vote(self, bill_id: str) -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id)
            if not bill or bill.status != BillStatus.HOUSE_VOTING:
                return None

            result = bill.house_result
            if result["passed"]:
                bill.status = BillStatus.HOUSE_PASSED
                bill._log("house_passed", f"Yea {result['yea']} - Nay {result['nay']}")
                bill.status = BillStatus.SENATE_VOTING
                logger.info("Bill %s passed House (%d-%d), moving to Senate",
                            bill_id, result['yea'], result['nay'])
            else:
                bill.status = BillStatus.HOUSE_REJECTED
                bill._log("house_rejected", f"Yea {result['yea']} - Nay {result['nay']}")
                logger.info("Bill %s rejected by House (%d-%d)",
                            bill_id, result['yea'], result['nay'])
            return bill

    async def cast_senate_vote(self, bill_id: str, voter_id: str, approve: bool,
                                reason: str = "", yea_count: int = 0,
                                nay_count: int = 0, total_count: int = 0) -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id)
            if not bill or bill.status != BillStatus.SENATE_VOTING:
                return None

            bill.senate_votes.append(Vote(
                voter_id=voter_id, voter_role="senator",
                approve=approve, reason=reason,
                yea_count=yea_count, nay_count=nay_count, total_count=total_count,
            ))
            bill._log("senate_vote", f"{voter_id}: {'Yea' if approve else 'Nay'}")
            return bill

    async def finalize_senate_vote(self, bill_id: str) -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id)
            if not bill or bill.status != BillStatus.SENATE_VOTING:
                return None

            result = bill.senate_result
            if result["passed"]:
                bill.status = BillStatus.SENATE_PASSED
                bill._log("senate_passed", f"Yea {result['yea']} - Nay {result['nay']}")
                bill.status = BillStatus.AWAITING_SIGNATURE
                logger.info("Bill %s passed Senate (%d-%d), awaiting presidential signature",
                            bill_id, result['yea'], result['nay'])
            else:
                bill.status = BillStatus.SENATE_REJECTED
                bill._log("senate_rejected", f"Yea {result['yea']} - Nay {result['nay']}")
                logger.info("Bill %s rejected by Senate (%d-%d)",
                            bill_id, result['yea'], result['nay'])
            return bill

    async def presidential_action(self, bill_id: str, sign: bool,
                                   veto_reason: str = "") -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id)
            if not bill or bill.status != BillStatus.AWAITING_SIGNATURE:
                return None

            if sign:
                bill.status = BillStatus.SIGNED
                bill._log("signed", "Signed by President")
                await self._enact_bill(bill)
                logger.info("Bill %s signed into law by President", bill_id)
            else:
                bill.status = BillStatus.VETOED
                bill.veto_reason = veto_reason
                bill._log("vetoed", f"Vetoed: {veto_reason}")
                bill.status = BillStatus.VETO_OVERRIDE_VOTING
                logger.info("Bill %s vetoed by President: %s", bill_id, veto_reason)
            return bill

    async def cast_override_vote(self, bill_id: str, voter_id: str, voter_role: str,
                                  approve: bool, reason: str = "",
                                  yea_count: int = 0, nay_count: int = 0,
                                  total_count: int = 0) -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id)
            if not bill or bill.status != BillStatus.VETO_OVERRIDE_VOTING:
                return None

            bill.override_votes.append(Vote(
                voter_id=voter_id, voter_role=voter_role,
                approve=approve, reason=reason,
                yea_count=yea_count, nay_count=nay_count, total_count=total_count,
            ))
            bill._log("override_vote", f"{voter_id} ({voter_role}): {'Yea' if approve else 'Nay'}")
            return bill

    async def finalize_override_vote(self, bill_id: str) -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id)
            if not bill or bill.status != BillStatus.VETO_OVERRIDE_VOTING:
                return None

            result = bill.override_result
            if result["overridden"]:
                bill.status = BillStatus.VETO_OVERRIDDEN
                bill._log(
                    "veto_overridden",
                    "Override succeeded in both chambers: "
                    f"House {result['house']['yea']}/{result['house']['total']}, "
                    f"Senate {result['senate']['yea']}/{result['senate']['total']}",
                )
                await self._enact_bill(bill)
                logger.info(
                    "Presidential veto overridden for bill %s (House %d/%d, Senate %d/%d)",
                    bill_id,
                    result["house"]["yea"], result["house"]["total"],
                    result["senate"]["yea"], result["senate"]["total"],
                )
            else:
                bill.status = BillStatus.VETOED
                bill._log(
                    "override_failed",
                    "Override failed: "
                    f"House {result['house']['yea']}/{result['house']['total']}, "
                    f"Senate {result['senate']['yea']}/{result['senate']['total']}",
                )
                logger.info(
                    "Veto override failed for bill %s (House %d/%d, Senate %d/%d)",
                    bill_id,
                    result["house"]["yea"], result["house"]["total"],
                    result["senate"]["yea"], result["senate"]["total"],
                )
            return bill

    async def mark_unconstitutional(self, bill_id: str, ruling: str) -> Bill | None:
        async with self._lock:
            bill = self._bills.get(bill_id) or self._enacted_laws.get(bill_id)
            if not bill:
                return None

            bill.status = BillStatus.UNCONSTITUTIONAL
            bill.judicial_review_result = ruling
            bill._log("unconstitutional", ruling)
            self._enacted_laws.pop(bill_id, None)
            logger.info("Bill %s ruled unconstitutional: %s", bill_id, ruling)
            return bill

    async def _enact_bill(self, bill: Bill) -> None:
        bill.status = BillStatus.ENACTED
        bill.enacted_at = timestamp_now()
        bill._log("enacted", "Law is now in effect")
        self._enacted_laws[bill.bill_id] = bill
        logger.info("Bill %s enacted as law: %s", bill.bill_id, bill.title)

    async def get_bill(self, bill_id: str) -> Bill | None:
        async with self._lock:
            return self._bills.get(bill_id)

    async def get_active_bills(self) -> list[Bill]:
        async with self._lock:
            terminal = {BillStatus.HOUSE_REJECTED, BillStatus.SENATE_REJECTED,
                        BillStatus.UNCONSTITUTIONAL, BillStatus.EXPIRED}
            return [b for b in self._bills.values() if b.status not in terminal]

    async def get_enacted_laws(self) -> list[Bill]:
        async with self._lock:
            return list(self._enacted_laws.values())

    async def get_laws_by_type(self, bill_type: BillType) -> list[Bill]:
        async with self._lock:
            return [b for b in self._enacted_laws.values() if b.bill_type == bill_type]

    async def status_summary(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "total_bills": len(self._bills),
                "enacted_laws": len(self._enacted_laws),
                "active_bills": len([b for b in self._bills.values()
                                     if b.status not in {BillStatus.HOUSE_REJECTED,
                                                         BillStatus.SENATE_REJECTED,
                                                         BillStatus.UNCONSTITUTIONAL,
                                                         BillStatus.EXPIRED}]),
                "recent_bills": [b.to_dict() for b in list(self._bills.values())[-5:]],
            }
