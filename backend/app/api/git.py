"""Git repository API routes."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_owned_project
from app.core.config import settings
from app.models.project import Project
from app.schemas.git import (
    BranchResponse,
    CheckoutBranchRequest,
    CommitChangesRequest,
    CommitResponse,
    CreateExperimentBranchRequest,
    GitErrorResponse,
    RepositoryResponse,
    RepositoryStatusResponse,
)
from app.services.git.exceptions import GitServiceError, InvalidRepositoryPathError
from app.services.git.service import GitService

router = APIRouter(prefix="/api/projects/{project_id}/repository", tags=["git"])


def get_git_service() -> GitService:
    return GitService(settings.STORAGE_PATH)


def _raise_http_error(error: GitServiceError) -> NoReturn:
    status_code = 422 if isinstance(error, InvalidRepositoryPathError) else 409
    if type(error) is GitServiceError:
        status_code = 500
    raise HTTPException(
        status_code=status_code,
        detail=GitErrorResponse(code=error.code, detail=error.message, hint=error.hint).model_dump(),
    )


@router.post("", response_model=RepositoryResponse)
def initialize_repository(
    project: Project = Depends(get_owned_project),  # noqa: B008
    service: GitService = Depends(get_git_service),  # noqa: B008
) -> RepositoryResponse:
    try:
        info = service.initialize_project_repository(project.id)
    except GitServiceError as error:
        _raise_http_error(error)
    return RepositoryResponse(current_branch=info.current_branch, head_sha=info.head_sha)


@router.get("/status", response_model=RepositoryStatusResponse)
def repository_status(
    project: Project = Depends(get_owned_project),  # noqa: B008
    service: GitService = Depends(get_git_service),  # noqa: B008
) -> RepositoryStatusResponse:
    try:
        repository_status = service.get_repository_status(project.id)
    except GitServiceError as error:
        _raise_http_error(error)
    return RepositoryStatusResponse(
        current_branch=repository_status.current_branch,
        head_sha=repository_status.head_sha,
        is_clean=repository_status.is_clean,
        branches=repository_status.branches,
    )


@router.post("/branches", response_model=BranchResponse)
def create_branch(
    request: CreateExperimentBranchRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    service: GitService = Depends(get_git_service),  # noqa: B008
) -> BranchResponse:
    try:
        branch = service.create_experiment_branch(
            project.id, request.node_id, request.parent_commit_sha
        )
    except GitServiceError as error:
        _raise_http_error(error)
    return BranchResponse(name=branch.name, head_sha=branch.head_sha)


@router.post("/checkout", response_model=BranchResponse)
def checkout_branch(
    request: CheckoutBranchRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    service: GitService = Depends(get_git_service),  # noqa: B008
) -> BranchResponse:
    try:
        branch = service.checkout_branch(project.id, request.branch_name)
    except GitServiceError as error:
        _raise_http_error(error)
    return BranchResponse(name=branch.name, head_sha=branch.head_sha)


@router.post("/commits", response_model=CommitResponse)
def commit_changes(
    request: CommitChangesRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    service: GitService = Depends(get_git_service),  # noqa: B008
) -> CommitResponse:
    try:
        commit = service.commit_changes(project.id, request.message)
    except GitServiceError as error:
        _raise_http_error(error)
    return CommitResponse(sha=commit.sha, summary=commit.summary, branch_name=commit.branch_name)
