"""Paper library management service.

Organizes reference papers for a project: file storage, keyword grouping,
database records, and search queries.
"""

import json
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reference_paper import ReferencePaper
from app.schemas.paper import PaperMetadata


class PaperLibrary:
    """Manage reference papers for a project."""

    def __init__(self, storage_root: str = "/data/projects"):
        self._storage_root = Path(storage_root)

    def _project_papers_dir(self, project_id: uuid.UUID) -> Path:
        """Get the papers directory for a project."""
        return self._storage_root / str(project_id) / "reference_papers"

    def _keyword_dir(self, project_id: uuid.UUID, keyword: str) -> Path:
        """Get the directory for papers under a keyword."""
        safe_keyword = keyword.replace("/", "_").replace("\\", "_")
        return self._project_papers_dir(project_id) / "by_keyword" / safe_keyword

    # ── Database operations ──────────────────────────────────────

    async def list_papers(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        *,
        keyword: str | None = None,
        source: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ReferencePaper]:
        """List papers for a project, optionally filtered."""
        stmt = select(ReferencePaper).where(
            ReferencePaper.project_id == project_id
        )

        if keyword:
            stmt = stmt.where(ReferencePaper.keywords.any(keyword))
        if source:
            stmt = stmt.where(ReferencePaper.source == source)

        stmt = stmt.offset(skip).limit(limit).order_by(ReferencePaper.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def add_paper(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        metadata: PaperMetadata,
        source: str = "ai_recommended",
    ) -> ReferencePaper:
        """Add a paper to the project library."""
        paper = ReferencePaper(
            project_id=project_id,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            arxiv_id=metadata.arxiv_id,
            url=metadata.url,
            abstract=metadata.abstract,
            keywords=metadata.keywords,
            source=source,
            download_status="pending",
        )
        db.add(paper)
        await db.flush()
        await db.refresh(paper)
        return paper

    async def get_paper(
        self,
        db: AsyncSession,
        paper_id: uuid.UUID,
    ) -> ReferencePaper | None:
        """Get a single paper by ID."""
        result = await db.execute(
            select(ReferencePaper).where(ReferencePaper.id == paper_id)
        )
        return result.scalar_one_or_none()

    async def delete_paper(
        self,
        db: AsyncSession,
        paper_id: uuid.UUID,
    ) -> bool:
        """Delete a paper and its local files."""
        paper = await self.get_paper(db, paper_id)
        if not paper:
            return False

        # Remove local file if exists
        if paper.local_path:
            local = Path(paper.local_path)
            if local.exists():
                local.unlink()

        await db.delete(paper)
        await db.flush()
        return True

    async def mark_download_failed(
        self,
        db: AsyncSession,
        paper_id: uuid.UUID,
        error: str,
    ) -> ReferencePaper | None:
        """Mark a paper as download-failed with error message."""
        paper = await self.get_paper(db, paper_id)
        if not paper:
            return None
        paper.download_status = "failed"
        paper.download_error = error
        await db.flush()
        await db.refresh(paper)
        return paper

    async def mark_download_success(
        self,
        db: AsyncSession,
        paper_id: uuid.UUID,
        local_path: str,
    ) -> ReferencePaper | None:
        """Mark a paper as successfully downloaded."""
        paper = await self.get_paper(db, paper_id)
        if not paper:
            return None
        paper.download_status = "success"
        paper.local_path = local_path
        await db.flush()
        await db.refresh(paper)
        return paper

    # ── Keyword operations ───────────────────────────────────────

    async def get_keyword_groups(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
    ) -> dict[str, list[uuid.UUID]]:
        """Group papers by keyword."""
        papers = await self.list_papers(db, project_id, limit=500)
        groups: dict[str, list[uuid.UUID]] = {}

        for paper in papers:
            for kw in paper.keywords:
                if kw not in groups:
                    groups[kw] = []
                groups[kw].append(paper.id)

        return groups

    # ── File storage ─────────────────────────────────────────────

    def save_uploaded_pdf(
        self,
        project_id: uuid.UUID,
        paper_id: uuid.UUID,
        file_data: bytes,
        filename: str,
    ) -> str:
        """Save an uploaded PDF to the project's paper storage."""
        base_dir = self._project_papers_dir(project_id) / "successful"
        base_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{paper_id}_{filename}"
        file_path = base_dir / safe_name
        file_path.write_bytes(file_data)

        return str(file_path)

    def get_pending_uploads(
        self,
        project_id: uuid.UUID,
    ) -> list[dict]:
        """Get list of papers pending manual upload."""
        pending_file = self._project_papers_dir(project_id) / "failed" / "pending_upload.json"
        if not pending_file.exists():
            return []
        return json.loads(pending_file.read_text())

    def save_pending_upload_list(
        self,
        project_id: uuid.UUID,
        papers: list[dict],
    ) -> None:
        """Save the list of papers needing manual upload."""
        pending_file = self._project_papers_dir(project_id) / "failed" / "pending_upload.json"
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text(json.dumps(papers, indent=2, default=str))