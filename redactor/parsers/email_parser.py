"""Email parser for EML and MSG files."""

import email
import os
import tempfile
from email import policy
from typing import List, Optional

from .base import BaseParser, TextRegion, RedactionTarget


class EmailParser(BaseParser):
    def extract(self) -> List[TextRegion]:
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext == '.msg':
            return self._extract_msg()
        return self._extract_eml()

    def _extract_eml(self) -> List[TextRegion]:
        with open(self.file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        return self._extract_from_email_message(msg)

    def _extract_msg(self) -> List[TextRegion]:
        import extract_msg
        msg = extract_msg.Message(self.file_path)
        regions = []

        # Headers
        for field, value in [
            ('From', msg.sender),
            ('To', msg.to),
            ('CC', msg.cc),
            ('Subject', msg.subject),
            ('Date', msg.date),
        ]:
            if value:
                text = str(value).strip()
                if text:
                    regions.append(TextRegion(
                        text=text,
                        location={'field': field, 'type': 'header'},
                        source_file=self.file_path,
                    ))

        # Body
        body = msg.body
        if body:
            for i, line in enumerate(body.splitlines()):
                line = line.strip()
                if line:
                    regions.append(TextRegion(
                        text=line,
                        location={'field': 'body', 'type': 'body', 'line': i},
                        source_file=self.file_path,
                    ))

        msg.close()
        return regions

    def _extract_from_email_message(self, msg) -> List[TextRegion]:
        """Extract text regions from a stdlib email.message.EmailMessage."""
        regions = []

        # Headers
        for field in ('From', 'To', 'CC', 'Subject', 'Date'):
            value = msg.get(field)
            if value:
                text = str(value).strip()
                if text:
                    regions.append(TextRegion(
                        text=text,
                        location={'field': field, 'type': 'header'},
                        source_file=self.file_path,
                    ))

        # Body text
        body = msg.get_body(preferencelist=('plain', 'html'))
        if body:
            content = body.get_content()
            if isinstance(content, str):
                for i, line in enumerate(content.splitlines()):
                    line = line.strip()
                    if line:
                        regions.append(TextRegion(
                            text=line,
                            location={'field': 'body', 'type': 'body', 'line': i},
                            source_file=self.file_path,
                        ))

        return regions

    def redact(self, targets: List[RedactionTarget], output_path: str) -> None:
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext == '.msg':
            self._redact_msg(targets, output_path)
        else:
            self._redact_eml(targets, output_path)

    def _redact_eml(self, targets: List[RedactionTarget], output_path: str) -> None:
        with open(self.file_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        for target in targets:
            loc = target.region.location
            if loc.get('type') == 'header':
                field = loc['field']
                old_val = msg.get(field, '')
                if target.region.text in old_val:
                    new_val = old_val.replace(target.region.text, target.replacement)
                    del msg[field]
                    msg[field] = new_val

            elif loc.get('type') == 'body':
                body_part = msg.get_body(preferencelist=('plain', 'html'))
                if body_part:
                    content = body_part.get_content()
                    if isinstance(content, str) and target.region.text in content:
                        new_content = content.replace(
                            target.region.text, target.replacement
                        )
                        body_part.set_content(new_content)

        # Handle attachments — recurse into them
        self._redact_attachments(msg, targets, output_path)

        with open(output_path, 'wb') as f:
            f.write(msg.as_bytes())

    def _redact_msg(self, targets: List[RedactionTarget], output_path: str) -> None:
        # MSG format is complex binary — convert to EML-like text output
        import extract_msg
        msg = extract_msg.Message(self.file_path)

        # Build a new EML from the MSG content
        new_msg = email.message.EmailMessage()

        # Copy and redact headers
        header_map = {
            'From': msg.sender or '',
            'To': msg.to or '',
            'CC': msg.cc or '',
            'Subject': msg.subject or '',
            'Date': str(msg.date or ''),
        }

        for target in targets:
            loc = target.region.location
            if loc.get('type') == 'header':
                field = loc['field']
                if field in header_map and target.region.text in header_map[field]:
                    header_map[field] = header_map[field].replace(
                        target.region.text, target.replacement
                    )

        for field, value in header_map.items():
            if value:
                new_msg[field] = value

        # Redact body
        body = msg.body or ''
        for target in targets:
            if target.region.location.get('type') == 'body':
                body = body.replace(target.region.text, target.replacement)

        new_msg.set_content(body)
        msg.close()

        # Save as .eml (MSG binary redaction not supported)
        eml_path = output_path
        if eml_path.endswith('.msg'):
            eml_path = eml_path.rsplit('.', 1)[0] + '.eml'
        with open(eml_path, 'wb') as f:
            f.write(new_msg.as_bytes())

        if eml_path != output_path:
            print(f"  Note: MSG converted to EML format: {eml_path}")

    def _redact_attachments(self, msg, targets, output_dir):
        """Recurse into email attachments and redact supported formats."""
        from ..pipeline import redact_file, get_supported_extensions

        supported = get_supported_extensions()
        attach_dir = os.path.dirname(output_dir)

        for part in msg.iter_attachments():
            filename = part.get_filename()
            if not filename:
                continue
            _, ext = os.path.splitext(filename)
            if ext.lower() not in supported:
                continue

            # Save attachment to temp, redact, and update in message
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(part.get_content())
                tmp_path = tmp.name

            try:
                result = redact_file(
                    input_path=tmp_path,
                    output_dir=attach_dir,
                    _depth=1,
                )
                if result and os.path.exists(result):
                    with open(result, 'rb') as f:
                        part.set_content(f.read(), maintype='application',
                                         subtype='octet-stream', filename=filename)
                    os.unlink(result)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
