import uuid

import pytest

from app.services.git.exceptions import (
    BranchAlreadyExistsError,
    DirtyWorkingTreeError,
    InvalidBranchNameError,
    InvalidCommitError,
    NothingToCommitError,
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


def test_get_branch_info_reads_an_arbitrary_branch_without_checkout(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)
    service.create_experiment_branch(project_id, "1", initial.head_sha)
    repository_path = tmp_path / str(project_id) / "git_repo"
    (repository_path / "experiment.py").write_text("variant = 1\n", encoding="utf-8")
    experiment_commit = service.commit_changes(project_id, "Add experiment variant")
    service.checkout_branch(project_id, "main")

    branch = service.get_branch_info(project_id, "exp/1")
    status = service.get_repository_status(project_id)

    assert branch.name == "exp/1"
    assert branch.head_sha == experiment_commit.sha
    assert status.current_branch == "main"
    assert status.head_sha == initial.head_sha


def test_compare_branches_returns_bounded_diff_without_checkout(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)
    repository_path = tmp_path / str(project_id) / "git_repo"

    service.create_experiment_branch(project_id, "1", initial.head_sha)
    train_file = repository_path / "train.py"
    train_file.write_text("learning_rate = 0.1\n", encoding="utf-8")
    parent_commit = service.commit_changes(project_id, "Add baseline training")

    service.create_experiment_branch(project_id, "2-1", parent_commit.sha)
    train_file.write_text(
        "learning_rate = 0.01\nscheduler = 'cosine'\n",
        encoding="utf-8",
    )
    service.commit_changes(project_id, "Use cosine scheduling")

    branch_diff = service.compare_branches(
        project_id,
        "exp/1",
        "exp/2-1",
    )
    status = service.get_repository_status(project_id)

    assert branch_diff.files == ["train.py"]
    assert branch_diff.insertions == 2
    assert branch_diff.deletions == 1
    assert "-learning_rate = 0.1" in branch_diff.patch
    assert "+scheduler = 'cosine'" in branch_diff.patch
    assert branch_diff.truncated is False
    assert status.current_branch == "exp/2-1"


def test_checkout_branch_rejects_dirty_worktree_without_losing_changes(
    tmp_path,
) -> None:
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


def test_branch_creation_rejects_invalid_node_duplicate_and_unknown_commit(
    tmp_path,
) -> None:
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


def test_branch_create_and_checkout_reject_dirty_worktree_without_losing_changes(
    tmp_path,
) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    initial = service.initialize_project_repository(project_id)
    repository_path = tmp_path / str(project_id) / "git_repo"
    dirty_file = repository_path / "uncommitted.py"
    dirty_file.write_text("value = 1\n", encoding="utf-8")

    with pytest.raises(DirtyWorkingTreeError):
        service.create_experiment_branch(project_id, "1", initial.head_sha)

    assert dirty_file.read_text(encoding="utf-8") == "value = 1\n"


def test_commit_changes_stages_real_changes_and_returns_commit_info(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    service.initialize_project_repository(project_id)
    repository_path = tmp_path / str(project_id) / "git_repo"
    (repository_path / "model.py").write_text("class Model: pass\n", encoding="utf-8")

    commit = service.commit_changes(project_id, "Add initial model")
    status = service.get_repository_status(project_id)

    assert commit.summary == "Add initial model"
    assert commit.branch_name == "main"
    assert len(commit.sha) == 40
    assert status.head_sha == commit.sha
    assert status.is_clean is True


def test_commit_changes_rejects_empty_worktree_and_blank_message(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    service.initialize_project_repository(project_id)

    with pytest.raises(NothingToCommitError):
        service.commit_changes(project_id, "No changes")
    with pytest.raises(NothingToCommitError):
        service.commit_changes(project_id, "   ")
