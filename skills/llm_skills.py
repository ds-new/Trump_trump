"""
LLM 驱动的智能技能 — 用大模型完成复杂任务。

每个技能封装一种「大模型使用模式」：
- ChatSkill:     通用对话 / 问答
- CodeGenSkill:  代码生成
- AnalysisSkill: 深度分析（数据/文本/逻辑）
- SummarySkill:  文本摘要
- PlanSkill:     任务规划与分解
"""

from __future__ import annotations

from typing import Any

from core.llm_client import LLMClient
from .base_skill import BaseSkill, SkillResult
from utils import get_logger

_logger = get_logger("LLMSkill")


class ChatSkill(BaseSkill):
    """通用对话技能 — 直接与大模型对话完成任务"""

    def __init__(self, llm: LLMClient):
        super().__init__(name="chat", description="General conversation and Q&A via LLM")
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        prompt = params.get("prompt") or params.get("query") or params.get("message", "")
        if not prompt:
            return SkillResult(success=False, error="No prompt provided")

        system = params.get("system_prompt", "你是一个高效的AI助手，请准确、简洁地回答用户的问题。")
        history = params.get("history", [])

        messages = list(history)
        messages.append({"role": "user", "content": prompt})

        _logger.info("ChatSkill calling LLM: prompt=%s..., url=%s",
                      prompt[:60], self._llm._config.base_url)
        resp = await self._llm.chat(messages=messages, system_prompt=system)
        _logger.info("ChatSkill LLM result: success=%s, error=%s, content_len=%d",
                      resp.success, resp.error or "none", len(resp.content))

        return SkillResult(
            success=resp.success,
            data={"response": resp.content, "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )


class CodeGenSkill(BaseSkill):
    """代码生成技能"""

    SYSTEM_PROMPT = (
        "你是一位资深的软件工程师。根据用户需求生成高质量代码。\n"
        "要求：\n"
        "1. 代码简洁、可读性强\n"
        "2. 包含必要的错误处理\n"
        "3. 使用现代最佳实践\n"
        "4. 如果用户没有指定语言，默认使用 Python\n"
        "5. 用中文注释解释关键逻辑"
    )

    def __init__(self, llm: LLMClient):
        super().__init__(name="codegen", description="Code generation via LLM")
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        requirement = params.get("requirement") or params.get("prompt", "")
        language = params.get("language", "")
        if not requirement:
            return SkillResult(success=False, error="No requirement provided")

        prompt = requirement
        if language:
            prompt = f"使用 {language} 语言：{requirement}"

        resp = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,
        )

        return SkillResult(
            success=resp.success,
            data={"code": resp.content, "language": language, "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )


class AnalysisSkill(BaseSkill):
    """深度分析技能"""

    SYSTEM_PROMPT = (
        "你是一位数据分析和逻辑推理专家。\n"
        "请对用户提供的内容进行深度分析，提供结构化的分析结果。\n"
        "分析应包含：关键发现、数据解读、趋势判断、建议。\n"
        "使用中文回答。"
    )

    def __init__(self, llm: LLMClient):
        super().__init__(name="analysis", description="Deep analysis via LLM")
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        content = params.get("content") or params.get("data") or params.get("prompt", "")
        if not content:
            return SkillResult(success=False, error="No content to analyze")

        if isinstance(content, (list, dict)):
            import json
            content = json.dumps(content, ensure_ascii=False, indent=2)

        prompt = f"请对以下内容进行深度分析：\n\n{content}"

        resp = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=self.SYSTEM_PROMPT,
        )

        return SkillResult(
            success=resp.success,
            data={"analysis": resp.content, "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )


class SummarySkill(BaseSkill):
    """文本摘要技能"""

    SYSTEM_PROMPT = (
        "你是一位专业的文本摘要专家。\n"
        "请将用户提供的长文本精炼为简洁的摘要。\n"
        "保留关键信息，去除冗余细节。使用中文回答。"
    )

    def __init__(self, llm: LLMClient):
        super().__init__(name="summary", description="Text summarization via LLM")
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        text = params.get("text") or params.get("content") or params.get("prompt", "")
        max_length = params.get("max_length", "")
        if not text:
            return SkillResult(success=False, error="No text to summarize")

        prompt = f"请摘要以下内容"
        if max_length:
            prompt += f"（控制在{max_length}字以内）"
        prompt += f"：\n\n{text}"

        resp = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,
        )

        return SkillResult(
            success=resp.success,
            data={"summary": resp.content, "model": resp.model, "usage": resp.usage},
            error=resp.error,
        )


class PlanSkill(BaseSkill):
    """任务规划技能 — 将复杂任务分解为可执行步骤"""

    SYSTEM_PROMPT = (
        "你是一位项目管理和任务规划专家。\n"
        "用户会给你一个复杂任务，你需要将其分解为清晰、可执行的步骤。\n"
        "输出格式为 JSON 数组，每个元素包含：\n"
        '  {"step": 步骤编号, "task": "任务描述", "skill": "所需技能类型", "priority": 优先级1-5}\n'
        "技能类型可选：chat, codegen, analysis, summary, search, transform\n"
        "请只输出 JSON，不要包含其他文字。"
    )

    def __init__(self, llm: LLMClient):
        super().__init__(name="plan", description="Task decomposition and planning via LLM")
        self._llm = llm

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        import json as json_module

        task_desc = params.get("task") or params.get("prompt", "")
        if not task_desc:
            return SkillResult(success=False, error="No task description provided")

        resp = await self._llm.chat(
            messages=[{"role": "user", "content": f"请分解以下任务：\n{task_desc}"}],
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,
        )

        if not resp.success:
            return SkillResult(success=False, error=resp.error)

        try:
            content = resp.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            steps = json_module.loads(content)
        except (json_module.JSONDecodeError, IndexError):
            steps = [{"step": 1, "task": task_desc, "skill": "chat", "priority": 3}]

        return SkillResult(
            success=True,
            data={"plan": steps, "raw_response": resp.content, "model": resp.model, "usage": resp.usage},
        )
