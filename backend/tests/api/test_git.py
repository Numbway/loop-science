import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_owned_project
from app.api.git import get_git_service
from app.main import app
from app.schemas.git import CreateExperimentBranchRequest
from app.services.git.service import GitService


def test_branch_request_accepts_only_valid_experiment_node_ids() -> None:
    assert CreateExperimentBranchRequest(node_id="3-2", parent_commit_sha="a" * 40).node_id == "3-2"

    with pytest.raises(ValidationError):
        CreateExperimentBranchRequest(node_id="../main", parent_commit_sha="a" * 40)


@pytest.mark.asyncio
async def test_get_owned_project_returns_404_for_other_users() -> None:
    other_user_id = uuid.uuid4()
    project = SimpleNamespace(id=uuid.uuid4(), user_id=other_user_id)

    class FakeResult:
        def scalar_one_or_none(self):
            return project

    class FakeSession:
        async def execute(self, statement):
            return FakeResult()

    with pytest.raises(HTTPException) as exc_info:
        await get_owned_project(
            project_id=project.id,
            db=FakeSession(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
        )

    assert exc_info.value.status_code == 404


def test_initialize_repository_endpoint_uses_owned_project_id_and_hides_storage_path(tmp_path) -> None:
    route_project_id = uuid.uuid4()
    owned_project_id = uuid.uuid4()
    app.dependency_overrides[get_git_service] = lambda: GitService(tmp_path)
    app.dependency_overrides[get_owned_project] = lambda: SimpleNamespace(id=owned_project_id)

    try:
        response = TestClient(app).post(f"/api/projects/{route_project_id}/repository")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["current_branch"] == "main"
    assert len(body["head_sha"]) == 40
    assert "path" not in body
    assert str(tmp_path) not in response.text
    assert (tmp_path / str(owned_project_id) / "git_repo").exists()
    assert not (tmp_path / str(route_project_id) / "git_repo").exists()


def test_branch_endpoint_maps_dirty_worktree_to_safe_conflict(tmp_path) -> None:
    route_project_id = uuid.uuid4()
    owned_project_id = uuid.uuid4()
    service = GitService(tmp_path)
    info = service.initialize_project_repository(owned_project_id)
    repository_path = tmp_path / str(owned_project_id) / "git_repo"
    (repository_path / "uncommitted.txt").write_text("keep me", encoding="utf-8")

    app.dependency_overrides[get_git_service] = lambda: service
    app.dependency_overrides[get_owned_project] = lambda: SimpleNamespace(id=owned_project_id)

    try:
        response = TestClient(app).post(
            f"/api/projects/{route_project_id}/repository/branches",
            json={"node_id": "1", "parent_commit_sha": info.head_sha},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "dirty_working_tree",
            "detail": "Repository contains uncommitted changes.",
            "hint": "Commit or resolve the changes before switching branches.",
        }
    }
    assert (repository_path / "uncommitted.txt").read_text(encoding="utf-8") == "keep me"


def test_repository_api_supports_initialize_branch_commit_and_status(tmp_path) -> None:
    project_id = uuid.uuid4()
    service = GitService(tmp_path)
    app.dependency_overrides[get_git_service] = lambda: service
    app.dependency_overrides[get_owned_project] = lambda: SimpleNamespace(id=project_id)

    try:
        client = TestClient(app)
        initialized = client.post(f"/api/projects/{project_id}/repository")
        parent_sha = initialized.json()["head_sha"]
        branch = client.post(
            f"/api/projects/{project_id}/repository/branches",
            json={"node_id": "1", "parent_commit_sha": parent_sha},
        )
        repository_path = tmp_path / str(project_id) / "git_repo"
        (repository_path / "train.py").write_text("print('train')\n", encoding="utf-8")
        committed = client.post(
            f"/api/projects/{project_id}/repository/commits",
            json={"message": "Add training entry point"},
        )
        final_status = client.get(f"/api/projects/{project_id}/repository/status")
    finally:
        app.dependency_overrides.clear()

    assert initialized.status_code == 200
    assert branch.status_code == 200
    assert branch.json()["name"] == "exp/1"
    assert committed.status_code == 200
    assert final_status.status_code == 200
    assert final_status.json()["current_branch"] == "exp/1"
    assert final_status.json()["head_sha"] == committed.json()["sha"]
    assert final_status.json()["is_clean"] is True
