"""PII Detection and Masking for ParseAnything Atlas.

Detects emails, phone numbers, SSNs, and credit cards using rule-based patterns.
Produces masked text without mutating source evidence.
"""

import re
from typing import NamedTuple

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")


class PIIMatch(NamedTuple):
    entity_type: str
    original: str
    start: int
    end: int


def find_pii(text: str) -> list[PIIMatch]:
    """Find all PII occurrences in text."""
    if not text:
        return []
    matches: list[PIIMatch] = []

    for m in EMAIL_REGEX.finditer(text):
        matches.append(PIIMatch("email", m.group(0), m.start(), m.end()))
    for m in PHONE_REGEX.finditer(text):
        # Avoid matching simple 4-digit numbers or dates like 2024
        val = m.group(0)
        digits = re.sub(r"\D", "", val)
        if len(digits) >= 10:
            matches.append(PIIMatch("phone", val, m.start(), m.end()))
    for m in SSN_REGEX.finditer(text):
        matches.append(PIIMatch("ssn", m.group(0), m.start(), m.end()))
    for m in CREDIT_CARD_REGEX.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 16:
            matches.append(PIIMatch("credit_card", m.group(0), m.start(), m.end()))

    return sorted(matches, key=lambda x: x.start)


def mask_text(text: str, mask_char: str = "•") -> str:
    """Return text with sensitive PII replaced by mask characters."""
    if not text:
        return ""

    masked = text
    # Mask emails
    masked = EMAIL_REGEX.sub(lambda m: mask_char * min(16, len(m.group(0))), masked)
    # Mask phones
    masked = PHONE_REGEX.sub(
        lambda m: (mask_char * 12) if len(re.sub(r"\D", "", m.group(0))) >= 10 else m.group(0),
        masked,
    )
    # Mask SSNs
    masked = SSN_REGEX.sub(mask_char * 11, masked)
    # Mask credit cards
    masked = CREDIT_CARD_REGEX.sub(mask_char * 19, masked)

    return masked
