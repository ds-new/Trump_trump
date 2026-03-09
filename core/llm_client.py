"""
LLM 客户端 — 对接大模型 API（OpenAI 兼容格式）。

支持 DeepSeek / OpenAI / Azure / 火山引擎 等 OpenAI 兼容 API。
每个 Agent 可以独立持有 LLM 客户端实例，实现自主推理。
"""

from __future__ import annotations

import json
import asyncio
from collections import defaultdict
from typing import Any
from dataclasses import dataclass, field

from config.settings import LLMConfig
from utils import get_logger

logger = get_logger("LLM")

try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


@dataclass
class LLMMessage:
    role: str  # system / user / assistant / tool
    content: str
    name: str | None = None


@dataclass
class LLMResponse:
    content: str = ""
    role: str = "assistant"
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    success: bool = True
    error: str = ""


class LLMClient:
    """
    异步 LLM 客户端，封装 OpenAI 兼容 API 调用。

    特性：
    - 异步非阻塞调用
    - 自动重试
    - 会话上下文管理
    - token 用量追踪
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._total_tokens = 0
        self._call_count = 0
        self._caller_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0}
        )

        if HAS_OPENAI:
            self._client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout,
                max_retries=config.max_retries,
            )
            logger.info("LLMClient initialized (openai): model=%s url=%s timeout=%.0fs",
                        config.model, config.base_url, config.timeout)
        else:
            self._client = None
            logger.warning("LLMClient initialized (fallback/urllib): openai not installed")

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        caller_id: str | None = None,
    ) -> LLMResponse:
        """
        发送对话请求到大模型。

        Args:
            messages: 对话历史 [{"role": "user", "content": "..."}]
            system_prompt: 系统提示词（会插入到消息列表开头）
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            model: 模型名（覆盖默认配置）
        """
        if not HAS_OPENAI:
            logger.warning("openai not installed — using urllib fallback")
            return await self._fallback_chat(messages, system_prompt, caller_id=caller_id)

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        try:
            response = await self._client.chat.completions.create(
                model=model or self._config.model,
                messages=full_messages,
                temperature=temperature if temperature is not None else self._config.temperature,
                max_tokens=max_tokens or self._config.max_tokens,
            )

            choice = response.choices[0]
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
                self._total_tokens += response.usage.total_tokens
                if caller_id:
                    cs = self._caller_stats[caller_id]
                    cs["prompt_tokens"] += response.usage.prompt_tokens
                    cs["completion_tokens"] += response.usage.completion_tokens
                    cs["total_tokens"] += response.usage.total_tokens
                    cs["call_count"] += 1

            self._call_count += 1

            return LLMResponse(
                content=choice.message.content or "",
                role=choice.message.role,
                model=response.model,
                usage=usage,
                success=True,
            )

        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(e, "status", "")
            err_body = getattr(e, "body", None) or getattr(e, "message", "")
            logger.error(
                "LLM call failed [%s]: %s | status=%s detail=%s",
                type(e).__name__, e, status, err_body,
            )
            return LLMResponse(
                success=False,
                error=f"[{type(e).__name__}] {e}",
            )

    async def _fallback_chat(
        self, messages: list[dict[str, str]], system_prompt: str | None,
        caller_id: str | None = None,
    ) -> LLMResponse:
        """openai 库未安装时的降级处理：使用 httpx/urllib 直接调用"""
        import urllib.request
        import ssl

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        body = json.dumps({
            "model": self._config.model,
            "messages": full_messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }).encode()

        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        ctx = ssl.create_default_context()

        try:
            loop = asyncio.get_event_loop()
            resp_bytes = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(req, context=ctx, timeout=self._config.timeout).read()
            )
            data = json.loads(resp_bytes)

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            self._total_tokens += usage.get("total_tokens", 0)
            self._call_count += 1
            if caller_id and usage:
                cs = self._caller_stats[caller_id]
                cs["prompt_tokens"] += usage.get("prompt_tokens", 0)
                cs["completion_tokens"] += usage.get("completion_tokens", 0)
                cs["total_tokens"] += usage.get("total_tokens", 0)
                cs["call_count"] += 1

            return LLMResponse(
                content=content,
                role="assistant",
                model=data.get("model", self._config.model),
                usage=usage,
                success=True,
            )
        except Exception as e:
            logger.error("LLM fallback call failed: %s", e)
            return LLMResponse(success=False, error=str(e))

    async def simple_ask(self, question: str, system_prompt: str | None = None) -> str:
        """简单问答接口"""
        resp = await self.chat(
            messages=[{"role": "user", "content": question}],
            system_prompt=system_prompt,
        )
        if resp.success:
            return resp.content
        return f"[LLM Error] {resp.error}"

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_tokens": self._total_tokens,
            "call_count": self._call_count,
            "model": self._config.model,
            "base_url": self._config.base_url,
        }

    @property
    def caller_stats(self) -> dict[str, dict[str, int]]:
        return dict(self._caller_stats)
