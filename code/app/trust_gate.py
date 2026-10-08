"""Confidence calculation and Trust Gate enforcement for ParseAnything Atlas.

Trust Gate rules:
- >= 0.85 -> verified
- 0.60 - 0.849 -> review
- < 0.60 -> abstain
- Low-confidence blocks cannot become verified automatically.
- Ambiguous or ragged blocks route to human review.
- Raw extracted text is preserved in raw_content for audit.
"""

from typing import Any

from app.schema import Block
from backend.config import get_settings


class TrustGate:
    def __init__(
        self,
        verified_threshold: float | None = None,
        review_threshold: float | None = None,
    ):
        settings = get_settings()
        self.verified_threshold = (
            verified_threshold
            if verified_threshold is not None
            else settings.confidence_verified_threshold
        )
        self.review_threshold = (
            review_threshold
            if review_threshold is not None
            else settings.confidence_review_threshold
        )

    def evaluate_block(
        self,
        block: Block,
        validation_signals: list[dict[str, Any]] | None = None,
    ) -> Block:
        """Score confidence, set status, and flag blocks if needed."""
        confidence = block.confidence

        # Deduct confidence if validation signals indicate mismatches
        if validation_signals:
            mismatches = [s for s in validation_signals if s.get("status") == "mismatch"]
            if mismatches:
                # Downweight confidence on mathematical or structural discrepancy
                penalty = min(0.30, len(mismatches) * 0.10)
                confidence = max(0.20, confidence - penalty)

        # Ragged or question-mark text heuristic (e.g. OCR uncertainty like "$8?3M")
        if "?" in block.content or "\ufffd" in block.content:
            confidence = min(confidence, 0.55)
            block.flagged = True
            block.flag_reason = (
                block.flag_reason or "Low OCR character certainty: contains ambiguous glyphs ('?')"
            )

        # Handwriting rule
        if block.type == "handwriting":
            confidence = min(confidence, 0.65)
            block.flagged = True
            block.flag_reason = (
                block.flag_reason or "Likely handwriting - manual verification required"
            )

        block.confidence = round(confidence, 2)

        # Assign status based on configurable thresholds
        if block.confidence >= self.verified_threshold and not block.flagged:
            block.status = "verified"
        elif block.confidence >= self.review_threshold or block.flagged:
            block.status = "review"
            block.flagged = True
            if not block.flag_reason:
                block.flag_reason = f"Confidence {int(block.confidence * 100)}% below verified threshold ({int(self.verified_threshold * 100)}%)"
        else:
            block.status = "abstain"
            block.flagged = True
            if not block.flag_reason:
                block.flag_reason = f"Confidence {int(block.confidence * 100)}% below minimum acceptable threshold ({int(self.review_threshold * 100)}%)"

        # Ensure raw_content is always preserved for audit
        if not block.raw_content:
            block.raw_content = block.content

        return block
