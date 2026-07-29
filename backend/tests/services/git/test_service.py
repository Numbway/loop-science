import uuid

import pytest

from app.services.git.exceptions import (
    BranchAlreadyExistsError,
    DirtyWorkingTreeError,
    InvalidBranchNameError,
    InvalidCommitError,
)
from app.services.git.service import GitService


def test_initialize_repository_creates_main_and_initial_commit(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)

    info = service.initialize_project_repository(project_id)
    status = service.get_repository_status(project_id)

    assert info.current_branch == "main"
    assert info.head_sha == status.head_sha
    assert len(info.head_sha) == 40
    assert status.is_clean is True
    assert status.branches == ["main"]
    assert (tmp_path / str(project_id) / "git_repo" / ".gitkeep").is_file()


def test_initialize_repository_is_idempotent(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)

    first = service.initialize_project_repository(project_id)
    second = service.initialize_project_repository(project_id)

    assert second.head_sha == first.head_sha
    assert second.current_branch == "main"


def test_create_experiment_branch_from_parent_commit_and_checkout(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)

    branch = service.create_experiment_branch(project_id, "2-1", initial.head_sha)
    status = service.get_repository_status(project_id)

    assert branch.name == "exp/2-1"
    assert branch.head_sha == initial.head_sha
    assert status.current_branch == "exp/2-1"
    assert status.branches == ["exp/2-1", "main"]


def test_checkout_branch_switches_existing_branch_from_clean_worktree(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)
    service.create_experiment_branch(project_id, "2-1", initial.head_sha)
    service.checkout_branch(project_id, "main")

    branch = service.checkout_branch(project_id, "exp/2-1")
    status = service.get_repository_status(project_id)

    assert branch.name == "exp/2-1"
    assert branch.head_sha == status.head_sha
    assert status.current_branch == "exp/2-1"
    assert status.is_clean is True


def test_checkout_branch_rejects_dirty_worktree_without_losing_changes(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)
    service.create_experiment_branch(project_id, "2-1", initial.head_sha)
    service.checkout_branch(project_id, "main")

    repository_path = tmp_path / str(project_id) / "git_repo"
    dirty_file = repository_path / "checkout-dirty.py"
    dirty_file.write_text("pending = True\n", encoding="utf-8")

    with pytest.raises(DirtyWorkingTreeError):
        service.checkout_branch(project_id, "exp/2-1")

    assert dirty_file.read_text(encoding="utf-8") == "pending = True\n"


def test_branch_creation_rejects_invalid_node_duplicate_and_unknown_commit(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)

    with pytest.raises(InvalidBranchNameError):
        service.create_experiment_branch(project_id, "../main", initial.head_sha)
    with pytest.raises(InvalidCommitError):
        service.create_experiment_branch(project_id, "1", "0" * 40)

    service.create_experiment_branch(project_id, "1", initial.head_sha)
    with pytest.raises(BranchAlreadyExistsError):
        service.create_experiment_branch(project_id, "1", initial.head_sha)


def test_branch_create_and_checkout_reject_dirty_worktree_without_losing_changes(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)
    repository_path = tmp_path / str(project_id) / "git_repo"
    dirty_file = repository_path / "uncommitted.py"
    dirty_file.write_text("value = 1\n", encoding="utf-8")

    with pytest.raises(DirtyWorkingTreeError):
        service.create_experiment_branch(project_id, "1", initial.head_sha)

    assert dirty_file.read_text(encoding="utf-8") == "value = 1\n"
