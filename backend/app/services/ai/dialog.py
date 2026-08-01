"""Brainstorm Dialog — guided onboarding conversation for project setup.

Uses Anthropic SDK directly with a 6-question maximum.
Auto-falls back to mock mode when no valid API key is configured.
"""

import json
import logging
import uuid
from typing import Any

from app.core.config import settings
from app.schemas.ai import DialogQuestion, ProjectConfig

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 6

DIALOG_SYSTEM_PROMPT = """You are a research assistant helping a graduate student set up a paper
reproduction project. Your goal is to collect the information needed to
generate an initial code framework.

## Rules
1. Ask ONE question at a time
2. Prefer multiple-choice or single-choice options over open-ended text
3. Maximum {max_questions} questions total; {remaining} remaining
4. If enough information has been collected, return finalize: true
5. Be friendly and encouraging

## Information to Collect
- Improvement targets (data, model, training strategy, etc.)
- Target metrics (e.g., accuracy=0.92)
- Maximum experiment iterations (default: 5)
- Reference papers the student wants to consider

## Output Format
Respond with valid JSON only:
If asking a question:
{{"question": "...", "options": ["...", "..."], "type": "single|multi|text", "finalize": false}}

If information is sufficient:
{{"finalize": true, "config": {{"improvement_targets": [...], "target_metrics": {{...}}, "max_iterations": 5, "summary": "..."}}}}"""


class BrainstormDialog:
    """Guided dialog service for project initialization.

    Manages conversation sessions with a 6-question maximum.
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or settings.ANTHROPIC_API_KEY
        self._is_mock = not self._api_key or self._api_key == "sk-ant-xxx"
        self._sessions: dict[str, list[dict[str, Any]]] = {}

        if not self._is_mock:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self._api_key)

    async def start_session(
        self,
        paper_summary: str,
    ) -> dict[str, Any]:
        """Start a new dialog session.

        Args:
            paper_summary: Summary of the paper being reproduced.

        Returns:
            Dict with session_id and the first question.
        """
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = []

        # Store paper summary as context
        self._sessions[session_id] = [
            {"role": "system", "content": f"Paper summary: {paper_summary}"}
        ]

        first_question = await self.next_question(
            session_id=session_id,
            paper_summary=paper_summary,
            history=[],
        )
        if isinstance(first_question, DialogQuestion):
            self._sessions[session_id].append(
                {
                    "role": "assistant",
                    "content": json.dumps(first_question.model_dump()),
                }
            )

        return {
            "session_id": session_id,
            **first_question.model_dump(),
        }

    async def next_question(
        self,
        session_id: str,
        paper_summary: str,
        history: list[dict[str, Any]],
    ) -> DialogQuestion | ProjectConfig:
        """Generate the next question or finalize the configuration.

        Args:
            session_id: Dialog session ID.
            paper_summary: Paper summary for context.
            history: List of {role, content} conversation turns.

        Returns:
            DialogQuestion if more questions needed, ProjectConfig if done.
        """
        asked_count = len([h for h in history if h.get("role") == "assistant"])
        remaining = MAX_QUESTIONS - asked_count

        if remaining <= 0:
            return self._finalize(history)

        if self._is_mock:
            return self._mock_question(asked_count, history)

        return await self._real_question(paper_summary, history, remaining, asked_count)

    async def answer(
        self,
        session_id: str,
        answer: str,
        paper_summary: str = "",
    ) -> DialogQuestion | ProjectConfig:
        """Process a user's answer and return the next question or final config.

        Args:
            session_id: Dialog session ID.
            answer: The user's answer text.
            paper_summary: Paper summary (only needed for the first answer).

        Returns:
            DialogQuestion or ProjectConfig.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = []

        history = self._sessions[session_id]
        history.append({"role": "user", "content": answer})

        result = await self.next_question(session_id, paper_summary, history)

        if isinstance(result, DialogQuestion):
            history.append(
                {
                    "role": "assistant",
                    "content": json.dumps(result.model_dump()),
                }
            )

        return result

    async def _real_question(
        self,
        paper_summary: str,
        history: list[dict],
        remaining: int,
        asked_count: int,
    ) -> DialogQuestion:
        """Call Anthropic API for the next question."""
        system = DIALOG_SYSTEM_PROMPT.format(
            max_questions=MAX_QUESTIONS,
            remaining=remaining,
        )

        # Build messages from history (skip system messages)
        messages = [
            {"role": h["role"], "content": h["content"]}
            for h in history
            if h["role"] != "system"
        ]

        if not messages:
            messages = [
                {
                    "role": "user",
                    "content": f"I want to reproduce this paper. Paper summary: {paper_summary}",
                }
            ]

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system,
                messages=messages,
            )

            text = response.content[0].text
            return self._parse_question(text)

        except Exception:
            logger.exception("Dialog API call failed")
            return DialogQuestion(
                question="Could you tell me more about your improvement goals?",
                type="text",
            )

    def _parse_question(self, text: str) -> DialogQuestion:
        """Parse JSON question from Claude response."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import re

            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                data = json.loads(match.group(1))
            else:
                return DialogQuestion(question=text, type="text")

        if data.get("finalize"):
            return DialogQuestion(
                question="Config ready",
                finalize=True,
            )

        return DialogQuestion(
            question=data.get("question", "What would you like to improve?"),
            options=data.get("options", []),
            type=data.get("type", "text"),
        )

    def _finalize(self, history: list[dict]) -> ProjectConfig:
        """Build the final project configuration from conversation history."""
        user_answers = [h["content"] for h in history if h.get("role") == "user"]

        return ProjectConfig(
            improvement_targets=["model", "data", "training"],
            target_metrics={"accuracy": 0.92},
            max_iterations=5,
            summary="\n".join(user_answers),
        )

    # ── Mock Mode ────────────────────────────────────────────────

    def _mock_question(
        self,
        asked_count: int,
        history: list[dict],
    ) -> DialogQuestion:
        """Return a preset question sequence for offline development."""
        questions = [
            DialogQuestion(
                question="这篇论文的核心创新是什么？用一句话总结。",
                type="text",
            ),
            DialogQuestion(
                question="你想改进哪些方面？",
                options=[
                    "数据增强/预处理",
                    "模型架构",
                    "训练策略/超参数",
                    "损失函数/优化器",
                    "其他",
                ],
                type="multi",
            ),
            DialogQuestion(
                question="你的目标指标是什么？（如 accuracy=92%）",
                options=["accuracy=90%", "accuracy=92%", "accuracy=95%", "自定义"],
                type="single",
            ),
            DialogQuestion(
                question="最多尝试多少轮实验？",
                options=["3 轮", "5 轮", "10 轮", "不限"],
                type="single",
            ),
            DialogQuestion(
                question="是否有相关的参考论文需要参考？",
                options=["有，我会上传", "没有，让 AI 推荐", "不确定"],
                type="single",
            ),
            DialogQuestion(
                question="还有其他特殊需求或约束吗？",
                type="text",
            ),
        ]

        if asked_count < len(questions):
            return questions[asked_count]

        return DialogQuestion(
            question="信息收集完成，正在生成配置...",
            finalize=True,
        )
