from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_owned_project
from app.core.database import get_db
from app.main import app


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
