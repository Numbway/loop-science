"""Paper management API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.paper import PaperAddRequest, PaperMetadata, PaperSearchRequest
from app.services.paper.downloader import ArxivClient, FakeSearchClient, PaperSearchClient
from app.services.paper.library import PaperLibrary

router = APIRouter(prefix="/api", tags=["papers"])

# ── Dependencies ─────────────────────────────────────────────────


def get_paper_library() -> PaperLibrary:
    """Dependency: paper library service."""
    return PaperLibrary()


def get_search_client() -> PaperSearchClient:
    """Dependency: paper search client.

    Uses FakeSearchClient when no API key is configured,
    ArxivClient otherwise.
    """
    from app.core.config import settings

    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "sk-ant-xxx":
        # In dev/test mode without real API key, use fake client
        return FakeSearchClient()
    return ArxivClient()


# ── Routes ───────────────────────────────────────────────────────


@router.get("/projects/{project_id}/papers")
async def list_papers(
    project_id: uuid.UUID,
    keyword: str | None = None,
    source: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    library: PaperLibrary = Depends(get_paper_library),
    current_user: User = Depends(get_current_user),
):
    """List papers in a project's library."""
    papers = await library.list_papers(
        db, project_id, keyword=keyword, source=source, skip=skip, limit=limit
    )
    return {
        "items": papers,
        "total": len(papers),
        "skip": skip,
        "limit": limit,
    }


@router.post("/projects/{project_id}/papers/search")
async def search_papers(
    project_id: uuid.UUID,
    search_req: PaperSearchRequest,
    client: PaperSearchClient = Depends(get_search_client),
    current_user: User = Depends(get_current_user),
):
    """Search for papers externally (arXiv, Semantic Scholar)."""
    results = await client.search(search_req.query, search_req.max_results)
    return {"items": results, "total": len(results)}


@router.post("/projects/{project_id}/papers", status_code=status.HTTP_201_CREATED)
async def add_paper(
    project_id: uuid.UUID,
    paper_req: PaperAddRequest,
    db: AsyncSession = Depends(get_db),
    library: PaperLibrary = Depends(get_paper_library),
    current_user: User = Depends(get_current_user),
):
    """Add a paper to the project library."""
    paper = await library.add_paper(
        db, project_id, paper_req.metadata, paper_req.source
    )
    return paper


@router.get("/papers/{paper_id}")
async def get_paper(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    library: PaperLibrary = Depends(get_paper_library),
    current_user: User = Depends(get_current_user),
):
    """Get a single paper's details."""
    paper = await library.get_paper(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.delete("/papers/{paper_id}")
async def delete_paper(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    library: PaperLibrary = Depends(get_paper_library),
    current_user: User = Depends(get_current_user),
):
    """Delete a paper from the library."""
    deleted = await library.delete_paper(db, paper_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Paper not found")
    return {"ok": True}


@router.post("/papers/{paper_id}/upload")
async def upload_paper_pdf(
    paper_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    library: PaperLibrary = Depends(get_paper_library),
    current_user: User = Depends(get_current_user),
):
    """Manually upload a PDF for a paper that failed automatic download."""
    paper = await library.get_paper(db, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    content = await file.read()
    local_path = library.save_uploaded_pdf(
        paper.project_id, paper_id, content, file.filename or "paper.pdf"
    )
    await library.mark_download_success(db, paper_id, local_path)

    return {"ok": True, "local_path": local_path}


@router.get("/projects/{project_id}/papers/keywords")
async def get_paper_keywords(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    library: PaperLibrary = Depends(get_paper_library),
    current_user: User = Depends(get_current_user),
):
    """Get papers grouped by keyword."""
    groups = await library.get_keyword_groups(db, project_id)
    return {"groups": {k: [str(v) for v in vals] for k, vals in groups.items()}}