"""Paper search and download service.

Provides a protocol-based design that allows swapping real API clients
(arXiv, Semantic Scholar) with test doubles.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

from app.schemas.paper import DownloadResult, PaperMetadata


# ── Protocol ─────────────────────────────────────────────────────


class PaperSearchClient(Protocol):
    """Protocol for paper search and download clients."""

    async def search(self, query: str, max_results: int = 5) -> list[PaperMetadata]:
        """Search for papers matching the query."""
        ...

    async def download(self, paper_id: str, save_path: str) -> DownloadResult:
        """Download a paper PDF by its identifier."""
        ...


# ── ArXiv Client ──────────────────────────────────────────────────


class ArxivClient:
    """Search and download papers from arXiv."""

    BASE_SEARCH_URL = "https://export.arxiv.org/api/query"
    BASE_PDF_URL = "https://arxiv.org/pdf"

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self._timeout = timeout
        self._max_retries = max_retries

    async def search(self, query: str, max_results: int = 5) -> list[PaperMetadata]:
        """Search arXiv for papers matching the query."""
        import xml.etree.ElementTree as ET

        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self.BASE_SEARCH_URL, params=params)
                    response.raise_for_status()

                root = ET.fromstring(response.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}

                results: list[PaperMetadata] = []
                for entry in root.findall("atom:entry", ns):
                    title_el = entry.find("atom:title", ns)
                    title = title_el.text.strip() if title_el is not None else ""

                    summary_el = entry.find("atom:summary", ns)
                    abstract = summary_el.text.strip() if summary_el is not None else ""

                    # Extract arxiv ID from the entry ID
                    id_el = entry.find("atom:id", ns)
                    arxiv_id = ""
                    url = ""
                    if id_el is not None and id_el.text:
                        # ID format: http://arxiv.org/abs/XXXX.XXXXX
                        parts = id_el.text.strip().split("/")
                        arxiv_id = parts[-1] if parts else ""
                        url = id_el.text.strip().replace("abs", "pdf") if "arxiv.org" in id_el.text else ""

                    # Extract authors
                    authors: list[str] = []
                    for author_el in entry.findall("atom:author", ns):
                        name_el = author_el.find("atom:name", ns)
                        if name_el is not None and name_el.text:
                            authors.append(name_el.text.strip())

                    # Extract year from published date
                    year = None
                    pub_el = entry.find("atom:published", ns)
                    if pub_el is not None and pub_el.text:
                        try:
                            year = int(pub_el.text.strip()[:4])
                        except ValueError:
                            pass

                    # Extract keywords from categories
                    keywords: list[str] = []
                    for cat_el in entry.findall("atom:category", ns):
                        term = cat_el.get("term", "")
                        if term:
                            keywords.append(term)

                    results.append(
                        PaperMetadata(
                            title=title,
                            authors=authors,
                            year=year,
                            arxiv_id=arxiv_id,
                            url=url or f"{self.BASE_PDF_URL}/{arxiv_id}",
                            abstract=abstract,
                            keywords=keywords,
                        )
                    )

                return results

            except (httpx.RequestError, ET.ParseError) as e:
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                logger.warning(f"arXiv search failed after {self._max_retries} attempts: {e}")
                return []

            except Exception:
                return []

        return []

    async def download(self, paper_id: str, save_path: str) -> DownloadResult:
        """Download a PDF from arXiv by its ID."""
        url = f"{self.BASE_PDF_URL}/{paper_id}.pdf"
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                save_path.write_bytes(response.content)
                return DownloadResult(
                    success=True,
                    local_path=str(save_path),
                )

            except httpx.HTTPStatusError as e:
                return DownloadResult(
                    success=False,
                    error=f"HTTP {e.response.status_code}: {url}",
                )

            except httpx.RequestError as e:
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                return DownloadResult(
                    success=False,
                    error=str(e),
                )

            except OSError as e:
                return DownloadResult(
                    success=False,
                    error=f"File write error: {e}",
                )

        return DownloadResult(
            success=False,
            error=f"Download failed after {self._max_retries} attempts",
        )


# ── Semantic Scholar Client ───────────────────────────────────────


class SemanticScholarClient:
    """Search papers on Semantic Scholar (no PDF download, metadata only)."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str = "", timeout: int = 30, max_retries: int = 3):
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries

    async def search(self, query: str, max_results: int = 5) -> list[PaperMetadata]:
        """Search Semantic Scholar for papers."""
        headers = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,year,externalIds,url,abstract",
        }

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(
                        f"{self.BASE_URL}/paper/search",
                        params=params,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                results: list[PaperMetadata] = []
                for paper in data.get("data", []):
                    authors = [
                        a.get("name", "") for a in paper.get("authors", [])
                    ]
                    external_ids = paper.get("externalIds", {})

                    results.append(
                        PaperMetadata(
                            title=paper.get("title", ""),
                            authors=authors,
                            year=paper.get("year"),
                            arxiv_id=external_ids.get("ArXiv"),
                            url=paper.get("url"),
                            abstract=paper.get("abstract"),
                        )
                    )

                return results

            except (httpx.RequestError, KeyError) as e:
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                logger.warning(f"Semantic Scholar search failed: {e}")
                return []

        return []

    async def download(self, paper_id: str, save_path: str) -> DownloadResult:
        """Semantic Scholar does not provide PDF downloads."""
        return DownloadResult(
            success=False,
            error="Semantic Scholar does not support PDF downloads. Use arXiv or manual upload.",
        )


# ── Fake Client (Testing) ─────────────────────────────────────────


class FakeSearchClient:
    """Fake paper search client for testing, returns preset data."""

    def __init__(self, papers: list[PaperMetadata] | None = None):
        self._papers = papers or []
        self._downloads: dict[str, bytes] = {}
        self.search_calls: list[tuple[str, int]] = []
        self.download_calls: list[tuple[str, str]] = []

    def set_papers(self, papers: list[PaperMetadata]) -> None:
        """Set the papers to return on search."""
        self._papers = papers

    def set_pdf_content(self, paper_id: str, content: bytes) -> None:
        """Register a fake PDF to return on download."""
        self._downloads[paper_id] = content

    async def search(self, query: str, max_results: int = 5) -> list[PaperMetadata]:
        """Return preset papers (ignoring the query)."""
        self.search_calls.append((query, max_results))
        return self._papers[:max_results]

    async def download(self, paper_id: str, save_path: str) -> DownloadResult:
        """Save a fake PDF or fail."""
        self.download_calls.append((paper_id, save_path))
        if paper_id in self._downloads:
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self._downloads[paper_id])
            return DownloadResult(success=True, local_path=str(path))
        return DownloadResult(
            success=False,
            error=f"Fake paper '{paper_id}' not registered",
        )