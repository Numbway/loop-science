"""End-to-end project creation wizard API."""

from __future__ import annotations

import json
import shutil
import shlex
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.config import settings
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.credential_profile import CredentialProfile
from app.models.project import Project
from app.models.user import User
from app.schemas.ai import DialogQuestion, ProjectConfig
from app.schemas.project_wizard import (
    CodeGenerationResponse,
    DataSelectionResponse,
    DialogAnswerRequest,
    DialogResponse,
    ExistingAssetsProjectRequest,
    ExistingAssetsProjectResponse,
    GeneratedFile,
    PaperUploadResponse,
    PaperAnalysisResponse,
    PreparationStatusResponse,
    RemoteDataEntryResponse,
    RemoteDataListingResponse,
    RemoteDataSelectionRequest,
    RemoteCodeImportRequest,
    RemoteCodeImportResponse,
    SaveCodeRequest,
    SaveCodeResponse,
    SshConnectionResponse,
    StartExperimentResponse,
    WizardProjectSnapshot,
)
from app.schemas.system_config import ProjectProfileSelectionRequest
from app.services.ai import BrainstormDialog, CodeAgent
from app.services.credentials import decrypt_credentials
from app.services.git import GitService
from app.services.git.exceptions import GitServiceError
from app.services.paper.analyzer import PaperAnalysisError, PaperAnalyzer
from app.services.paper.parser import PaperParseError, PDFParser
from app.services.ssh import SshCodeImporter, SshConnectionError, SshDataBrowser
from app.tasks.experiment_tasks import run_experiment_task

router = APIRouter(prefix="/api", tags=["project-wizard"])

MAX_PDF_BYTES = 25 * 1024 * 1024
_dialogs: dict[uuid.UUID, BrainstormDialog] = {}


def get_wizard_storage() -> Path:
    """Return the project storage root for dependency overrides and deployment."""
    return Path(settings.STORAGE_PATH).resolve()


def get_brainstorm_dialog() -> BrainstormDialog | None:
    """Dependency seam; production creates a project-keyed dialog."""
    return None


def get_ssh_data_browser() -> SshDataBrowser:
    """Return a browser for data already present on a verified SSH server."""
    return SshDataBrowser()


def get_ssh_code_importer() -> SshCodeImporter:
    """Return an importer for a bounded remote training-code snapshot."""
    return SshCodeImporter()


def _paper_summary(project: Project) -> str:
    analysis = getattr(project, "paper_analysis", {}) or {}
    if analysis:
        return json.dumps(analysis, ensure_ascii=False)
    metadata = project.paper_metadata or {}
    return str(metadata.get("abstract") or project.paper_title)


def _preparation(project: Project) -> dict[str, Any]:
    value = getattr(project, "preparation_config", {}) or {}
    return dict(value)


async def _selected_profile(
    project: Project,
    db: AsyncSession,
    kind: str,
) -> CredentialProfile | None:
    field = (
        "ai_credential_profile_id"
        if kind == "llm"
        else "ssh_credential_profile_id"
    )
    profile_id = getattr(project, field, None)
    if not profile_id:
        return None
    profile = await db.get(CredentialProfile, profile_id)
    if (
        profile is None
        or profile.user_id != project.user_id
        or profile.kind != kind
        or not profile.verified
    ):
        return None
    return profile


async def _project_llm_connection(
    project: Project,
    db: AsyncSession,
) -> dict[str, str]:
    profile = await _selected_profile(project, db, "llm")
    if profile is None:
        return {}
    public = profile.public_config or {}
    return {
        "api_key": str(
            decrypt_credentials(profile.encrypted_credentials).get("api_key")
            or ""
        ),
        "model": str(public.get("model") or settings.ANTHROPIC_MODEL),
        "base_url": str(
            public.get("base_url") or settings.ANTHROPIC_BASE_URL
        ),
        "provider": str(public.get("provider") or "anthropic"),
    }


def _data_response(value: dict[str, Any] | None) -> DataSelectionResponse | None:
    if (
        not value
        or not value.get("ready")
        or value.get("source") != "remote"
        or not value.get("remote_path")
    ):
        return None
    return DataSelectionResponse(
        ready=True,
        source="remote",
        kind=value["kind"],
        selected_name=value["selected_name"],
        path=value["remote_path"],
        file_count=int(value["file_count"]),
        total_bytes=int(value["total_bytes"]),
    )


def _code_response(value: dict[str, Any] | None) -> RemoteCodeImportResponse | None:
    if (
        not value
        or not value.get("ready")
        or value.get("source") != "remote"
        or not value.get("remote_path")
        or not value.get("entrypoint")
    ):
        return None
    return RemoteCodeImportResponse(
        ready=True,
        source="remote",
        selected_name=str(value["selected_name"]),
        path=str(value["remote_path"]),
        entrypoint=str(value["entrypoint"]),
        arguments=[
            str(argument) for argument in (value.get("arguments") or [])
        ],
        file_count=int(value["file_count"]),
        total_bytes=int(value["total_bytes"]),
        skipped_count=int(value.get("skipped_count") or 0),
    )


def _execution_response(
    value: dict[str, Any] | None,
) -> SshConnectionResponse | None:
    if not value or not value.get("ready"):
        return None
    return SshConnectionResponse(
        ready=True,
        host=value["host"],
        port=int(value["port"]),
        username=value["username"],
        auth_type=value["auth_type"],
        host_key_fingerprint=value["host_key_fingerprint"],
        capabilities=value.get("capabilities") or {},
    )


async def _preparation_status(
    project: Project,
    db: AsyncSession,
) -> PreparationStatusResponse:
    preparation = _preparation(project)
    workflow = str(preparation.get("workflow") or "paper_reproduction")
    existing_assets = workflow == "existing_assets"
    ai_profile = await _selected_profile(project, db, "llm")
    ssh_profile = await _selected_profile(project, db, "ssh")
    api_key_ready = bool(ai_profile) or existing_assets
    analysis_ready = (
        bool(getattr(project, "paper_analysis", {}) or {}) or existing_assets
    )
    data_value = preparation.get("data")
    code_value = preparation.get("code")
    code_response = _code_response(code_value)
    execution_value = dict(ssh_profile.public_config) if ssh_profile else None
    data_ready = bool(
        data_value
        and data_value.get("ready")
        and data_value.get("source") == "remote"
        and ssh_profile
        and data_value.get("ssh_profile_id") == str(ssh_profile.id)
    )
    execution_ready = bool(execution_value and execution_value.get("ready"))
    code_ready = bool(getattr(project, "repo_path", "")) and (
        not existing_assets or code_response is not None
    )
    ready_to_generate = (
        not existing_assets
        and all((api_key_ready, analysis_ready, data_ready, execution_ready))
    )
    launch_inputs_ready = data_ready and execution_ready
    if not existing_assets:
        launch_inputs_ready = (
            launch_inputs_ready and api_key_ready and analysis_ready
        )
    requirements = [
        (data_ready, "在所选 SSH 服务器上选择数据文件或文件夹"),
        (execution_ready, "验证 SSH 实验服务器"),
        (
            code_ready,
            (
                "从 SSH 服务器导入现有训练代码"
                if existing_assets
                else "生成并审核实验代码"
            ),
        ),
    ]
    if not existing_assets:
        requirements[0:0] = [
            (api_key_ready, "配置大模型 API Key"),
            (analysis_ready, "完成论文大模型分析"),
        ]
    missing_labels = [label for ready, label in requirements if not ready]
    return PreparationStatusResponse(
        workflow=(
            "existing_assets" if existing_assets else "paper_reproduction"
        ),
        api_key_ready=api_key_ready,
        paper_analysis_ready=analysis_ready,
        data_ready=data_ready,
        execution_ready=execution_ready,
        code_ready=code_ready,
        ready_to_generate=ready_to_generate,
        ready_to_start=launch_inputs_ready and code_ready,
        ai_profile_id=ai_profile.id if ai_profile else None,
        ssh_profile_id=ssh_profile.id if ssh_profile else None,
        data=_data_response(data_value),
        code=code_response,
        execution=_execution_response(execution_value),
        missing=missing_labels,
    )


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Generated file path must remain inside the project repository.",
        )
    resolved = (repository / candidate_path).resolve()
    if not resolved.is_relative_to(repository.resolve()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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


def _reviewable_repository_files(repository: Path) -> list[GeneratedFile]:
    """Return a bounded set of editable text files from an existing repository."""
    if not repository.is_dir():
        return []
    supported = {
        ".json",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
    files: list[GeneratedFile] = []
    for file_path in sorted(repository.rglob("*")):
        if (
            not file_path.is_file()
            or ".git" in file_path.parts
            or file_path.suffix.lower() not in supported
            or file_path.stat().st_size > 2 * 1024 * 1024
        ):
            continue
        resolved = file_path.resolve()
        if not resolved.is_relative_to(repository.resolve()):
            continue
        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = resolved.relative_to(repository.resolve()).as_posix()
        files.append(
            GeneratedFile(
                path=relative,
                language=_language_for(relative),
                content=content,
            )
        )
        if len(files) >= 50:
            break
    return files


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        paper_analysis={},
        improvement_targets=[],
        target_metrics={},
        max_iterations=5,
        repo_path="",
        preparation_config={},
        encrypted_credentials="",
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
    "/projects/wizard/existing-assets",
    response_model=ExistingAssetsProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_existing_assets_project(
    request: ExistingAssetsProjectRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ExistingAssetsProjectResponse:
    """Create a draft that skips paper analysis and framework generation."""
    project = Project(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=request.name.strip(),
        paper_title="Existing training assets",
        paper_path="",
        paper_metadata={},
        paper_analysis={},
        improvement_targets=[],
        target_metrics={},
        max_iterations=1,
        repo_path="",
        preparation_config={"workflow": "existing_assets"},
        encrypted_credentials="",
        status="created",
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return ExistingAssetsProjectResponse(
        project_id=project.id,
        project_name=project.name,
    )


@router.put(
    "/projects/{project_id}/wizard/configurations",
    response_model=PreparationStatusResponse,
)
async def select_project_configurations(
    request: ProjectProfileSelectionRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PreparationStatusResponse:
    """Select reusable user-level LLM and SSH profiles for this project."""

    async def validate(
        profile_id: uuid.UUID | None,
        expected_kind: str,
    ) -> CredentialProfile | None:
        if profile_id is None:
            return None
        profile = await db.get(CredentialProfile, profile_id)
        if (
            profile is None
            or profile.user_id != project.user_id
            or profile.kind != expected_kind
            or not profile.verified
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"所选 {expected_kind.upper()} 配置不存在或尚未验证。",
            )
        return profile

    preparation = _preparation(project)
    if "ai_profile_id" in request.model_fields_set:
        profile = await validate(request.ai_profile_id, "llm")
        project.ai_credential_profile_id = profile.id if profile else None
        preparation["ai"] = (
            {
                **profile.public_config,
                "configured": True,
                "profile_id": str(profile.id),
                "profile_name": profile.name,
            }
            if profile
            else {}
        )
        project.paper_analysis = {}
        _dialogs.pop(project.id, None)
    if "ssh_profile_id" in request.model_fields_set:
        profile = await validate(request.ssh_profile_id, "ssh")
        previous_profile_id = project.ssh_credential_profile_id
        project.ssh_credential_profile_id = profile.id if profile else None
        preparation["execution"] = (
            {
                **profile.public_config,
                "profile_id": str(profile.id),
                "profile_name": profile.name,
            }
            if profile
            else {}
        )
        if previous_profile_id != project.ssh_credential_profile_id:
            preparation["data"] = {}
    project.preparation_config = preparation
    await db.commit()
    return await _preparation_status(project, db)


@router.post(
    "/projects/{project_id}/wizard/analyze",
    response_model=PaperAnalysisResponse,
)
async def analyze_project_paper(
    project: Project = Depends(get_owned_project),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PaperAnalysisResponse:
    """Call the configured LLM and retain a structured paper analysis."""
    connection = await _project_llm_connection(project, db)
    if not connection.get("api_key"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先配置大模型 API Key。",
        )
    parsed = await PDFParser().parse(project.paper_path)
    try:
        analysis = await PaperAnalyzer(
            connection["api_key"],
            connection["model"],
            connection["base_url"],
            provider=connection["provider"],
        ).analyze(parsed.model_dump())
    except PaperAnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    project.paper_analysis = analysis.model_dump()
    await db.commit()
    return analysis


@router.get(
    "/projects/{project_id}/wizard/remote-data",
    response_model=RemoteDataListingResponse,
)
async def browse_project_remote_data(
    path: str = "",
    project: Project = Depends(get_owned_project),  # noqa: B008
    browser: SshDataBrowser = Depends(get_ssh_data_browser),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> RemoteDataListingResponse:
    """Browse files and folders visible to the selected SSH account."""
    profile = await _selected_profile(project, db, "ssh")
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先为项目选择一个已验证的 SSH 服务器配置。",
        )
    try:
        listing = await browser.list_directory(
            dict(profile.public_config or {}),
            decrypt_credentials(profile.encrypted_credentials),
            path,
        )
    except SshConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return RemoteDataListingResponse(
        current_path=listing.current_path,
        parent_path=listing.parent_path,
        entries=[
            RemoteDataEntryResponse(
                name=entry.name,
                path=entry.path,
                kind=entry.kind,
                size=entry.size,
            )
            for entry in listing.entries
        ],
        truncated=listing.truncated,
    )


@router.put(
    "/projects/{project_id}/wizard/remote-data",
    response_model=DataSelectionResponse,
)
async def select_project_remote_data(
    request: RemoteDataSelectionRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    browser: SshDataBrowser = Depends(get_ssh_data_browser),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> DataSelectionResponse:
    """Validate and retain one remote file or folder without copying it."""
    profile = await _selected_profile(project, db, "ssh")
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先为项目选择一个已验证的 SSH 服务器配置。",
        )
    try:
        selected = await browser.select(
            dict(profile.public_config or {}),
            decrypt_credentials(profile.encrypted_credentials),
            request.path,
            request.kind,
        )
    except SshConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    data_config = {
        "ready": True,
        "source": "remote",
        "kind": selected.kind,
        "selected_name": selected.selected_name,
        "remote_path": selected.path,
        "file_count": selected.file_count,
        "total_bytes": selected.total_bytes,
        "ssh_profile_id": str(profile.id),
        "host": str((profile.public_config or {}).get("host") or ""),
    }
    preparation = _preparation(project)
    preparation["data"] = data_config
    project.preparation_config = preparation
    await db.commit()
    response = _data_response(data_config)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="远端数据选择未能保存。",
        )
    return response


@router.post(
    "/projects/{project_id}/wizard/remote-code",
    response_model=RemoteCodeImportResponse,
)
async def import_project_remote_code(
    request: RemoteCodeImportRequest,
    project: Project = Depends(get_owned_project),  # noqa: B008
    importer: SshCodeImporter = Depends(get_ssh_code_importer),  # noqa: B008
    storage_root: Path = Depends(get_wizard_storage),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> RemoteCodeImportResponse:
    """Import existing server-side code as the project's Git baseline."""
    preparation = _preparation(project)
    if preparation.get("workflow") != "existing_assets":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="现有代码导入只适用于“已有代码与数据”快捷流程。",
        )
    if project.repo_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="训练代码已经导入。请创建新项目以更换整套基线代码。",
        )
    profile = await _selected_profile(project, db, "ssh")
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先为项目选择一个已验证的 SSH 服务器配置。",
        )

    project_directory = (storage_root / str(project.id)).resolve()
    if not project_directory.is_relative_to(storage_root.resolve()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="项目代码存储路径无效。",
        )
    project_directory.mkdir(parents=True, exist_ok=True)
    try:
        arguments = shlex.split(request.arguments, posix=True)
        if len(arguments) > 50 or any(len(argument) > 500 for argument in arguments):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="启动参数格式无效，最多允许 50 个参数。",
        ) from exc
    try:
        with TemporaryDirectory(
            prefix="remote-code-",
            dir=project_directory,
        ) as temporary:
            staging = Path(temporary)
            imported = await importer.import_directory(
                dict(profile.public_config or {}),
                decrypt_credentials(profile.encrypted_credentials),
                request.path,
                request.entrypoint,
                staging,
            )
            git_service = GitService(storage_root)
            git_service.initialize_project_repository(project.id)
            repository = git_service._repository_path(project.id)
            for item in staging.iterdir():
                destination = repository / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                elif item.is_file():
                    shutil.copy2(item, destination)
            commit = git_service.commit_changes(
                project.id,
                "Import existing training code from SSH server",
            )
    except SshConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except GitServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "detail": exc.message,
                "hint": exc.hint,
            },
        ) from exc

    code_config = {
        "ready": True,
        "source": "remote",
        "selected_name": imported.selected_name,
        "remote_path": imported.remote_path,
        "entrypoint": imported.entrypoint,
        "arguments": arguments,
        "file_count": imported.file_count,
        "total_bytes": imported.total_bytes,
        "skipped_count": imported.skipped_count,
        "ssh_profile_id": str(profile.id),
        "commit_sha": commit.sha,
    }
    preparation["code"] = code_config
    project.preparation_config = preparation
    project.repo_path = str(repository)
    await db.commit()
    response = _code_response(code_config)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="远端训练代码未能保存。",
        )
    return response


@router.get(
    "/projects/{project_id}/wizard/preparation",
    response_model=PreparationStatusResponse,
)
async def get_project_preparation(
    project: Project = Depends(get_owned_project),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PreparationStatusResponse:
    """Return the current start-gate status without secrets."""
    return await _preparation_status(project, db)


@router.get(
    "/projects/{project_id}/wizard/snapshot",
    response_model=WizardProjectSnapshot,
)
async def get_project_wizard_snapshot(
    project: Project = Depends(get_owned_project),  # noqa: B008
    storage_root: Path = Depends(get_wizard_storage),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> WizardProjectSnapshot:
    """Return enough persisted state to resume a paper project wizard."""
    preparation = _preparation(project)
    metadata = dict(project.paper_metadata or {})
    analysis = (
        PaperAnalysisResponse.model_validate(project.paper_analysis)
        if project.paper_analysis
        else None
    )
    dialog_complete = bool(preparation.get("dialog_complete"))
    config = (
        ProjectConfig(
            improvement_targets=list(project.improvement_targets or []),
            target_metrics=dict(project.target_metrics or {}),
            max_iterations=project.max_iterations,
            summary="已恢复保存的研究配置。",
        )
        if dialog_complete
        else None
    )
    repository = GitService(storage_root)._repository_path(project.id)
    return WizardProjectSnapshot(
        project_id=project.id,
        project_name=project.name,
        paper_title=project.paper_title,
        abstract=str(metadata.get("abstract") or ""),
        authors=[str(value) for value in (metadata.get("authors") or [])],
        keywords=[str(value) for value in (metadata.get("keywords") or [])],
        analysis=analysis,
        dialog_complete=dialog_complete,
        config=config,
        preparation=await _preparation_status(project, db),
        files=_reviewable_repository_files(repository),
    )


@router.post(
    "/projects/{project_id}/wizard/dialog/start",
    response_model=DialogResponse,
)
async def start_project_dialog(
    project: Project = Depends(get_owned_project),  # noqa: B008
    dialog: BrainstormDialog | None = Depends(get_brainstorm_dialog),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> DialogResponse:
    """Start the one-question-at-a-time configuration dialog."""
    connection = await _project_llm_connection(project, db)
    if (
        not getattr(project, "paper_analysis", {})
        or not connection.get("api_key")
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先使用大模型完成论文分析。",
        )
    if dialog is None:
        dialog = BrainstormDialog(
            api_key=connection["api_key"],
            model=connection["model"],
            base_url=connection["base_url"],
            provider=connection["provider"],
        )
        _dialogs[project.id] = dialog
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
    dialog: BrainstormDialog | None = Depends(get_brainstorm_dialog),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> DialogResponse:
    """Store one answer and return only the next question."""
    if dialog is None:
        dialog = _dialogs.get(project.id)
    if dialog is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="研究问答会话已失效，请重新开始。",
        )
    result = await dialog.answer(
        request.session_id,
        request.answer,
        _paper_summary(project),
    )
    if isinstance(result, ProjectConfig):
        project.improvement_targets = result.improvement_targets
        project.target_metrics = result.target_metrics
        project.max_iterations = result.max_iterations
        preparation = _preparation(project)
        preparation["dialog_complete"] = True
        project.preparation_config = preparation
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
    readiness = await _preparation_status(project, db)
    if not readiness.ready_to_generate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": "实验准备尚未完成。",
                "missing": readiness.missing,
            },
        )
    git_service = GitService(storage_root)
    git_service.initialize_project_repository(project.id)
    repository = git_service._repository_path(project.id)
    parsed = await PDFParser().parse(project.paper_path)
    preparation = _preparation(project)
    connection = await _project_llm_connection(project, db)
    result = await CodeAgent(
        repository,
        api_key=connection["api_key"],
        model=connection["model"],
        base_url=connection["base_url"],
        provider=connection["provider"],
    ).generate_framework(
        parsed.model_dump(),
        {
            "improvement_targets": project.improvement_targets,
            "target_metrics": project.target_metrics,
            "max_iterations": project.max_iterations,
            "paper_analysis": project.paper_analysis,
            "data": {
                key: value
                for key, value in (preparation.get("data") or {}).items()
                if key not in {"storage_path"}
            },
            "execution": {
                "mode": "ssh",
                "capabilities": (
                    preparation.get("execution", {}).get("capabilities") or {}
                ),
            },
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
    """Create the first experiment branch and queue its verified SSH task."""
    if project.status != "created":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project has already started.",
        )
    readiness = await _preparation_status(project, db)
    if not readiness.ready_to_start:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": "实验尚未具备启动条件。",
                "missing": readiness.missing,
            },
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
        improvement_description=(
            "Imported training baseline"
            if readiness.workflow == "existing_assets"
            else "Initial reproduction baseline"
        ),
        code_changes={},
        config={
            "entrypoint": (
                readiness.code.entrypoint
                if readiness.code is not None
                else "train.py"
            ),
            "arguments": (
                readiness.code.arguments
                if readiness.code is not None
                else []
            ),
            "target_metrics": project.target_metrics,
            "data": {
                "kind": readiness.data.kind,
                "selected_name": readiness.data.selected_name,
            },
            "execution": {
                "mode": "ssh",
                "host": readiness.execution.host,
                "port": readiness.execution.port,
                "username": readiness.execution.username,
            },
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
