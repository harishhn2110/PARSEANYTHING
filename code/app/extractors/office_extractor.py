"""Office and Email Extractor for ParseAnything Atlas.

Extracts structured blocks from DOCX, XLSX, PPTX, and EML files.
Normalizes all content into standard Page and Block objects.
"""

from email import message_from_bytes
from io import BytesIO
from typing import Any

import docx
import openpyxl
from pptx import Presentation
from pptx.util import Inches, Pt

from app.detect import detect_language
from app.schema import Block, Page


class OfficeExtractor:
    VERSION = "2.0.0"

    @classmethod
    def extract_docx(cls, file_bytes: bytes, filename: str) -> list[Page]:
        try:
            doc = docx.Document(BytesIO(file_bytes))
        except Exception:
            return []
        blocks: list[Block] = []
        counter = 1
        y_cursor = 72.0  # standard 1-inch top margin in points
        page_width, page_height = 612.0, 792.0

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            style_name = p.style.name.lower() if p.style else ""
            b_type = "paragraph"
            confidence = 0.98

            if "heading" in style_name or "title" in style_name:
                b_type = "heading"
            elif "list" in style_name or text.startswith(("- ", "• ", "* ")) or text[:2].isdigit() and text[2:4] in (". ", ") "):
                b_type = "list"

            b_id = f"W{counter:02d}"
            counter += 1
            bbox = [72.0, round(y_cursor, 2), page_width - 72.0, round(y_cursor + 24.0, 2)]
            y_cursor += 30.0

            blocks.append(
                Block(
                    id=b_id,
                    type=b_type,
                    page=1,
                    bbox=bbox,
                    reading_order=float(f"1.{len(blocks) + 1:02d}"),
                    content=text,
                    confidence=confidence,
                    status="verified",
                    extractor="office_docx_parser",
                    extractor_version=cls.VERSION,
                    source="office_docx_parser",
                    language=detect_language(text),
                )
            )

        # Extract docx tables
        for tbl in doc.tables:
            raw_rows = []
            for row in tbl.rows:
                row_vals = [c.text.strip() for c in row.cells]
                raw_rows.append(row_vals)
            if not raw_rows:
                continue

            headers = raw_rows[0]
            data_rows = raw_rows[1:] if len(raw_rows) > 1 else []

            header_line = "| " + " | ".join(headers) + " |"
            sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
            data_lines = ["| " + " | ".join(r) + " |" for r in data_rows]
            markdown_content = "\n".join([header_line, sep_line] + data_lines)

            t_id = f"WT{counter:02d}"
            counter += 1
            t_bbox = [72.0, round(y_cursor, 2), page_width - 72.0, round(y_cursor + (len(raw_rows) * 22.0), 2)]
            y_cursor += (len(raw_rows) * 25.0) + 20.0

            t_block = Block(
                id=t_id,
                type="table",
                page=1,
                bbox=t_bbox,
                reading_order=float(f"1.{len(blocks) + 1:02d}"),
                content=markdown_content,
                confidence=0.98,
                status="verified",
                extractor="office_docx_parser",
                extractor_version=cls.VERSION,
                source="office_docx_parser",
                language="en",
                data={"headers": headers, "rows": data_rows},
            )
            blocks.append(t_block)

            # Table row and cell children
            for r_idx, row in enumerate(data_rows):
                r_id = f"{t_id}_R{r_idx + 1}"
                row_block = Block(
                    id=r_id,
                    type="table_row",
                    page=1,
                    bbox=[t_bbox[0], t_bbox[1] + (r_idx * 22.0), t_bbox[2], t_bbox[1] + ((r_idx + 1) * 22.0)],
                    reading_order=float(f"1.{len(blocks) + 1:02d}"),
                    content=" | ".join(row),
                    confidence=0.98,
                    status="verified",
                    extractor="office_docx_parser",
                    extractor_version=cls.VERSION,
                    source="office_docx_parser",
                    parent_id=t_id,
                    language="en",
                )
                blocks.append(row_block)

        return [Page(page=1, width=page_width, height=max(page_height, y_cursor + 72.0), page_type="digital", language="en", blocks=blocks)]

    @classmethod
    def extract_xlsx(cls, file_bytes: bytes, filename: str) -> list[Page]:
        try:
            wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
        except Exception:
            return []
        pages: list[Page] = []

        for p_idx, sheet_name in enumerate(wb.sheetnames, 1):
            sheet = wb[sheet_name]
            blocks: list[Block] = []
            rows = []
            for row in sheet.iter_rows(values_only=True):
                str_row = [str(c).strip() if c is not None else "" for c in row]
                if any(str_row):
                    rows.append(str_row)

            # Add sheet header
            h_id = f"X{p_idx}_H01"
            blocks.append(
                Block(
                    id=h_id,
                    type="heading",
                    page=p_idx,
                    bbox=[36.0, 36.0, 756.0, 60.0],
                    reading_order=float(f"{p_idx}.01"),
                    content=f"Sheet: {sheet_name}",
                    confidence=0.99,
                    status="verified",
                    extractor="office_xlsx_parser",
                    extractor_version=cls.VERSION,
                    source="office_xlsx_parser",
                    language="en",
                )
            )

            if rows:
                headers = rows[0]
                data_rows = rows[1:] if len(rows) > 1 else []
                header_line = "| " + " | ".join(headers) + " |"
                sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
                data_lines = ["| " + " | ".join(r) + " |" for r in data_rows]
                markdown_content = "\n".join([header_line, sep_line] + data_lines)

                t_id = f"X{p_idx}_T01"
                t_bbox = [36.0, 72.0, 756.0, min(550.0, 72.0 + len(rows) * 22.0)]
                t_block = Block(
                    id=t_id,
                    type="table",
                    page=p_idx,
                    bbox=t_bbox,
                    reading_order=float(f"{p_idx}.02"),
                    content=markdown_content,
                    confidence=0.98,
                    status="verified",
                    extractor="office_xlsx_parser",
                    extractor_version=cls.VERSION,
                    source="office_xlsx_parser",
                    language="en",
                    data={"headers": headers, "rows": data_rows},
                )
                blocks.append(t_block)

                for r_idx, row in enumerate(data_rows):
                    r_id = f"{t_id}_R{r_idx + 1}"
                    row_block = Block(
                        id=r_id,
                        type="table_row",
                        page=p_idx,
                        bbox=[t_bbox[0], t_bbox[1] + (r_idx * 20.0), t_bbox[2], t_bbox[1] + ((r_idx + 1) * 20.0)],
                        reading_order=float(f"{p_idx}.{len(blocks) + 1:02d}"),
                        content=" | ".join(row),
                        confidence=0.98,
                        status="verified",
                        extractor="office_xlsx_parser",
                        extractor_version=cls.VERSION,
                        source="office_xlsx_parser",
                        parent_id=t_id,
                        language="en",
                    )
                    blocks.append(row_block)

            pages.append(Page(page=p_idx, width=792.0, height=612.0, page_type="digital", language="en", blocks=blocks))

        return pages

    @classmethod
    def extract_pptx(cls, file_bytes: bytes, filename: str) -> list[Page]:
        prs = Presentation(BytesIO(file_bytes))
        pages: list[Page] = []
        slide_w = float(prs.slide_width.pt) if hasattr(prs.slide_width, "pt") else 720.0
        slide_h = float(prs.slide_height.pt) if hasattr(prs.slide_height, "pt") else 540.0

        for p_idx, slide in enumerate(prs.slides, 1):
            blocks: list[Block] = []
            for s_idx, shape in enumerate(slide.shapes, 1):
                left = float(shape.left.pt) if hasattr(shape.left, "pt") else 50.0
                top = float(shape.top.pt) if hasattr(shape.top, "pt") else 50.0
                width = float(shape.width.pt) if hasattr(shape.width, "pt") else 200.0
                height = float(shape.height.pt) if hasattr(shape.height, "pt") else 50.0
                bbox = [round(left, 2), round(top, 2), round(left + width, 2), round(top + height, 2)]

                if shape.has_text_frame:
                    text = shape.text.strip()
                    if text:
                        b_type = "heading" if top < 120.0 and len(text) < 100 else "paragraph"
                        b_id = f"P{p_idx}_{s_idx:02d}"
                        blocks.append(
                            Block(
                                id=b_id,
                                type=b_type,
                                page=p_idx,
                                bbox=bbox,
                                reading_order=float(f"{p_idx}.{len(blocks) + 1:02d}"),
                                content=text,
                                confidence=0.98,
                                status="verified",
                                extractor="office_pptx_parser",
                                extractor_version=cls.VERSION,
                                source="office_pptx_parser",
                                language=detect_language(text),
                            )
                        )
                elif shape.has_table:
                    tbl = shape.table
                    raw_rows = []
                    for row in tbl.rows:
                        raw_rows.append([c.text.strip() for c in row.cells])
                    if raw_rows:
                        headers = raw_rows[0]
                        data_rows = raw_rows[1:]
                        md = "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"] + ["| " + " | ".join(r) + " |" for r in data_rows])
                        t_id = f"PT{p_idx}_{s_idx:02d}"
                        blocks.append(
                            Block(
                                id=t_id,
                                type="table",
                                page=p_idx,
                                bbox=bbox,
                                reading_order=float(f"{p_idx}.{len(blocks) + 1:02d}"),
                                content=md,
                                confidence=0.98,
                                status="verified",
                                extractor="office_pptx_parser",
                                extractor_version=cls.VERSION,
                                source="office_pptx_parser",
                                language="en",
                                data={"headers": headers, "rows": data_rows},
                            )
                        )

            pages.append(Page(page=p_idx, width=slide_w, height=slide_h, page_type="digital", language="en", blocks=blocks))

        return pages

    @classmethod
    def extract_eml(cls, file_bytes: bytes, filename: str) -> list[Page]:
        msg = message_from_bytes(file_bytes)
        blocks: list[Block] = []

        headers = [
            ("From", msg.get("from", "")),
            ("To", msg.get("to", "")),
            ("Subject", msg.get("subject", "")),
            ("Date", msg.get("date", "")),
        ]
        y = 36.0
        for name, val in headers:
            if val:
                blocks.append(
                    Block(
                        id=f"E_{name.lower()}",
                        type="header",
                        page=1,
                        bbox=[36.0, y, 576.0, y + 20.0],
                        reading_order=float(f"1.{len(blocks) + 1:02d}"),
                        content=f"**{name}**: {val}",
                        confidence=0.99,
                        status="verified",
                        extractor="email_parser",
                        extractor_version=cls.VERSION,
                        source="email_parser",
                        language="en",
                    )
                )
                y += 24.0

        # Body
        body_text = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body_text = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body_text = payload.decode("utf-8", errors="replace")

        if body_text:
            paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
            for p_idx, para in enumerate(paragraphs, 1):
                blocks.append(
                    Block(
                        id=f"E_body_{p_idx:02d}",
                        type="paragraph",
                        page=1,
                        bbox=[36.0, y, 576.0, y + 40.0],
                        reading_order=float(f"1.{len(blocks) + 1:02d}"),
                        content=para,
                        confidence=0.98,
                        status="verified",
                        extractor="email_parser",
                        extractor_version=cls.VERSION,
                        source="email_parser",
                        language=detect_language(para),
                    )
                )
                y += 45.0

        return [Page(page=1, width=612.0, height=max(792.0, y + 72.0), page_type="digital", language="en", blocks=blocks)]
