"""Bounded automatic recovery for common experiment failures."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from app.schemas.ai import AgentResult

RecoveryCategory = Literal[
    "cuda_out_of_memory",
    "cuda_unavailable",
    "non_finite_metric",
    "missing_dependency",
    "disk_full",
    "runtime_error",
]
RecoveryStatus = Literal["retrying", "recovered", "needs_attention"]

RECOVERY_METADATA_KEY = "_recovery"
MAX_RECOVERY_ATTEMPTS = 1

_MISSING_MODULE_PATTERN = re.compile(
    r"(?:ModuleNotFoundError|ImportError).*?(?:named|import)\s+['\"]?([A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)


class RuntimeRepairAgent(Protocol):
    async def fix_runtime_error(self, error_log: str) -> AgentResult: ...


@dataclass(frozen=True)
class FailureDiagnosis:
    category: RecoveryCategory
    title: str
    user_message: str
    suggested_action: str


@dataclass(frozen=True)
class RecoveryOutcome:
    """One recovery decision ready to persist and publish."""

    fixed: bool
    retry: bool
    requires_commit: bool
    category: RecoveryCategory
    status: RecoveryStatus
    attempt: int
    max_attempts: int
    message: str
    action: str
    config: dict[str, Any]
    log_messages: tuple[str, ...]
    modified_files: tuple[str, ...] = ()

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self.config.get(RECOVERY_METADATA_KEY, {}))

    def as_unresolved(self, *, message: str, action: str) -> RecoveryOutcome:
        config = copy.deepcopy(self.config)
        metadata = dict(config.get(RECOVERY_METADATA_KEY, {}))
        metadata.update(
            {
                "status": "needs_attention",
                "message": message,
                "action": action,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        config[RECOVERY_METADATA_KEY] = metadata
        return replace(
            self,
            fixed=False,
            retry=False,
            requires_commit=False,
            status="needs_attention",
            message=message,
            action=action,
            config=config,
            log_messages=(
                *self.log_messages,
                f"[auto-recovery] Manual action required: {message} {action}",
            ),
        )


def classify_failure(error_log: str) -> FailureDiagnosis:
    """Map raw runtime output to a stable, user-facing failure category."""
    normalized = error_log.casefold()
    if "cuda out of memory" in normalized or "cudnn_status_alloc_failed" in normalized:
        return FailureDiagnosis(
            category="cuda_out_of_memory",
            title="GPU memory exhausted",
            user_message="GPU memory was exhausted during training.",
            suggested_action="Reduce batch size or model memory usage before retrying.",
        )
    if any(
        marker in normalized
        for marker in (
            "cuda is not available",
            "no cuda gpus are available",
            "cuda driver",
            "nvidia driver",
        )
    ):
        return FailureDiagnosis(
            category="cuda_unavailable",
            title="GPU unavailable",
            user_message="The configured GPU runtime is unavailable.",
            suggested_action="Run this attempt on CPU or restore the GPU runtime.",
        )
    if any(
        marker in normalized
        for marker in (
            "non-finite",
            "loss=nan",
            "loss: nan",
            "loss=inf",
            "loss: inf",
            "found nan",
        )
    ):
        return FailureDiagnosis(
            category="non_finite_metric",
            title="Training became numerically unstable",
            user_message="Training produced a non-finite loss or metric.",
            suggested_action="Lower the learning rate and verify input normalization.",
        )
    if _MISSING_MODULE_PATTERN.search(error_log):
        return FailureDiagnosis(
            category="missing_dependency",
            title="Python dependency missing",
            user_message="The experiment imports a package unavailable to the executor.",
            suggested_action="Add the dependency to the project requirements and image.",
        )
    if "no space left on device" in normalized or "disk quota exceeded" in normalized:
        return FailureDiagnosis(
            category="disk_full",
            title="Experiment storage is full",
            user_message="The executor cannot write additional experiment artifacts.",
            suggested_action="Free storage or archive old checkpoints, then retry.",
        )
    return FailureDiagnosis(
        category="runtime_error",
        title="Experiment runtime error",
        user_message="The experiment stopped because of a runtime code error.",
        suggested_action="Review the latest error log and repair the experiment branch.",
    )


def recovery_metadata(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return validated public recovery metadata from an experiment config."""
    value = (config or {}).get(RECOVERY_METADATA_KEY)
    if not isinstance(value, dict):
        return None
    required = {
        "status",
        "category",
        "attempt",
        "max_attempts",
        "message",
        "action",
        "updated_at",
    }
    return dict(value) if required.issubset(value) else None


def public_experiment_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Hide internal recovery bookkeeping from the regular config panel."""
    public_config = copy.deepcopy(config or {})
    public_config.pop(RECOVERY_METADATA_KEY, None)
    return public_config


def _find_numeric_setting(
    value: dict[str, Any],
    keys: tuple[str, ...],
) -> tuple[dict[str, Any], str, float] | None:
    for key, candidate in value.items():
        if key.casefold() in keys and isinstance(candidate, (int, float)):
            return value, key, float(candidate)
    for key, candidate in value.items():
        if isinstance(candidate, dict):
            found = _find_numeric_setting(candidate, keys)
            if found is not None:
                return found
    return None


class AutoErrorHandler:
    """Try one safe recovery, then require explicit user intervention."""

    def __init__(
        self,
        *,
        repair_agent: RuntimeRepairAgent | None = None,
        max_attempts: int = MAX_RECOVERY_ATTEMPTS,
    ) -> None:
        self._repair_agent = repair_agent
        self._max_attempts = max(0, max_attempts)

    async def handle(
        self,
        error_log: str,
        config: dict[str, Any] | None,
    ) -> RecoveryOutcome:
        diagnosis = classify_failure(error_log)
        next_config = copy.deepcopy(config or {})
        previous = recovery_metadata(next_config) or {}
        previous_attempts = int(previous.get("attempt", 0))
        attempt = previous_attempts + 1

        if previous_attempts >= self._max_attempts:
            return self._outcome(
                diagnosis=diagnosis,
                config=next_config,
                attempt=previous_attempts,
                fixed=False,
                retry=False,
                requires_commit=False,
                message=(
                    "Automatic recovery already ran once and will not retry again "
                    "without review."
                ),
                action=diagnosis.suggested_action,
                details=("Recovery limit reached; automatic retry suppressed.",),
            )

        if diagnosis.category == "cuda_out_of_memory":
            setting = _find_numeric_setting(next_config, ("batch_size", "batch-size"))
            if setting is None:
                next_config["batch_size"] = 32
                old_value, new_value = "default", 32
            else:
                owner, key, current = setting
                new_value = max(1, int(current) // 2)
                owner[key] = new_value
                old_value = int(current)
            return self._outcome(
                diagnosis=diagnosis,
                config=next_config,
                attempt=attempt,
                fixed=True,
                retry=True,
                requires_commit=False,
                message="GPU memory pressure was detected; the batch size was reduced.",
                action=f"Retrying automatically with batch_size={new_value}.",
                details=(
                    f"Adjusted batch size from {old_value} to {new_value}.",
                ),
            )

        if diagnosis.category == "cuda_unavailable":
            next_config["device"] = "cpu"
            return self._outcome(
                diagnosis=diagnosis,
                config=next_config,
                attempt=attempt,
                fixed=True,
                retry=True,
                requires_commit=False,
                message="The GPU runtime is unavailable; this attempt was moved to CPU.",
                action="Retrying automatically with device=cpu.",
                details=("Set experiment device override to CPU.",),
            )

        if diagnosis.category == "non_finite_metric":
            setting = _find_numeric_setting(
                next_config,
                ("learning_rate", "learning-rate", "lr"),
            )
            if setting is None:
                next_config["learning_rate"] = 0.0005
                old_value, new_value = "default", 0.0005
            else:
                owner, key, current = setting
                new_value = max(current * 0.5, 1e-8)
                owner[key] = new_value
                old_value = current
            return self._outcome(
                diagnosis=diagnosis,
                config=next_config,
                attempt=attempt,
                fixed=True,
                retry=True,
                requires_commit=False,
                message="Numerical instability was detected; the learning rate was reduced.",
                action=f"Retrying automatically with learning_rate={new_value:g}.",
                details=(
                    f"Adjusted learning rate from {old_value} to {new_value:g}.",
                ),
            )

        if diagnosis.category == "disk_full":
            return self._outcome(
                diagnosis=diagnosis,
                config=next_config,
                attempt=attempt,
                fixed=False,
                retry=False,
                requires_commit=False,
                message=diagnosis.user_message,
                action=diagnosis.suggested_action,
                details=(
                    "Automatic deletion is disabled to protect experiment artifacts.",
                ),
            )

        if self._repair_agent is None:
            return self._outcome(
                diagnosis=diagnosis,
                config=next_config,
                attempt=attempt,
                fixed=False,
                retry=False,
                requires_commit=False,
                message=diagnosis.user_message,
                action=diagnosis.suggested_action,
                details=("No runtime repair agent is available.",),
            )

        agent_result = await self._repair_agent.fix_runtime_error(error_log)
        if not agent_result.success:
            return self._outcome(
                diagnosis=diagnosis,
                config=next_config,
                attempt=attempt,
                fixed=False,
                retry=False,
                requires_commit=False,
                message="The repair agent could not validate a safe fix.",
                action=diagnosis.suggested_action,
                details=tuple(agent_result.errors[:3]) or ("Agent validation failed.",),
            )
        modified_files = tuple(dict.fromkeys(agent_result.modified_files))
        return self._outcome(
            diagnosis=diagnosis,
            config=next_config,
            attempt=attempt,
            fixed=True,
            retry=True,
            requires_commit=True,
            message="The repair agent produced and validated a runtime fix.",
            action="Committing the repair before one automatic retry.",
            details=(
                f"Repair agent completed in {agent_result.iterations} iteration(s).",
            ),
            modified_files=modified_files,
        )

    def _outcome(
        self,
        *,
        diagnosis: FailureDiagnosis,
        config: dict[str, Any],
        attempt: int,
        fixed: bool,
        retry: bool,
        requires_commit: bool,
        message: str,
        action: str,
        details: tuple[str, ...],
        modified_files: tuple[str, ...] = (),
    ) -> RecoveryOutcome:
        status: RecoveryStatus = "retrying" if retry else "needs_attention"
        metadata = {
            "status": status,
            "category": diagnosis.category,
            "attempt": attempt,
            "max_attempts": self._max_attempts,
            "message": message,
            "action": action,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        config[RECOVERY_METADATA_KEY] = metadata
        return RecoveryOutcome(
            fixed=fixed,
            retry=retry,
            requires_commit=requires_commit,
            category=diagnosis.category,
            status=status,
            attempt=attempt,
            max_attempts=self._max_attempts,
            message=message,
            action=action,
            config=config,
            log_messages=(
                (
                    f"[auto-recovery] Detected {diagnosis.category}: "
                    f"{diagnosis.user_message}"
                ),
                *(f"[auto-recovery] {detail}" for detail in details),
                f"[auto-recovery] {action}",
            ),
            modified_files=modified_files,
        )
