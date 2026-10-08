"""Modular Document Router for ParseAnything Atlas.

Routes documents and pages to appropriate extractors based on detected characteristics.
Persists routing decisions with extractor name and version.
"""

from dataclasses import asdict, dataclass
from typing import Any

from app.detect import PageProfile


@dataclass
class RoutingDecision:
    primary_extractor: str
    primary_version: str
    specialized_extractors: list[str]
    rationale: str
    target_stage: str = "extracting"

    def to_dict(self) -> dict:
        return asdict(self)


class DocumentRouter:
    VERSION = "1.0.0"

    @classmethod
    def route_page(cls, profile: PageProfile) -> RoutingDecision:
        """Route a single page based on detected PageProfile."""
        specialized = []

        if profile.has_tables:
            specialized.append("table_extractor")
        if profile.has_figures:
            specialized.append("vision_extractor")
        if profile.has_equations:
            specialized.append("formula_extractor")
        if profile.has_handwriting:
            specialized.append("handwriting_adapter")

        if profile.is_scan or profile.char_count < 20:
            return RoutingDecision(
                primary_extractor="ocr_extractor",
                primary_version=cls.VERSION,
                specialized_extractors=specialized,
                rationale="Page has no native text layer; routed to OCR with pre-processing",
            )
        elif profile.is_digital:
            return RoutingDecision(
                primary_extractor="native_parser",
                primary_version=cls.VERSION,
                specialized_extractors=specialized,
                rationale="Born-digital PDF; routed to native PyMuPDF/pdfplumber parser",
            )
        else:
            return RoutingDecision(
                primary_extractor="fallback_parser",
                primary_version=cls.VERSION,
                specialized_extractors=specialized,
                rationale="Ambiguous layout; routed to fallback with review flagging",
            )

    @classmethod
    def route_format(cls, fmt: str) -> RoutingDecision:
        """Route based on overall document format."""
        fmt_lower = (fmt or "").lower()
        if fmt_lower == "pdf":
            return RoutingDecision(
                primary_extractor="pdf_native",
                primary_version=cls.VERSION,
                specialized_extractors=["table_extractor", "vision_extractor"],
                rationale="PDF document; routed to hybrid native/OCR pipeline",
            )
        elif fmt_lower in ("png", "jpg", "jpeg"):
            return RoutingDecision(
                primary_extractor="ocr_extractor",
                primary_version=cls.VERSION,
                specialized_extractors=["vision_extractor"],
                rationale="Raster image; routed directly to OCR extraction",
            )
        elif fmt_lower == "docx":
            return RoutingDecision(
                primary_extractor="office_docx_parser",
                primary_version=cls.VERSION,
                specialized_extractors=["table_extractor"],
                rationale="Word document; routed to native python-docx parser",
            )
        elif fmt_lower == "xlsx":
            return RoutingDecision(
                primary_extractor="office_xlsx_parser",
                primary_version=cls.VERSION,
                specialized_extractors=["table_extractor"],
                rationale="Excel spreadsheet; routed to openpyxl sheet/table parser",
            )
        elif fmt_lower == "pptx":
            return RoutingDecision(
                primary_extractor="office_pptx_parser",
                primary_version=cls.VERSION,
                specialized_extractors=["table_extractor", "vision_extractor"],
                rationale="PowerPoint deck; routed to python-pptx slide parser",
            )
        elif fmt_lower == "eml":
            return RoutingDecision(
                primary_extractor="email_parser",
                primary_version=cls.VERSION,
                specialized_extractors=[],
                rationale="Email RFC822; routed to standard library email parser",
            )
        return RoutingDecision(
            primary_extractor="fallback_parser",
            primary_version=cls.VERSION,
            specialized_extractors=[],
            rationale=f"Unrecognized format {fmt}; fallback",
        )


def route(fmt: str) -> Any:
    """Backward-compatible route function."""
    from app.extractors.core import extract_document
    return extract_document
