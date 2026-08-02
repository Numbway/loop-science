"""Paper-related Pydantic schemas."""

from pydantic import BaseModel


class PaperSection(BaseModel):
    """A section of a paper (e.g., Introduction, Methods)."""

    heading: str
    content: str


class PaperReference(BaseModel):
    """A reference cited in the paper."""

    title: str = ""
    authors: list[str] = []
    year: int | None = None


class PaperContent(BaseModel):
    """Structured content extracted from a PDF paper."""

    title: str = ""
    authors: list[str] = []
    abstract: str = ""
    keywords: list[str] = []
    sections: list[PaperSection] = []
    full_text: str = ""
    references: list[PaperReference] = []
    key_contributions: list[str] = []


class PaperMetadata(BaseModel):
    """Metadata for a paper (search result or database record)."""

    title: str
    authors: list[str] = []
    year: int | None = None
    arxiv_id: str | None = None
    url: str | None = None
    abstract: str | None = None
    keywords: list[str] = []


class DownloadResult(BaseModel):
    """Result of a paper download attempt."""

    success: bool
    local_path: str | None = None
    error: str | None = None


class PaperSearchRequest(BaseModel):
    """Request to search for papers externally."""

    query: str
    max_results: int = 5
    source: str = "arxiv"  # "arxiv" or "semantic_scholar"


class PaperAddRequest(BaseModel):
    """Request to add a paper to the project library."""

    metadata: PaperMetadata
    source: str = "ai_recommended"  # "ai_recommended" or "user_uploaded"