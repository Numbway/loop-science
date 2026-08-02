"""Git-related Pydantic schemas."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

NODE_ID_PATTERN = re.compile(r"^[1-9][0-9]*(?:-[1-9][0-9]*)*$")


class CreateExperimentBranchRequest(BaseModel):
    """Request body for creating an experiment branch."""

    node_id: str
    parent_commit_sha: str = Field(min_length=7, max_length=40)

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, value: str) -> str:
        if not NODE_ID_PATTERN.fullmatch(value):
            raise ValueError("node_id must look like '1', '2-1', or '3-2'")
        return value


class CheckoutBranchRequest(BaseModel):
    """Request body for checking out an existing branch."""

    branch_name: str = Field(min_length=1, max_length=255)


class CommitChangesRequest(BaseModel):
    """Request body for committing repository changes."""

    message: str = Field(min_length=1, max_length=500)


class RepositoryResponse(BaseModel):
    """Repository state summary returned by Git endpoints."""

    current_branch: str
    head_sha: str


class RepositoryStatusResponse(RepositoryResponse):
    """Repository state plus branch list and cleanliness flag."""

    is_clean: bool
    branches: list[str]


class BranchResponse(BaseModel):
    """Details about a checked-out or created branch."""

    name: str
    head_sha: str


class CommitResponse(BaseModel):
    """Details about a repository commit."""

    sha: str
    summary: str
    branch_name: str


class GitErrorResponse(BaseModel):
    """Standard Git API error payload."""

    code: str
    detail: str
    hint: str
