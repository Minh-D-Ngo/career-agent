"""Local extraction and DOCX rendering for the optional documents extra."""

import html
import re
from io import BytesIO
from pathlib import Path


class DocumentError(ValueError):
    pass


def read_document(path: Path) -> tuple[bytes, str]:
    suffix = path.suffix.lower()
    if suffix not in {".txt", ".md", ".docx", ".pdf"}:
        raise DocumentError("Use a UTF-8 TXT or Markdown file, a DOCX, or a text-based PDF.")
    raw = path.read_bytes()
    try:
        if suffix in {".txt", ".md"}:
            text = raw.decode("utf-8-sig")
        elif suffix == ".docx":
            from docx import Document
            from docx.table import Table

            document = Document(BytesIO(raw))
            lines = []
            for block in document.iter_inner_content():
                if isinstance(block, Table):
                    lines.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
                else:
                    lines.append(block.text)
            text = "\n".join(lines)
        else:
            from pypdf import PdfReader

            pdf = PdfReader(BytesIO(raw))
            if pdf.is_encrypted:
                raise DocumentError("Use an unlocked copy of the PDF.")
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError as exc:
        raise DocumentError("Install the documents extra with python -m pip install -e '.[documents]'.") from exc
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(f"Could not extract text from {path.name}. Try saving it as UTF-8 text.") from exc

    if not text.strip():
        raise DocumentError(f"No text was found in {path.name}. Scanned PDFs need OCR or a text copy.")
    return raw, text


def render_docx(markdown: str) -> bytes:
    try:
        from docx import Document
    except ImportError as exc:
        raise DocumentError("Install the documents extra with python -m pip install -e '.[documents]'.") from exc

    document = Document()
    for line in markdown.splitlines():
        if not line or line.startswith("Review status:"):
            continue
        if line.startswith("- "):
            text = re.sub(r" \[`claim_[a-z0-9_-]+`\]$", "", line[2:])
            document.add_paragraph(_plain(text), style="List Bullet")
        elif heading := re.match(r"^(#{1,3}) (.*)$", line):
            document.add_heading(_plain(heading[2]), level=len(heading[1]) - 1)
        else:
            document.add_paragraph(_plain(line))
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _plain(text: str) -> str:
    return html.unescape(re.sub(r"\\([\\`*_\[\]#|~])", r"\1", text))
