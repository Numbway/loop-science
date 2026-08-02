"""Generate and securely serve standalone experiment HTML reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.experiment_detail import get_owned_experiment
from app.core.config import settings
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.project import Project
from app.models.reference_paper import ReferencePaper
from app.schemas.experiment_report import ExperimentReportResponse
from app.services.report import HTMLReportGenerator

router = APIRouter(
    prefix="/api/experiments/{experiment_id}/report",
    tags=["experiment-report"],
)


def get_report_storage() -> Path:
    return Path(settings.STORAGE_PATH).resolve()


def get_report_generator() -> HTMLReportGenerator:
    return HTMLReportGenerator(settings.STORAGE_PATH)


def _canonical_report_path(storage_root: Path, experiment_id: uuid.UUID) -> Path:
    path = (
        storage_root / "experiment_reports" / str(experiment_id) / "report.html"
    ).resolve()
    if not path.is_relative_to(storage_root):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Experiment report path is invalid",
        )
    return path


def _existing_report_path(
    experiment: Experiment,
    storage_root: Path,
) -> Path:
    canonical = _canonical_report_path(storage_root, experiment.id)
    if not experiment.report_html_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment report has not been generated",
        )
    stored = Path(experiment.report_html_path).resolve()
    if stored != canonical or not canonical.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment report is unavailable",
        )
    return canonical


@router.post("", response_model=ExperimentReportResponse)
async def generate_experiment_report(
    experiment: Experiment = Depends(get_owned_experiment),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    generator: HTMLReportGenerator = Depends(get_report_generator),  # noqa: B008
) -> ExperimentReportResponse:
    """Generate or replace the owned experiment's standalone report."""
    project = await db.get(Project, experiment.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    parent = (
        await db.scalar(
            select(Experiment).where(
                Experiment.project_id == project.id,
                Experiment.node_id == experiment.parent_node_id,
            )
        )
        if experiment.parent_node_id
        else None
    )
    references = list(
        (
            await db.scalars(
                select(ReferencePaper)
                .where(ReferencePaper.project_id == project.id)
                .order_by(ReferencePaper.created_at.desc())
            )
        ).all()
    )
    try:
        experiment.report_html_path = await generator.generate(
            experiment,
            project,
            parent,
            references,
        )
        await db.commit()
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Experiment report could not be generated",
        ) from error

    generated_at = datetime.fromtimestamp(
        Path(experiment.report_html_path).stat().st_mtime,
        tz=timezone.utc,
    )
    return ExperimentReportResponse(
        available=True,
        generated_at=generated_at,
        view_endpoint=f"/api/experiments/{experiment.id}/report",
        download_endpoint=f"/api/experiments/{experiment.id}/report/download",
    )


@router.get("")
async def view_experiment_report(
    experiment: Experiment = Depends(get_owned_experiment),  # noqa: B008
    storage_root: Path = Depends(get_report_storage),  # noqa: B008
) -> FileResponse:
    """Serve an owned report inline without exposing its private path."""
    report_path = _existing_report_path(experiment, storage_root)
    return FileResponse(
        report_path,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'inline; filename="experiment-{experiment.id}-report.html"'
            ),
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/download")
async def download_experiment_report(
    experiment: Experiment = Depends(get_owned_experiment),  # noqa: B008
    storage_root: Path = Depends(get_report_storage),  # noqa: B008
) -> FileResponse:
    """Download an owned report as a portable HTML file."""
    report_path = _existing_report_path(experiment, storage_root)
    return FileResponse(
        report_path,
        media_type="text/html; charset=utf-8",
        filename=f"experiment-{experiment.node_id}-report.html",
        headers={"X-Content-Type-Options": "nosniff"},
    )
