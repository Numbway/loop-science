"""End-to-end project creation wizard API."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.config import settings
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.project import Project
from app.models.user import User
from app.schemas.ai import DialogQuestion, ProjectConfig
from app.schemas.project_wizard import (
    CodeGenerationResponse,
    DialogAnswerRequest,
    DialogResponse,
    GeneratedFile,
    PaperUploadResponse,
    SaveCodeRequest,
    SaveCodeResponse,
    StartExperimentResponse,
)
from app.services.ai import BrainstormDialog, CodeAgent
from app.services.git import GitService
from app.services.git.exceptions import GitServiceError
from app.services.paper.parser import PaperParseError, PDFParser
from app.tasks.experiment_tasks import run_experiment_task

router = APIRouter(prefix="/api", tags=["project-wizard"])

MAX_PDF_BYTES = 25 * 1024 * 1024
_dialog = BrainstormDialog()


def get_wizard_storage() -> Path:
    """Return the project storage root for dependency overrides and deployment."""
    return Path(settings.STORAGE_PATH).resolve()


def get_brainstorm_dialog() -> BrainstormDialog:
    """Return the process-local guided dialog service."""
    return _dialog


def _paper_summary(project: Project) -> str:
    metadata = project.paper_metadata or {}
    return str(metadata.get("abstract") or project.paper_title)


def _dialog_response(
    session_id: str,
    result: DialogQuestion | ProjectConfig,
) -> DialogResponse:
    if isinstance(result, ProjectConfig):
        return DialogResponse(
            session_id=session_id,
            complete=True,
            config=result,
        )
    return DialogResponse(
        session_id=session_id,
        question=result.question,
        options=result.options,
        input_type=result.type,
    )


def _safe_repository_file(repository: Path, relative_path: str) -> Path:
    candidate_path = Path(relative_path)
    if (
        candidate_path.is_absolute()
        or ".." in candidate_path.parts
        or ".git" in candidate_path.parts
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Generated file path must remain inside the project repository.",
        )
    resolved = (repository / candidate_path).resolve()
    if not resolved.is_relative_to(repository.resolve()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Generated file path must remain inside the project repository.",
        )
    return resolved


def _language_for(path: str) -> str:
    return {
        ".py": "python",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".txt": "text",
        ".json": "json",
    }.get(Path(path).suffix.lower(), "text")


@router.post(
    "/projects/wizard/upload",
    response_model=PaperUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_paper(
    paper: UploadFile = File(...),  # noqa: B008
    project_name: str = Form(""),
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    storage_root: Path = Depends(get_wizard_storage),  # noqa: B008
) -> PaperUploadResponse:
    """Validate, save, and parse the source paper into a draft project."""
    filename = paper.filename or ""
    content = await paper.read(MAX_PDF_BYTES + 1)
    if (
        not filename.lower().endswith(".pdf")
        or not content.startswith(b"%PDF-")
        or len(content) > MAX_PDF_BYTES
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload a valid PDF no larger than 25 MB.",
        )

    project_id = uuid.uuid4()
    source_directory = storage_root / str(project_id) / "source"
    source_directory.mkdir(parents=True, exist_ok=True)
    paper_path = source_directory / "paper.pdf"
    paper_path.write_bytes(content)

    try:
        parsed = await PDFParser().parse(paper_path)
    except PaperParseError as exc:
        paper_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The PDF could not be parsed. Export it again and retry.",
        ) from exc

    resolved_name = (
        project_name.strip() or parsed.title or "Untitled research project"
    )[:200]
    project = Project(
        id=project_id,
        user_id=current_user.id,
        name=resolved_name,
        paper_title=(parsed.title or filename)[:500],
        paper_path=str(paper_path),
        paper_metadata={
            "authors": parsed.authors,
            "abstract": parsed.abstract,
            "keywords": parsed.keywords,
            "key_contributions": parsed.key_contributions,
        },
        improvement_targets=[],
        target_metrics={},
        max_iterations=5,
        repo_path="",
        status="created",
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)

    return PaperUploadResponse(
        project_id=project.id,
        project_name=project.name,
        paper_title=project.paper_title,
        abstract=parsed.abstract,
        authors=parsed.authors,
        keywords=parsed.keywords,
    )


@router.post(
    "/projects/{project_id}/wizard/dialog/start",
    response_model=DialogResponse,
)
async def start_project_dialog(
    project: Project = Depends(get_owned_project),  # noqa: B008
    dialog: BrainstormDialog = Depends(get_brainstorm_dialog),  # noqa: B008
) -> DialogResponse:
    """Start the one-question-at-a-time configuration dialog."""
    result = await dialog.start_session(_paper_summary(project))
    session_id = str(result.pop("session_id"))
    return _dialog_response(
        session_id,
        DialogQuestion.model_validate(result),
    )


@router.post(
    "/projects/{project_id}/wizard/dialog/answer",
    response_model=DialogResponse,
)
async def answer_project_dialog(
    request: DialogAnswerRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    dialog: BrainstormDialog = Depends(get_brainstorm_dialog),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> DialogResponse:
    """Store one answer and return only the next question."""
    result = await dialog.answer(
        request.session_id,
        request.answer,
        _paper_summary(project),
    )
    if isinstance(result, ProjectConfig):
        project.improvement_targets = result.improvement_targets
        project.target_metrics = result.target_metrics
        project.max_iterations = result.max_iterations
        await db.commit()
    return _dialog_response(request.session_id, result)


@router.post(
    "/projects/{project_id}/wizard/generate",
    response_model=CodeGenerationResponse,
)
async def generate_project_code(
    project: Project = Depends(get_owned_project),  # noqa: B008
    storage_root: Path = Depends(get_wizard_storage),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CodeGenerationResponse:
    """Generate an editable framework in the project's Git repository."""
    if project.status != "created":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Code can only be generated before the project starts.",
        )
    git_service = GitService(storage_root)
    git_service.initialize_project_repository(project.id)
    repository = git_service._repository_path(project.id)
    parsed = await PDFParser().parse(project.paper_path)
    result = await CodeAgent(repository).generate_framework(
        parsed.model_dump(),
        {
            "improvement_targets": project.improvement_targets,
            "target_metrics": project.target_metrics,
            "max_iterations": project.max_iterations,
        },
    )
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Code generation did not complete. Review the agent logs and retry.",
        )

    files: list[GeneratedFile] = []
    for relative_path in result.modified_files:
        file_path = _safe_repository_file(repository, relative_path)
        if file_path.is_file():
            files.append(
                GeneratedFile(
                    path=relative_path,
                    language=_language_for(relative_path),
                    content=file_path.read_text(encoding="utf-8"),
                )
            )
    repository_status = git_service.get_repository_status(project.id)
    if repository_status.is_clean:
        commit_sha = repository_status.head_sha
    else:
        commit_sha = git_service.commit_changes(
            project.id, "Generate initial experiment framework"
        ).sha
    project.repo_path = str(repository)
    await db.commit()
    return CodeGenerationResponse(
        project_id=project.id,
        files=files,
        summary=f"{result.final_message}\n\nInitial commit: {commit_sha[:10]}",
    )


@router.put(
    "/projects/{project_id}/wizard/code",
    response_model=SaveCodeResponse,
)
async def save_reviewed_code(
    request: SaveCodeRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    storage_root: Path = Depends(get_wizard_storage),  # noqa: B008
) -> SaveCodeResponse:
    """Persist the student's reviewed file contents as one Git commit."""
    if project.status != "created":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Code review is closed after the project starts.",
        )
    git_service = GitService(storage_root)
    repository = git_service._repository_path(project.id)
    for generated_file in request.files:
        if len(generated_file.content.encode("utf-8")) > 2 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"{generated_file.path} exceeds the 2 MB review limit.",
            )
        file_path = _safe_repository_file(repository, generated_file.path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(generated_file.content, encoding="utf-8")

    repository_status = git_service.get_repository_status(project.id)
    if repository_status.is_clean:
        commit_sha = repository_status.head_sha
    else:
        commit_sha = git_service.commit_changes(
            project.id, "Apply reviewed experiment code"
        ).sha
    return SaveCodeResponse(
        project_id=project.id,
        commit_sha=commit_sha,
        files_saved=len(request.files),
    )


@router.post(
    "/projects/{project_id}/wizard/start",
    response_model=StartExperimentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_initial_experiment(
    project: Project = Depends(get_owned_project),  # noqa: B008
    storage_root: Path = Depends(get_wizard_storage),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> StartExperimentResponse:
    """Create the first experiment branch and queue its container task."""
    if project.status != "created":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project has already started.",
        )
    git_service = GitService(storage_root)
    repository_status = git_service.get_repository_status(project.id)
    try:
        branch = git_service.create_experiment_branch(
            project.id,
            "1",
            repository_status.head_sha,
        )
    except GitServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "detail": exc.message,
                "hint": exc.hint,
            },
        ) from exc

    experiment = Experiment(
        id=uuid.uuid4(),
        project_id=project.id,
        node_id="1",
        parent_node_id=None,
        git_branch=branch.name,
        improvement_description="Initial reproduction baseline",
        code_changes={},
        config={
            "entrypoint": "train.py",
            "target_metrics": project.target_metrics,
        },
        status="pending",
        created_by="user",
    )
    project.status = "running"
    db.add(experiment)
    await db.commit()
    run_experiment_task.delay(str(experiment.id))
    return StartExperimentResponse(
        project_id=project.id,
        experiment_id=experiment.id,
        status="queued",
    )
