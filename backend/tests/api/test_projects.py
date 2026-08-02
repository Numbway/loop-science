from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.api.projects import list_user_projects


class ScalarResult:
    def __init__(self, values) -> None:
        self.values = values

    def all(self):
        return self.values


class FakeSession:
    def __init__(self, *results) -> None:
        self.results = list(results)

    async def scalars(self, _query):
        return ScalarResult(self.results.pop(0))


@pytest.mark.asyncio
async def test_project_dashboard_returns_owned_projects_with_latest_run() -> None:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    project = SimpleNamespace(
        id=project_id,
        user_id=user_id,
        name="TIM test",
        status="running",
        paper_title="Existing training assets",
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=1),
        preparation_config={
            "workflow": "existing_assets",
            "data": {"selected_name": "case00"},
            "execution": {"host": "gpu.example.edu"},
            "code": {"entrypoint": "src/train.py"},
        },
    )
    older = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=project_id,
        status="failed",
        metrics=None,
        created_at=now - timedelta(minutes=20),
    )
    latest = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=project_id,
        status="running",
        metrics={"loss": 0.25},
        created_at=now,
    )
    response = await list_user_projects(
        current_user=SimpleNamespace(id=user_id),
        db=FakeSession([project], [latest, older]),
    )

    assert len(response.projects) == 1
    item = response.projects[0]
    assert item.name == "TIM test"
    assert item.workflow == "existing_assets"
    assert item.experiment_count == 2
    assert item.experiment_status_counts == {"running": 1, "failed": 1}
    assert item.latest_experiment_id == latest.id
    assert item.latest_metrics == {"loss": 0.25}
    assert item.data_name == "case00"
    assert item.remote_host == "gpu.example.edu"
    assert item.code_entrypoint == "src/train.py"
