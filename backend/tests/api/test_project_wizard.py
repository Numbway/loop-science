from __future__ import annotations

import uuid
from io import BytesIO
from types import SimpleNamespace

import fitz
import pytest
from fastapi import HTTPException, UploadFile

from app.api import project_wizard
from app.api.project_wizard import (
    answer_project_dialog,
    generate_project_code,
    save_reviewed_code,
    start_initial_experiment,
    start_project_dialog,
    upload_project_paper,
)
from app.schemas.project_wizard import SaveCodeRequest
from app.services.ai import BrainstormDialog, CodeAgent


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0

    def add(self, value) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def refresh(self, _value) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def make_paper_upload() -> UploadFile:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Adaptive Vision Systems\nAda Researcher\n\n"
        "Abstract\nThis paper studies a compact neural network for image classification. "
        "The method improves accuracy through adaptive feature selection.",
    )
    content = document.write()
    document.close()
    return UploadFile(filename="adaptive-vision.pdf", file=BytesIO(content))


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf(tmp_path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await upload_project_paper(
            paper=UploadFile(filename="notes.txt", file=BytesIO(b"not a pdf")),
            project_name="",
            db=FakeSession(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            storage_root=tmp_path,
        )

    assert exc_info.value.status_code == 422
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_code_agent_rejects_paths_outside_project_workspace(tmp_path) -> None:
    agent = CodeAgent(tmp_path / "project")

    result = await agent._execute_tool(
        "write_file",
        {"path": "../outside.py", "content": "print('unsafe')"},
    )

    assert result == "Error: path must remain within the workspace"
    assert not (tmp_path / "outside.py").exists()
    git_result = await agent._execute_tool(
        "write_file",
        {"path": ".git/config", "content": "unsafe"},
    )
    assert git_result == "Error: path must remain within the workspace"


@pytest.mark.asyncio
async def test_complete_wizard_creates_reviewed_code_and_queues_experiment(
    tmp_path, monkeypatch
) -> None:
    db = FakeSession()
    uploaded = await upload_project_paper(
        paper=make_paper_upload(),
        project_name="Adaptive reproduction",
        db=db,
        current_user=SimpleNamespace(id=uuid.uuid4()),
        storage_root=tmp_path,
    )
    project = db.added[0]
    assert uploaded.paper_title == "Adaptive Vision Systems"
    assert project.paper_path.endswith("paper.pdf")

    dialog = BrainstormDialog()
    question = await start_project_dialog(project=project, dialog=dialog)
    assert question.complete is False
    assert question.question

    for answer in (
        "Adaptive feature selection",
        "模型架构",
        "accuracy=92%",
        "5 轮",
        "让 AI 推荐参考论文",
        "单张 GPU，优先保证可复现",
    ):
        question = await answer_project_dialog(
            request=SimpleNamespace(
                session_id=question.session_id,
                answer=answer,
            ),
            project=project,
            dialog=dialog,
            db=db,
        )
    assert question.complete is True
    assert question.config is not None
    assert project.target_metrics == {"accuracy": 0.92}

    generated = await generate_project_code(
        project=project,
        storage_root=tmp_path,
        db=db,
    )
    assert len(generated.files) == 7
    assert {item.path for item in generated.files} >= {"train.py", "model.py"}
    train_file = next(item for item in generated.files if item.path == "train.py")
    assert 'in {"1", "true"}' in train_file.content
    regenerated = await generate_project_code(
        project=project,
        storage_root=tmp_path,
        db=db,
    )
    assert len(regenerated.files) == 7

    generated.files[0].content += "\n# Reviewed by the researcher.\n"
    saved = await save_reviewed_code(
        request=SaveCodeRequest(files=generated.files),
        project=project,
        storage_root=tmp_path,
    )
    assert saved.files_saved == 7
    assert len(saved.commit_sha) == 40

    queued = []
    monkeypatch.setattr(project_wizard.run_experiment_task, "delay", queued.append)
    started = await start_initial_experiment(
        project=project,
        storage_root=tmp_path,
        db=db,
    )

    assert started.status == "queued"
    assert project.status == "running"
    assert queued == [str(started.experiment_id)]
    assert (tmp_path / str(project.id) / "git_repo" / "train.py").is_file()
    assert db.added[-1].git_branch == "exp/1"
