import io
import logging
import zipfile
from dataclasses import dataclass
from typing import Literal

from docx import Document
from docx.table import Table
from pypdf import PdfReader, apply_configuration

from app.config import Settings
from app.context_library.schemas import Segment
from app.database import PlatformError

# Parser warnings can contain document strings. Never forward those to application logs.
logging.getLogger("pypdf").addHandler(logging.NullHandler())
logging.getLogger("pypdf").propagate = False


@dataclass(frozen=True)
class Extraction:
    text: str
    structure: list[Segment]
    status: Literal["ready", "insufficient", "failed"]
    error: Literal["no_readable_text", "extraction_failed"] | None = None


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if any(ord(c) < 32 and c not in "\n\t\f" for c in text):
        raise PlatformError("invalid_document", "The document contains unusable text.", 422)
    return text


def assemble(parts, settings: Settings) -> Extraction:
    text, structure = "", []
    for number, (kind, value) in enumerate(parts, 1):
        if number > settings.context_max_blocks:
            raise PlatformError("extraction_limit", "This document has too many text blocks.", 413)
        value = normalize_text(value)
        separator = "\n\n" if text else ""
        start = len(text) + len(separator)
        if start + len(value) > settings.context_text_characters:
            raise PlatformError(
                "extraction_limit", "Extracted text exceeds the configured limit.", 413
            )
        text += separator + value
        structure.append(Segment(kind=kind, number=number, start=start, end=len(text)))
    status = "ready" if text.strip() else "insufficient"
    return Extraction(text, structure, status, None if text.strip() else "no_readable_text")


def decode_text(data: bytes) -> str:
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode("utf-16")
        return data.decode("utf-8-sig")
    except UnicodeError:
        raise PlatformError(
            "invalid_document", "Use UTF-8 or BOM-marked UTF-16 text.", 422
        ) from None


def docx_parts(data: bytes, settings: Settings):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if (
            len(entries) > 2000
            or sum(e.file_size for e in entries) > settings.context_expanded_bytes
        ):
            raise PlatformError("extraction_limit", "The expanded document is too large.", 413)
        names = [entry.filename for entry in entries]
        if len(set(names)) != len(names) or "word/document.xml" not in names:
            raise ValueError("invalid package")
        for entry in entries:
            if entry.flag_bits & 1 or "vbaproject" in entry.filename.lower():
                raise ValueError("encrypted or macro package")
            if entry.filename.endswith((".xml", ".rels")):
                xml = archive.read(entry).replace(b"\x00", b"").upper()
                if xml.count(b"<") > settings.context_max_blocks * 20:
                    raise PlatformError("extraction_limit", "This document is too complex.", 413)
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise ValueError("unsafe XML")
    document = Document(io.BytesIO(data))
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            yield (
                "table",
                "\n".join("\t".join(cell.text for cell in row.cells) for row in block.rows),
            )
        else:
            yield "paragraph", block.text


def pdf_parts(data: bytes, settings: Settings):
    # Context-local parser limits: no global mutable parser configuration or external decoder.
    limit = settings.context_expanded_bytes
    with apply_configuration(
        maximum_declared_stream_length=limit,
        zlib_maximum_output_length=limit,
        lzw_maximum_output_length=limit,
        run_length_maximum_output_length=limit,
        array_based_stream_maximum_output_length=limit,
        stream_decoding_work_maximum_length=limit * 2,
        page_tree_maximum_entries=settings.context_max_pages * 10,
        xform_maximum_invocations_per_extraction=500,
        jbig2dec_binary=None,
    ):
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted PDF")
        if len(reader.pages) > settings.context_max_pages:
            raise PlatformError("extraction_limit", "This PDF has too many pages.", 413)
        expanded = 0
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None:
                expanded += len(contents.get_data())
                if expanded > limit:
                    raise PlatformError(
                        "extraction_limit", "PDF content exceeds the parsing limit.", 413
                    )
            yield "page", page.extract_text() or ""


def extract(data: bytes, kind: str, settings: Settings) -> Extraction:
    if kind == "pdf" and not data.startswith(b"%PDF-"):
        raise PlatformError("invalid_document", "This file is not a PDF document.", 422)
    if kind == "docx" and not zipfile.is_zipfile(io.BytesIO(data)):
        raise PlatformError("invalid_document", "This file is not a DOCX package.", 422)
    try:
        if kind == "txt":
            return assemble([("text", decode_text(data))], settings)
        if kind == "docx":
            return assemble(docx_parts(data, settings), settings)
        return assemble(pdf_parts(data, settings), settings)
    except PlatformError:
        raise
    except Exception:
        # Untrusted parser exceptions may include document content or internal paths.
        return Extraction("", [], "failed", "extraction_failed")
