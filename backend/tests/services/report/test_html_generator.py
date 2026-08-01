from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import time
from types import SimpleNamespace

import pytest
from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary
from tensorboard.summary.writer.event_file_writer import EventFileWriter

from app.services.git import BranchDiff
from app.services.report import HTMLReportGenerator


class FakeGitService:
    def compare_branches(
        self,
        _project_id,
        base_branch,
        target_branch,
        *,
        max_patch_characters,
    ):
        assert max_patch_characters == 80_000
        return BranchDiff(
            base_branch=base_branch,
            target_branch=target_branch,
            files=["train.py"],
            patch=(
                "diff --git a/train.py b/train.py\n"
                "--- a/train.py\n"
                "+++ b/train.py\n"
                "@@ -1 +1 @@\n"
                "-learning_rate = 0.1\n"
                "+learning_rate = 0.01\n"
            ),
            insertions=1,
            deletions=1,
            truncated=False,
        )


def report_entities():
    project_id = uuid.uuid4()
    experiment_id = uuid.uuid4()
    project = SimpleNamespace(
        id=project_id,
        name="Adaptive vision",
        paper_title="Deep Residual Learning",
        paper_metadata={"authors": ["Kaiming He"]},
        target_metrics={"validation/accuracy": 0.92, "validation/loss": 0.28},
        improvement_targets=["提高少数类召回率"],
    )
    parent = SimpleNamespace(
        id=uuid.uuid4(),
        node_id="1",
        git_branch="exp/1",
        metrics={"validation/accuracy": 0.84, "validation/loss": 0.43},
    )
    experiment = SimpleNamespace(
        id=experiment_id,
        project_id=project_id,
        node_id="2-1",
        parent_node_id="1",
        git_branch="exp/2-1",
        status="completed",
        improvement_description="Use cosine decay with layered augmentation",
        metrics={"validation/accuracy": 0.89, "validation/loss": 0.31},
        config={"epochs": 90, "learning_rate": 0.01},
        diagnosis="<script>alert('unsafe')</script> validation gap narrowed.",
        duration_seconds=3724,
        created_by="ai",
        started_at=datetime(2026, 8, 1, 9, 10, tzinfo=UTC),
        completed_at=datetime(2026, 8, 1, 10, 12, 4, tzinfo=UTC),
        report_html_path=None,
    )
    references = [
        SimpleNamespace(
            title="SGDR",
            authors=["Ilya Loshchilov", "Frank Hutter"],
            year=2017,
            url="https://arxiv.org/abs/1608.03983",
            key_contributions=["Introduces cosine annealing."],
        ),
        SimpleNamespace(
            title="Unsafe URL evidence",
            authors=[],
            year=None,
            url="javascript:alert(1)",
            key_contributions=[],
        ),
    ]
    return experiment, project, parent, references


@pytest.mark.asyncio
async def test_generator_creates_portable_seven_section_report(tmp_path) -> None:
    experiment, project, parent, references = report_entities()
    run_directory = tmp_path / "experiment_runs" / str(experiment.id) / "runs"
    writer = EventFileWriter(str(run_directory))
    for step, value in ((1, 0.72), (2, 0.81), (3, 0.89)):
        writer.add_event(
            Event(
                wall_time=time(),
                step=step,
                summary=Summary(
                    value=[
                        Summary.Value(
                            tag="validation/accuracy",
                            simple_value=value,
                        )
                    ]
                ),
            )
        )
    writer.close()

    generator = HTMLReportGenerator(tmp_path, git_service=FakeGitService())
    report_path = await generator.generate(
        experiment,
        project,
        parent,
        references,
    )

    expected_path = (
        tmp_path / "experiment_reports" / str(experiment.id) / "report.html"
    ).resolve()
    assert report_path == str(expected_path)
    html = expected_path.read_text(encoding="utf-8")
    assert all(
        f'id="report-{section}"' in html
        for section in (
            "summary",
            "analysis",
            "comparison",
            "curves",
            "code",
            "references",
            "next-steps",
        )
    )
    assert "<style>" in html
    assert "<polyline" in html
    assert "validation/accuracy" in html
    assert "+5.00 pp" in html
    assert "learning_rate = 0.01" in html
    assert "&lt;script&gt;alert" in html
    assert "javascript:alert" not in html
    assert "<iframe" not in html
    assert "<link " not in html
    assert "<script " not in html
