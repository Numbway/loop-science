"""Git service domain errors."""

from __future__ import annotations


class GitServiceError(Exception):
    code = "git_service_error"

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class RepositoryNotFoundError(GitServiceError):
    code = "repository_not_found"


class InvalidRepositoryPathError(GitServiceError):
    code = "invalid_repository_path"


class InvalidBranchNameError(GitServiceError):
    code = "invalid_branch_name"


class BranchAlreadyExistsError(GitServiceError):
    code = "branch_already_exists"


class BranchNotFoundError(GitServiceError):
    code = "branch_not_found"


class InvalidCommitError(GitServiceError):
    code = "invalid_commit"


class DirtyWorkingTreeError(GitServiceError):
    code = "dirty_working_tree"


class NothingToCommitError(GitServiceError):
    code = "nothing_to_commit"
