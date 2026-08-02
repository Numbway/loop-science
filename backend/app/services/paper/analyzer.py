"""LLM-backed scientific paper analysis."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.schemas.project_wizard import PaperAnalysisResponse
from app.services.ai.provider import build_model_client, create_text_completion

ANALYSIS_SYSTEM_PROMPT = """You are a senior machine-learning reproduction engineer.
Read the supplied scientific paper content and produce an implementation-oriented
analysis. Do not invent datasets, hardware, metrics, or hyperparameters. When the
paper omits an important detail, record that uncertainty under reproducibility_risks.
The fields method_steps, datasets, metrics, implementation_requirements,
compute_requirements, and reproducibility_risks MUST always be JSON arrays of
strings, including when there is only one item.
Return one valid JSON object and no markdown."""

LIST_FIELDS = (
    "method_steps",
    "datasets",
    "metrics",
    "implementation_requirements",
    "compute_requirements",
    "reproducibility_risks",
)


class PaperAnalysisError(RuntimeError):
    """Raised when the provider cannot produce a usable analysis."""


class PaperAnalyzer:
    """Analyze parsed paper content with a researcher-supplied API key."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        base_url: str = "https://api.anthropic.com",
        provider: str = "anthropic",
    ) -> None:
        self._provider = provider
        self._client = build_model_client(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
        )
        self._model = model

    async def analyze(self, paper_content: dict[str, Any]) -> PaperAnalysisResponse:
        prompt = f"""Analyze this parsed paper for a reproducible training run.

Return exactly these JSON fields:
- summary: concise overview
- research_problem: the task and hypothesis
- method_steps: ordered implementation steps
- datasets: explicitly named datasets or "Not specified"
- metrics: explicitly named evaluation metrics
- implementation_requirements: libraries, preprocessing, model and training details
- compute_requirements: hardware or scale stated/inferred; label inferences clearly
- reproducibility_risks: missing or ambiguous details

Type requirements:
- summary and research_problem MUST be JSON strings
- method_steps, datasets, metrics, implementation_requirements,
  compute_requirements, and reproducibility_risks MUST be JSON arrays of strings
- Never return a scalar string for an array field; use ["Not specified"] instead

Paper content:
{json.dumps(paper_content, ensure_ascii=False)[:60000]}"""

        def request() -> Any:
            return create_text_completion(
                client=self._client,
                provider=self._provider,
                model=self._model,
                max_tokens=4096,
                system=ANALYSIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        try:
            response = await asyncio.to_thread(request)
            text = str(response)
            data = self._normalize_analysis(self._parse_json(text))
            return PaperAnalysisResponse.model_validate(
                {**data, "model": self._model}
            )
        except Exception as exc:  # noqa: BLE001 - provider response boundary
            raise PaperAnalysisError(
                f"Paper analysis failed: {type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if not match:
                raise PaperAnalysisError("The model did not return valid JSON.")
            value = json.loads(match.group(1))
        if not isinstance(value, dict):
            raise PaperAnalysisError("The model returned an invalid analysis object.")
        return value

    @classmethod
    def _normalize_analysis(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Coerce common provider output variations into the response schema."""
        normalized = dict(value)
        normalized["summary"] = cls._text_value(value.get("summary"))
        normalized["research_problem"] = cls._text_value(
            value.get("research_problem")
        )
        for field in LIST_FIELDS:
            normalized[field] = cls._list_value(value.get(field))
        return normalized

    @staticmethod
    def _text_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            return "; ".join(PaperAnalyzer._text_value(item) for item in value)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @classmethod
    def _list_value(cls, value: Any) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple, set)) else [value]
        result = [cls._text_value(item).strip() for item in items]
        return [item for item in result if item]
