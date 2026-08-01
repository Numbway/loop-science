"""Owned experiment detail, evidence, and monitoring API."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.experiment_log import ExperimentLog
from app.models.project import Project
from app.models.reference_paper import ReferencePaper
from app.models.user import User
from app.schemas.experiment_detail import (
    CodeDiffResponse,
    ExperimentDetailResponse,
    ExperimentRecovery,
    MetricComparison,
    ReferenceEvidence,
    TensorBoardEmbed,
    TrainingLogEntry,
)
from app.services.experiment.error_recovery import (
    public_experiment_config,
    recovery_metadata,
)
from app.services.git.exceptions import GitServiceError
from app.services.git.service import GitService

router = APIRouter(
    prefix="/api/experiments/{experiment_id}", tags=["experiment-detail"]
)


def get_detail_git_service() -> GitService:
    return GitService(settings.STORAGE_PATH)


def get_detail_storage() -> Path:
    return Path(settings.STORAGE_PATH).resolve()


def get_tensorboard_public_url() -> str:
    return settings.TENSORBOARD_PUBLIC_URL


async def get_owned_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> Experiment:
    experiment = await db.scalar(
        select(Experiment)
        .join(Project, Project.id == Experiment.project_id)
        .where(
            Experiment.id == experiment_id,
            Project.user_id == current_user.id,
        )
    )
    if experiment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment not found",
        )
    return experiment


def _format_metric(name: str, value: float) -> str:
    if "acc" in name.lower() or "precision" in name.lower():
        return f"{(value * 100 if value <= 1 else value):.2f}%"
    return f"{value:.4f}"


def _summary(experiment: Experiment) -> str:
    metrics = experiment.metrics or {}
    preferred = next(
        (
            (name, metrics[name])
            for name in ("accuracy", "validation_accuracy", "val_accuracy", "loss")
            if name in metrics
        ),
        next(iter(metrics.items()), None),
    )
    metric_text = (
        f"{preferred[0]} {_format_metric(*preferred)}" if preferred is not None else ""
    )
    if experiment.status == "completed":
        return f"实验已完成{f'，最终 {metric_text}' if metric_text else ''}。"
    if experiment.status == "running":
        return f"实验正在运行{f'，最新 {metric_text}' if metric_text else ''}。"
    if experiment.status == "failed":
        return "实验运行失败；请结合诊断和错误日志定位原因。"
    return "实验已排队，训练指标将在执行开始后出现。"


def _tensorboard_embed(
    storage_root: Path,
    experiment_id: uuid.UUID,
    public_url: str,
) -> TensorBoardEmbed:
    output_directory = (storage_root / "experiment_runs" / str(experiment_id)).resolve()
    if not output_directory.is_relative_to(storage_root):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Experiment output path is invalid",
        )
    event_count = (
        sum(1 for _ in output_directory.rglob("events.out.tfevents.*"))
        if output_directory.is_dir()
        else 0
    )
    embed_url = (
        f"{public_url.rstrip('/')}/" if event_count > 0 and public_url.strip() else None
    )
    return TensorBoardEmbed(
        available=event_count > 0,
        event_file_count=event_count,
        embed_url=embed_url,
    )


def _metric_comparisons(
    experiment: Experiment,
    parent: Experiment | None,
    target_metrics: dict[str, float],
) -> list[MetricComparison]:
    parent_metrics = (parent.metrics or {}) if parent else {}
    comparisons = []
    for name, current in sorted((experiment.metrics or {}).items()):
        parent_value = parent_metrics.get(name)
        comparisons.append(
            MetricComparison(
                name=name,
                current=current,
                parent=parent_value,
                delta=current - parent_value if parent_value is not None else None,
                target=target_metrics.get(name),
            )
        )
    return comparisons


@router.get("", response_model=ExperimentDetailResponse)
async def get_experiment_detail(
    experiment: Experiment = Depends(get_owned_experiment),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    git_service: GitService = Depends(get_detail_git_service),  # noqa: B008
    storage_root: Path = Depends(get_detail_storage),  # noqa: B008
    tensorboard_public_url: str = Depends(get_tensorboard_public_url),
) -> ExperimentDetailResponse:
    """Return the full evidence bundle for one owned experiment."""
    project = await db.get(Project, experiment.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    parent = (
        await db.scalar(
            select(Experiment).where(
                Experiment.project_id == project.id,
                Experiment.node_id == experiment.parent_node_id,
            )
        )
        if experiment.parent_node_id
        else None
    )
    logs = list(
        (
            await db.scalars(
                select(ExperimentLog)
                .where(ExperimentLog.experiment_id == experiment.id)
                .order_by(ExperimentLog.timestamp.desc())
                .limit(120)
            )
        ).all()
    )
    references = list(
        (
            await db.scalars(
                select(ReferencePaper)
                .where(ReferencePaper.project_id == project.id)
                .order_by(ReferencePaper.created_at.desc())
                .limit(5)
            )
        ).all()
    )

    base_branch = parent.git_branch if parent else "main"
    try:
        branch_diff = git_service.compare_branches(
            project.id,
            base_branch,
            experiment.git_branch,
        )
        code_diff = CodeDiffResponse(
            available=True,
            base_branch=branch_diff.base_branch,
            target_branch=branch_diff.target_branch,
            files=branch_diff.files,
            patch=branch_diff.patch,
            insertions=branch_diff.insertions,
            deletions=branch_diff.deletions,
            truncated=branch_diff.truncated,
        )
    except GitServiceError as error:
        code_diff = CodeDiffResponse(
            available=False,
            base_branch=base_branch,
            target_branch=experiment.git_branch,
            unavailable_reason=error.message,
        )

    return ExperimentDetailResponse(
        id=experiment.id,
        project_id=project.id,
        project_name=project.name,
        paper_title=project.paper_title,
        node_id=experiment.node_id,
        parent_node_id=experiment.parent_node_id,
        parent_experiment_id=parent.id if parent else None,
        git_branch=experiment.git_branch,
        status=experiment.status,
        summary=_summary(experiment),
        improvement_description=experiment.improvement_description,
        metrics=experiment.metrics or {},
        metric_comparisons=_metric_comparisons(
            experiment,
            parent,
            project.target_metrics or {},
        ),
        target_metrics=project.target_metrics or {},
        config=public_experiment_config(experiment.config),
        recovery=(
            ExperimentRecovery.model_validate(metadata)
            if (metadata := recovery_metadata(experiment.config))
            else None
        ),
        diagnosis=experiment.diagnosis,
        code_changes=experiment.code_changes or {},
        code_diff=code_diff,
        tensorboard=_tensorboard_embed(
            storage_root,
            experiment.id,
            tensorboard_public_url,
        ),
        recent_logs=[
            TrainingLogEntry(
                level=log.level,
                message=log.message[:2_000],
                timestamp=log.timestamp,
            )
            for log in reversed(logs)
        ],
        references=[
            ReferenceEvidence(
                id=reference.id,
                title=reference.title,
                authors=reference.authors or [],
                year=reference.year,
                url=reference.url,
                key_contributions=reference.key_contributions or [],
            )
            for reference in references
        ],
        duration_seconds=experiment.duration_seconds,
        created_by=experiment.created_by,
        started_at=experiment.started_at,
        completed_at=experiment.completed_at,
        report_available=bool(experiment.report_html_path),
    )
