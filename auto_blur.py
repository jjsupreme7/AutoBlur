#!/usr/bin/env python3
"""
Auto-blur sensitive information in screenshots.
Detects SSNs, phone numbers, emails, dollar amounts, account numbers, dates, and addresses.
"""

import pytesseract
from PIL import Image
import re
import subprocess
import sys
import os

# Sensitive data patterns
PATTERNS = {
    'ssn': r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
    'phone': r'\b(\+?1[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b',
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'dollar': r'\$[\d,]+\.?\d*',
    'account_number': r'\b\d{8,17}\b',  # 8-17 digit numbers (bank accounts, etc.)
    'date': r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
    'zip_code': r'\b\d{5}(-\d{4})?\b',
    'ein': r'\b\d{2}[-]?\d{7}\b',  # Employer Identification Number
    'address_number': r'^\d+\s+[A-Za-z]',  # Street addresses starting with numbers
}

def is_sensitive(text):
    """Check if text matches any sensitive pattern."""
    text = text.strip()
    if len(text) < 3:
        return False

    for pattern_name, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def get_sensitive_regions(image_path):
    """Use OCR to find text regions and identify sensitive ones."""
    img = Image.open(image_path)

    # Get detailed OCR data with bounding boxes
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    sensitive_boxes = []
    n_boxes = len(data['text'])

    # Group words by line for multi-word pattern matching
    lines = {}
    for i in range(n_boxes):
        text = data['text'][i]
        conf = int(data['conf'][i])
        if conf < 30 or not text.strip():
            continue
        key = (data['block_num'][i], data['line_num'][i])
        if key not in lines:
            lines[key] = []
        lines[key].append(i)

    padding = 5
    individually_matched = set()

    # Pass 1: Check individual words
    for indices in lines.values():
        for i in indices:
            if is_sensitive(data['text'][i]):
                individually_matched.add(i)

    # Pass 2: Check adjacent word pairs/triples to catch split values (e.g. "(555) 123-4567")
    # Only keep matches where the regex spans across words (not just re-finding an individual match)
    grouped = set()
    for indices in lines.values():
        for window_size in range(2, min(4, len(indices) + 1)):
            for start in range(len(indices) - window_size + 1):
                window = indices[start:start + window_size]
                if all(j in individually_matched for j in window):
                    continue
                # At least one unmatched word must have digits or symbols
                unmatched = [j for j in window if j not in individually_matched]
                if not any(re.search(r'[\d@$#()+]', data['text'][j]) for j in unmatched):
                    continue
                combined_text = ' '.join(data['text'][j] for j in window)
                # Check that a match actually spans across word boundaries
                has_spanning_match = False
                for pattern in PATTERNS.values():
                    for m in re.finditer(pattern, combined_text, re.IGNORECASE):
                        # Check if the match covers text from more than one word
                        match_start, match_end = m.start(), m.end()
                        # Find which words the match overlaps
                        pos = 0
                        words_in_match = set()
                        for idx, j in enumerate(window):
                            word = data['text'][j]
                            word_start = pos
                            word_end = pos + len(word)
                            if match_start < word_end and match_end > word_start:
                                words_in_match.add(j)
                            pos = word_end + 1  # +1 for the space
                        if len(words_in_match) > 1 and any(j not in individually_matched for j in words_in_match) and not words_in_match.issubset(grouped):
                            # Blur only the words the match actually covers
                            matched_text = ' '.join(data['text'][j] for j in sorted(words_in_match))
                            x_min = min(data['left'][j] for j in words_in_match)
                            y_min = min(data['top'][j] for j in words_in_match)
                            x_max = max(data['left'][j] + data['width'][j] for j in words_in_match)
                            y_max = max(data['top'][j] + data['height'][j] for j in words_in_match)
                            sensitive_boxes.append({
                                'x': max(0, x_min - padding),
                                'y': max(0, y_min - padding),
                                'w': (x_max - x_min) + (padding * 2),
                                'h': (y_max - y_min) + (padding * 2),
                                'text': matched_text
                            })
                            grouped.update(words_in_match)

    # Add individual matches not already covered by a group
    for i in individually_matched:
        if i not in grouped:
            x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
            sensitive_boxes.append({
                'x': max(0, x - padding),
                'y': max(0, y - padding),
                'w': w + (padding * 2),
                'h': h + (padding * 2),
                'text': data['text'][i]
            })

    return sensitive_boxes, img.size

def blur_regions(input_path, output_path, regions):
    """Use ImageMagick to blur the specified regions."""
    if not regions:
        # No sensitive data found, just copy the file
        subprocess.run(['cp', input_path, output_path])
        return False

    # Build ImageMagick command
    cmd = ['magick', input_path]

    for region in regions:
        # Create a blur effect for each region
        x, y, w, h = region['x'], region['y'], region['w'], region['h']
        # Use -region to select area, then blur it
        cmd.extend([
            '-region', f'{w}x{h}+{x}+{y}',
            '-blur', '0x8',
            '+region'
        ])

    cmd.append(output_path)

    subprocess.run(cmd, check=True)
    return True

def process_image(input_path, output_dir):
    """Process a single image."""
    filename = os.path.basename(input_path)
    name, ext = os.path.splitext(filename)
    output_path = os.path.join(output_dir, f"{name}_blurred{ext}")

    print(f"Processing: {filename}")

    try:
        regions, img_size = get_sensitive_regions(input_path)

        if regions:
            print(f"  Found {len(regions)} sensitive region(s)")
            for r in regions:
                print(f"    - '{r['text']}' at ({r['x']}, {r['y']})")

            blur_regions(input_path, output_path, regions)
            print(f"  Saved to: {output_path}")
        else:
            print("  No sensitive data detected")
            # Copy original to output
            subprocess.run(['cp', input_path, output_path])
            print(f"  Copied original to: {output_path}")

        return output_path

    except Exception as e:
        print(f"  Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python auto_blur.py <image_path> [output_dir]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(input_path)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    process_image(input_path, output_dir)
