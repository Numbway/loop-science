import uuid

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
