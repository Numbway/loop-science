"""Experiment Diagnostician — analyze results and generate improvement suggestions.

Uses Anthropic SDK directly (not Agent SDK) for pure analysis tasks.
Auto-falls back to mock mode when no valid API key is configured.
"""

import json
import logging
from typing import Any

from app.core.config import settings
from app.schemas.ai import Diagnosis, Suggestion

logger = logging.getLogger(__name__)

DIAGNOSIS_SYSTEM_PROMPT = """You are an expert machine learning experiment diagnostician.
Analyze experiment results, compare with reference papers, and generate
actionable improvement suggestions.

## Output Format
You MUST respond with valid JSON only:
{
  "problem_analysis": "Analysis of what problems exist in the current experiment",
  "suggestions": [
    {
      "priority": "high|medium|low",
      "method": "Specific method name",
      "reason": "Why this improvement is needed",
      "evidence": ["Reference paper X mentions...", "Reference paper Y proves..."],
      "expected_improvement": "Expected improvement magnitude",
      "code_changes": {"filename": "Specific code change description"}
    }
  ],
  "top_recommendation_index": 0
}

## Rules
- Each suggestion must be actionable at the code level — no vague advice
- Always cite specific reference papers as evidence
- Prioritize suggestions by expected impact
- Consider the gap between current metrics and target metrics"""


class Diagnostician:
    """Analyze experiment results and suggest improvements.

    Uses Anthropic SDK for real mode, with prompt caching for reference papers.
    Falls back to mock mode with simulated analysis when no API key.
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or settings.ANTHROPIC_API_KEY
        self._is_mock = not self._api_key or self._api_key == "sk-ant-xxx"

        if not self._is_mock:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self._api_key)

    async def diagnose(
        self,
        experiment_metrics: dict[str, Any],
        experiment_log: str = "",
        parent_metrics: dict[str, Any] | None = None,
        target_metrics: dict[str, Any] | None = None,
        reference_papers: list[dict[str, Any]] | None = None,
    ) -> Diagnosis:
        """Generate structured diagnosis and improvement suggestions.

        Args:
            experiment_metrics: Current experiment metrics (e.g., {"accuracy": 0.85, "loss": 0.42}).
            experiment_log: Training log summary.
            parent_metrics: Metrics from parent experiment node (for comparison).
            target_metrics: Target metrics the student wants to achieve.
            reference_papers: Up to 5 reference papers with title, abstract, key_contributions.

        Returns:
            Diagnosis with problem analysis and ranked suggestions.
        """
        if self._is_mock:
            return self._mock_diagnose(experiment_metrics, target_metrics)

        return await self._real_diagnose(
            experiment_metrics,
            experiment_log,
            parent_metrics,
            target_metrics,
            reference_papers or [],
        )

    async def _real_diagnose(
        self,
        metrics: dict,
        log: str,
        parent_metrics: dict | None,
        target_metrics: dict | None,
        papers: list[dict],
    ) -> Diagnosis:
        """Call Anthropic API for real diagnosis."""
        # Build reference papers content (for prompt caching)
        papers_text = "\n\n".join([
            f"### Paper {i+1}: {p.get('title', 'Unknown')}\n"
            f"Abstract: {p.get('abstract', 'N/A')}\n"
            f"Key Contributions: {p.get('key_contributions', [])}"
            for i, p in enumerate(papers[:5])
        ])

        user_message = f"""## Current Experiment
Metrics: {json.dumps(metrics, indent=2)}
Log Summary: {log[:2000] if log else 'No log available'}

## Parent Experiment (for comparison)
{json.dumps(parent_metrics, indent=2) if parent_metrics else 'None (this is the first experiment)'}

## Target Metrics
{json.dumps(target_metrics, indent=2) if target_metrics else 'Not specified'}

## Reference Papers
{papers_text if papers_text else 'No reference papers provided'}

Analyze the experiment and generate improvement suggestions in the specified JSON format."""

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=[
                    {"type": "text", "text": DIAGNOSIS_SYSTEM_PROMPT},
                    {
                        "type": "text",
                        "text": f"## Reference Papers (cached)\n{papers_text}",
                        "cache_control": {"type": "ephemeral"},
                    },
                ] if papers_text else DIAGNOSIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            text = response.content[0].text
            return self._parse_diagnosis(text)

        except Exception as e:
            logger.error(f"Diagnosis API call failed: {e}")
            return Diagnosis(
                problem_analysis=f"Diagnosis failed: {e}",
                suggestions=[],
                top_recommendation_index=0,
            )

    def _parse_diagnosis(self, text: str) -> Diagnosis:
        """Parse JSON diagnosis from Claude response."""
        try:
            # Try direct JSON parse
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            import re

            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                data = json.loads(match.group(1))
            else:
                return Diagnosis(problem_analysis=text)

        suggestions = [
            Suggestion(
                priority=s.get("priority", "medium"),
                method=s.get("method", ""),
                reason=s.get("reason", ""),
                evidence=s.get("evidence", []),
                expected_improvement=s.get("expected_improvement", ""),
                code_changes=s.get("code_changes", {}),
            )
            for s in data.get("suggestions", [])
        ]

        return Diagnosis(
            problem_analysis=data.get("problem_analysis", ""),
            suggestions=suggestions,
            top_recommendation_index=data.get("top_recommendation_index", 0),
        )

    # ── Mock Mode ────────────────────────────────────────────────

    def _mock_diagnose(
        self,
        metrics: dict,
        target_metrics: dict | None,
    ) -> Diagnosis:
        """Generate a simulated diagnosis for offline development."""
        target = target_metrics or {}

        # Build problem analysis based on metrics
        problems: list[str] = []
        suggestions: list[Suggestion] = []

        acc = metrics.get("accuracy", metrics.get("acc", 0))
        loss = metrics.get("loss", 0)
        target_acc = target.get("accuracy", target.get("acc", 0.95))

        if acc < target_acc:
            gap = target_acc - acc
            problems.append(
                f"Accuracy is {acc:.1%}, {gap:.1%} below target of {target_acc:.1%}."
            )

        if loss > 0.5:
            problems.append(f"Loss is high ({loss:.3f}), suggesting optimization issues.")

        if not problems:
            problems.append("Metrics are on track. Consider fine-tuning for further gains.")

        # Generate suggestions based on gap analysis
        if acc < target_acc:
            suggestions.append(
                Suggestion(
                    priority="high",
                    method="Add BatchNorm + Dropout regularization",
                    reason="Training instability detected; regularization can improve "
                    "generalization and reduce overfitting.",
                    evidence=[
                        "BatchNorm (Ioffe & Szegedy 2015): improves training stability, "
                        "reported +6.8% on ImageNet",
                        "Dropout (Srivastava et al. 2014): reduces overfitting, "
                        "typical improvement of 1-3%",
                    ],
                    expected_improvement="2-5% accuracy improvement",
                    code_changes={
                        "model.py": "Add nn.BatchNorm2d after each conv layer, "
                        "add nn.Dropout(0.3) before classifier"
                    },
                )
            )

            suggestions.append(
                Suggestion(
                    priority="medium",
                    method="Learning rate scheduling with warmup",
                    reason="Current fixed LR may cause convergence issues. "
                    "Cosine annealing with warmup is standard practice.",
                    evidence=[
                        "He et al. (2019): warmup prevents early training instability",
                        "Loshchilov & Hutter (2017): cosine annealing improves final accuracy",
                    ],
                    expected_improvement="1-3% accuracy improvement",
                    code_changes={
                        "train.py": "Add torch.optim.lr_scheduler.CosineAnnealingWarmRestarts",
                        "config.yaml": "Add warmup_epochs: 5, min_lr: 1e-6",
                    },
                )
            )

        suggestions.append(
            Suggestion(
                priority="low",
                method="Data augmentation (RandAugment)",
                reason="Additional data diversity can improve model robustness.",
                evidence=[
                    "Cubuk et al. (2020): RandAugment achieves SOTA with simple augmentation",
                ],
                expected_improvement="1-2% accuracy improvement",
                code_changes={
                    "data.py": "Add RandAugment transforms to training pipeline"
                },
            )
        )

        problem_analysis = " ".join(problems) if problems else "No major issues detected."

        return Diagnosis(
            problem_analysis=problem_analysis,
            suggestions=suggestions,
            top_recommendation_index=0,
        )