"""Schemas for the end-to-end project creation wizard."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.ai import ProjectConfig


class PaperUploadResponse(BaseModel):
    """Parsed paper details and the newly created draft project."""

    project_id: uuid.UUID
    project_name: str
    paper_title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ExistingAssetsProjectRequest(BaseModel):
    """Create a project that starts from prepared code and data."""

    name: str = Field(min_length=1, max_length=200)


class ExistingAssetsProjectResponse(BaseModel):
    """Draft project created for the existing-assets workflow."""

    project_id: uuid.UUID
    project_name: str
    workflow: Literal["existing_assets"] = "existing_assets"


class PaperAnalysisResponse(BaseModel):
    """Structured implementation-oriented reading of the source paper."""

    summary: str
    research_problem: str
    method_steps: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    implementation_requirements: list[str] = Field(default_factory=list)
    compute_requirements: list[str] = Field(default_factory=list)
    reproducibility_risks: list[str] = Field(default_factory=list)
    model: str


class DataSelectionResponse(BaseModel):
    """Manifest for a selected file or folder on the SSH server."""

    ready: bool
    source: Literal["remote"] = "remote"
    kind: Literal["file", "folder"]
    selected_name: str
    path: str
    file_count: int
    total_bytes: int


class RemoteDataEntryResponse(BaseModel):
    """One selectable data entry returned by the remote browser."""

    name: str
    path: str
    kind: Literal["file", "folder"]
    size: int


class RemoteDataListingResponse(BaseModel):
    """A bounded directory listing from the selected SSH server."""

    current_path: str
    parent_path: str | None = None
    entries: list[RemoteDataEntryResponse] = Field(default_factory=list)
    truncated: bool = False


class RemoteDataSelectionRequest(BaseModel):
    """One remote file or folder chosen through the server browser."""

    path: str = Field(min_length=1, max_length=4096)
    kind: Literal["file", "folder"]


class RemoteCodeImportRequest(BaseModel):
    """Remote code directory and its relative training entrypoint."""

    path: str = Field(min_length=1, max_length=4096)
    entrypoint: str = Field(min_length=1, max_length=500)
    arguments: str = Field(default="", max_length=2000)


class RemoteCodeImportResponse(BaseModel):
    """Git-backed snapshot imported from an SSH server directory."""

    ready: bool
    source: Literal["remote"] = "remote"
    selected_name: str
    path: str
    entrypoint: str
    arguments: list[str] = Field(default_factory=list)
    file_count: int
    total_bytes: int
    skipped_count: int


class SshConnectionResponse(BaseModel):
    """Verified remote execution target without its credentials."""

    ready: bool
    host: str
    port: int
    username: str
    auth_type: Literal["password", "key"]
    host_key_fingerprint: str
    capabilities: dict[str, str | bool]


class PreparationStatusResponse(BaseModel):
    """Current hard-gate status for an experiment project."""

    workflow: Literal["paper_reproduction", "existing_assets"]
    api_key_ready: bool
    paper_analysis_ready: bool
    data_ready: bool
    execution_ready: bool
    code_ready: bool
    ready_to_generate: bool
    ready_to_start: bool
    ai_profile_id: uuid.UUID | None = None
    ssh_profile_id: uuid.UUID | None = None
    data: DataSelectionResponse | None = None
    code: RemoteCodeImportResponse | None = None
    execution: SshConnectionResponse | None = None
    missing: list[str] = Field(default_factory=list)


class DialogAnswerRequest(BaseModel):
    """One answer in a guided configuration dialog."""

    session_id: str
    answer: str = Field(min_length=1, max_length=2000)


class DialogResponse(BaseModel):
    """Either the next question or a completed project configuration."""

    session_id: str
    complete: bool = False
    question: str | None = None
    options: list[str] = Field(default_factory=list)
    input_type: Literal["single", "multi", "text"] | None = None
    config: ProjectConfig | None = None


class GeneratedFile(BaseModel):
    """One generated source file exposed for review."""

    path: str
    language: str
    content: str


class CodeGenerationResponse(BaseModel):
    """Generated framework and the agent's explanation."""

    project_id: uuid.UUID
    files: list[GeneratedFile]
    summary: str


class WizardProjectSnapshot(BaseModel):
    """Persisted wizard state used to resume an unfinished project."""

    project_id: uuid.UUID
    project_name: str
    paper_title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    analysis: PaperAnalysisResponse | None = None
    dialog_complete: bool = False
    config: ProjectConfig | None = None
    preparation: PreparationStatusResponse
    files: list[GeneratedFile] = Field(default_factory=list)


class SaveCodeRequest(BaseModel):
    """Reviewed files to persist in the project repository."""

    files: list[GeneratedFile] = Field(min_length=1, max_length=50)


class SaveCodeResponse(BaseModel):
    """Commit created after saving reviewed source files."""

    project_id: uuid.UUID
    commit_sha: str
    files_saved: int


class StartExperimentResponse(BaseModel):
    """Initial experiment queued from the completed wizard."""

    project_id: uuid.UUID
    experiment_id: uuid.UUID
    status: Literal["queued"]
