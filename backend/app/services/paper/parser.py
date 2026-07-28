"""PDF paper parser.

Extracts structured information from academic PDFs using PyMuPDF,
with optional Claude-based AI enhancement for keywords and contributions.
"""

import re
from pathlib import Path

import fitz  # PyMuPDF

from app.schemas.paper import PaperContent, PaperReference, PaperSection


class PaperParseError(Exception):
    """Raised when PDF parsing fails."""


class PDFParser:
    """Parse academic PDF papers into structured content.

    Uses PyMuPDF for text extraction. Optionally enhances results
    with Claude API for keyword extraction and contribution identification.
    """

    # Common section heading patterns in academic papers
    SECTION_PATTERNS = re.compile(
        r"^(?:\d+\.?\s*)?(?:"
        r"abstract|introduction|related work|background|"
        r"method|approach|model|architecture|"
        r"experiment|evaluation|result|discussion|"
        r"conclusion|future work|acknowledgment|reference|"
        r"implementation|training|dataset|setup"
        r")",
        re.IGNORECASE,
    )

    def __init__(self, ai_enhancer=None):
        """Initialize parser.

        Args:
            ai_enhancer: Optional async callable that takes a PaperContent
                         and returns enriched keywords and key_contributions.
        """
        self._ai_enhancer = ai_enhancer

    async def parse(self, pdf_path: str | Path) -> PaperContent:
        """Parse a PDF paper and extract structured content.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            PaperContent with extracted title, authors, abstract, sections, etc.

        Raises:
            PaperParseError: If the PDF cannot be read or parsed.
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise PaperParseError(f"PDF file not found: {pdf_path}")

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            raise PaperParseError(f"Failed to open PDF: {e}") from e

        try:
            full_text = self._extract_full_text(doc)
            title = self._extract_title(doc, full_text)
            authors = self._extract_authors(doc, full_text)
            abstract = self._extract_abstract(full_text)
            sections = self._extract_sections(full_text)
            references = self._extract_references(full_text)
            keywords = self._extract_keywords_local(full_text)
            key_contributions: list[str] = []

            content = PaperContent(
                title=title,
                authors=authors,
                abstract=abstract,
                keywords=keywords,
                sections=sections,
                full_text=full_text,
                references=references,
                key_contributions=key_contributions,
            )

            # AI enhancement (optional)
            if self._ai_enhancer:
                try:
                    content = await self._ai_enhancer(content)
                except Exception:
                    pass  # Graceful degradation: keep local results

            return content

        finally:
            doc.close()

    # ── Private helpers ──────────────────────────────────────────

    def _extract_full_text(self, doc: fitz.Document) -> str:
        """Extract full text from all pages."""
        texts = []
        for page in doc:
            text = page.get_text("text")
            if text:
                texts.append(text)
        return "\n\n".join(texts)

    def _extract_title(self, doc: fitz.Document, full_text: str) -> str:
        """Extract paper title from first page or metadata."""
        # Try PDF metadata first
        metadata = doc.metadata
        if metadata and metadata.get("title"):
            return metadata["title"].strip()

        # Fall back to first non-empty line of first page
        lines = full_text.strip().split("\n")
        for line in lines[:10]:
            line = line.strip()
            if len(line) > 10:
                return line[:500]

        return ""

    def _extract_authors(self, doc: fitz.Document, full_text: str) -> list[str]:
        """Extract author names."""
        metadata = doc.metadata
        if metadata and metadata.get("author"):
            authors = metadata["author"]
            # Split by common separators
            return [a.strip() for a in re.split(r"[,;]|\band\b", authors) if a.strip()]

        # Try to find author line after title
        lines = full_text.strip().split("\n")
        for i, line in enumerate(lines[1:15], start=1):
            line = line.strip()
            # Author lines often contain affiliations, emails, commas
            if line and "@" not in line and len(line) < 300:
                # Check for author-like patterns
                if re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", line):
                    return [a.strip() for a in re.split(r"[,;]\s*", line) if a.strip()]

        return []

    def _extract_abstract(self, full_text: str) -> str:
        """Extract abstract section."""
        # Try to find "Abstract" heading
        pattern = re.compile(
            r"(?:^|\n)(?:abstract|a b s t r a c t)\s*\n(.*?)(?:\n\n|\n(?:\d+\.?\s*)?[A-Z][a-z]+)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(full_text)
        if match:
            return match.group(1).strip()[:5000]

        # Fallback: first substantial paragraph
        paragraphs = full_text.split("\n\n")
        for para in paragraphs[:5]:
            para = para.strip()
            if len(para) > 200:
                return para[:5000]

        return ""

    def _extract_sections(self, full_text: str) -> list[PaperSection]:
        """Split text into sections based on heading patterns."""
        sections: list[PaperSection] = []
        lines = full_text.split("\n")
        current_heading = "Preamble"
        current_content: list[str] = []

        for line in lines:
            stripped = line.strip()
            if self.SECTION_PATTERNS.match(stripped) and len(stripped) < 80:
                if current_content:
                    sections.append(
                        PaperSection(
                            heading=current_heading,
                            content="\n".join(current_content).strip(),
                        )
                    )
                current_heading = stripped
                current_content = []
            else:
                current_content.append(line)

        # Don't forget the last section
        if current_content:
            sections.append(
                PaperSection(
                    heading=current_heading,
                    content="\n".join(current_content).strip(),
                )
            )

        return sections

    def _extract_references(self, full_text: str) -> list[PaperReference]:
        """Extract references from the reference section."""
        # Find reference section
        ref_pattern = re.compile(
            r"(?:^|\n)(?:references?|bibliography)\s*\n(.*?)(?:\n\n(?:\d+\.?\s*)?[A-Z][a-z]+|$)",
            re.IGNORECASE | re.DOTALL,
        )
        match = ref_pattern.search(full_text)
        if not match:
            return []

        ref_text = match.group(1)

        # Split into individual references
        ref_entries = re.split(r"\n\s*(?=\[\d+\]|\d+\.)", ref_text)
        references: list[PaperReference] = []

        for entry in ref_entries[:50]:  # Limit to 50 references
            entry = entry.strip()
            if len(entry) < 20:
                continue

            # Try to extract title (usually in quotes or after first comma)
            title_match = re.search(r'"([^"]+)"', entry)
            title = title_match.group(1) if title_match else ""

            # Try to extract year
            year_match = re.search(r"(?:19|20)(\d{2})", entry)
            year = int(year_match.group(0)) if year_match else None

            # Try to extract authors (before title or first part)
            author_part = entry.split(",")[0] if "," in entry else entry[:100]
            authors = [a.strip() for a in re.split(r"[,;]|\band\b", author_part) if a.strip() and len(a.strip()) > 2]

            references.append(
                PaperReference(
                    title=title,
                    authors=authors[:5],  # Limit authors
                    year=year,
                )
            )

        return references

    def _extract_keywords_local(self, full_text: str) -> list[str]:
        """Extract keywords using simple TF-IDF-like heuristics.

        This is a fallback when AI enhancement is not available.
        """
        # Try explicit keywords section
        kw_pattern = re.compile(
            r"(?:keywords|key words|index terms)\s*[:：-]\s*(.*?)(?:\n\n|\n[A-Z])",
            re.IGNORECASE,
        )
        match = kw_pattern.search(full_text)
        if match:
            kw_text = match.group(1)
            return [k.strip().lower() for k in re.split(r"[,;，；]", kw_text) if k.strip()]

        # Fallback: extract common ML terms
        ml_terms = {
            "deep learning", "neural network", "convolutional", "transformer",
            "attention", "batch normalization", "dropout", "regularization",
            "optimization", "gradient descent", "backpropagation",
            "classification", "regression", "segmentation", "detection",
            "reinforcement learning", "generative", "self-supervised",
            "transfer learning", "fine-tuning", "pre-training",
        }
        found = [term for term in ml_terms if term.lower() in full_text.lower()]
        return found[:10]