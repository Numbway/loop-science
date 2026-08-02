"""Real-time experiment log, status, and TensorBoard metric monitoring."""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.database import async_session_factory
from app.models.experiment import Experiment
from app.models.experiment_log import ExperimentLog
from app.services.experiment.executor import ExperimentExecutor

_EPOCH_PATTERN = re.compile(r"\bepoch\s*[:=]?\s*(\d+)(?:\s*/\s*(\d+))?", re.IGNORECASE)
_METRIC_PATTERN = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9_./-]*)\s*[:=]\s*"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|nan|inf|-inf)\b",
    re.IGNORECASE,
)
_LOSS_NAMES = ("loss", "error", "perplexity")
_ERROR_MARKERS = ("traceback", "out of memory", "cuda error", "fatal", "exception")
_WARNING_MARKERS = ("warning", "nan", " inf", "=inf", ":inf")


@dataclass(frozen=True)
class LogSummary:
    """Structured values extracted from plain training output."""

    total_lines: int
    completed_epochs: int
    total_epochs: int | None
    latest_metrics: dict[str, float]
    best_metrics: dict[str, float]
    anomalies: tuple[str, ...]


@dataclass(frozen=True)
class ExperimentMetrics:
    """Latest scalar values collected from TensorBoard event files."""

    scalars: dict[str, float]
    steps: dict[str, int]
    event_files: tuple[str, ...]


@dataclass(frozen=True)
class MonitorResult:
    """Final state written by one monitoring run."""

    experiment_id: uuid.UUID
    status: str
    metrics: dict[str, float]
    log_lines: int
    anomalies: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable Celery task result."""
        return {
            "experiment_id": str(self.experiment_id),
            "status": self.status,
            "metrics": self.metrics,
            "log_lines": self.log_lines,
            "anomalies": list(self.anomalies),
        }


def classify_log_level(message: str) -> str:
    """Classify a streamed line for persistence and alerting."""
    lowered = message.lower()
    if any(marker in lowered for marker in _ERROR_MARKERS):
        return "error"
    if any(marker in lowered for marker in _WARNING_MARKERS):
        return "warning"
    return "info"


def parse_train_log(source: Path | str | Iterable[str]) -> LogSummary:
    """Extract epochs, metrics, and common failure signals from training output."""
    if isinstance(source, (Path, str)):
        lines = Path(source).read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        lines = list(source)

    completed_epochs = 0
    total_epochs: int | None = None
    latest_metrics: dict[str, float] = {}
    best_metrics: dict[str, float] = {}
    anomalies: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        epoch_match = _EPOCH_PATTERN.search(line)
        if epoch_match:
            completed_epochs = max(completed_epochs, int(epoch_match.group(1)))
            if epoch_match.group(2):
                total_epochs = max(total_epochs or 0, int(epoch_match.group(2)))

        level = classify_log_level(line)
        if level != "info":
            anomalies.append(f"line {line_number}: {line.strip()}")

        for name, raw_value in _METRIC_PATTERN.findall(line):
            normalized_name = name.lower().replace("/", "_")
            if normalized_name == "epoch":
                continue
            value = float(raw_value)
            if not math.isfinite(value):
                anomaly = (
                    f"line {line_number}: non-finite {normalized_name}={raw_value}"
                )
                if anomaly not in anomalies:
                    anomalies.append(anomaly)
                continue
            latest_metrics[normalized_name] = value
            if normalized_name not in best_metrics:
                best_metrics[normalized_name] = value
            elif any(token in normalized_name for token in _LOSS_NAMES):
                best_metrics[normalized_name] = min(
                    best_metrics[normalized_name], value
                )
            else:
                best_metrics[normalized_name] = max(
                    best_metrics[normalized_name], value
                )

    return LogSummary(
        total_lines=len(lines),
        completed_epochs=completed_epochs,
        total_epochs=total_epochs,
        latest_metrics=latest_metrics,
        best_metrics=best_metrics,
        anomalies=tuple(anomalies),
    )


class ExperimentMonitor:
    """Persist live container output and collect experiment metrics."""

    def __init__(
        self,
        storage_root: Path | str,
        *,
        executor: ExperimentExecutor | None = None,
        session_factory: Any = async_session_factory,
        progress_callback: Callable[[uuid.UUID, str], Awaitable[None]] | None = None,
    ) -> None:
        self._storage_root = Path(storage_root).resolve()
        self._executor = executor or ExperimentExecutor(self._storage_root)
        self._session_factory = session_factory
        self._progress_callback = progress_callback

    def _output_directory(self, experiment_id: uuid.UUID) -> Path:
        output_directory = (
            self._storage_root / "experiment_runs" / str(experiment_id)
        ).resolve()
        if not output_directory.is_relative_to(self._storage_root):
            raise ValueError("Experiment output must remain within storage.")
        return output_directory

    def collect_metrics(self, experiment_id: uuid.UUID) -> ExperimentMetrics:
        """Read the latest scalar value for every TensorBoard tag."""
        try:
            from tensorboard.backend.event_processing.event_accumulator import (
                EventAccumulator,
            )
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError(
                "TensorBoard is required to collect experiment metrics."
            ) from exc

        output_directory = self._output_directory(experiment_id)
        event_files = tuple(
            sorted(output_directory.rglob("events.out.tfevents.*"))
            if output_directory.exists()
            else ()
        )
        latest_events: dict[str, Any] = {}
        for event_file in event_files:
            accumulator = EventAccumulator(
                str(event_file), size_guidance={"scalars": 0}
            )
            accumulator.Reload()
            for tag in accumulator.Tags().get("scalars", []):
                events = accumulator.Scalars(tag)
                if not events:
                    continue
                candidate = events[-1]
                current = latest_events.get(tag)
                if current is None or (candidate.wall_time, candidate.step) > (
                    current.wall_time,
                    current.step,
                ):
                    latest_events[tag] = candidate

        return ExperimentMetrics(
            scalars={tag: float(event.value) for tag, event in latest_events.items()},
            steps={tag: int(event.step) for tag, event in latest_events.items()},
            event_files=tuple(
                str(path.relative_to(output_directory)) for path in event_files
            ),
        )

    async def _persist_log(self, experiment_id: uuid.UUID, message: str) -> None:
        async with self._session_factory() as session:
            session.add(
                ExperimentLog(
                    experiment_id=experiment_id,
                    level=classify_log_level(message),
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    async def _finalize(
        self,
        experiment_id: uuid.UUID,
        *,
        status: str,
        metrics: dict[str, float],
    ) -> None:
        async with self._session_factory() as session:
            experiment = await session.get(Experiment, experiment_id)
            if experiment is None:
                raise LookupError(f"Experiment {experiment_id} does not exist.")
            completed_at = datetime.now(timezone.utc)
            experiment.status = status
            experiment.metrics = metrics
            experiment.completed_at = completed_at
            if experiment.started_at is not None:
                started_at = experiment.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                experiment.duration_seconds = max(
                    0, int((completed_at - started_at).total_seconds())
                )
            await session.commit()

    async def stream(self, experiment_id: uuid.UUID) -> AsyncIterator[str]:
        """Stream and persist container logs as they arrive."""
        async for line in self._executor.stream_logs(experiment_id):
            await self._persist_log(experiment_id, line)
            if self._progress_callback is not None:
                await self._progress_callback(experiment_id, line)
            yield line

    async def monitor_experiment(self, experiment_id: uuid.UUID) -> MonitorResult:
        """Monitor one container until exit and persist its final state."""
        lines: list[str] = []
        try:
            async for line in self.stream(experiment_id):
                lines.append(line)
            container_status = await self._executor.get_status(experiment_id)
            exit_code = await self._executor.get_exit_code(experiment_id)
            tensorboard_metrics = self.collect_metrics(experiment_id)
            summary = parse_train_log(lines)
            metrics = {**summary.latest_metrics, **tensorboard_metrics.scalars}
            status = (
                "completed"
                if container_status == "exited" and exit_code == 0
                else "failed"
            )
            await self._finalize(
                experiment_id,
                status=status,
                metrics=metrics,
            )
            return MonitorResult(
                experiment_id=experiment_id,
                status=status,
                metrics=metrics,
                log_lines=summary.total_lines,
                anomalies=summary.anomalies,
            )
        except Exception as exc:
            await self._persist_log(
                experiment_id,
                f"Experiment monitoring failed: {type(exc).__name__}: {exc}",
            )
            await self._finalize(experiment_id, status="failed", metrics={})
            raise
