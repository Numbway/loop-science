from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.experiment_detail import (
    get_detail_git_service,
    get_detail_storage,
    get_owned_experiment,
    get_tensorboard_public_url,
)
from app.core.database import get_db
from app.main import app
from app.services.git.service import BranchDiff


class FakeScalarResult:
    def __init__(self, values) -> None:
        self.values = values

    def all(self):
        return list(self.values)


class FakeSession:
    def __init__(self, project, parent, logs, references) -> None:
        self.project = project
        self.parent = parent
        self.scalar_results = [logs, references]

    async def get(self, _model, _identifier):
        return self.project

    async def scalar(self, _statement):
        return self.parent

    async def scalars(self, _statement):
        return FakeScalarResult(self.scalar_results.pop(0))


class FakeGitService:
    def compare_branches(self, project_id, base_branch, target_branch):
        return BranchDiff(
            base_branch=base_branch,
            target_branch=target_branch,
            files=["train.py", "config.yaml"],
            patch=(
                "diff --git a/train.py b/train.py\n"
                "--- a/train.py\n"
                "+++ b/train.py\n"
                "@@ -1 +1,2 @@\n"
                "-learning_rate = 0.1\n"
                "+learning_rate = 0.01\n"
                "+scheduler = 'cosine'\n"
            ),
            insertions=2,
            deletions=1,
            truncated=False,
        )


def make_experiment(project_id: uuid.UUID):
    return SimpleNamespace(
        id=uuid.uuid4(),
        project_id=project_id,
        node_id="2-1",
        parent_node_id="1",
        git_branch="exp/2-1",
        status="completed",
        improvement_description="Use cosine decay with warmup",
        metrics={"accuracy": 0.914, "loss": 0.286},
        config={
            "epochs": 120,
            "scheduler": "cosine",
            "_recovery": {
                "status": "recovered",
                "category": "cuda_out_of_memory",
                "attempt": 1,
                "max_attempts": 1,
                "message": "The automatic retry completed successfully.",
                "action": "No further action is required.",
                "updated_at": "2026-08-01T10:12:04Z",
            },
        },
        diagnosis="Convergence improved while validation loss remained stable.",
        code_changes={"train.py": "Add cosine learning-rate scheduler"},
        duration_seconds=3724,
        created_by="user",
        started_at=datetime(2026, 8, 1, 9, 10, tzinfo=UTC),
        completed_at=datetime(2026, 8, 1, 10, 12, 4, tzinfo=UTC),
        report_html_path="/private/reports/2-1.html",
    )


def test_experiment_detail_returns_metrics_evidence_diff_and_monitoring(
    tmp_path,
) -> None:
    project_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    experiment = make_experiment(project_id)
    project = SimpleNamespace(
        id=project_id,
        name="Adaptive vision",
        paper_title="Deep Residual Learning",
        target_metrics={"accuracy": 0.94},
    )
    parent = SimpleNamespace(
        id=parent_id,
        node_id="1",
        git_branch="exp/1",
        metrics={"accuracy": 0.873, "loss": 0.421},
    )
    logs = [
        SimpleNamespace(
            level="warning",
            message="Epoch 2/2 validation plateau",
            timestamp=datetime(2026, 8, 1, 10, 11, tzinfo=UTC),
        ),
        SimpleNamespace(
            level="info",
            message="Epoch 1/2 accuracy=0.90",
            timestamp=datetime(2026, 8, 1, 10, 10, tzinfo=UTC),
        ),
    ]
    reference = SimpleNamespace(
        id=uuid.uuid4(),
        title="SGDR: Stochastic Gradient Descent with Warm Restarts",
        authors=["Ilya Loshchilov", "Frank Hutter"],
        year=2017,
        url="https://arxiv.org/abs/1608.03983",
        key_contributions=["Introduces cosine annealing with warm restarts"],
    )
    session = FakeSession(project, parent, logs, [reference])
    event_directory = tmp_path / "experiment_runs" / str(experiment.id) / "tensorboard"
    event_directory.mkdir(parents=True)
    (event_directory / "events.out.tfevents.test").write_bytes(b"fixture")

    app.dependency_overrides[get_owned_experiment] = lambda: experiment
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_detail_git_service] = lambda: FakeGitService()
    app.dependency_overrides[get_detail_storage] = lambda: tmp_path
    app.dependency_overrides[get_tensorboard_public_url] = lambda: (
        "http://localhost:6006"
    )

    try:
        response = TestClient(app).get(f"/api/experiments/{experiment.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["node_id"] == "2-1"
    assert body["parent_experiment_id"] == str(parent_id)
    accuracy = next(
        metric for metric in body["metric_comparisons"] if metric["name"] == "accuracy"
    )
    assert accuracy["current"] == 0.914
    assert accuracy["parent"] == 0.873
    assert accuracy["delta"] == 0.041000000000000036
    assert accuracy["target"] == 0.94
    assert body["code_diff"]["files"] == ["train.py", "config.yaml"]
    assert body["code_diff"]["insertions"] == 2
    assert body["tensorboard"] == {
        "available": True,
        "event_file_count": 1,
        "embed_url": "http://localhost:6006/",
    }
    assert body["recent_logs"][0]["message"].startswith("Epoch 1/2")
    assert body["references"][0]["year"] == 2017
    assert body["report_available"] is True
    assert body["recovery"]["status"] == "recovered"
    assert body["recovery"]["category"] == "cuda_out_of_memory"
    assert "_recovery" not in body["config"]
    assert "/private/reports" not in response.text
