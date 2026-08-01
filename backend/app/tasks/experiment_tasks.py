"""Celery tasks for isolated experiment execution."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.core.celery_app import celery_app
from app.core.config import settings
from app.services.experiment import ExperimentExecutor


def should_continue(
    *,
    project_status: str,
    completed_iterations: int,
    max_iterations: int,
    target_metrics: dict[str, float],
    latest_metrics: dict[str, float] | None,
) -> bool:
    """Return whether a project may schedule another experiment iteration."""
    if project_status != "running" or completed_iterations >= max_iterations:
        return False
    metrics = latest_metrics or {}
    return not target_metrics or not all(metrics.get(key, float("-inf")) >= value for key, value in target_metrics.items())


@celery_app.task(name="experiments.run", bind=True)
def run_experiment_task(
    self: Any,
    experiment_id: str,
    code_path: str,
    config: dict[str, Any],
) -> dict[str, str]:
    """Schedule one isolated experiment container from a Celery worker."""
    result = asyncio.run(
        ExperimentExecutor(settings.STORAGE_PATH).run_experiment(
            uuid.UUID(experiment_id), code_path, config
        )
    )
    return {
        "experiment_id": str(result.experiment_id),
        "container_id": result.container_id,
        "status": result.status,
        "output_path": str(result.output_path),
    }
