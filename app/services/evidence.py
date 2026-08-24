from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 500_000
MAX_PDF_PAGES = 200
EXCERPT_CHARACTERS = 480


class EvidenceIngestionError(ValueError):
    pass


class UnsupportedEvidenceType(EvidenceIngestionError):
    pass


class EvidenceTooLarge(EvidenceIngestionError):
    pass


class EvidenceExtractionError(EvidenceIngestionError):
    pass


@dataclass(frozen=True)
class ExtractedEvidence:
    filename: str
    media_type: str
    content_text: str
    excerpt: str
    source_sha256: str
    page_count: int | None
    character_count: int


class EvidenceIngestionService:
    def extract(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> ExtractedEvidence:
        safe_filename = self._safe_filename(filename)
        if not content:
            raise EvidenceExtractionError("The uploaded document is empty.")
        if len(content) > MAX_EVIDENCE_BYTES:
            raise EvidenceTooLarge("Evidence files must be 5 MB or smaller.")

        suffix = Path(safe_filename).suffix.lower()
        normalized_media_type = media_type.split(";", maxsplit=1)[0].strip().lower()
        if normalized_media_type == "text/plain" or (
            suffix == ".txt" and normalized_media_type == "application/octet-stream"
        ):
            content_text = self._extract_text(content)
            resolved_media_type = "text/plain"
            page_count = None
        elif normalized_media_type == "application/pdf" or (
            suffix == ".pdf" and normalized_media_type == "application/octet-stream"
        ):
            content_text, page_count = self._extract_pdf(content)
            resolved_media_type = "application/pdf"
        else:
            raise UnsupportedEvidenceType("Only UTF-8 text and PDF evidence files are supported.")

        normalized_text = content_text.strip()
        if not normalized_text:
            raise EvidenceExtractionError("No readable text was found in the uploaded document.")
        if len(normalized_text) > MAX_EXTRACTED_CHARACTERS:
            raise EvidenceTooLarge("Extracted evidence must contain 500,000 characters or fewer.")

        compact_text = " ".join(normalized_text.split())
        excerpt = compact_text[:EXCERPT_CHARACTERS]
        if len(compact_text) > EXCERPT_CHARACTERS:
            excerpt = f"{excerpt.rstrip()}…"

        return ExtractedEvidence(
            filename=safe_filename,
            media_type=resolved_media_type,
            content_text=normalized_text,
            excerpt=excerpt,
            source_sha256=sha256(content).hexdigest(),
            page_count=page_count,
            character_count=len(normalized_text),
        )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        safe_filename = Path(filename.replace("\\", "/")).name.strip()
        if not safe_filename:
            raise EvidenceExtractionError("A filename is required.")
        return safe_filename[:255]

    @staticmethod
    def _extract_text(content: bytes) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise EvidenceExtractionError("Text evidence must use UTF-8 encoding.") from error

    @staticmethod
    def _extract_pdf(content: bytes) -> tuple[str, int]:
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise EvidenceExtractionError("Encrypted PDF evidence is not supported.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise EvidenceTooLarge("PDF evidence must contain 200 pages or fewer.")
            page_text = [page.extract_text() or "" for page in reader.pages]
        except (PdfReadError, EOFError) as error:
            raise EvidenceExtractionError("The uploaded PDF could not be read.") from error
        return "\n\n".join(page_text), len(reader.pages)
