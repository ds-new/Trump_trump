"""
Gateway — 三权分立 Agent System 的宪法框架。

Gateway 不再是简单的控制平面，而是映射美国宪法（Constitution）：
- 它定义了三个分支的权力边界
- 它管理法案从提出到生效的完整流程
- 它协调制衡机制（Checks & Balances）
- 它不偏向任何一个分支 — 保持中立

三个分支：
1. 行政权（Executive）: President + Workers（内阁）
2. 立法权（Legislative）: Senate + House
3. 司法权（Judicial）: Supreme Court

关键流程：
- 常规任务 → 总统分配给内阁执行
- 政策变更 → 众议院正式提案 → 参议院审议 → 总统签署/否决
- 总统建议立法 → 众议院决定是否正式发起 → 走正常立法流程
- 行政令 → 总统发布 → 内阁执行（司法审查仅在有人起诉时发生）
- 弹劾 → 众议院发起 → 参议院 2/3 投票定罪
- 拨款/预算法案 → 必须从众议院发起（Origination Clause）
"""

from __future__ import annotations

import asyncio
from typing import Any

from utils import get_logger, generate_id
from config import SystemConfig, GatewayConfig
from core.agent import BaseAgent
from core.event_bus import EventBus
from core.registry import AgentRegistry
from core.environment import SharedEnvironment
from core.message import Message, MessageType
from core.llm_client import LLMClient
from self_org.emergence import EmergenceEngine
from self_org.feedback import FeedbackLoop
from self_org.adaptation import AdaptationStrategy
from self_org.stigmergy import StigmergyManager
from checks_balances.legislation import LegislationManager, BillType
from checks_balances.judicial_review import JudicialReviewSystem
from core.task_tracker import TaskTracker
from .router import MessageRouter
from .http_api import HttpApiServer

logger = get_logger("Gateway")


class Gateway:
    """
    三权分立 Agent System 的宪法框架（Gateway）。

    核心职责：
    1. 管理三个分支的 Agent 生命周期
    2. 协调法案的立法流程
    3. 执行制衡机制
    4. 路由消息到正确的分支
    5. 维护系统"宪法"秩序
    """

    def __init__(self, config: SystemConfig | None = None):
        self.config = config or SystemConfig()

        self.event_bus = EventBus(queue_size=self.config.gateway.message_queue_size)
        self.registry = AgentRegistry(heartbeat_timeout=self.config.gateway.heartbeat_interval * 3)
        self.environment = SharedEnvironment(
            decay_rate=self.config.self_org.pheromone_decay,
            amplify_factor=self.config.self_org.pheromone_amplify,
        )

        self.feedback = FeedbackLoop(self.environment, window_size=self.config.self_org.feedback_window)
        self.stigmergy = StigmergyManager(self.environment)
        self.emergence = EmergenceEngine(
            self.registry, self.environment, self.event_bus,
            threshold=self.config.self_org.emergence_threshold,
            min_agents=self.config.self_org.min_agents,
        )
        self.adaptation = AdaptationStrategy(
            self.registry, self.environment, self.feedback,
            adaptation_rate=self.config.self_org.adaptation_rate,
            min_agents=self.config.self_org.min_agents,
            max_agents=self.config.self_org.max_agents,
        )
        self.router = MessageRouter(
            self.registry, self.environment, self.feedback, self.stigmergy,
            strategy=self.config.gateway.routing_strategy,
        )

        self.legislation = LegislationManager()
        self.task_tracker = TaskTracker()

        self.llm_client = LLMClient(self.config.llm)
        self._http_server = HttpApiServer(
            self, host=self.config.gateway.host, port=self.config.gateway.port,
        )

        self._agents: dict[str, BaseAgent] = {}
        self._agent_tasks: dict[str, asyncio.Task] = {}
        self._background_tasks: list[asyncio.Task] = []
        self._running = False
        self._agent_factory: dict[str, type] = {}

        self._branches: dict[str, list[str]] = {
            "executive": [],
            "legislative": [],
            "judicial": [],
        }

        self.event_bus.subscribe_type(MessageType.FEEDBACK, self._on_feedback)
        self.event_bus.subscribe_type(MessageType.TASK, self._on_task_route)
        self.event_bus.subscribe_type(MessageType.RESULT, self._on_result_route)
        self.event_bus.subscribe_type(MessageType.BILL, self._on_bill)
        self.event_bus.subscribe_type(MessageType.VOTE, self._on_vote)
        self.event_bus.subscribe_type(MessageType.VETO, self._on_veto)
        self.event_bus.subscribe_type(MessageType.EXECUTIVE_ORDER, self._on_executive_order)
        self.event_bus.subscribe_type(MessageType.JUDICIAL_REVIEW, self._on_judicial_review)
        self.event_bus.subscribe_type(MessageType.RULING, self._on_ruling)

    def _get_branch(self, agent_type: str) -> str:
        if agent_type in ("president", "worker"):
            return "executive"
        elif agent_type in ("senate", "house"):
            return "legislative"
        elif agent_type == "supreme_court":
            return "judicial"
        return "executive"

    async def _on_feedback(self, message: Message) -> None:
        payload = message.payload
        agent_id = payload.get("agent_id", message.sender)
        success = payload.get("success", True)
        task_type = payload.get("task_type", "general")
        duration = payload.get("duration", 0.0)

        await self.feedback.record(agent_id, success, task_type, duration)
        await self.stigmergy.mark_task(task_type, agent_id, success)

        for aid in self._branches.get("legislative", []):
            agent = self._agents.get(aid)
            if agent and agent.agent_type == "house":
                await agent.receive(message)

    async def _on_task_route(self, message: Message) -> None:
        if message.sender == "gateway" or message.receiver != "auto":
            return
        target = await self.router.route(message)
        if target and target in self._agents:
            message.receiver = target
            agent = self._agents[target]
            await self.task_tracker.on_task_dispatched(
                task_id=message.msg_id,
                agent_id=target,
                agent_type=agent.agent_type,
                task_type=message.payload.get("task_type", "general"),
                department=getattr(agent, "_department", ""),
            )
            await agent.receive(message)

    async def _on_result_route(self, message: Message) -> None:
        payload = message.payload
        task_id = payload.get("task_id") or payload.get("root_task_id", "")
        worker_id = payload.get("worker_id", message.sender)
        usage = payload.get("data", {}).get("usage") if isinstance(payload.get("data"), dict) else None

        if task_id:
            agent = self._agents.get(worker_id)
            await self.task_tracker.on_task_completed(
                task_id=task_id,
                agent_id=worker_id,
                success=payload.get("success", False),
                duration=payload.get("duration", 0.0),
                skill_used=payload.get("skill_used", ""),
                usage=usage,
                error=payload.get("error", ""),
            )

        receiver = message.receiver
        if receiver in self._agents:
            await self._agents[receiver].receive(message)

    async def _on_bill(self, message: Message) -> None:
        """处理立法流程中的法案消息"""
        payload = message.payload
        action = payload.get("action", "")

        if action == "new_bill":
            bill_type_str = payload.get("bill_type", "policy")
            sponsor_agent = self._agents.get(payload.get("sponsor", ""))
            sponsor_type = sponsor_agent.agent_type if sponsor_agent else ""
            is_revenue_bill = bill_type_str in ("budget", "resource")

            if is_revenue_bill and sponsor_type != "house":
                logger.warning(
                    "Origination Clause violation: %s bill must originate in the House. "
                    "Redirecting to House for formal introduction.",
                    bill_type_str,
                )
                for aid in self._branches.get("legislative", []):
                    agent = self._agents.get(aid)
                    if agent and agent.agent_type == "house":
                        await agent.receive(Message(
                            msg_type=MessageType.BILL,
                            sender="gateway",
                            receiver=aid,
                            payload={
                                "action": "propose",
                                "title": payload.get("title", "Unnamed"),
                                "bill_type": bill_type_str,
                                "content": payload.get("content", {}),
                                "origination_redirect": True,
                            },
                        ))
                return

            bill = await self.legislation.propose_bill(
                title=payload.get("title", "Unnamed"),
                bill_type=BillType(bill_type_str),
                sponsor=payload.get("sponsor", message.sender),
                sponsor_branch=payload.get("sponsor_branch", "legislative"),
                content=payload.get("content", {}),
            )

            for aid in self._branches.get("legislative", []):
                agent = self._agents.get(aid)
                if agent and agent.agent_type == "house":
                    await self.task_tracker.on_task_dispatched(
                        task_id=f"bill-house-{bill.bill_id}",
                        agent_id=aid,
                        agent_type="house",
                        task_type="bill_vote",
                        activity_type="bill",
                    )
                    await agent.receive(Message(
                        msg_type=MessageType.BILL,
                        sender="gateway",
                        receiver=aid,
                        payload={
                            "action": "house_vote",
                            "bill_id": bill.bill_id,
                            "title": bill.title,
                            "content": bill.content,
                        },
                    ))

        elif action == "sign":
            bill_id = payload.get("bill_id", "")
            await self.legislation.presidential_action(bill_id, sign=True)
            logger.info("Law enacted: bill %s signed by President", bill_id)

            president_ids = [aid for aid in self._branches.get("executive", [])
                             if self._agents.get(aid) and self._agents[aid].agent_type == "president"]
            if president_ids:
                await self.task_tracker.on_task_completed(
                    task_id=f"bill-sign-{bill_id}",
                    agent_id=president_ids[0],
                    success=True,
                    skill_used="bill_sign",
                )
                await self.task_tracker.on_activity(
                    activity_id=f"sign-{bill_id}",
                    agent_id=president_ids[0],
                    agent_type="president",
                    activity_type="bill_sign",
                    detail=f"Signed bill {bill_id}",
                    success=True,
                )

            bill = await self.legislation.get_bill(bill_id)
            if bill:
                await self._enforce_law(bill.content)

        elif action == "propose":
            for aid in self._branches.get("legislative", []):
                agent = self._agents.get(aid)
                if agent and agent.agent_type == "house":
                    await self.task_tracker.on_task_dispatched(
                        task_id=f"propose-{message.msg_id}",
                        agent_id=aid,
                        agent_type="house",
                        task_type="bill_propose",
                        activity_type="bill",
                    )
                    await agent.receive(Message(
                        msg_type=MessageType.BILL,
                        sender=message.sender,
                        receiver=aid,
                        payload={
                            "action": "propose",
                            "title": payload.get("title", "Presidential Recommendation"),
                            "bill_type": payload.get("bill_type", "policy"),
                            "content": payload.get("content", {}),
                            "presidential_recommendation": True,
                        },
                    ))
            logger.info("Presidential recommendation forwarded to House for formal introduction")

    async def _on_vote(self, message: Message) -> None:
        """处理投票消息"""
        payload = message.payload
        action = payload.get("action", "")
        bill_id = payload.get("bill_id", "")

        if action == "house_vote":
            voter_id = payload.get("voter_id", "")
            if voter_id:
                await self.task_tracker.on_activity(
                    activity_id=f"hvote-{bill_id}-{voter_id}",
                    agent_id=voter_id,
                    agent_type="house",
                    activity_type="vote",
                    detail=f"House vote on {bill_id}: {'Yea' if payload.get('approve') else 'Nay'}",
                    success=True,
                )
            await self.task_tracker.on_task_completed(
                task_id=f"bill-house-{bill_id}",
                agent_id=voter_id or message.sender,
                success=True,
                skill_used="house_vote",
            )
            await self.legislation.cast_house_vote(
                bill_id, voter_id,
                payload.get("approve", False), payload.get("reason", ""),
                payload.get("yea_count", 0), payload.get("nay_count", 0), payload.get("total_count", 0),
            )
            bill = await self.legislation.finalize_house_vote(bill_id)
            if bill and bill.status.value == "senate_voting":
                for aid in self._branches.get("legislative", []):
                    agent = self._agents.get(aid)
                    if agent and agent.agent_type == "senate":
                        await self.task_tracker.on_task_dispatched(
                            task_id=f"bill-senate-{bill_id}",
                            agent_id=aid,
                            agent_type="senate",
                            task_type="bill_vote",
                            activity_type="bill",
                        )
                        await agent.receive(Message(
                            msg_type=MessageType.BILL,
                            sender="gateway",
                            receiver=aid,
                            payload={
                                "action": "senate_vote",
                                "bill_id": bill.bill_id,
                                "title": bill.title,
                                "content": bill.content,
                            },
                        ))

        elif action == "senate_vote":
            voter_id = payload.get("voter_id", "")
            if voter_id:
                await self.task_tracker.on_activity(
                    activity_id=f"svote-{bill_id}-{voter_id}",
                    agent_id=voter_id,
                    agent_type="senate",
                    activity_type="vote",
                    detail=f"Senate vote on {bill_id}: {'Yea' if payload.get('approve') else 'Nay'}",
                    success=True,
                )
            await self.task_tracker.on_task_completed(
                task_id=f"bill-senate-{bill_id}",
                agent_id=voter_id or message.sender,
                success=True,
                skill_used="senate_vote",
            )
            await self.legislation.cast_senate_vote(
                bill_id, voter_id,
                payload.get("approve", False), payload.get("reason", ""),
                payload.get("yea_count", 0), payload.get("nay_count", 0), payload.get("total_count", 0),
            )
            bill = await self.legislation.finalize_senate_vote(bill_id)
            if bill and bill.status.value == "awaiting_signature":
                for aid in self._branches.get("executive", []):
                    agent = self._agents.get(aid)
                    if agent and agent.agent_type == "president":
                        await self.task_tracker.on_task_dispatched(
                            task_id=f"bill-sign-{bill_id}",
                            agent_id=aid,
                            agent_type="president",
                            task_type="bill_signature",
                            activity_type="bill",
                        )
                        await agent.receive(Message(
                            msg_type=MessageType.BILL,
                            sender="gateway",
                            receiver=aid,
                            payload={
                                "action": "awaiting_signature",
                                "bill_id": bill.bill_id,
                                "title": bill.title,
                                "content": bill.content,
                            },
                        ))

        elif action == "override_vote":
            await self.legislation.cast_override_vote(
                bill_id, payload.get("voter_id", ""),
                payload.get("voter_role", ""), payload.get("approve", False),
                payload.get("reason", ""),
                payload.get("yea_count", 0), payload.get("nay_count", 0), payload.get("total_count", 0),
            )
            await self._check_override_complete(bill_id)

        elif action == "confirmation":
            logger.info("Senate confirmation: %s for %s — %s",
                        payload.get("nominee"), payload.get("position"),
                        "confirmed" if payload.get("confirmed") else "rejected")

    async def _on_veto(self, message: Message) -> None:
        """处理总统否决"""
        payload = message.payload
        bill_id = payload.get("bill_id", "")
        reason = payload.get("reason", "")

        await self.task_tracker.on_task_completed(
            task_id=f"bill-sign-{bill_id}",
            agent_id=message.sender,
            success=True,
            skill_used="veto",
        )
        await self.task_tracker.on_activity(
            activity_id=f"veto-{bill_id}",
            agent_id=message.sender,
            agent_type="president",
            activity_type="veto",
            detail=f"Vetoed bill {bill_id}: {reason}",
            success=True,
        )

        await self.legislation.presidential_action(bill_id, sign=False, veto_reason=reason)
        bill = await self.legislation.get_bill(bill_id)

        for aid in self._branches.get("legislative", []):
            agent = self._agents.get(aid)
            if agent:
                await agent.receive(Message(
                    msg_type=MessageType.VETO,
                    sender="gateway",
                    receiver=aid,
                    payload={
                        "action": "override_vote",
                        "bill_id": bill_id,
                        "veto_reason": reason,
                        "content": bill.content if bill else {},
                    },
                ))

    async def _check_override_complete(self, bill_id: str) -> None:
        """检查否决推翻投票是否完成"""
        total_legislators = len(self._branches.get("legislative", []))
        bill = await self.legislation.get_bill(bill_id)
        if bill and len(bill.override_votes) >= total_legislators:
            await self.legislation.finalize_override_vote(bill_id)
            updated = await self.legislation.get_bill(bill_id)
            if updated and updated.status.value == "enacted":
                await self._enforce_law(updated.content)

    async def _on_executive_order(self, message: Message) -> None:
        """将行政令交由行政部门执行（司法审查仅在有人起诉时发生）"""
        order_id = message.payload.get("order_id", message.msg_id)
        for aid in self._branches.get("executive", []):
            agent = self._agents.get(aid)
            if agent and agent.agent_type == "worker":
                await self.task_tracker.on_task_dispatched(
                    task_id=f"eo-{order_id}-{aid}",
                    agent_id=aid,
                    agent_type="worker",
                    task_type="executive_order",
                    activity_type="executive_order",
                    department=getattr(agent, "_department", ""),
                )
                await agent.receive(message)

    async def _on_judicial_review(self, message: Message) -> None:
        """将司法审查请求转发给最高法院"""
        subject_id = message.payload.get("subject_id", message.msg_id)
        for aid in self._branches.get("judicial", []):
            agent = self._agents.get(aid)
            if agent:
                await self.task_tracker.on_task_dispatched(
                    task_id=f"review-{subject_id}",
                    agent_id=aid,
                    agent_type="supreme_court",
                    task_type="judicial_review",
                    activity_type="judicial_review",
                )
                await agent.receive(message)

    async def _on_ruling(self, message: Message) -> None:
        """处理最高法院裁决"""
        payload = message.payload
        verdict = payload.get("verdict", "")
        subject_id = payload.get("subject_id", "")

        await self.task_tracker.on_task_completed(
            task_id=f"review-{subject_id}",
            agent_id=message.sender,
            success=True,
            skill_used="judicial_ruling",
        )
        await self.task_tracker.on_activity(
            activity_id=f"ruling-{subject_id}",
            agent_id=message.sender,
            agent_type="supreme_court",
            activity_type="ruling",
            detail=f"Ruling on {subject_id}: {verdict}",
            success=True,
        )

        if verdict == "unconstitutional":
            logger.warning("SUPREME COURT: %s ruled unconstitutional", subject_id)
            if subject_id.startswith("bill"):
                await self.legislation.mark_unconstitutional(subject_id, payload.get("opinion", ""))

        if message.receiver and message.receiver in self._agents:
            await self._agents[message.receiver].receive(message)

    async def _enforce_law(self, law_content: dict[str, Any]) -> None:
        """将生效的法律转化为系统实际行为"""
        action = law_content.get("action", "")

        if action == "scale_up":
            count = law_content.get("count", 1)
            for _ in range(count):
                if "worker" in self._agent_factory:
                    await self.spawn_agent("worker")
            logger.info("Law enforced: scaled up %d workers", count)

        elif action == "scale_down":
            count = law_content.get("count", 1)
            workers = [aid for aid in self._branches.get("executive", [])
                       if self._agents.get(aid) and self._agents[aid].agent_type == "worker"]
            for aid in workers[:count]:
                await self.kill_agent(aid)
            logger.info("Law enforced: scaled down %d workers", min(count, len(workers)))

        elif action == "change_routing":
            new_strategy = law_content.get("strategy", "adaptive")
            self.router._strategy = new_strategy
            logger.info("Law enforced: routing strategy changed to %s", new_strategy)

        elif action == "policy_update":
            key = law_content.get("key", "")
            value = law_content.get("value")
            if key:
                await self.environment.write_blackboard(f"policy:{key}", value)
                logger.info("Law enforced: policy %s updated", key)

    def register_agent_type(self, agent_type: str, agent_class: type) -> None:
        self._agent_factory[agent_type] = agent_class

    async def spawn_agent(self, agent_type: str, skills: list | None = None, **kwargs: Any) -> BaseAgent:
        if agent_type not in self._agent_factory:
            raise ValueError(f"Unknown agent type: {agent_type}")

        agent_class = self._agent_factory[agent_type]
        agent = agent_class(
            event_bus=self.event_bus,
            skills=skills or [],
            **kwargs,
        )

        agent.metadata["llm_client"] = self.llm_client

        self._agents[agent.agent_id] = agent
        await self.registry.register(agent)

        branch = self._get_branch(agent_type)
        self._branches[branch].append(agent.agent_id)

        self.task_tracker.register_agent(
            agent_id=agent.agent_id,
            agent_type=agent_type,
            department=getattr(agent, "_department", ""),
            branch=branch,
        )

        task = asyncio.create_task(agent.run())
        self._agent_tasks[agent.agent_id] = task

        logger.info("Spawned [%s branch] agent: %s [%s]", branch.upper(), agent.agent_id, agent_type)
        return agent

    async def kill_agent(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if not agent:
            return

        protected_types = {"president", "senate", "house", "supreme_court"}
        if agent.agent_type in protected_types:
            logger.warning("Cannot kill %s — protected by Constitution", agent.agent_type)
            return

        await agent.stop()
        task = self._agent_tasks.pop(agent_id, None)
        if task:
            task.cancel()

        del self._agents[agent_id]
        await self.registry.unregister(agent_id)

        for branch_agents in self._branches.values():
            if agent_id in branch_agents:
                branch_agents.remove(agent_id)

        logger.info("Terminated agent: %s", agent_id)

    async def submit_task(self, task_payload: dict[str, Any]) -> str:
        """提交任务 — 所有外部任务通过总统分配给内阁"""
        msg = Message(
            msg_type=MessageType.TASK,
            sender="gateway",
            receiver="auto",
            payload=task_payload,
        )

        president_ids = [aid for aid in self._branches.get("executive", [])
                         if self._agents.get(aid) and self._agents[aid].agent_type == "president"]

        if president_ids:
            president = self._agents[president_ids[0]]
            msg.receiver = president.agent_id
            await president.receive(msg)
            await self.task_tracker.on_task_dispatched(
                task_id=msg.msg_id,
                agent_id=president.agent_id,
                agent_type="president",
                task_type=task_payload.get("task_type", "general"),
            )
            logger.info("Task %s → President %s", msg.msg_id, president.agent_id)
            return msg.msg_id

        target = await self.router.route(msg)
        if not target:
            logger.warning("No available agent for task: %s",
                           task_payload.get("task_type", "unknown"))
            return ""

        msg.receiver = target
        agent = self._agents.get(target)
        if agent:
            await agent.receive(msg)
            await self.task_tracker.on_task_dispatched(
                task_id=msg.msg_id,
                agent_id=target,
                agent_type=agent.agent_type,
                task_type=task_payload.get("task_type", "general"),
                department=getattr(agent, "_department", ""),
            )
            logger.info("Task %s → %s (direct route, no president)", msg.msg_id, target)

        return msg.msg_id

    async def submit_comprehensive_task(self, message: str = "") -> dict[str, Any]:
        """
        提交一个触发全部三权分立流程的综合任务。

        流程：
        1. 行政分支：总统接收任务 → 分解为 3 个子任务分配给所有内阁部门执行
        2. 立法分支：众议院提出法案 → 众议院投票 → 参议院投票 → 总统签署
        3. 司法分支：最高法院对法案进行司法审查

        所有消息通过 EventBus 发布以确保完整追踪。
        """
        results = {}
        task_msg = message or "请分析当前系统运行状况并给出优化建议"

        task_payload = {
            "task_type": "analysis",
            "required_skill": "chat",
            "complexity": 3,
            "data": {
                "prompt": task_msg,
                "query": task_msg,
                "message": task_msg,
                "requirement": task_msg,
                "content": task_msg,
                "text": task_msg,
                "task": task_msg,
            },
        }
        task_id = await self.submit_task(task_payload)
        results["executive_task_id"] = task_id

        bill_content = {
            "action": "policy_update",
            "key": "comprehensive_test",
            "value": "System comprehensive test triggered",
            "description": task_msg or "Comprehensive system test",
        }

        bill_msg = Message(
            msg_type=MessageType.BILL,
            sender="gateway",
            receiver="gateway",
            payload={
                "action": "new_bill",
                "title": "System Performance Review Act",
                "bill_type": "policy",
                "content": bill_content,
                "sponsor": "gateway",
                "sponsor_branch": "system",
            },
        )
        await self.event_bus.publish(bill_msg)
        results["bill_status"] = "submitted_via_event_bus"

        review_msg = Message(
            msg_type=MessageType.JUDICIAL_REVIEW,
            sender="gateway",
            receiver="auto",
            payload={
                "subject_type": "system_review",
                "subject_id": f"system-review-{task_id}",
                "content": bill_content,
                "reason": "Comprehensive system review — constitutional compliance check",
            },
        )
        await self.event_bus.publish(review_msg)
        results["judicial_review_status"] = "submitted_via_event_bus"

        results["status"] = "all_branches_engaged"
        return results

    async def _health_check_loop(self) -> None:
        interval = self.config.self_org.health_check_interval
        while self._running:
            await asyncio.sleep(interval)
            try:
                stale = await self.registry.cleanup_stale()
                for agent_id in stale:
                    self._agents.pop(agent_id, None)
                    task = self._agent_tasks.pop(agent_id, None)
                    if task:
                        task.cancel()
                    for branch_agents in self._branches.values():
                        if agent_id in branch_agents:
                            branch_agents.remove(agent_id)

                if await self.feedback.is_system_overheated():
                    await self.feedback.apply_cooling()

                action = await self.adaptation.evaluate()
                if action.get("action") not in ("none", "cooldown"):
                    await self._propose_adaptation_bill(action)
                elif action.get("action") == "cooldown":
                    await self._execute_cooldown()

            except Exception as e:
                logger.error("Health check error: %s", e)

    async def _propose_adaptation_bill(self, action: dict[str, Any]) -> None:
        """系统自适应建议通过立法流程执行"""
        action_type = action.get("action", "none")
        if action_type == "none":
            return

        title = f"System Adaptation: {action_type}"
        content = {
            "action": action_type,
            "count": action.get("count", 1),
            "reason": action.get("reason", ""),
        }

        for aid in self._branches.get("legislative", []):
            agent = self._agents.get(aid)
            if agent and agent.agent_type == "house":
                await agent.receive(Message(
                    msg_type=MessageType.BILL,
                    sender="gateway",
                    receiver=aid,
                    payload={
                        "action": "propose",
                        "title": title,
                        "bill_type": "resource",
                        "content": content,
                        "sponsor": "system_adaptation",
                        "sponsor_branch": "system",
                    },
                ))
                break

    async def _execute_cooldown(self) -> None:
        logger.warning("System cooldown triggered — pausing task intake")
        await self.environment.write_blackboard("cooldown_active", True)
        await asyncio.sleep(5.0)
        await self.environment.write_blackboard("cooldown_active", False)

    async def _heartbeat_loop(self) -> None:
        interval = self.config.gateway.heartbeat_interval
        while self._running:
            await asyncio.sleep(interval)
            for agent_id, agent in list(self._agents.items()):
                await self.registry.heartbeat(agent_id, agent.load, agent.state.value)

    async def start(self) -> None:
        self._running = True
        logger.info("=" * 60)
        logger.info("  USA Three-Branch Agent System — Gateway Starting")
        logger.info("  Constitution: Separation of Powers")
        logger.info("  LLM: %s @ %s", self.config.llm.model, self.config.llm.base_url)
        logger.info("  API: http://%s:%d", self.config.gateway.host, self.config.gateway.port)
        logger.info("=" * 60)

        self._background_tasks = [
            asyncio.create_task(self.event_bus.start()),
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self.emergence.run(self.config.self_org.leader_election_interval)),
            asyncio.create_task(self.stigmergy.run()),
        ]

        self._http_server.start(asyncio.get_event_loop())
        await self._test_llm_connectivity()
        logger.info("Gateway ready — Constitutional framework active")

    async def _test_llm_connectivity(self) -> None:
        try:
            resp = await self.llm_client.chat(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            if resp.success:
                logger.info("LLM connectivity OK — model=%s", resp.model)
            else:
                logger.error("LLM connectivity FAILED: %s", resp.error)
        except Exception as e:
            logger.error("LLM connectivity test exception: %s", e)

    async def stop(self) -> None:
        self._running = False
        logger.info("Gateway shutting down — all branches dissolving...")

        self._http_server.stop()

        for agent_id in list(self._agents.keys()):
            agent = self._agents.get(agent_id)
            if agent:
                await agent.stop()
                task = self._agent_tasks.pop(agent_id, None)
                if task:
                    task.cancel()

        self._agents.clear()
        self._branches = {"executive": [], "legislative": [], "judicial": []}

        await self.event_bus.stop()
        await self.emergence.stop()

        for task in self._background_tasks:
            task.cancel()

        logger.info("Gateway stopped — Republic dissolved")

    async def status(self) -> dict[str, Any]:
        patterns = await self.emergence.detect_patterns()
        global_stats = await self.feedback.get_global_stats()
        legislation_status = await self.legislation.status_summary()

        branch_status = {}
        for branch, agent_ids in self._branches.items():
            branch_agents = []
            for aid in agent_ids:
                agent = self._agents.get(aid)
                if agent:
                    record = None
                    for r in self.registry.all_agents:
                        if r.agent_id == aid:
                            record = r
                            break
                    branch_agents.append({
                        "id": aid,
                        "type": agent.agent_type,
                        "state": record.state if record else agent.state.value,
                        "load": record.load if record else agent.load,
                        "skills": record.skills if record else [s.name for s in agent.skills],
                    })
            branch_status[branch] = {
                "agents": branch_agents,
                "count": len(branch_agents),
            }

        tracker_overview = await self.task_tracker.get_overview()

        return {
            "system": "USA Three-Branch Agent System",
            "constitution": "Separation of Powers — Checks & Balances",
            "branches": branch_status,
            "agents": {
                "total": self.registry.count,
                "by_branch": {b: len(a) for b, a in self._branches.items()},
            },
            "legislation": legislation_status,
            "self_organization": {
                "patterns": patterns,
                "pheromone_count": self.environment.pheromone_count,
            },
            "performance": global_stats,
            "task_tracker": tracker_overview,
            "routing": {
                "strategy": self.config.gateway.routing_strategy,
                "total_routes": self.router.total_routes,
            },
            "llm": self.llm_client.stats,
        }
