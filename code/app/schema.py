"""Output schema for ParseAnything Atlas.

Every block stays traceable: page + bbox + id + confidence + extractor + status.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

DEFAULT_CONFIDENCE_THRESHOLD = 0.60
VERIFIED_CONFIDENCE_THRESHOLD = 0.85

BlockType = Literal[
    "heading",
    "paragraph",
    "list",
    "table",
    "table_row",
    "table_cell",
    "figure",
    "chart",
    "equation",
    "caption",
    "header",
    "footer",
    "footnote",
    "image",
    "handwriting",
]

BlockStatus = Literal["verified", "review", "abstain"]


@dataclass
class Block:
    id: str
    type: BlockType
    page: int
    bbox: list[float]  # [x0, y0, x1, y1] in PDF points / canvas units
    reading_order: float
    content: str  # markdown / text
    confidence: float  # 0.0 - 1.0
    status: BlockStatus = "verified"
    extractor: str = "native_parser"
    extractor_version: str = "1.0.0"
    source: str = "native_parser"  # alias for extractor
    lang: str = "en"
    language: str = "en"
    flagged: bool = False
    flag_reason: Optional[str] = None
    parent_id: Optional[str] = None
    data: Any = None  # e.g. table rows or structured cells
    raw_content: Optional[str] = None

    def __post_init__(self):
        if not self.source and self.extractor:
            self.source = self.extractor
        elif not self.extractor and self.source:
            self.extractor = self.source
        if not self.language and self.lang:
            self.language = self.lang
        elif not self.lang and self.language:
            self.lang = self.language
        if self.raw_content is None:
            self.raw_content = self.content

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Page:
    page: int
    width: float
    height: float
    page_type: str = "digital"  # digital, scanned, hybrid
    language: str = "en"
    blocks: list[Block] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "width": self.width,
            "height": self.height,
            "page_type": self.page_type,
            "language": self.language,
            "blocks": [b.to_dict() for b in self.blocks],
        }


@dataclass
class Document:
    doc_id: str
    filename: str
    format: str
    pages: list[Page] = field(default_factory=list)
    markdown: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    overall_confidence: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "format": self.format,
            "pages": [p.to_dict() for p in self.pages],
            "markdown": self.markdown,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "overall_confidence": self.overall_confidence,
            "metrics": dict(self.metrics),
        }
