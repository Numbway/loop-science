"""Experiment tree and branch-planning API."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_project
from app.core.config import settings
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.project import Project
from app.schemas.experiment_tree import (
    BranchPlanCreate,
    BranchPlanResponse,
    CreatedBranch,
    ExperimentTreeNode,
    ProjectTreeResponse,
)
from app.schemas.git import GitErrorResponse
from app.services.git.exceptions import GitServiceError, InvalidRepositoryPathError
from app.services.git.service import GitService

router = APIRouter(prefix="/api/projects/{project_id}/tree", tags=["experiment-tree"])
CHILD_NODE_PATTERN = re.compile(r"^(?P<depth>[1-9][0-9]*)-(?P<index>[1-9][0-9]*)$")


def get_tree_git_service() -> GitService:
    """Build the Git service used by branch planning."""
    return GitService(settings.STORAGE_PATH)


def _node_sort_key(node_id: str) -> tuple[int, ...]:
    """Sort numeric lineage IDs naturally: 2-2 before 10-1."""
    try:
        return tuple(int(part) for part in node_id.split("-"))
    except ValueError:
        return (10**9,)


def _tree_node(experiment: Experiment) -> ExperimentTreeNode:
    return ExperimentTreeNode(
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


def _next_child_node_id(parent_node_id: str, existing_node_ids: list[str]) -> str:
    """Allocate the next globally unique node at the parent's next depth."""
    try:
        child_depth = int(parent_node_id.split("-", maxsplit=1)[0]) + 1
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The parent experiment has an invalid lineage identifier.",
        ) from exc

    used_indexes = [
        int(match.group("index"))
        for node_id in existing_node_ids
        if (match := CHILD_NODE_PATTERN.fullmatch(node_id))
        and int(match.group("depth")) == child_depth
    ]
    return f"{child_depth}-{max(used_indexes, default=0) + 1}"


def _raise_git_http_error(error: GitServiceError) -> NoReturn:
    status_code = (
        status.HTTP_422_UNPROCESSABLE_ENTITY
        if isinstance(error, InvalidRepositoryPathError)
        else status.HTTP_409_CONFLICT
    )
    raise HTTPException(
        status_code=status_code,
        detail=GitErrorResponse(
            code=error.code,
            detail=error.message,
            hint=error.hint,
        ).model_dump(),
    )


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
        nodes=[_tree_node(experiment) for experiment in experiments],
        updated_at=datetime.now(UTC),
    )


@router.post(
    "/nodes/{parent_experiment_id}/branches",
    response_model=BranchPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_planned_branch(
    parent_experiment_id: uuid.UUID,
    request: BranchPlanCreate,
    project: Project = Depends(get_owned_project),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    git_service: GitService = Depends(get_tree_git_service),  # noqa: B008
) -> BranchPlanResponse:
    """Create a pending child experiment from a three-decision branch plan."""
    parent = await db.scalar(
        select(Experiment).where(
            Experiment.id == parent_experiment_id,
            Experiment.project_id == project.id,
        )
    )
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent experiment not found",
        )

    node_ids = list(
        (
            await db.scalars(
                select(Experiment.node_id).where(Experiment.project_id == project.id)
            )
        ).all()
    )
    node_id = _next_child_node_id(parent.node_id, node_ids)
    try:
        parent_branch = git_service.get_branch_info(project.id, parent.git_branch)
        branch = git_service.create_experiment_branch(
            project.id,
            node_id,
            parent_branch.head_sha,
        )
    except GitServiceError as error:
        _raise_git_http_error(error)

    inherited_config = dict(parent.config or {})
    inherited_config["branch_plan"] = request.model_dump()
    experiment = Experiment(
        id=uuid.uuid4(),
        project_id=project.id,
        node_id=node_id,
        parent_node_id=parent.node_id,
        git_branch=branch.name,
        improvement_description=request.approach.strip(),
        code_changes={},
        config=inherited_config,
        metrics=None,
        status="pending",
        created_by="user",
    )
    db.add(experiment)
    await db.commit()

    return BranchPlanResponse(
        node=_tree_node(experiment),
        branch=CreatedBranch(
            name=branch.name,
            head_sha=branch.head_sha,
            parent_head_sha=parent_branch.head_sha,
        ),
    )
