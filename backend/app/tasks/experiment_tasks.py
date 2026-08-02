"""Celery tasks for isolated experiment execution."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import async_session_factory
from app.models.experiment import Experiment
from app.models.experiment_log import ExperimentLog
from app.models.credential_profile import CredentialProfile
from app.models.project import Project
from app.schemas.realtime import ProjectRealtimeEvent
from app.services.ai.code_agent import CodeAgent
from app.services.credentials import decrypt_credentials
from app.services.experiment import (
    AutoErrorHandler,
    ExperimentExecutor,
    ExperimentMonitor,
    RemoteExperimentExecutor,
    RecoveryOutcome,
    parse_train_log,
    recovery_metadata,
)
from app.services.git import GitService, GitServiceError
from app.services.realtime import RealtimeEventBroker, publish_project_event


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
    return not target_metrics or not all(
        metrics.get(key, float("-inf")) >= value
        for key, value in target_metrics.items()
    )


async def _executor_for_project(project: Project, session: Any) -> Any:
    """Build the local or verified SSH executor selected during preparation."""
    has_preparation_field = hasattr(project, "preparation_config")
    preparation = getattr(project, "preparation_config", {}) or {}
    data_config = preparation.get("data") or {}
    local_data_path = data_config.get("storage_path")
    profile_id = getattr(project, "ssh_credential_profile_id", None)
    if profile_id:
        profile = await session.get(CredentialProfile, profile_id)
        if (
            profile is None
            or profile.user_id != project.user_id
            or profile.kind != "ssh"
            or not profile.verified
        ):
            raise RuntimeError("The selected SSH configuration is unavailable.")
        execution = dict(profile.public_config or {})
        ssh_secret = decrypt_credentials(profile.encrypted_credentials)
        remote_data_path = data_config.get("remote_path")
        if (
            data_config.get("source") != "remote"
            or data_config.get("ssh_profile_id") != str(profile.id)
            or not remote_data_path
            or not ssh_secret
        ):
            raise RuntimeError(
                "Remote execution credentials or selected data are unavailable."
            )
        return RemoteExperimentExecutor(
            settings.STORAGE_PATH,
            execution,
            ssh_secret,
            remote_data_path,
        )
    if has_preparation_field:
        raise RuntimeError(
            "This project has no verified SSH execution target. "
            "Complete experiment preparation before scheduling it."
        )
    if local_data_path:
        return ExperimentExecutor(
            settings.STORAGE_PATH,
            data_path=local_data_path,
        )
    return ExperimentExecutor(settings.STORAGE_PATH)


async def _llm_connection_for_project(
    project: Project,
    session: Any,
) -> dict[str, str]:
    """Load the reusable model connection selected by a project."""
    profile_id = getattr(project, "ai_credential_profile_id", None)
    if not profile_id:
        return {}
    profile = await session.get(CredentialProfile, profile_id)
    if (
        profile is None
        or profile.user_id != project.user_id
        or profile.kind != "llm"
        or not profile.verified
    ):
        return {}
    public = profile.public_config or {}
    api_key = str(
        decrypt_credentials(profile.encrypted_credentials).get("api_key") or ""
    )
    if not api_key:
        return {}
    return {
        "api_key": api_key,
        "model": str(public.get("model") or settings.ANTHROPIC_MODEL),
        "base_url": str(
            public.get("base_url") or settings.ANTHROPIC_BASE_URL
        ),
        "provider": str(public.get("provider") or "anthropic"),
    }


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


async def _cleanup_container_for_retry(experiment_id: uuid.UUID) -> str | None:
    """Remove an exited container so its stable experiment name can be reused."""
    try:
        async with async_session_factory() as session:
            experiment = await session.get(Experiment, experiment_id)
            if experiment is None:
                return None
            project = await session.get(Project, experiment.project_id)
            if project is None:
                return None
            executor = await _executor_for_project(project, session)
        await executor.cleanup(experiment_id)
    except Exception as error:  # noqa: BLE001 - Docker SDK boundary
        detail = f"{type(error).__name__}: {error}"
        normalized = detail.casefold()
        if "not found" in normalized or "404" in normalized:
            return None
        return type(error).__name__
    return None


async def _attempt_error_recovery(
    experiment_id: uuid.UUID,
    error_log: str,
) -> RecoveryOutcome:
    """Persist one bounded repair attempt and enqueue a safe retry when possible."""
    async with async_session_factory() as session:
        experiment = await session.get(Experiment, experiment_id)
        if experiment is None:
            raise LookupError(f"Experiment {experiment_id} does not exist.")
        project = await session.get(Project, experiment.project_id)
        if project is None:
            raise LookupError(f"Project {experiment.project_id} does not exist.")

        git_service = GitService(settings.STORAGE_PATH)
        repair_agent = None
        repository_error = ""
        try:
            git_service.checkout_branch(project.id, experiment.git_branch)
            llm_connection = await _llm_connection_for_project(project, session)
            repair_agent = CodeAgent(
                git_service._repository_path(project.id),
                **llm_connection,
            )
        except GitServiceError as error:
            repository_error = f"{error.message} {error.hint}"

        handler = AutoErrorHandler(repair_agent=repair_agent)
        try:
            outcome = await handler.handle(error_log[-5_000:], experiment.config)
        except Exception as error:  # noqa: BLE001 - AI provider boundary
            fallback = await AutoErrorHandler().handle(
                error_log[-5_000:],
                experiment.config,
            )
            outcome = fallback.as_unresolved(
                message="Automatic recovery stopped before a safe fix was validated.",
                action=(
                    "Review the recovery log and repair the experiment branch manually. "
                    f"Internal boundary: {type(error).__name__}."
                ),
            )

        if outcome.requires_commit:
            if repository_error:
                outcome = outcome.as_unresolved(
                    message="The repair could not be committed to the experiment branch.",
                    action=repository_error,
                )
            else:
                try:
                    commit = git_service.commit_changes(
                        project.id,
                        f"Auto-recover experiment {experiment.node_id}",
                    )
                except GitServiceError as error:
                    outcome = outcome.as_unresolved(
                        message="The repair agent did not leave a committable validated fix.",
                        action=f"{error.message} {error.hint}",
                    )
                else:
                    outcome = replace(
                        outcome,
                        log_messages=(
                            *outcome.log_messages,
                            (
                                "[auto-recovery] Committed validated repair "
                                f"{commit.sha[:10]} on {commit.branch_name}."
                            ),
                        ),
                    )

        if outcome.retry:
            cleanup_error = await _cleanup_container_for_retry(experiment.id)
            if cleanup_error:
                outcome = outcome.as_unresolved(
                    message="The failed container could not be prepared for a safe retry.",
                    action=(
                        "Remove the stopped container, then retry manually. "
                        f"Cleanup boundary: {cleanup_error}."
                    ),
                )

        experiment.config = outcome.config
        for message in outcome.log_messages:
            session.add(
                ExperimentLog(
                    experiment_id=experiment.id,
                    level="warning" if outcome.retry else "error",
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        if outcome.retry:
            experiment.status = "pending"
            experiment.started_at = None
            experiment.completed_at = None
            experiment.duration_seconds = None
        await session.commit()

    await publish_project_event(
        ProjectRealtimeEvent(
            type="experiment_recovery",
            project_id=project.id,
            experiment_id=experiment.id,
            status="pending" if outcome.retry else "failed",
            recovery=outcome.metadata,
        )
    )
    if outcome.retry:
        run_experiment_task.delay(str(experiment.id))
    return outcome


async def _mark_recovery_succeeded(
    experiment_id: uuid.UUID,
) -> tuple[uuid.UUID, dict[str, Any]] | None:
    """Close the recovery audit trail after a successful automatic retry."""
    async with async_session_factory() as session:
        experiment = await session.get(Experiment, experiment_id)
        if experiment is None:
            return None
        metadata = recovery_metadata(experiment.config)
        if metadata is None or metadata["status"] != "retrying":
            return None
        metadata.update(
            {
                "status": "recovered",
                "message": "The automatic retry completed successfully.",
                "action": "No further action is required.",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        config = dict(experiment.config or {})
        config["_recovery"] = metadata
        experiment.config = config
        session.add(
            ExperimentLog(
                experiment_id=experiment.id,
                level="info",
                message="[auto-recovery] Automatic retry completed successfully.",
                timestamp=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        return experiment.project_id, metadata


async def _start_experiment(experiment_id: uuid.UUID) -> dict[str, str]:
    async with async_session_factory() as session:
        experiment = await session.get(Experiment, experiment_id)
        if experiment is None or experiment.status != "pending":
            return {"experiment_id": str(experiment_id), "status": "not_scheduled"}
        project = await session.get(Project, experiment.project_id)
        if project is None or project.status != "running":
            return {"experiment_id": str(experiment_id), "status": "not_scheduled"}
        experiment.status = "running"
        experiment.started_at = datetime.now(timezone.utc)
        await session.commit()
        await publish_project_event(
            ProjectRealtimeEvent(
                type="experiment_started",
                project_id=project.id,
                experiment_id=experiment.id,
                status="running",
                started_at=experiment.started_at,
            )
        )
        try:
            GitService(settings.STORAGE_PATH).checkout_branch(
                project.id, experiment.git_branch
            )
            result = await (
                await _executor_for_project(project, session)
            ).run_experiment(
                experiment.id,
                GitService(settings.STORAGE_PATH)._repository_path(project.id),
                experiment.config,
            )
        except Exception as error:
            experiment.status = "failed"
            experiment.completed_at = datetime.now(timezone.utc)
            await session.commit()
            error_text = f"Experiment launch failed: {type(error).__name__}: {error}"
            await publish_project_event(
                ProjectRealtimeEvent(
                    type="experiment_failed",
                    project_id=project.id,
                    experiment_id=experiment.id,
                    status="failed",
                    completed_at=experiment.completed_at,
                    error=error_text,
                )
            )
            recovery = await _attempt_error_recovery(experiment.id, error_text)
            if recovery.retry:
                return {
                    "experiment_id": str(experiment.id),
                    "status": "retrying",
                }
            raise
        monitor_experiment_task.delay(str(result.experiment_id))
        return {
            "experiment_id": str(result.experiment_id),
            "container_id": result.container_id,
            "status": result.status,
        }


async def _monitor_experiment(experiment_id: uuid.UUID) -> dict[str, Any]:
    async with async_session_factory() as session:
        experiment = await session.get(Experiment, experiment_id)
        if experiment is None:
            raise LookupError(f"Experiment {experiment_id} does not exist.")
        project_id = experiment.project_id
        project = await session.get(Project, project_id)
        if project is None:
            raise LookupError(f"Project {project_id} does not exist.")
        executor = await _executor_for_project(project, session)

    broker = RealtimeEventBroker(settings.REDIS_URL)

    async def publish_progress(_experiment_id: uuid.UUID, line: str) -> None:
        summary = parse_train_log([line])
        if summary.completed_epochs == 0 and not summary.latest_metrics:
            return
        await broker.publish(
            ProjectRealtimeEvent(
                type="experiment_progress",
                project_id=project_id,
                experiment_id=experiment_id,
                status="running",
                epoch=summary.completed_epochs or None,
                total_epochs=summary.total_epochs,
                metrics=summary.latest_metrics,
            )
        )

    monitor = ExperimentMonitor(
        settings.STORAGE_PATH,
        executor=executor,
        progress_callback=publish_progress,
    )
    try:
        result = await monitor.monitor_experiment(experiment_id)
    except Exception as error:
        error_text = f"Experiment monitoring failed: {type(error).__name__}: {error}"
        await broker.publish(
            ProjectRealtimeEvent(
                type="experiment_failed",
                project_id=project_id,
                experiment_id=experiment_id,
                status="failed",
                completed_at=datetime.now(timezone.utc),
                error=error_text,
            )
        )
        recovery = await _attempt_error_recovery(experiment_id, error_text)
        if recovery.retry:
            return {
                "experiment_id": str(experiment_id),
                "status": "retrying",
                "recovery": recovery.metadata,
            }
        raise
    else:
        if result.status == "completed":
            recovered = await _mark_recovery_succeeded(experiment_id)
            if recovered is not None:
                _, recovery = recovered
                await broker.publish(
                    ProjectRealtimeEvent(
                        type="experiment_recovery",
                        project_id=project_id,
                        experiment_id=experiment_id,
                        status="completed",
                        recovery=recovery,
                    )
                )
        event_type = (
            "experiment_completed"
            if result.status == "completed"
            else "experiment_failed"
        )
        await broker.publish(
            ProjectRealtimeEvent(
                type=event_type,
                project_id=project_id,
                experiment_id=experiment_id,
                status=result.status,
                metrics=result.metrics,
                completed_at=datetime.now(timezone.utc),
                error=(
                    "Experiment container exited without success"
                    if result.status == "failed"
                    else None
                ),
            )
        )
        response = result.as_dict()
        if result.status == "failed":
            error_log = "\n".join(result.anomalies) or (
                "Experiment container exited without success."
            )
            recovery = await _attempt_error_recovery(experiment_id, error_log)
            response["recovery"] = recovery.metadata
        return response
    finally:
        await broker.close()


@celery_app.task(name="experiments.run", bind=True)
def run_experiment_task(self: Any, experiment_id: str) -> dict[str, str]:
    """Schedule one isolated experiment container from a Celery worker."""
    return asyncio.run(_start_experiment(uuid.UUID(experiment_id)))


@celery_app.task(name="experiments.monitor")
def monitor_experiment_task(experiment_id: str) -> dict[str, Any]:
    """Persist live logs and final metrics until an experiment container exits."""
    return asyncio.run(_monitor_experiment(uuid.UUID(experiment_id)))


@celery_app.task(name="experiments.iterate")
def iterate_experiment_loop_task(project_id: str) -> dict[str, str]:
    """Queue the next pending experiment only while project limits allow it."""
    experiment_id = asyncio.run(_next_experiment_id(uuid.UUID(project_id)))
    if experiment_id is None:
        return {"project_id": project_id, "status": "stopped"}
    run_experiment_task.delay(experiment_id)
    return {
        "project_id": project_id,
        "experiment_id": experiment_id,
        "status": "queued",
    }
