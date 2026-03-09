"""
司法审查系统 — 最高法院的违宪审查权。

映射美国司法制度（Marbury v. Madison, 1803）：
- 最高法院有权审查国会立法是否违宪
- 最高法院有权审查总统行政令是否违宪
- 司法裁决具有终局效力（Final and Binding）
- 最高法院独立于行政和立法，不受其干预

审查标准（映射为系统规则）：
1. 合宪性：是否符合系统基本原则（稳定性、公平性、效率）
2. 正当程序：法案是否经过完整的立法流程
3. 权力越界：某个分支是否越权行事
4. 先例遵循：是否与已有判例一致
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from utils import get_logger, generate_id, timestamp_now

logger = get_logger("JudicialReview")


class ReviewVerdict(Enum):
    CONSTITUTIONAL = "constitutional"
    UNCONSTITUTIONAL = "unconstitutional"
    PARTIALLY_UNCONSTITUTIONAL = "partially_unconstitutional"
    REMANDED = "remanded"
    DISMISSED = "dismissed"


class ReviewType(Enum):
    BILL_REVIEW = "bill_review"
    EXECUTIVE_ORDER_REVIEW = "executive_order_review"
    ACTION_REVIEW = "action_review"
    DISPUTE_RESOLUTION = "dispute_resolution"


@dataclass
class ReviewCase:
    case_id: str = field(default_factory=lambda: generate_id("case"))
    case_type: ReviewType = ReviewType.BILL_REVIEW
    subject_id: str = ""
    subject_type: str = ""
    plaintiff: str = ""
    description: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    verdict: ReviewVerdict | None = None
    opinion: str = ""
    dissent: str = ""
    precedent_cited: list[str] = field(default_factory=list)
    filed_at: float = field(default_factory=timestamp_now)
    decided_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type.value,
            "subject_id": self.subject_id,
            "subject_type": self.subject_type,
            "plaintiff": self.plaintiff,
            "description": self.description,
            "verdict": self.verdict.value if self.verdict else None,
            "opinion": self.opinion,
            "dissent": self.dissent,
            "filed_at": self.filed_at,
            "decided_at": self.decided_at,
        }


class ConstitutionalPrinciple:
    """系统宪法原则 — 不可违反的基本规则"""

    STABILITY = "stability"
    FAIRNESS = "fairness"
    EFFICIENCY = "efficiency"
    SEPARATION_OF_POWERS = "separation_of_powers"
    DUE_PROCESS = "due_process"
    CHECKS_AND_BALANCES = "checks_and_balances"

    PRINCIPLES = {
        STABILITY: "系统必须保持稳定运行，不可因单一法案导致系统崩溃",
        FAIRNESS: "资源分配和任务路由必须公平，不可过度偏向单一 Agent",
        EFFICIENCY: "法案不可导致系统效率显著下降（性能下降超过 50%）",
        SEPARATION_OF_POWERS: "三权分立不可被侵犯，任何分支不可越权行事",
        DUE_PROCESS: "法案必须经过完整的立法程序，不可跳过关键步骤",
        CHECKS_AND_BALANCES: "制衡机制不可被绕过或削弱",
    }


class JudicialReviewSystem:
    """
    司法审查系统 — 维护系统宪法秩序。

    职责：
    1. 审查法案合宪性
    2. 审查行政令合法性
    3. 解决分支间争议
    4. 建立判例体系
    """

    def __init__(self) -> None:
        self._cases: dict[str, ReviewCase] = {}
        self._precedents: list[ReviewCase] = []
        self._lock = asyncio.Lock()

    async def file_case(self, case_type: ReviewType, subject_id: str, subject_type: str,
                        plaintiff: str, description: str,
                        evidence: dict[str, Any] | None = None) -> ReviewCase:
        async with self._lock:
            case = ReviewCase(
                case_type=case_type,
                subject_id=subject_id,
                subject_type=subject_type,
                plaintiff=plaintiff,
                description=description,
                evidence=evidence or {},
            )
            self._cases[case.case_id] = case
            logger.info("Case filed: [%s] %s v. %s — %s",
                        case.case_id, plaintiff, subject_id, description)
            return case

    async def review_bill(self, bill_content: dict[str, Any],
                          bill_id: str) -> tuple[ReviewVerdict, str]:
        """
        审查法案合宪性。

        审查维度：
        1. 是否违反系统稳定性原则
        2. 是否导致资源分配不公
        3. 是否越权（如立法权试图直接执行任务）
        4. 是否经过正当程序
        """
        violations = []

        action = bill_content.get("action", "")
        if action in ("shutdown_system", "remove_all_agents", "disable_judicial"):
            violations.append(ConstitutionalPrinciple.STABILITY)

        if bill_content.get("bypass_routing", False):
            violations.append(ConstitutionalPrinciple.FAIRNESS)

        if bill_content.get("override_judicial", False):
            violations.append(ConstitutionalPrinciple.SEPARATION_OF_POWERS)

        if bill_content.get("skip_process", False):
            violations.append(ConstitutionalPrinciple.DUE_PROCESS)

        max_agents = bill_content.get("max_agents", 0)
        min_agents = bill_content.get("min_agents", 0)
        if max_agents > 0 and min_agents > max_agents:
            violations.append(ConstitutionalPrinciple.EFFICIENCY)

        if violations:
            reasons = [f"Violates {v}: {ConstitutionalPrinciple.PRINCIPLES[v]}" for v in violations]
            opinion = f"UNCONSTITUTIONAL — {'; '.join(reasons)}"
            return ReviewVerdict.UNCONSTITUTIONAL, opinion

        return ReviewVerdict.CONSTITUTIONAL, "Bill is constitutional and within proper authority."

    async def review_executive_order(self, order_content: dict[str, Any],
                                      order_id: str) -> tuple[ReviewVerdict, str]:
        """审查总统行政令"""
        violations = []

        if order_content.get("create_law", False):
            violations.append(ConstitutionalPrinciple.SEPARATION_OF_POWERS)

        if order_content.get("override_court", False):
            violations.append(ConstitutionalPrinciple.CHECKS_AND_BALANCES)

        scope = order_content.get("scope", "")
        if scope == "legislative":
            violations.append(ConstitutionalPrinciple.SEPARATION_OF_POWERS)

        if violations:
            reasons = [f"Violates {v}: {ConstitutionalPrinciple.PRINCIPLES[v]}" for v in violations]
            opinion = f"Executive order exceeds presidential authority — {'; '.join(reasons)}"
            return ReviewVerdict.UNCONSTITUTIONAL, opinion

        return ReviewVerdict.CONSTITUTIONAL, "Executive order is within presidential authority."

    async def decide_case(self, case_id: str, verdict: ReviewVerdict,
                          opinion: str, dissent: str = "") -> ReviewCase | None:
        async with self._lock:
            case = self._cases.get(case_id)
            if not case:
                return None

            case.verdict = verdict
            case.opinion = opinion
            case.dissent = dissent
            case.decided_at = timestamp_now()

            if verdict in (ReviewVerdict.CONSTITUTIONAL, ReviewVerdict.UNCONSTITUTIONAL):
                self._precedents.append(case)

            logger.info("Case decided: [%s] %s — %s", case_id, verdict.value, opinion[:100])
            return case

    async def find_precedent(self, case_type: ReviewType,
                             keywords: list[str] | None = None) -> list[ReviewCase]:
        async with self._lock:
            matches = [p for p in self._precedents if p.case_type == case_type]
            if keywords:
                matches = [p for p in matches
                           if any(kw in p.description or kw in p.opinion for kw in keywords)]
            return matches

    async def get_case(self, case_id: str) -> ReviewCase | None:
        async with self._lock:
            return self._cases.get(case_id)

    async def get_all_cases(self) -> list[ReviewCase]:
        async with self._lock:
            return list(self._cases.values())

    async def status_summary(self) -> dict[str, Any]:
        async with self._lock:
            decided = [c for c in self._cases.values() if c.verdict]
            unconstitutional = [c for c in decided if c.verdict == ReviewVerdict.UNCONSTITUTIONAL]
            return {
                "total_cases": len(self._cases),
                "decided": len(decided),
                "pending": len(self._cases) - len(decided),
                "unconstitutional_rulings": len(unconstitutional),
                "precedents": len(self._precedents),
                "recent_cases": [c.to_dict() for c in list(self._cases.values())[-5:]],
            }
