"""Image parser using OCR (pytesseract) and ImageMagick blur."""

import re
import subprocess
from typing import List

import pytesseract
from PIL import Image

from .base import BaseParser, TextRegion, RedactionTarget
from ..patterns import PATTERNS


class ImageParser(BaseParser):
    def extract(self) -> List[TextRegion]:
        img = Image.open(self.file_path)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        regions = []
        for i in range(len(data['text'])):
            if int(data['conf'][i]) < 30 or not data['text'][i].strip():
                continue
            regions.append(TextRegion(
                text=data['text'][i],
                location={
                    'x': data['left'][i],
                    'y': data['top'][i],
                    'w': data['width'][i],
                    'h': data['height'][i],
                    'block_num': data['block_num'][i],
                    'line_num': data['line_num'][i],
                },
                source_file=self.file_path,
            ))
        return regions

    def redact(self, targets: List[RedactionTarget], output_path: str) -> None:
        if not targets:
            subprocess.run(['cp', self.file_path, output_path])
            return

        cmd = ['magick', self.file_path]
        for target in targets:
            loc = target.region.location
            x, y, w, h = loc['x'], loc['y'], loc['w'], loc['h']
            cmd.extend([
                '-region', f'{w}x{h}+{x}+{y}',
                '-blur', '0x8',
                '+region',
            ])
        cmd.append(output_path)
        subprocess.run(cmd, check=True)

    @staticmethod
    def group_multiword_regions(
        regions: List[TextRegion], replacement: str = "****"
    ) -> List[RedactionTarget]:
        """Image-specific: detect sensitive patterns split across OCR words.

        Groups adjacent words on the same line and checks multi-word combinations
        against regex patterns. Returns RedactionTargets with merged bounding boxes.
        This handles cases like "(555) 123-4567" being split into two OCR words.
        """
        from ..patterns import is_sensitive

        # Group regions by line
        lines: dict[tuple, list[int]] = {}
        for idx, region in enumerate(regions):
            loc = region.location
            key = (loc.get('block_num'), loc.get('line_num'))
            if key not in lines:
                lines[key] = []
            lines[key].append(idx)

        padding = 5
        individually_matched = set()

        # Pass 1: individual words
        for indices in lines.values():
            for i in indices:
                if is_sensitive(regions[i].text):
                    individually_matched.add(i)

        # Pass 2: multi-word combinations
        targets = []
        grouped = set()
        for indices in lines.values():
            for window_size in range(2, min(4, len(indices) + 1)):
                for start in range(len(indices) - window_size + 1):
                    window = indices[start:start + window_size]
                    if all(j in individually_matched for j in window):
                        continue
                    unmatched = [j for j in window if j not in individually_matched]
                    if not any(re.search(r'[\d@$#()+]', regions[j].text) for j in unmatched):
                        continue
                    combined_text = ' '.join(regions[j].text for j in window)
                    for pattern in PATTERNS.values():
                        for m in re.finditer(pattern, combined_text, re.IGNORECASE):
                            pos = 0
                            words_in_match = set()
                            for j in window:
                                word = regions[j].text
                                word_start = pos
                                word_end = pos + len(word)
                                if m.start() < word_end and m.end() > word_start:
                                    words_in_match.add(j)
                                pos = word_end + 1
                            if (len(words_in_match) > 1
                                    and any(j not in individually_matched for j in words_in_match)
                                    and not words_in_match.issubset(grouped)):
                                locs = [regions[j].location for j in words_in_match]
                                x_min = min(l['x'] for l in locs)
                                y_min = min(l['y'] for l in locs)
                                x_max = max(l['x'] + l['w'] for l in locs)
                                y_max = max(l['y'] + l['h'] for l in locs)
                                merged = TextRegion(
                                    text=' '.join(regions[j].text for j in sorted(words_in_match)),
                                    location={
                                        'x': max(0, x_min - padding),
                                        'y': max(0, y_min - padding),
                                        'w': (x_max - x_min) + (padding * 2),
                                        'h': (y_max - y_min) + (padding * 2),
                                    },
                                    source_file=regions[window[0]].source_file,
                                )
                                targets.append(RedactionTarget(
                                    region=merged, reason="multiword_pattern", replacement=replacement,
                                ))
                                grouped.update(words_in_match)

        # Add individual matches not covered by groups
        for i in individually_matched:
            if i not in grouped:
                loc = regions[i].location
                padded = TextRegion(
                    text=regions[i].text,
                    location={
                        'x': max(0, loc['x'] - padding),
                        'y': max(0, loc['y'] - padding),
                        'w': loc['w'] + (padding * 2),
                        'h': loc['h'] + (padding * 2),
                    },
                    source_file=regions[i].source_file,
                )
                targets.append(RedactionTarget(
                    region=padded,
                    reason=is_sensitive(regions[i].text) or "unknown",
                    replacement=replacement,
                ))

        return targets
