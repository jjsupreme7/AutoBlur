"""Sensitive data patterns and auto-detection logic."""

import re
from typing import List
from .parsers.base import TextRegion, RedactionTarget

PATTERNS = {
    'ssn': r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
    'phone': r'(\+?1[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b',
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'dollar': r'\$[\d,]+\.?\d*',
    'account_number': r'\b\d{8,17}\b',
    'date': r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
    'zip_code': r'\b\d{5}(-\d{4})?\b',
    'ein': r'\b\d{2}[-]?\d{7}\b',
    'address_number': r'^\d+\s+[A-Za-z]',
}


def is_sensitive(text: str) -> str | None:
    """Check if text matches any sensitive pattern. Returns pattern name or None."""
    text = text.strip()
    if len(text) < 3:
        return None
    for pattern_name, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return pattern_name
    return None


def find_sensitive_regions(
    regions: List[TextRegion], replacement: str = "****"
) -> List[RedactionTarget]:
    """Apply regex patterns to all text regions. Returns targets to redact.

    Extracts only the matched substring so that labels like 'Phone:' are preserved.
    """
    targets = []
    seen = set()
    for region in regions:
        text = region.text.strip()
        if len(text) < 3:
            continue
        for pattern_name, pattern in PATTERNS.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                matched_text = m.group()
                # Deduplicate by location + matched text
                key = (id(region), matched_text)
                if key in seen:
                    continue
                seen.add(key)
                targets.append(RedactionTarget(
                    region=TextRegion(
                        text=matched_text,
                        location=region.location,
                        source_file=region.source_file,
                    ),
                    reason=pattern_name,
                    replacement=replacement,
                ))
    return targets
