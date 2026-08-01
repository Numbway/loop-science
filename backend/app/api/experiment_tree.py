"""Read-only experiment tree API."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.project import Project
from app.schemas.experiment_tree import ExperimentTreeNode, ProjectTreeResponse

router = APIRouter(prefix="/api/projects/{project_id}/tree", tags=["experiment-tree"])


def _node_sort_key(node_id: str) -> tuple[int, ...]:
    """Sort numeric lineage IDs naturally: 2-2 before 10-1."""
    try:
        return tuple(int(part) for part in node_id.split("-"))
    except ValueError:
        return (10**9,)


@router.get("", response_model=ProjectTreeResponse)
async def get_experiment_tree(
    project: Project = Depends(get_owned_project),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ProjectTreeResponse:
    """Return every experiment owned by the project in stable lineage order."""
    experiments = (
        await db.scalars(select(Experiment).where(Experiment.project_id == project.id))
    ).all()
    experiments.sort(key=lambda experiment: _node_sort_key(experiment.node_id))

    return ProjectTreeResponse(
        project_id=project.id,
        name=project.name,
        paper_title=project.paper_title,
        status=project.status,
        target_metrics=project.target_metrics or {},
        max_iterations=project.max_iterations,
        nodes=[
            ExperimentTreeNode(
                id=experiment.id,
                node_id=experiment.node_id,
                parent_node_id=experiment.parent_node_id,
                git_branch=experiment.git_branch,
                improvement_description=experiment.improvement_description,
                status=experiment.status,
                metrics=experiment.metrics or {},
                config=experiment.config or {},
                diagnosis=experiment.diagnosis,
                duration_seconds=experiment.duration_seconds,
                created_by=experiment.created_by,
                started_at=experiment.started_at,
                completed_at=experiment.completed_at,
                report_available=bool(experiment.report_html_path),
            )
            for experiment in experiments
        ],
        updated_at=datetime.now(UTC),
    )
