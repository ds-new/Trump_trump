"""
HTTP API 服务 — 接收前端下发的任务。

提供 RESTful API：
- POST /api/task      — 提交任务（同步等待结果）
- POST /api/task/async — 提交任务（异步，返回 task_id）
- GET  /api/status    — 获取系统状态
- GET  /api/agents    — 获取 Agent 列表
- POST /api/chat      — 直接对话（最常用的前端接口）

使用标准库 asyncio + http.server 实现，无需 Flask/FastAPI 依赖。
"""

from __future__ import annotations

import asyncio
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse, parse_qs
import threading

from utils import get_logger

if TYPE_CHECKING:
    from .gateway import Gateway

logger = get_logger("HttpAPI")


class APIHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    gateway: Gateway = None  # type: ignore
    event_loop: asyncio.AbstractEventLoop = None  # type: ignore

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def _run_async(self, coro):
        """在 Gateway 的事件循环中执行异步协程"""
        future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)
        return future.result(timeout=180)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/status":
            self._handle_status()
        elif path == "/api/agents":
            self._handle_agents()
        elif path == "/api/health":
            self._send_json({"status": "ok"})
        elif path == "/api/monitor":
            self._handle_monitor_page()
        elif path == "/api/monitor/data":
            self._handle_monitor_data()
        elif path == "/api/monitor/tasks":
            limit = int(query.get("limit", [50])[0])
            offset = int(query.get("offset", [0])[0])
            self._handle_monitor_tasks(limit, offset)
        elif path == "/api/monitor/agents":
            self._handle_monitor_agents()
        elif path == "/api/monitor/tokens":
            self._handle_monitor_tokens()
        else:
            self._send_json({"error": "Not found", "available": [
                "GET /api/status", "GET /api/agents", "GET /api/health",
                "GET /api/monitor", "GET /api/monitor/data",
                "GET /api/monitor/tasks", "GET /api/monitor/agents",
                "GET /api/monitor/tokens",
                "POST /api/chat", "POST /api/task", "POST /api/task/async",
            ]}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        try:
            body = self._read_body()
        except Exception as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, 400)
            return

        if path == "/api/chat":
            self._handle_chat(body)
        elif path == "/api/task":
            self._handle_task_sync(body)
        elif path == "/api/task/async":
            self._handle_task_async(body)
        elif path == "/api/task/comprehensive":
            self._handle_comprehensive_task(body)
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_status(self) -> None:
        try:
            status = self._run_async(self.gateway.status())
            self._send_json(status)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_agents(self) -> None:
        agents = []
        for record in self.gateway.registry.all_agents:
            agents.append({
                "id": record.agent_id,
                "type": record.agent_type,
                "state": record.state,
                "load": record.load,
                "skills": record.skills,
            })
        self._send_json({"agents": agents, "count": len(agents)})

    def _handle_chat(self, body: dict[str, Any]) -> None:
        """
        对话接口 — 前端最常用的接口。

        请求体：
        {
            "message": "你好，帮我写一段Python排序代码",
            "skill": "chat",         // 可选，指定技能
            "system_prompt": "...",   // 可选，自定义系统提示
            "history": [...]          // 可选，对话历史
        }
        """
        message = body.get("message", "")
        if not message:
            self._send_json({"error": "message field is required"}, 400)
            return

        skill = body.get("skill", "chat")
        system_prompt = body.get("system_prompt")
        history = body.get("history", [])

        task_payload = {
            "task_type": skill,
            "required_skill": skill,
            "data": {
                "prompt": message,
                "query": message,
                "message": message,
                "system_prompt": system_prompt,
                "history": history,
                "requirement": message,
                "content": message,
                "text": message,
                "task": message,
            },
        }

        try:
            result = self._run_async(self._submit_and_wait(task_payload))
            self._send_json(result)
        except Exception as e:
            logger.error("Chat error: %s", e)
            self._send_json({"error": str(e)}, 500)

    async def _submit_and_wait(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        """提交任务并等待结果（通过监听 EventBus）"""
        result_future: asyncio.Future = asyncio.get_event_loop().create_future()
        task_id = ""

        async def on_result(message):
            nonlocal task_id
            if message.payload.get("task_id") == task_id:
                if not result_future.done():
                    result_future.set_result(message.payload)

        from core.message import MessageType
        self.gateway.event_bus.subscribe_type(MessageType.RESULT, on_result)

        try:
            task_id = await self.gateway.submit_task(task_payload)
            if not task_id:
                return {"success": False, "error": "No available agent to handle this task"}

            result = await asyncio.wait_for(result_future, timeout=120)
            resp = {
                "success": result.get("success", False),
                "data": result.get("data", {}),
                "worker_id": result.get("worker_id", ""),
                "skill_used": result.get("skill_used", ""),
                "duration": result.get("duration", 0),
                "task_id": task_id,
            }
            if not resp["success"]:
                resp["error"] = result.get("error", "Unknown error")
            return resp
        except asyncio.TimeoutError:
            return {"success": False, "error": "Task timeout (120s)", "task_id": task_id}
        finally:
            self.gateway.event_bus.unsubscribe_type(MessageType.RESULT, on_result)

    def _handle_monitor_page(self) -> None:
        """返回监控面板 HTML 页面"""
        try:
            html_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "dashboard", "monitor.html",
            )
            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()
            self._send_html(html)
        except FileNotFoundError:
            self._send_html("<h1>Monitor dashboard not found</h1>", 404)
        except Exception as e:
            self._send_html(f"<h1>Error: {e}</h1>", 500)

    def _handle_monitor_data(self) -> None:
        """返回监控面板所需的全部 JSON 数据"""
        try:
            data = self._run_async(self.gateway.task_tracker.get_monitor_data())
            data["llm"] = self.gateway.llm_client.stats
            data["llm_caller_stats"] = self.gateway.llm_client.caller_stats
            self._send_json(data)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_monitor_tasks(self, limit: int, offset: int) -> None:
        """返回任务历史"""
        try:
            tasks = self._run_async(self.gateway.task_tracker.get_task_history(limit, offset))
            self._send_json({"tasks": tasks, "count": len(tasks), "offset": offset})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_monitor_agents(self) -> None:
        """返回按智能体分组的统计"""
        try:
            stats = self._run_async(self.gateway.task_tracker.get_agent_stats())
            self._send_json({"agents": stats, "count": len(stats)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_monitor_tokens(self) -> None:
        """返回 Token 消耗统计"""
        try:
            data = self._run_async(self.gateway.task_tracker.get_token_stats())
            data["llm_global"] = self.gateway.llm_client.stats
            data["llm_per_caller"] = self.gateway.llm_client.caller_stats
            self._send_json(data)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_task_sync(self, body: dict[str, Any]) -> None:
        """同步提交任务"""
        try:
            result = self._run_async(self._submit_and_wait(body))
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_task_async(self, body: dict[str, Any]) -> None:
        """异步提交任务（立即返回 task_id）"""
        try:
            task_id = self._run_async(self.gateway.submit_task(body))
            self._send_json({"task_id": task_id, "status": "submitted"})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_comprehensive_task(self, body: dict[str, Any]) -> None:
        """
        全流程综合任务 — 触发所有智能体工作。

        同时启动：
        1. 行政任务（总统 → 内阁执行）
        2. 立法流程（众议院提案 → 投票 → 参议院投票 → 总统签署）
        3. 司法审查（最高法院审查）

        请求体：
        { "message": "可选的任务描述" }
        """
        message = body.get("message", "")
        try:
            result = self._run_async(self.gateway.submit_comprehensive_task(message))
            self._send_json({
                "success": True,
                "message": "全流程任务已下发，所有三权分立分支已启动工作",
                "details": result,
            })
        except Exception as e:
            logger.error("Comprehensive task error: %s", e)
            self._send_json({"error": str(e)}, 500)


class HttpApiServer:
    """HTTP API 服务器（在独立线程中运行）"""

    def __init__(self, gateway: Gateway, host: str = "0.0.0.0", port: int = 18790):
        self._gateway = gateway
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self, event_loop: asyncio.AbstractEventLoop) -> None:
        APIHandler.gateway = self._gateway
        APIHandler.event_loop = event_loop

        self._server = HTTPServer((self._host, self._port), APIHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("HTTP API server started at http://%s:%d", self._host, self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            logger.info("HTTP API server stopped")
