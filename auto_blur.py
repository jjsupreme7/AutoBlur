#!/usr/bin/env python3
"""
AutoBlur - Universal document redaction tool.
Detects and redacts sensitive information in images, PDFs, Excel, PowerPoint, and email files.
"""

import argparse
import os
import sys

from redactor.pipeline import redact_file


def main():
    parser = argparse.ArgumentParser(
        description="Redact sensitive information from documents.",
        usage="%(prog)s <file_path> [options]",
    )
    parser.add_argument("file_path", help="Path to the file to redact")
    parser.add_argument("-o", "--output", help="Output directory (default: same as input)")
    parser.add_argument(
        "-i", "--instruction",
        help='Natural language redaction instruction (e.g., "blur PO numbers in column B"). '
             "Requires ANTHROPIC_API_KEY. If omitted, uses auto-detect mode.",
    )
    parser.add_argument(
        "-r", "--replacement",
        default="****",
        help='Replacement text for redacted content (default: "****")',
    )

    args = parser.parse_args()

    if not os.path.exists(args.file_path):
        print(f"Error: File not found: {args.file_path}")
        sys.exit(1)

    output_dir = args.output or os.path.dirname(os.path.abspath(args.file_path))
    os.makedirs(output_dir, exist_ok=True)

    if args.instruction:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            # Try loading from .env
            try:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.environ.get("ANTHROPIC_API_KEY")
            except ImportError:
                pass
            if not api_key:
                print("Error: ANTHROPIC_API_KEY required for --instruction mode")
                print("Set it with: export ANTHROPIC_API_KEY=your-key-here")
                sys.exit(1)

    result = redact_file(
        input_path=args.file_path,
        output_dir=output_dir,
        instruction=args.instruction,
        replacement=args.replacement,
    )

    if result:
        print(f"\nDone: {result}")
    else:
        print("\nRedaction failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
