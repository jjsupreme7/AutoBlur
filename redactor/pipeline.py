"""Unified redaction pipeline orchestrator."""

import os
from typing import Optional

from .parsers.base import BaseParser
from .parsers.image_parser import ImageParser

PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    '.png': ImageParser,
    '.jpg': ImageParser,
    '.jpeg': ImageParser,
    '.gif': ImageParser,
    '.bmp': ImageParser,
    '.tiff': ImageParser,
    '.webp': ImageParser,
}

# Lazy-register parsers for formats with optional dependencies
_LAZY_PARSERS: dict[str, tuple[str, str]] = {
    '.xlsx': ('redactor.parsers.excel_parser', 'ExcelParser'),
    '.xls': ('redactor.parsers.excel_parser', 'ExcelParser'),
    '.pdf': ('redactor.parsers.pdf_parser', 'PdfParser'),
    '.eml': ('redactor.parsers.email_parser', 'EmailParser'),
    '.msg': ('redactor.parsers.email_parser', 'EmailParser'),
    '.pptx': ('redactor.parsers.pptx_parser', 'PptxParser'),
}


def _get_parser_class(ext: str) -> Optional[type[BaseParser]]:
    """Get parser class for a file extension, with lazy imports."""
    if ext in PARSER_REGISTRY:
        return PARSER_REGISTRY[ext]
    if ext in _LAZY_PARSERS:
        module_name, class_name = _LAZY_PARSERS[ext]
        import importlib
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        PARSER_REGISTRY[ext] = cls
        return cls
    return None


def get_supported_extensions() -> set[str]:
    """Return all supported file extensions."""
    return set(PARSER_REGISTRY.keys()) | set(_LAZY_PARSERS.keys())


def redact_file(
    input_path: str,
    output_dir: str,
    instruction: Optional[str] = None,
    replacement: str = "****",
    _depth: int = 0,
) -> Optional[str]:
    """Redact a file. Returns output path, or None on error.

    Args:
        input_path: Path to the file to redact.
        output_dir: Directory to write the redacted file.
        instruction: Natural language instruction for Claude API mode.
                     If None, uses auto-detect (regex patterns).
        replacement: Text to replace sensitive data with.
        _depth: Internal recursion depth counter (for email attachments).
    """
    if _depth > 3:
        print(f"  Skipping (max recursion depth): {input_path}")
        return None

    filename = os.path.basename(input_path)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    parser_cls = _get_parser_class(ext)
    if parser_cls is None:
        print(f"  Unsupported format: {ext}")
        return None

    output_path = os.path.join(output_dir, f"{name}_redacted{ext}")

    print(f"Processing: {filename}")

    try:
        parser = parser_cls(input_path)
        regions = parser.extract()

        if instruction:
            from .claude_instructor import identify_redactions
            targets = identify_redactions(regions, instruction, ext, replacement)
        elif isinstance(parser, ImageParser):
            # Image-specific: use multi-word grouping for OCR split patterns
            targets = ImageParser.group_multiword_regions(regions, replacement)
        else:
            from .patterns import find_sensitive_regions
            targets = find_sensitive_regions(regions, replacement)

        if targets:
            print(f"  Found {len(targets)} redaction(s)")
            for t in targets:
                print(f"    - '{t.region.text}' ({t.reason})")
            parser.redact(targets, output_path)
            print(f"  Saved to: {output_path}")
        else:
            print("  No sensitive data detected")
            import shutil
            shutil.copy2(input_path, output_path)
            print(f"  Copied original to: {output_path}")

        return output_path

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
        return None
