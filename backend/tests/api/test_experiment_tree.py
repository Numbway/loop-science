from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_owned_project
from app.api.experiment_tree import get_tree_git_service
from app.core.database import get_db
from app.main import app
from app.schemas.experiment_tree import BranchPlanCreate
from app.services.git.service import GitService


class FakeScalarResult:
    def __init__(self, experiments) -> None:
        self._experiments = experiments

    def all(self):
        return list(self._experiments)


class FakeSession:
    def __init__(self, experiments) -> None:
        self._experiments = experiments

    async def scalars(self, _statement):
        return FakeScalarResult(self._experiments)


def make_experiment(node_id: str, parent_node_id: str | None, **overrides):
    defaults = {
        "id": uuid.uuid4(),
        "node_id": node_id,
        "parent_node_id": parent_node_id,
        "git_branch": f"exp/{node_id}",
        "improvement_description": f"Experiment {node_id}",
        "status": "completed",
        "metrics": {"accuracy": 0.91, "loss": 0.3},
        "config": {"entrypoint": "train.py"},
        "diagnosis": None,
        "duration_seconds": 80,
        "created_by": "ai",
        "started_at": datetime.now(UTC),
        "completed_at": datetime.now(UTC),
        "report_html_path": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_tree_endpoint_returns_owned_project_in_natural_lineage_order() -> None:
    project_id = uuid.uuid4()
    project = SimpleNamespace(
        id=project_id,
        name="Adaptive vision",
        paper_title="Adaptive Vision Systems",
        status="running",
        target_metrics={"accuracy": 0.95},
        max_iterations=10,
    )
    experiments = [
        make_experiment("10-1", "2-1"),
        make_experiment("2-1", "1", status="running", metrics={"loss": 0.4}),
        make_experiment("1", None, report_html_path="/private/report.html"),
        make_experiment("2-2", "1", status="failed", metrics=None),
    ]
    app.dependency_overrides[get_owned_project] = lambda: project
    app.dependency_overrides[get_db] = lambda: FakeSession(experiments)

    try:
        response = TestClient(app).get(f"/api/projects/{project_id}/tree")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == str(project_id)
    assert [node["node_id"] for node in body["nodes"]] == [
        "1",
        "2-1",
        "2-2",
        "10-1",
    ]
    assert body["nodes"][0]["report_available"] is True
    assert "report_html_path" not in response.text
    assert body["nodes"][1]["status"] == "running"
    assert body["nodes"][2]["metrics"] == {}


class BranchFakeSession:
    def __init__(self, parent, node_ids: list[str]) -> None:
        self.parent = parent
        self.node_ids = node_ids
        self.added = []
        self.committed = False

    async def scalar(self, _statement):
        return self.parent

    async def scalars(self, _statement):
        return FakeScalarResult(self.node_ids)

    def add(self, experiment) -> None:
        self.added.append(experiment)

    async def commit(self) -> None:
        self.committed = True


def test_branch_dialog_creates_git_branch_and_pending_child_node(tmp_path) -> None:
    project_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    project = SimpleNamespace(id=project_id)
    parent = make_experiment(
        "1",
        None,
        id=parent_id,
        git_branch="exp/1",
        config={"entrypoint": "train.py"},
    )
    session = BranchFakeSession(parent, ["1", "2-1"])
    git_service = GitService(tmp_path)
    initial = git_service.initialize_project_repository(project_id)
    git_service.create_experiment_branch(project_id, "1", initial.head_sha)
    git_service.create_experiment_branch(project_id, "2-1", initial.head_sha)

    app.dependency_overrides[get_owned_project] = lambda: project
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_tree_git_service] = lambda: git_service

    try:
        response = TestClient(app).post(
            f"/api/projects/{project_id}/tree/nodes/{parent_id}/branches",
            json={
                "focus": "training",
                "approach": "Use cosine decay with a five-epoch warmup",
                "budget": "balanced",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["node"]["node_id"] == "2-2"
    assert body["node"]["parent_node_id"] == "1"
    assert body["node"]["git_branch"] == "exp/2-2"
    assert body["node"]["status"] == "pending"
    assert body["node"]["config"]["entrypoint"] == "train.py"
    assert body["node"]["config"]["branch_plan"]["focus"] == "training"
    assert body["branch"]["parent_head_sha"] == initial.head_sha
    assert session.committed is True
    assert session.added[0].node_id == "2-2"
    assert git_service.get_repository_status(project_id).current_branch == "exp/2-2"


def test_branch_dialog_rejects_an_empty_experiment_approach() -> None:
    with pytest.raises(ValidationError):
        BranchPlanCreate.model_validate(
            {
                "focus": "model",
                "approach": "          ",
                "budget": "quick",
            }
        )
