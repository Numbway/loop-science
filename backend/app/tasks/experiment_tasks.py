"""Celery tasks for isolated experiment execution."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import async_session_factory
from app.models.experiment import Experiment
from app.models.project import Project
from app.services.experiment import ExperimentExecutor
from app.services.git import GitService


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


async def _next_experiment_id(project_id: uuid.UUID) -> str | None:
    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        if project is None:
            return None
        completed = len(
            (
                await session.scalars(
                    select(Experiment).where(
                        Experiment.project_id == project.id,
                        Experiment.status == "completed",
                    )
                )
            ).all()
        )
        latest = (
            await session.scalars(
                select(Experiment)
                .where(
                    Experiment.project_id == project.id,
                    Experiment.metrics.is_not(None),
                )
                .order_by(Experiment.created_at.desc())
            )
        ).first()
        if not should_continue(
            project_status=project.status,
            completed_iterations=completed,
            max_iterations=project.max_iterations,
            target_metrics=project.target_metrics,
            latest_metrics=latest.metrics if latest else None,
        ):
            return None
        pending = (
            await session.scalars(
                select(Experiment)
                .where(
                    Experiment.project_id == project.id,
                    Experiment.status == "pending",
                )
                .order_by(Experiment.created_at)
            )
        ).first()
        return str(pending.id) if pending else None


async def _start_experiment(experiment_id: uuid.UUID) -> dict[str, str]:
    async with async_session_factory() as session:
        experiment = await session.get(Experiment, experiment_id)
        if experiment is None or experiment.status != "pending":
            return {"experiment_id": str(experiment_id), "status": "not_scheduled"}
        project = await session.get(Project, experiment.project_id)
        if project is None or project.status != "running":
            return {"experiment_id": str(experiment_id), "status": "not_scheduled"}
        experiment.status = "running"
        experiment.started_at = datetime.now(UTC)
        await session.commit()
        try:
            GitService(settings.STORAGE_PATH).checkout_branch(project.id, experiment.git_branch)
            result = await ExperimentExecutor(settings.STORAGE_PATH).run_experiment(
                experiment.id,
                GitService(settings.STORAGE_PATH)._repository_path(project.id),
                experiment.config,
            )
        except Exception:
            experiment.status = "failed"
            experiment.completed_at = datetime.now(UTC)
            await session.commit()
            raise
        return {"experiment_id": str(result.experiment_id), "container_id": result.container_id, "status": result.status}


@celery_app.task(name="experiments.run", bind=True)
def run_experiment_task(self: Any, experiment_id: str) -> dict[str, str]:
    """Schedule one isolated experiment container from a Celery worker."""
    return asyncio.run(_start_experiment(uuid.UUID(experiment_id)))


@celery_app.task(name="experiments.iterate")
def iterate_experiment_loop_task(project_id: str) -> dict[str, str]:
    """Queue the next pending experiment only while project limits allow it."""
    experiment_id = asyncio.run(_next_experiment_id(uuid.UUID(project_id)))
    if experiment_id is None:
        return {"project_id": project_id, "status": "stopped"}
    run_experiment_task.delay(experiment_id)
    return {"project_id": project_id, "experiment_id": experiment_id, "status": "queued"}
