"""
美国三权分立 Agent System — 主入口。

系统架构映射美国宪法（U.S. Constitution）的三权分立制度：

┌──────────────────────────────────────────────────────────────┐
│                    WE THE PEOPLE (用户/前端)                  │
│                     HTTP API → Gateway                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  LEGISLATIVE  │  │  EXECUTIVE   │  │    JUDICIAL      │   │
│  │  (立法权)     │  │  (行政权)    │  │    (司法权)      │   │
│  │              │  │              │  │                  │   │
│  │  Senate      │  │  President   │  │  Supreme Court   │   │
│  │  (参议院)    │  │  (总统)      │  │  (最高法院)      │   │
│  │              │  │      ↓       │  │                  │   │
│  │  House       │  │  Workers     │  │  Judicial Review │   │
│  │  (众议院)    │  │  (内阁/执行) │  │  (违宪审查)      │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                                                              │
│  Checks & Balances (制衡机制):                               │
│  - 国会立法 → 总统签署/否决 → 最高法院违宪审查               │
│  - 总统行政令 → 最高法院审查                                  │
│  - 众议院弹劾 → 参议院审判                                    │
│  - 总统否决 → 国会 2/3 多数推翻                               │
│  - 参议院确认总统任命                                         │
└──────────────────────────────────────────────────────────────┘

启动流程：
1. 加载配置（含 LLM 配置）
2. 初始化 Gateway（宪法框架）
3. 注册所有 Agent 类型
4. 建立三个分支：
   - Executive: President + 3 Workers（内阁部门）
   - Legislative: Senate + House
   - Judicial: Supreme Court
5. 启动 HTTP API 服务

前端 API:
  POST http://127.0.0.1:18790/api/chat      — 对话
  POST http://127.0.0.1:18790/api/task       — 提交任务（同步）
  POST http://127.0.0.1:18790/api/task/async — 提交任务（异步）
  GET  http://127.0.0.1:18790/api/status     — 系统状态（含三权分立信息）
  GET  http://127.0.0.1:18790/api/agents     — Agent 列表（按分支分组）
  GET  http://127.0.0.1:18790/api/health     — 健康检查
"""

from __future__ import annotations

import asyncio
import signal
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import SystemConfig
from core.llm_client import LLMClient
from gateway import Gateway
from agents import PresidentAgent, SenateAgent, HouseAgent, SupremeCourtAgent, WorkerAgent
from skills import (
    SearchSkill, AnalyzeSkill, TransformSkill,
    ChatSkill, CodeGenSkill, AnalysisSkill, SummarySkill, PlanSkill,
    ExecutiveDecisionSkill,
    DiplomacySkill, TacticalCodeSkill, FiscalAnalysisSkill,
    SenateDeliberationSkill, HouseDraftingSkill,
    ConstitutionalReviewSkill, JudicialOpinionSkill,
)
from utils import get_logger

logger = get_logger("Main")


def build_cabinet_skills(llm: LLMClient) -> dict[str, list]:
    """
    构建内阁（Worker）技能集 — 每个部门配备通用技能 + 部门专属技能。

    映射美国内阁部门：
    - State Department (国务院): chat, search, summary + diplomacy (外交沟通)
    - Defense Department (国防部): chat, codegen, transform + tactical_code (安全代码)
    - Treasury Department (财政部): chat, analysis, analyze, plan + fiscal_analysis (财务分析)
    """
    chat = ChatSkill(llm)
    codegen = CodeGenSkill(llm)
    analysis = AnalysisSkill(llm)
    summary = SummarySkill(llm)
    plan = PlanSkill(llm)
    search = SearchSkill()
    analyze = AnalyzeSkill()
    transform = TransformSkill()

    diplomacy = DiplomacySkill(llm)
    tactical_code = TacticalCodeSkill(llm)
    fiscal_analysis = FiscalAnalysisSkill(llm)

    return {
        "state_dept": [chat, search, summary, diplomacy],
        "defense_dept": [chat, codegen, transform, tactical_code],
        "treasury_dept": [chat, analysis, analyze, plan, fiscal_analysis],
    }


def build_branch_skills(llm: LLMClient) -> dict[str, list]:
    """
    构建三权分立分支的专属技能。

    - President (总统): executive_decision (行政决策)
    - Senate (参议院): senate_deliberation (深度审议)
    - House (众议院): house_drafting (立法起草)
    - Supreme Court (最高法院): constitutional_review (违宪审查) + judicial_opinion (司法意见)
    """
    return {
        "president": [ExecutiveDecisionSkill(llm)],
        "senate": [SenateDeliberationSkill(llm)],
        "house": [HouseDraftingSkill(llm)],
        "supreme_court": [ConstitutionalReviewSkill(llm), JudicialOpinionSkill(llm)],
    }


async def main() -> None:
    config = SystemConfig()
    config.log_level = "INFO"
    config.self_org.min_agents = 7
    config.self_org.leader_election_interval = 10.0
    config.self_org.health_check_interval = 8.0
    config.gateway.host = "0.0.0.0"
    config.gateway.port = 18790

    gw = Gateway(config)

    gw.register_agent_type("president", PresidentAgent)
    gw.register_agent_type("senate", SenateAgent)
    gw.register_agent_type("house", HouseAgent)
    gw.register_agent_type("supreme_court", SupremeCourtAgent)
    gw.register_agent_type("worker", WorkerAgent)

    await gw.start()

    logger.info("Establishing the three branches of government...")

    cabinet_skills = build_cabinet_skills(gw.llm_client)
    branch_skills = build_branch_skills(gw.llm_client)

    logger.info("─── EXECUTIVE BRANCH (行政权) ───")
    president = await gw.spawn_agent("president", skills=branch_skills["president"])
    logger.info("  President: %s  [skills: %s]",
                president.agent_id, [s.name for s in branch_skills["president"]])

    state_dept = await gw.spawn_agent("worker", skills=cabinet_skills["state_dept"],
                                       department="state")
    defense_dept = await gw.spawn_agent("worker", skills=cabinet_skills["defense_dept"],
                                         department="defense")
    treasury_dept = await gw.spawn_agent("worker", skills=cabinet_skills["treasury_dept"],
                                          department="treasury")
    logger.info("  Cabinet:")
    logger.info("    State Dept  =%s  [skills: chat, search, summary, diplomacy]", state_dept.agent_id)
    logger.info("    Defense Dept=%s  [skills: chat, codegen, transform, tactical_code]", defense_dept.agent_id)
    logger.info("    Treasury    =%s  [skills: chat, analysis, analyze, plan, fiscal_analysis]", treasury_dept.agent_id)

    logger.info("─── LEGISLATIVE BRANCH (立法权) ───")
    senate = await gw.spawn_agent("senate", skills=branch_skills["senate"])
    house = await gw.spawn_agent("house", skills=branch_skills["house"])
    logger.info("  Senate: %s  [skills: %s]",
                senate.agent_id, [s.name for s in branch_skills["senate"]])
    logger.info("  House:  %s  [skills: %s]",
                house.agent_id, [s.name for s in branch_skills["house"]])

    logger.info("─── JUDICIAL BRANCH (司法权) ───")
    court = await gw.spawn_agent("supreme_court", skills=branch_skills["supreme_court"])
    logger.info("  Supreme Court: %s  [skills: %s]",
                court.agent_id, [s.name for s in branch_skills["supreme_court"]])

    logger.info("=" * 60)
    logger.info("  🇺🇸 USA Three-Branch Agent System — ACTIVE")
    logger.info("  Constitution: Separation of Powers")
    logger.info("  Total agents: %d", gw.registry.count)
    logger.info("")
    logger.info("  Government Structure:")
    logger.info("    Executive  : President + 3 Cabinet Departments")
    logger.info("    Legislative: Senate + House of Representatives")
    logger.info("    Judicial   : Supreme Court")
    logger.info("")
    logger.info("  API endpoint: http://0.0.0.0:%d", config.gateway.port)
    logger.info("  Available endpoints:")
    logger.info("    POST /api/chat      — LLM 对话")
    logger.info("    POST /api/task      — 提交任务（同步）")
    logger.info("    POST /api/task/async — 提交任务（异步）")
    logger.info("    GET  /api/status    — 系统状态（含三权分立信息）")
    logger.info("    GET  /api/agents    — Agent 列表")
    logger.info("    GET  /api/health    — 健康检查")
    logger.info("")
    logger.info("  Example:")
    logger.info('    curl -X POST http://localhost:18790/api/chat \\')
    logger.info('      -H "Content-Type: application/json" \\')
    logger.info('      -d \'{"message": "帮我写一个Python快速排序"}\'')
    logger.info("=" * 60)

    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Received shutdown signal — dissolving the Republic...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        await gw.stop()
        logger.info("System shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
