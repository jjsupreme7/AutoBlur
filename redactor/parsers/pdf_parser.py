"""PDF parser using PyMuPDF (fitz)."""

from typing import List

import fitz

from .base import BaseParser, TextRegion, RedactionTarget


class PdfParser(BaseParser):
    def extract(self) -> List[TextRegion]:
        doc = fitz.open(self.file_path)
        regions = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                            bbox = span["bbox"]
                            regions.append(TextRegion(
                                text=text,
                                location={
                                    'page': page_num,
                                    'x0': bbox[0],
                                    'y0': bbox[1],
                                    'x1': bbox[2],
                                    'y1': bbox[3],
                                },
                                source_file=self.file_path,
                            ))
        doc.close()
        return regions

    def redact(self, targets: List[RedactionTarget], output_path: str) -> None:
        doc = fitz.open(self.file_path)
        for target in targets:
            loc = target.region.location
            page = doc[loc['page']]
            rect = fitz.Rect(loc['x0'], loc['y0'], loc['x1'], loc['y1'])
            page.add_redact_annot(rect, text=target.replacement)
        for page in doc:
            page.apply_redactions()
        doc.save(output_path)
        doc.close()
