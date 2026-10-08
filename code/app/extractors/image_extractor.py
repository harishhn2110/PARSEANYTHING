"""Image and Scanned Document Extractor for ParseAnything Atlas.

Extracts text from PNG, JPG, and raster scans using OCR or Computer Vision fallback.
Computes bounding boxes and confidence scores, routing uncertain text to review.
"""

from io import BytesIO
import re
from typing import Any

from PIL import Image
import pymupdf

from app.detect import detect_language
from app.schema import Block, Page


class ImageExtractor:
    VERSION = "1.5.0"

    @classmethod
    def extract_image(cls, file_bytes: bytes, filename: str) -> list[Page]:
        try:
            img = Image.open(BytesIO(file_bytes))
            width, height = float(img.width), float(img.height)
        except Exception:
            width, height = 612.0, 792.0

        blocks: list[Block] = []

        # Try Tesseract OCR
        ocr_blocks = cls._try_tesseract(file_bytes, width, height)
        if ocr_blocks:
            blocks.extend(ocr_blocks)
        else:
            # Fallback to image inspection & placeholder / OCR-fallback block
            blocks.append(
                Block(
                    id="IMG_01",
                    type="figure",
                    page=1,
                    bbox=[36.0, 36.0, width - 36.0, height - 36.0],
                    reading_order=1.01,
                    content=f"[Scanned Image: {filename}]",
                    confidence=0.75,
                    status="review",
                    extractor="ocr_cv_fallback",
                    extractor_version=cls.VERSION,
                    source="ocr_cv_fallback",
                    language="en",
                    flagged=True,
                    flag_reason="Scanned image processed without Tesseract OCR binary on PATH",
                )
            )

        return [
            Page(
                page=1,
                width=width,
                height=height,
                page_type="scanned",
                language="en",
                blocks=blocks,
            )
        ]

    @classmethod
    def _try_tesseract(cls, file_bytes: bytes, width: float, height: float) -> list[Block]:
        try:
            import pytesseract

            img = Image.open(BytesIO(file_bytes)).convert("RGB")
            # Get data with bounding boxes
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            n_boxes = len(data["text"])

            lines_map: dict[tuple[int, int], list[tuple[str, int, list[float]]]] = {}
            for i in range(n_boxes):
                text = data["text"][i].strip()
                if not text:
                    continue
                conf = int(data["conf"][i])
                if conf < 0:
                    conf = 50
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                line_key = (data["block_num"][i], data["line_num"][i])
                if line_key not in lines_map:
                    lines_map[line_key] = []
                lines_map[line_key].append((text, conf, [float(x), float(y), float(x + w), float(y + h)]))

            blocks: list[Block] = []
            for b_idx, (line_key, word_tuples) in enumerate(lines_map.items(), 1):
                full_text = " ".join(t[0] for t in word_tuples)
                mean_conf = sum(t[1] for t in word_tuples) / len(word_tuples) / 100.0
                min_x = min(t[2][0] for t in word_tuples)
                min_y = min(t[2][1] for t in word_tuples)
                max_x = max(t[2][2] for t in word_tuples)
                max_y = max(t[2][3] for t in word_tuples)

                flagged = mean_conf < 0.85 or "?" in full_text
                status = "verified" if mean_conf >= 0.85 and not flagged else "review"

                blocks.append(
                    Block(
                        id=f"OCR_{b_idx:02d}",
                        type="paragraph",
                        page=1,
                        bbox=[min_x, min_y, max_x, max_y],
                        reading_order=float(f"1.{b_idx:02d}"),
                        content=full_text,
                        confidence=round(mean_conf, 2),
                        status=status,
                        extractor="tesseract_ocr",
                        extractor_version=cls.VERSION,
                        source="tesseract_ocr",
                        language=detect_language(full_text),
                        flagged=flagged,
                        flag_reason="Low OCR confidence score" if flagged else None,
                    )
                )

            return blocks
        except Exception:
            return []
