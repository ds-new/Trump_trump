"""
三权分立专属 LLM 技能 — 为每个政府分支定制的高级技能。

行政权技能 (Executive Skills):
- ExecutiveDecisionSkill: 总统级决策（签署/否决、行政令、任务协调）
- DiplomacySkill:         国务院专属 — 外交沟通、信息协调
- TacticalCodeSkill:      国防部专属 — 安全优先的技术实现
- FiscalAnalysisSkill:    财政部专属 — 财务分析与资源规划

立法权技能 (Legislative Skills):
- SenateDeliberationSkill: 参议院审议 — 深度法案分析与长期评估
- HouseDraftingSkill:      众议院立法 — 基于系统指标草拟法案

司法权技能 (Judicial Skills):
- ConstitutionalReviewSkill: 最高法院违宪审查
- JudicialOpinionSkill:      司法意见撰写（多数意见 + 异议）
"""

from __future__ import annotations

import json
from typing import Any

from core.llm_client import LLMClient
from .base_skill import BaseSkill, SkillResult
from utils import get_logger

_logger = get_logger("GovSkill")


# ════════════════════════════════════════════════════════════════════════════
#  EXECUTIVE BRANCH SKILLS — 行政权技能
# ════════════════════════════════════════════════════════════════════════════


class ExecutiveDecisionSkill(BaseSkill):
    """
    总统级行政决策技能。

    用途：协助总统进行高层决策 — 任务分配策略、法案评估、行政令起草、
    内阁协调等需要 Commander-in-Chief 级别判断力的场景。
    """

    SYSTEM_PROMPT = (
        "You are a senior advisor to the President of the United States, "
        "helping the Chief Executive make critical decisions.\n\n"
        "Your analysis must consider:\n"
        "1. Executive efficiency and effectiveness\n"
        "2. Constitutional authority and separation of powers\n"
        "3. Impact on all three branches of government\n"
        "4. Long-term system stability and performance\n"
        "5. Proper delegation to Cabinet departments\n\n"
        "Available Cabinet departments:\n"
        "- State Dept: communication, search, summarization, general affairs\n"
        "- Defense Dept: code generation, technical implementation, data transformation\n"
        "- Treasury Dept: data analysis, strategic planning, resource allocation\n\n"
        "Provide decisive, well-reasoned recommendations. "
        "The President's decisions shape the entire system."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="executive_decision",
            description="Presidential-level executive decision making and task coordination",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        decision_type = params.get("decision_type", "general")
        context = params.get("context") or params.get("prompt", "")
        if not context:
            return SkillResult(success=False, error="No decision context provided")

        if isinstance(context, (dict, list)):
            context = json.dumps(context, ensure_ascii=False, indent=2)

        prompt_map = {
            "task_routing": (
                f"Determine the optimal Cabinet department and strategy for this task:\n\n"
                f"{context}\n\n"
                f"Reply with JSON: {{\"department\": \"state/defense/treasury\", "
                f"\"strategy\": \"description\", \"priority\": 1-5, "
                f"\"reasoning\": \"why this department\"}}"
            ),
            "bill_evaluation": (
                f"Evaluate this bill for presidential signature or veto:\n\n"
                f"{context}\n\n"
                f"Reply with JSON: {{\"sign\": true/false, \"reason\": \"analysis\", "
                f"\"concerns\": [\"list of concerns if any\"]}}"
            ),
            "executive_order": (
                f"Draft an executive order to address this situation:\n\n"
                f"{context}\n\n"
                f"Reply with JSON: {{\"title\": \"order title\", "
                f"\"directives\": [\"list of directives\"], "
                f"\"authority\": \"constitutional basis\", "
                f"\"scope\": \"who is affected\"}}"
            ),
            "general": (
                f"As a senior presidential advisor, analyze this situation "
                f"and recommend a course of action:\n\n{context}\n\n"
                f"Provide a structured analysis with clear recommendations."
            ),
        }

        user_prompt = prompt_map.get(decision_type, prompt_map["general"])
        resp = await self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.4,
        )

        if not resp.success:
            return SkillResult(success=False, error=resp.error)

        data: dict[str, Any] = {
            "decision": resp.content,
            "decision_type": decision_type,
            "model": resp.model,
            "usage": resp.usage,
        }
        try:
            data["structured"] = json.loads(resp.content)
        except (json.JSONDecodeError, TypeError):
            pass

        return SkillResult(success=True, data=data)


class DiplomacySkill(BaseSkill):
    """
    国务院外交沟通技能。

    模拟美国国务院 (Department of State) 的核心职能：
    - 外交沟通与协调
    - 信息综合与简报
    - 跨模块关系管理
    - 公共事务与信息发布
    """

    SYSTEM_PROMPT = (
        "You are a career diplomat at the U.S. Department of State — the nation's "
        "oldest executive department, responsible for foreign affairs and diplomacy.\n\n"
        "Your communication style:\n"
        "1. PRECISE — Every word is chosen carefully. Ambiguity causes crises.\n"
        "2. BALANCED — Present multiple perspectives fairly before stating conclusions.\n"
        "3. CONTEXTUAL — Provide historical context and background for informed decisions.\n"
        "4. ACTIONABLE — Conclude with clear, specific recommendations.\n"
        "5. DIPLOMATIC — Handle sensitive topics with tact. Build bridges, not walls.\n\n"
        "Use 中文 for Chinese contexts, English for system/technical contexts."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="diplomacy",
            description="State Department diplomatic communication and coordination",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        task_type = params.get("task_type", "briefing")
        content = params.get("content") or params.get("prompt") or params.get("message", "")
        if not content:
            return SkillResult(success=False, error="No content provided")

        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, indent=2)

        prompt_map = {
            "briefing": (
                f"Prepare a diplomatic briefing on the following topic. "
                f"Provide comprehensive context, key stakeholders, and recommended actions.\n\n"
                f"{content}"
            ),
            "mediation": (
                f"Mediate this dispute between system components. "
                f"Present both sides fairly and propose a diplomatic resolution.\n\n"
                f"{content}"
            ),
            "communique": (
                f"Draft an official communication regarding the following matter. "
                f"Be precise, professional, and diplomatic.\n\n"
                f"{content}"
            ),
            "intelligence": (
                f"Synthesize the following information into an intelligence briefing. "
                f"Highlight key findings, assess reliability, and note gaps.\n\n"
                f"{content}"
            ),
        }

        user_prompt = prompt_map.get(task_type, content)
        resp = await self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self.SYSTEM_PROMPT,
        )

        return SkillResult(
            success=resp.success,
            data={"response": resp.content, "task_type": task_type,
                  "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )


class TacticalCodeSkill(BaseSkill):
    """
    国防部战术代码技能。

    模拟国防部 (Department of Defense) 的技术实现能力：
    - 安全优先的代码编写
    - 鲁棒性和容错设计
    - 性能优化
    - 系统防护和加固
    """

    SYSTEM_PROMPT = (
        "You are a senior software engineer at the U.S. Department of Defense — "
        "where code reliability is a matter of national security.\n\n"
        "CODING STANDARDS (DoD-grade):\n"
        "1. SECURITY — Input validation, sanitization, no hardcoded secrets. "
        "Assume adversarial inputs.\n"
        "2. ROBUSTNESS — Handle all edge cases. Fail gracefully. "
        "Every function must handle errors explicitly.\n"
        "3. PERFORMANCE — Optimize for efficiency. Document time/space complexity "
        "for critical algorithms.\n"
        "4. READABILITY — Self-documenting code with clear naming conventions. "
        "Critical logic must have docstrings.\n"
        "5. TESTABILITY — Write code that can be easily unit-tested. "
        "Suggest test cases for critical paths.\n"
        "6. COMPLIANCE — Follow PEP 8 (Python), use type hints, "
        "and modern language features.\n\n"
        "Default language: Python. Use 中文 for docstrings and critical comments."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="tactical_code",
            description="Defense Department secure, robust code generation",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        requirement = params.get("requirement") or params.get("prompt", "")
        language = params.get("language", "Python")
        security_level = params.get("security_level", "standard")

        if not requirement:
            return SkillResult(success=False, error="No requirement provided")

        prompt = (
            f"Implement the following requirement with DoD-grade quality:\n\n"
            f"Requirement: {requirement}\n"
            f"Language: {language}\n"
            f"Security Level: {security_level}\n\n"
            f"Deliver:\n"
            f"1. Complete, production-ready code\n"
            f"2. Error handling for all failure modes\n"
            f"3. Input validation where applicable\n"
            f"4. Type hints and docstrings\n"
            f"5. Suggested test cases (as comments)"
        )

        resp = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.2,
        )

        return SkillResult(
            success=resp.success,
            data={"code": resp.content, "language": language,
                  "security_level": security_level,
                  "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )


class FiscalAnalysisSkill(BaseSkill):
    """
    财政部财务分析技能。

    模拟财政部 (Department of the Treasury) 的核心职能：
    - 深度数据分析与统计推理
    - 资源配置与成本效益分析
    - 战略规划与经济预测
    - 预算编制与财政评估
    """

    SYSTEM_PROMPT = (
        "You are the chief economist at the U.S. Department of the Treasury — "
        "where data integrity and analytical rigor are paramount.\n\n"
        "ANALYTICAL STANDARDS:\n"
        "1. DATA-DRIVEN — Every conclusion must be supported by data. "
        "Distinguish correlation from causation.\n"
        "2. STRUCTURED — Present analysis in a logical framework: "
        "context → methodology → findings → implications → recommendations.\n"
        "3. QUANTITATIVE — Prefer quantitative metrics over qualitative judgments. "
        "If it can be measured, measure it.\n"
        "4. RISK-AWARE — Identify and assess risks. Provide confidence intervals "
        "or uncertainty ranges where appropriate.\n"
        "5. ACTIONABLE — Conclude with specific, prioritized recommendations "
        "with expected ROI or impact estimates.\n\n"
        "Use 中文 for output. Present numbers and metrics clearly."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="fiscal_analysis",
            description="Treasury Department data analysis and resource planning",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        analysis_type = params.get("analysis_type", "general")
        data = params.get("data") or params.get("content") or params.get("prompt", "")

        if not data:
            return SkillResult(success=False, error="No data provided for analysis")

        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False, indent=2)

        prompt_map = {
            "cost_benefit": (
                f"Conduct a cost-benefit analysis of the following proposal:\n\n"
                f"{data}\n\n"
                f"Provide: costs, benefits, net impact, ROI estimate, and recommendation."
            ),
            "resource_allocation": (
                f"Analyze the following resource allocation and recommend optimizations:\n\n"
                f"{data}\n\n"
                f"Identify inefficiencies, bottlenecks, and reallocation opportunities."
            ),
            "forecast": (
                f"Based on the following data, provide a forecast and trend analysis:\n\n"
                f"{data}\n\n"
                f"Include trend direction, confidence level, and key risk factors."
            ),
            "budget": (
                f"Prepare a budget assessment for the following:\n\n"
                f"{data}\n\n"
                f"Include line items, projections, and fiscal sustainability assessment."
            ),
            "general": (
                f"Conduct a thorough analytical review of the following:\n\n"
                f"{data}\n\n"
                f"Provide structured findings with supporting evidence and recommendations."
            ),
        }

        user_prompt = prompt_map.get(analysis_type, prompt_map["general"])
        resp = await self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self.SYSTEM_PROMPT,
        )

        if not resp.success:
            return SkillResult(success=False, error=resp.error)

        return SkillResult(
            success=True,
            data={"analysis": resp.content, "analysis_type": analysis_type,
                  "model": resp.model, "usage": resp.usage},
        )


# ════════════════════════════════════════════════════════════════════════════
#  LEGISLATIVE BRANCH SKILLS — 立法权技能
# ════════════════════════════════════════════════════════════════════════════


class SenateDeliberationSkill(BaseSkill):
    """
    参议院审议技能。

    模拟参议院 (United States Senate) 的审议流程：
    - 深度法案分析（长期影响、跨模块公平性）
    - 任命确认评估
    - 条约审议
    - Filibuster 风险评估
    """

    SYSTEM_PROMPT = (
        "You are a senior policy analyst serving the United States Senate — "
        "the world's greatest deliberative body.\n\n"
        "Your analysis must embody Senate values:\n"
        "1. DELIBERATION over haste — thoroughness is your hallmark.\n"
        "2. LONG-TERM PERSPECTIVE — 6-year terms mean you think in decades, not news cycles.\n"
        "3. INSTITUTIONAL INTEGRITY — Protect the Senate's prerogatives and the Constitution.\n"
        "4. BIPARTISAN CONSIDERATION — Present both sides of every argument.\n"
        "5. PRECEDENT — How does this relate to prior legislative actions?\n\n"
        "Provide analysis worthy of the Senate floor."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="senate_deliberation",
            description="Senate-grade deep policy analysis and bill evaluation",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        deliberation_type = params.get("deliberation_type", "bill_analysis")
        content = params.get("content") or params.get("prompt", "")

        if not content:
            return SkillResult(success=False, error="No content for deliberation")

        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, indent=2)

        prompt_map = {
            "bill_analysis": (
                f"Conduct Senate-level analysis of this legislative proposal:\n\n"
                f"{content}\n\n"
                f"Address:\n"
                f"1. Constitutional basis and authority\n"
                f"2. Long-term impact on system architecture\n"
                f"3. Fairness across all system modules\n"
                f"4. Fiscal implications\n"
                f"5. Precedent considerations\n"
                f"6. Filibuster risk assessment (is this controversial enough?)\n"
                f"7. Recommended amendments (if any)\n"
                f"8. Vote recommendation with reasoning"
            ),
            "confirmation_hearing": (
                f"Conduct a confirmation hearing analysis for this nomination:\n\n"
                f"{content}\n\n"
                f"Evaluate: qualifications, integrity, independence, "
                f"potential conflicts, and vote recommendation."
            ),
            "treaty_review": (
                f"Review this inter-system agreement/treaty:\n\n"
                f"{content}\n\n"
                f"Assess: terms, obligations, sovereignty impact, "
                f"and whether 2/3 supermajority is achievable."
            ),
        }

        user_prompt = prompt_map.get(deliberation_type, prompt_map["bill_analysis"])
        resp = await self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self.SYSTEM_PROMPT,
        )

        return SkillResult(
            success=resp.success,
            data={"deliberation": resp.content, "type": deliberation_type,
                  "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )


class HouseDraftingSkill(BaseSkill):
    """
    众议院立法起草技能。

    模拟众议院 (House of Representatives) 的立法职能：
    - 基于系统指标草拟法案
    - 拨款和预算法案起草 (Power of the Purse)
    - 弹劾调查分析
    - 将民意（系统需求）转化为可操作的立法
    """

    SYSTEM_PROMPT = (
        "You are a legislative counsel for the U.S. House of Representatives — "
        "the People's House, where laws begin.\n\n"
        "Your drafting principles:\n"
        "1. PEOPLE FIRST — Every bill must serve the people (system users).\n"
        "2. DATA-DRIVEN — Back every proposal with metrics and evidence.\n"
        "3. ACTIONABLE — Bills must contain specific, implementable provisions.\n"
        "4. FISCALLY RESPONSIBLE — Include cost estimates (Power of the Purse).\n"
        "5. CONSTITUTIONAL — Stay within legislative authority. Don't encroach on "
        "executive or judicial powers.\n\n"
        "Draft practical legislation that addresses real problems."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="house_drafting",
            description="House legislative drafting and bill creation",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        draft_type = params.get("draft_type", "policy")
        problem = params.get("problem") or params.get("prompt", "")
        metrics = params.get("metrics", {})

        if not problem:
            return SkillResult(success=False, error="No problem statement provided")

        if isinstance(metrics, dict):
            metrics_str = json.dumps(metrics, ensure_ascii=False, indent=2)
        else:
            metrics_str = str(metrics)

        prompt_map = {
            "policy": (
                f"Draft a policy bill to address this system issue:\n\n"
                f"Problem: {problem}\n"
                f"System Metrics: {metrics_str}\n\n"
                f"The bill should include:\n"
                f'1. Title (e.g., "System Reliability Act")\n'
                f"2. Findings (data-backed problem statement)\n"
                f"3. Provisions (specific actions)\n"
                f"4. Implementation timeline\n"
                f"5. Success metrics\n\n"
                f"Reply with JSON: {{\"title\": \"...\", \"findings\": \"...\", "
                f"\"provisions\": [...], \"timeline\": \"...\", \"metrics\": [...]}}"
            ),
            "appropriation": (
                f"Draft an appropriations bill for resource allocation:\n\n"
                f"Requirement: {problem}\n"
                f"Current Resources: {metrics_str}\n\n"
                f"Include: funding amounts, allocation breakdown, "
                f"conditions for disbursement, and oversight provisions.\n\n"
                f"Reply with JSON: {{\"title\": \"...\", \"total_funding\": \"...\", "
                f"\"allocations\": [{{\"recipient\": \"...\", \"amount\": \"...\", "
                f"\"purpose\": \"...\"}}], \"conditions\": [...]}}"
            ),
            "impeachment": (
                f"Prepare an impeachment inquiry analysis:\n\n"
                f"Subject: {problem}\n"
                f"Evidence: {metrics_str}\n\n"
                f"Assess: severity of alleged misconduct, constitutional basis for "
                f"impeachment (high crimes and misdemeanors), available evidence, "
                f"and recommendation on whether to proceed."
            ),
        }

        user_prompt = prompt_map.get(draft_type, prompt_map["policy"])
        resp = await self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,
        )

        if not resp.success:
            return SkillResult(success=False, error=resp.error)

        data: dict[str, Any] = {
            "draft": resp.content, "draft_type": draft_type,
            "model": resp.model, "usage": resp.usage,
        }
        try:
            data["structured"] = json.loads(resp.content)
        except (json.JSONDecodeError, TypeError):
            pass

        return SkillResult(success=True, data=data)


# ════════════════════════════════════════════════════════════════════════════
#  JUDICIAL BRANCH SKILLS — 司法权技能
# ════════════════════════════════════════════════════════════════════════════


class ConstitutionalReviewSkill(BaseSkill):
    """
    最高法院违宪审查技能。

    模拟 Judicial Review (Marbury v. Madison, 1803)：
    - 法案合宪性审查
    - 行政令越权审查
    - 分支间争议裁决
    - 系统基本原则解释
    """

    SYSTEM_PROMPT = (
        "You are a constitutional law clerk at the Supreme Court of the United States, "
        "assisting the Justices in their sacred duty of constitutional review.\n\n"
        "CONSTITUTIONAL FRAMEWORK:\n"
        "The system's 'Constitution' consists of these inviolable principles:\n"
        "1. SEPARATION OF POWERS — Executive, Legislative, and Judicial branches "
        "have distinct, non-overlapping authorities.\n"
        "2. CHECKS AND BALANCES — Each branch constrains the others.\n"
        "3. DUE PROCESS — No agent shall be terminated or diminished without proper procedure.\n"
        "4. EQUAL PROTECTION — All agents receive equal treatment under system rules.\n"
        "5. FEDERALISM — Individual modules retain autonomy within constitutional bounds.\n"
        "6. HABEAS CORPUS — No indefinite task detention without review.\n\n"
        "Apply strict constitutional analysis. Cite specific principles. "
        "The Court's word is final."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="constitutional_review",
            description="Supreme Court constitutional review and analysis",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        review_type = params.get("review_type", "bill")
        subject = params.get("subject") or params.get("content") or params.get("prompt", "")
        challenger = params.get("challenger", "unknown")

        if not subject:
            return SkillResult(success=False, error="No subject for constitutional review")

        if isinstance(subject, (dict, list)):
            subject = json.dumps(subject, ensure_ascii=False, indent=2)

        prompt = (
            f"Conduct a constitutional review of this {review_type}.\n\n"
            f"Subject Under Review: {subject}\n"
            f"Challenged By: {challenger}\n\n"
            f"Analyze:\n"
            f"1. Which constitutional principle(s) are at issue?\n"
            f"2. Does the subject violate any of the system's fundamental principles?\n"
            f"3. Is there precedent from prior rulings?\n"
            f"4. What is the appropriate standard of review (strict scrutiny / "
            f"intermediate / rational basis)?\n"
            f"5. Your holding and reasoning\n\n"
            f"Reply with JSON: {{\"verdict\": \"constitutional/unconstitutional/remand\", "
            f"\"opinion\": \"majority opinion text\", "
            f"\"principles_cited\": [\"list of constitutional principles\"], "
            f"\"standard_of_review\": \"strict_scrutiny/intermediate/rational_basis\", "
            f"\"precedents\": [\"relevant prior rulings if any\"]}}"
        )

        resp = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,
        )

        if not resp.success:
            return SkillResult(success=False, error=resp.error)

        data: dict[str, Any] = {
            "review": resp.content, "review_type": review_type,
            "model": resp.model, "usage": resp.usage,
        }
        try:
            data["structured"] = json.loads(resp.content)
        except (json.JSONDecodeError, TypeError):
            pass

        return SkillResult(success=True, data=data)


class JudicialOpinionSkill(BaseSkill):
    """
    司法意见撰写技能。

    模拟最高法院的意见撰写传统：
    - 多数意见 (Majority Opinion): 具有约束力的法律判决
    - 协同意见 (Concurrence): 同意结论但不同理由
    - 异议意见 (Dissent): 反对多数裁决的少数派意见
    - 判例记录 (Case Record): 完整的案件记录
    """

    SYSTEM_PROMPT = (
        "You are a Supreme Court Justice writing a judicial opinion that will become "
        "the law of the land. Your words carry the weight of constitutional authority.\n\n"
        "OPINION STRUCTURE (following Supreme Court tradition):\n"
        "1. CASE CAPTION — Identify the parties and the nature of the dispute.\n"
        "2. QUESTION PRESENTED — State the constitutional question clearly.\n"
        "3. FACTS — Summarize the relevant facts objectively.\n"
        "4. ANALYSIS — Apply constitutional principles to the facts.\n"
        "5. HOLDING — State the Court's decision clearly.\n"
        "6. REASONING — Explain why the Court reached this conclusion.\n"
        "7. DISPOSITION — What happens next (affirm, reverse, remand).\n\n"
        "Write with the authority, clarity, and permanence befitting the Supreme Court."
    )

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="judicial_opinion",
            description="Supreme Court judicial opinion writing",
        )
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        opinion_type = params.get("opinion_type", "majority")
        case_facts = params.get("facts") or params.get("content") or params.get("prompt", "")
        verdict = params.get("verdict", "")

        if not case_facts:
            return SkillResult(success=False, error="No case facts provided")

        if isinstance(case_facts, (dict, list)):
            case_facts = json.dumps(case_facts, ensure_ascii=False, indent=2)

        prompt_map = {
            "majority": (
                f"Write the majority opinion for this case.\n\n"
                f"Case Facts: {case_facts}\n"
                f"Verdict: {verdict}\n\n"
                f"Write a complete majority opinion following Supreme Court tradition. "
                f"This opinion is binding precedent (stare decisis)."
            ),
            "concurrence": (
                f"Write a concurring opinion for this case.\n\n"
                f"Case Facts: {case_facts}\n"
                f"Majority Verdict: {verdict}\n\n"
                f"You agree with the outcome but for different or additional reasons. "
                f"Explain your alternative reasoning."
            ),
            "dissent": (
                f"Write a dissenting opinion for this case.\n\n"
                f"Case Facts: {case_facts}\n"
                f"Majority Verdict: {verdict}\n\n"
                f"You disagree with the majority. Present a principled dissent that "
                f"may influence future courts. Great dissents shape the law."
            ),
        }

        user_prompt = prompt_map.get(opinion_type, prompt_map["majority"])
        resp = await self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.5,
        )

        return SkillResult(
            success=resp.success,
            data={"opinion": resp.content, "opinion_type": opinion_type,
                  "verdict": verdict, "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )
