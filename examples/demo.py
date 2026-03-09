"""
自组织 Agent System — 高级演示。

展示自组织特性：
1. 涌现（Emergence）：观察领导者从群体中自然产生
2. 信息素协调（Stigmergy）：观察信息素如何引导任务分配
3. 反馈循环（Feedback）：观察系统如何根据成功/失败调整行为
4. 自适应（Adaptation）：观察系统如何自动扩缩容
5. 自愈（Self-healing）：观察系统如何处理 Agent 失效
"""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import SystemConfig
from gateway import Gateway
from agents import CoordinatorAgent, WorkerAgent, MonitorAgent
from skills import SearchSkill, AnalyzeSkill, TransformSkill
from utils import get_logger

logger = get_logger("Demo")


async def demo_emergence(gw: Gateway) -> None:
    """演示 1：领导者涌现"""
    logger.info("\n" + "=" * 50)
    logger.info("  Demo 1: Emergence — Leader Election")
    logger.info("=" * 50)

    leader = await gw.environment.read_blackboard("current_leader")
    logger.info("Initial leader: %s", leader or "None (not yet elected)")

    await asyncio.sleep(12)

    leader = await gw.environment.read_blackboard("current_leader")
    logger.info("Emerged leader: %s", leader)

    patterns = await gw.emergence.detect_patterns()
    for p in patterns:
        logger.info("  Pattern detected: %s", p)


async def demo_stigmergy(gw: Gateway) -> None:
    """演示 2：信息素协调"""
    logger.info("\n" + "=" * 50)
    logger.info("  Demo 2: Stigmergy — Pheromone Coordination")
    logger.info("=" * 50)

    for i in range(5):
        await gw.submit_task({
            "task_type": "search",
            "required_skill": "search",
            "data": {"query": "emergence"},
        })
        await asyncio.sleep(0.3)

    await asyncio.sleep(3)

    trails = await gw.environment.read_pheromones("task:search", "success_path")
    logger.info("Search task pheromone trails: %d", len(trails))
    for t in trails:
        logger.info("  Trail: depositor=%s, intensity=%.3f", t.depositor, t.intensity)

    best = await gw.stigmergy.find_best_agent_for_task("search")
    logger.info("Best agent for 'search' tasks (by stigmergy): %s", best)


async def demo_feedback(gw: Gateway) -> None:
    """演示 3：反馈循环"""
    logger.info("\n" + "=" * 50)
    logger.info("  Demo 3: Feedback Loop — Performance Tracking")
    logger.info("=" * 50)

    for i in range(8):
        await gw.submit_task({
            "task_type": "analyze",
            "required_skill": "analyze",
            "data": {"data": list(range(i, i + 10))},
        })
        await asyncio.sleep(0.3)

    await asyncio.sleep(5)

    global_stats = await gw.feedback.get_global_stats()
    logger.info("Global feedback stats: %s", global_stats)

    for agent in gw.registry.all_agents:
        stats = await gw.feedback.get_agent_stats(agent.agent_id)
        if stats["total"] > 0:
            logger.info("  Agent %s: %s", agent.agent_id, stats)


async def demo_adaptation(gw: Gateway) -> None:
    """演示 4：自适应扩缩容"""
    logger.info("\n" + "=" * 50)
    logger.info("  Demo 4: Adaptation — Auto-scaling")
    logger.info("=" * 50)

    logger.info("Current agent count: %d", gw.registry.count)

    logger.info("Flooding system with tasks to trigger adaptation...")
    for i in range(15):
        await gw.submit_task({
            "task_type": "transform",
            "required_skill": "transform",
            "data": {"data": f"task-{i}", "operation": "uppercase"},
        })

    await asyncio.sleep(3)

    action = await gw.adaptation.evaluate()
    logger.info("Adaptation evaluation: %s", action)
    logger.info("Agent count after adaptation: %d", gw.registry.count)


async def run_demo() -> None:
    config = SystemConfig()
    config.self_org.leader_election_interval = 5.0
    config.self_org.health_check_interval = 3.0

    gw = Gateway(config)

    gw.register_agent_type("coordinator", CoordinatorAgent)
    gw.register_agent_type("worker", WorkerAgent)
    gw.register_agent_type("monitor", MonitorAgent)

    await gw.start()

    await gw.spawn_agent("coordinator")
    await gw.spawn_agent("monitor")

    search_skill = SearchSkill()
    analyze_skill = AnalyzeSkill()
    transform_skill = TransformSkill()

    await gw.spawn_agent("worker", skills=[search_skill, analyze_skill])
    await gw.spawn_agent("worker", skills=[analyze_skill, transform_skill])
    await gw.spawn_agent("worker", skills=[search_skill, transform_skill])

    logger.info("System ready with %d agents", gw.registry.count)

    try:
        await demo_emergence(gw)
        await demo_stigmergy(gw)
        await demo_feedback(gw)
        await demo_adaptation(gw)

        logger.info("\n" + "=" * 50)
        logger.info("  Final System Status")
        logger.info("=" * 50)
        status = await gw.status()
        logger.info("Agents: %d", status["agents"]["total"])
        logger.info("Leader: %s", status["self_organization"]["leader"])
        logger.info("Pheromones: %d", status["self_organization"]["pheromone_count"])
        logger.info("Performance: %s", status["performance"])
        logger.info("Total routes: %d", status["routing"]["total_routes"])

    finally:
        await gw.stop()
        logger.info("Demo complete!")


if __name__ == "__main__":
    asyncio.run(run_demo())
