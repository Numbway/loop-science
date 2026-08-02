from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.experiment_detail import get_owned_experiment
from app.api.experiment_report import get_report_generator, get_report_storage
from app.core.database import get_db
from app.main import app
from app.services.git import BranchDiff
from app.services.report import HTMLReportGenerator


class FakeScalarResult:
    def __init__(self, values) -> None:
        self.values = values

    def all(self):
        return list(self.values)


class FakeSession:
    def __init__(self, project, parent, references) -> None:
        self.project = project
        self.parent = parent
        self.references = references
        self.committed = False

    async def get(self, _model, _identifier):
        return self.project

    async def scalar(self, _statement):
        return self.parent

    async def scalars(self, _statement):
        return FakeScalarResult(self.references)

    async def commit(self):
        self.committed = True


class FakeGitService:
    def compare_branches(
        self,
        _project_id,
        base_branch,
        target_branch,
        *,
        max_patch_characters,
    ):
        return BranchDiff(
            base_branch=base_branch,
            target_branch=target_branch,
            files=["train.py"],
            patch="+scheduler = 'cosine'\n",
            insertions=1,
            deletions=0,
            truncated=False,
        )


def report_entities():
    project_id = uuid.uuid4()
    experiment = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=project_id,
        node_id="2-1",
        parent_node_id="1",
        git_branch="exp/2-1",
        status="completed",
        improvement_description="Use cosine decay",
        metrics={"accuracy": 0.91},
        config={"epochs": 90},
        diagnosis="Validation gap narrowed.",
        duration_seconds=120,
        created_by="ai",
        started_at=datetime(2026, 8, 1, 9, 10, tzinfo=UTC),
        completed_at=datetime(2026, 8, 1, 9, 12, tzinfo=UTC),
        report_html_path=None,
    )
    project = SimpleNamespace(
        id=project_id,
        name="Adaptive vision",
        paper_title="Deep Residual Learning",
        paper_metadata={},
        target_metrics={"accuracy": 0.92},
        improvement_targets=[],
    )
    parent = SimpleNamespace(
        id=uuid.uuid4(),
        node_id="1",
        git_branch="exp/1",
        metrics={"accuracy": 0.87},
    )
    references = []
    return experiment, project, parent, references


def test_report_api_generates_views_and_downloads_owned_report(tmp_path) -> None:
    experiment, project, parent, references = report_entities()
    session = FakeSession(project, parent, references)
    generator = HTMLReportGenerator(tmp_path, git_service=FakeGitService())
    app.dependency_overrides[get_owned_experiment] = lambda: experiment
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_report_generator] = lambda: generator
    app.dependency_overrides[get_report_storage] = lambda: tmp_path

    try:
        client = TestClient(app)
        generated = client.post(f"/api/experiments/{experiment.id}/report")
        viewed = client.get(f"/api/experiments/{experiment.id}/report")
        downloaded = client.get(f"/api/experiments/{experiment.id}/report/download")
    finally:
        app.dependency_overrides.clear()

    assert generated.status_code == 200
    assert generated.json()["available"] is True
    assert generated.json()["view_endpoint"].endswith("/report")
    assert session.committed is True
    assert experiment.report_html_path.endswith("report.html")
    assert viewed.status_code == 200
    assert "text/html" in viewed.headers["content-type"]
    assert viewed.headers["content-disposition"].startswith("inline")
    assert "frame-ancestors 'none'" in viewed.headers["content-security-policy"]
    assert 'id="report-summary"' in viewed.text
    assert downloaded.status_code == 200
    assert downloaded.headers["content-disposition"].startswith("attachment")


def test_report_api_rejects_noncanonical_private_path(tmp_path) -> None:
    experiment, _project, _parent, _references = report_entities()
    private_report = tmp_path / "legacy-private-report.html"
    private_report.write_text("<h1>private</h1>", encoding="utf-8")
    experiment.report_html_path = str(private_report)
    app.dependency_overrides[get_owned_experiment] = lambda: experiment
    app.dependency_overrides[get_report_storage] = lambda: tmp_path

    try:
        response = TestClient(app).get(f"/api/experiments/{experiment.id}/report")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert str(private_report) not in response.text
