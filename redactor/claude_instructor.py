"""Claude API integration for natural language redaction instructions."""

import json
import os
from typing import List

import anthropic

from .parsers.base import TextRegion, RedactionTarget


def _format_regions_for_prompt(regions: List[TextRegion], ext: str) -> str:
    """Format extracted text regions into a readable representation for Claude."""
    if ext in ('.xlsx', '.xls'):
        # Group by sheet and present as a table
        sheets: dict[str, list] = {}
        for r in regions:
            sheet = r.location.get('sheet', 'Sheet1')
            sheets.setdefault(sheet, [])
            sheets[sheet].append(r)

        lines = []
        for sheet_name, sheet_regions in sheets.items():
            lines.append(f"## Sheet: {sheet_name}")
            for r in sheet_regions:
                col = r.location.get('col_letter', '?')
                row = r.location.get('row', '?')
                lines.append(f"  Cell {col}{row}: {r.text}")
        return "\n".join(lines)

    elif ext == '.pdf':
        lines = []
        current_page = -1
        for r in regions:
            page = r.location.get('page', 0)
            if page != current_page:
                lines.append(f"## Page {page + 1}")
                current_page = page
            lines.append(f"  {r.text}")
        return "\n".join(lines)

    elif ext == '.pptx':
        lines = []
        current_slide = -1
        for r in regions:
            slide = r.location.get('slide_index', 0)
            if slide != current_slide:
                lines.append(f"## Slide {slide + 1}")
                current_slide = slide
            lines.append(f"  {r.text}")
        return "\n".join(lines)

    elif ext in ('.eml', '.msg'):
        lines = ["## Email Content"]
        for r in regions:
            field = r.location.get('field', '')
            if field:
                lines.append(f"  [{field}] {r.text}")
            else:
                lines.append(f"  {r.text}")
        return "\n".join(lines)

    else:
        # Generic fallback
        return "\n".join(f"  {r.text}" for r in regions)


def identify_redactions(
    regions: List[TextRegion],
    instruction: str,
    ext: str,
    replacement: str = "****",
) -> List[RedactionTarget]:
    """Use Claude to identify which regions to redact based on a natural language instruction.

    Args:
        regions: Extracted text regions from the document.
        instruction: Natural language instruction (e.g., "blur PO numbers in column B").
        ext: File extension (e.g., '.xlsx').
        replacement: Replacement text for redacted content.

    Returns:
        List of RedactionTarget objects.
    """
    if not regions:
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for instruction mode")

    formatted = _format_regions_for_prompt(regions, ext)

    prompt = f"""You are a document redaction assistant. Given the document content below and the user's instruction, identify which specific text values should be redacted.

## Document Content
{formatted}

## Instruction
{instruction}

## Response Format
Respond with a JSON array of objects. Each object should have:
- "text": the exact text string to redact (must match exactly as shown in the document content)
- "reason": brief explanation of why this should be redacted

Only include text that matches the user's instruction. Return an empty array [] if nothing matches.
Respond ONLY with the JSON array, no other text."""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text.strip()

    # Parse JSON from response (handle markdown code blocks)
    if response_text.startswith("```"):
        # Strip markdown code fence
        lines = response_text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        response_text = "\n".join(lines).strip()

    try:
        items = json.loads(response_text)
    except json.JSONDecodeError:
        print(f"  Warning: Could not parse Claude response as JSON")
        print(f"  Response: {response_text[:200]}")
        return []

    # Match Claude's identified texts back to actual TextRegion objects
    targets = []
    for item in items:
        target_text = item.get("text", "")
        reason = item.get("reason", "instruction")

        for region in regions:
            if target_text == region.text or target_text in region.text:
                targets.append(RedactionTarget(
                    region=TextRegion(
                        text=target_text,
                        location=region.location,
                        source_file=region.source_file,
                    ),
                    reason=reason,
                    replacement=replacement,
                ))
                break

    return targets
