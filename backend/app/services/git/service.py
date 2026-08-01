"""Git repository service for project storage."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from git import BadName, InvalidGitRepositoryError, NoSuchPathError, Repo

from app.services.git.exceptions import (
    BranchAlreadyExistsError,
    BranchNotFoundError,
    DirtyWorkingTreeError,
    InvalidBranchNameError,
    InvalidCommitError,
    InvalidRepositoryPathError,
    NothingToCommitError,
    RepositoryNotFoundError,
)


@dataclass(frozen=True)
class RepositoryInfo:
    current_branch: str
    head_sha: str


@dataclass(frozen=True)
class RepositoryStatus:
    current_branch: str
    head_sha: str
    is_clean: bool
    branches: list[str]


@dataclass(frozen=True)
class BranchInfo:
    name: str
    head_sha: str


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    summary: str
    branch_name: str


class GitService:
    NODE_ID_PATTERN = re.compile(r"^[1-9][0-9]*(?:-[1-9][0-9]*)*$")

    def __init__(self, storage_root: Path | str):
        self._storage_root = Path(storage_root).resolve()

    def _repository_path(self, project_id: uuid.UUID) -> Path:
        repository_path = (self._storage_root / str(project_id) / "git_repo").resolve()
        if not repository_path.is_relative_to(self._storage_root):
            raise InvalidRepositoryPathError(
                message="Repository path escapes the configured storage root.",
                hint="Use a storage root that contains the project repository directory.",
            )
        return repository_path

    def _open_repository(self, project_id: uuid.UUID) -> Repo:
        repository_path = self._repository_path(project_id)
        try:
            return Repo(repository_path)
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise RepositoryNotFoundError(
                message="Git repository is missing or invalid for this project.",
                hint=(
                    "Initialize the project repository or inspect the repository path "
                    "manually."
                ),
            ) from exc

    def _ensure_clean(self, repo: Repo) -> None:
        if repo.is_dirty(untracked_files=True):
            raise DirtyWorkingTreeError(
                message="Repository contains uncommitted changes.",
                hint="Commit or resolve the changes before switching branches.",
            )

    def _experiment_branch_name(self, node_id: str) -> str:
        if not self.NODE_ID_PATTERN.fullmatch(node_id):
            raise InvalidBranchNameError(
                message=(
                    "Experiment node ID must contain positive integer segments separated "
                    "by hyphens."
                ),
                hint="Use a node ID such as '1', '2-1', or '3-2'.",
            )
        return f"exp/{node_id}"

    def _resolve_commit(self, repo: Repo, commit_sha: str):
        try:
            commit = repo.commit(commit_sha)
        except (BadName, ValueError) as exc:
            raise InvalidCommitError(
                message=f"Commit '{commit_sha}' is not valid for this repository.",
                hint="Use a commit SHA that already exists in this repository.",
            ) from exc
        if commit.hexsha == "0" * 40:
            raise InvalidCommitError(
                message=f"Commit '{commit_sha}' is not valid for this repository.",
                hint="Use a commit SHA that already exists in this repository.",
            )
        return commit

    def _branch_info(self, repo: Repo, name: str) -> BranchInfo:
        return BranchInfo(name=name, head_sha=repo.head.commit.hexsha)

    def initialize_project_repository(self, project_id: uuid.UUID) -> RepositoryInfo:
        repository_path = self._repository_path(project_id)
        if repository_path.exists():
            try:
                repo = Repo(repository_path)
            except (InvalidGitRepositoryError, NoSuchPathError) as exc:
                raise RepositoryNotFoundError(
                    message="Git repository is missing or invalid for this project.",
                    hint=(
                        "Initialize the project repository manually or remove the invalid "
                        "contents before trying again."
                    ),
                ) from exc
            return RepositoryInfo(
                current_branch=repo.active_branch.name,
                head_sha=repo.head.commit.hexsha,
            )

        repository_path.parent.mkdir(parents=True, exist_ok=True)
        repo = Repo.init(repository_path, initial_branch="main")
        gitkeep = repository_path / ".gitkeep"
        gitkeep.touch(exist_ok=True)
        repo.index.add([".gitkeep"])
        commit = repo.index.commit("Initial project repository")
        return RepositoryInfo(
            current_branch=repo.active_branch.name, head_sha=commit.hexsha
        )

    def get_repository_status(self, project_id: uuid.UUID) -> RepositoryStatus:
        repo = self._open_repository(project_id)
        branches = sorted(head.name for head in repo.heads)
        return RepositoryStatus(
            current_branch=repo.active_branch.name,
            head_sha=repo.head.commit.hexsha,
            is_clean=not repo.is_dirty(untracked_files=True),
            branches=branches,
        )

    def get_branch_info(self, project_id: uuid.UUID, branch_name: str) -> BranchInfo:
        """Return a branch head without changing the active worktree."""
        repo = self._open_repository(project_id)
        branch = next((head for head in repo.heads if head.name == branch_name), None)
        if branch is None:
            raise BranchNotFoundError(
                message=f"Branch '{branch_name}' does not exist in this repository.",
                hint="Choose a branch recorded by an existing experiment node.",
            )
        return BranchInfo(name=branch.name, head_sha=branch.commit.hexsha)

    def commit_changes(self, project_id: uuid.UUID, message: str) -> CommitInfo:
        repo = self._open_repository(project_id)
        normalized_message = message.strip()
        if not normalized_message or not repo.is_dirty(untracked_files=True):
            raise NothingToCommitError(
                message="Repository has no changes to commit.",
                hint="Add or modify files, then provide a non-empty commit message.",
            )

        repo.git.add(A=True)
        commit = repo.index.commit(normalized_message)
        return CommitInfo(
            sha=commit.hexsha,
            summary=normalized_message,
            branch_name=repo.active_branch.name,
        )

    def create_experiment_branch(
        self,
        project_id: uuid.UUID,
        node_id: str,
        parent_commit_sha: str,
    ) -> BranchInfo:
        repo = self._open_repository(project_id)
        self._ensure_clean(repo)
        branch_name = self._experiment_branch_name(node_id)
        if branch_name in {branch.name for branch in repo.heads}:
            raise BranchAlreadyExistsError(
                message=f"Experiment branch '{branch_name}' already exists.",
                hint="Choose a new experiment node ID or check out the existing branch.",
            )
        parent_commit = self._resolve_commit(repo, parent_commit_sha)
        repo.create_head(branch_name, parent_commit)
        repo.git.checkout(branch_name)
        return self._branch_info(repo, branch_name)

    def checkout_branch(self, project_id: uuid.UUID, branch_name: str) -> BranchInfo:
        repo = self._open_repository(project_id)
        self._ensure_clean(repo)
        if branch_name not in {branch.name for branch in repo.heads}:
            raise BranchNotFoundError(
                message=f"Branch '{branch_name}' does not exist in this repository.",
                hint="Choose one of the local branches returned by repository status.",
            )
        repo.git.checkout(branch_name)
        return self._branch_info(repo, branch_name)
