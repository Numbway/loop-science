"""Git repository service for project storage."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo

from app.services.git.exceptions import (
    InvalidRepositoryPathError,
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


class GitService:
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
        return RepositoryInfo(current_branch=repo.active_branch.name, head_sha=commit.hexsha)

    def get_repository_status(self, project_id: uuid.UUID) -> RepositoryStatus:
        repo = self._open_repository(project_id)
        branches = sorted(head.name for head in repo.heads)
        return RepositoryStatus(
            current_branch=repo.active_branch.name,
            head_sha=repo.head.commit.hexsha,
            is_clean=not repo.is_dirty(untracked_files=True),
            branches=branches,
        )
