from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from xml.etree import ElementTree

from aithru_agent.domain import AgentWorkspaceConversionResult, AgentWorkspaceFile
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.protocols import AgentStore


CONVERTER_NAME = "builtin_document_text"
OUTPUT_MEDIA_TYPE = "text/markdown"
MAX_CONVERTED_TEXT_CHARS = 200_000

PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

SUPPORTED_DOCUMENT_MEDIA_TYPES = frozenset(
    {
        PDF_MEDIA_TYPE,
        DOCX_MEDIA_TYPE,
        PPTX_MEDIA_TYPE,
        XLSX_MEDIA_TYPE,
    }
)
MODEL_READABLE_MEDIA_TYPES = frozenset({"text/plain", "text/markdown", "application/json"})

_PDF_TJ_RE = re.compile(rb"\(((?:\\.|[^\\()])*)\)\s*Tj", re.DOTALL)
_PDF_TJ_ARRAY_RE = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
_PRINTABLE_RE = re.compile(r"[A-Za-z0-9][ -~]{4,}")
_PDF_ESCAPE_BYTES = {
    ord("n"): 10,
    ord("r"): 13,
    ord("t"): 9,
    ord("b"): 8,
    ord("f"): 12,
}


async def convert_workspace_file(
    store: AgentStore,
    *,
    workspace_id: str,
    path: str,
) -> AgentWorkspaceConversionResult:
    source = await _workspace_file_metadata(store, workspace_id=workspace_id, path=path)
    media_type = _normalized_media_type(source.media_type)
    if media_type in MODEL_READABLE_MEDIA_TYPES:
        return _non_converted_result(
            source,
            status="skipped",
            reason="File is already model-readable.",
        )
    if media_type not in SUPPORTED_DOCUMENT_MEDIA_TYPES:
        return _non_converted_result(
            source,
            status="unsupported",
            reason="Unsupported workspace file media type.",
        )

    content = await store.read_workspace_file(workspace_id, source.path)
    text = _extract_text(_content_bytes(content.content), media_type)
    if text is None:
        return _non_converted_result(
            source,
            status="failed",
            reason="Could not extract text from workspace file.",
        )

    bounded_text, truncated = _bounded_text(text)
    output_path = _converted_output_path(source.path)
    output_file = await store.write_workspace_file(
        workspace_id=workspace_id,
        path=output_path,
        content=_conversion_markdown(
            source=source,
            text=bounded_text,
            truncated=truncated,
        ),
        media_type=OUTPUT_MEDIA_TYPE,
    )
    return AgentWorkspaceConversionResult(
        workspace_id=workspace_id,
        source_path=source.path,
        source_media_type=source.media_type,
        source_size=source.size,
        source_content_hash=source.content_hash,
        status="converted",
        output_path=output_file.path,
        output_media_type=OUTPUT_MEDIA_TYPE,
        output_file=output_file,
        converter=CONVERTER_NAME,
    )


def should_attempt_workspace_upload_conversion(media_type: str | None) -> bool:
    return _normalized_media_type(media_type) in SUPPORTED_DOCUMENT_MEDIA_TYPES


def failed_workspace_conversion_result(
    source: AgentWorkspaceFile,
    *,
    reason: str = "Could not extract text from workspace file.",
) -> AgentWorkspaceConversionResult:
    return _non_converted_result(source, status="failed", reason=reason)


async def _workspace_file_metadata(
    store: AgentStore,
    *,
    workspace_id: str,
    path: str,
) -> AgentWorkspaceFile:
    normalized_path = _normalize_workspace_path(path)
    for file in await store.list_workspace_files(workspace_id):
        if file.path == normalized_path:
            return file
    raise AgentError("NOT_FOUND", f"Workspace file not found: {normalized_path}")


def _non_converted_result(
    source: AgentWorkspaceFile,
    *,
    status: str,
    reason: str,
) -> AgentWorkspaceConversionResult:
    return AgentWorkspaceConversionResult(
        workspace_id=source.workspace_id,
        source_path=source.path,
        source_media_type=source.media_type,
        source_size=source.size,
        source_content_hash=source.content_hash,
        status=status,
        reason=reason,
        converter=CONVERTER_NAME,
    )


def _normalized_media_type(media_type: str | None) -> str | None:
    if media_type is None:
        return None
    return media_type.split(";", 1)[0].strip().lower() or None


def _normalize_workspace_path(raw: str) -> str:
    normalized = raw.replace("\\", "/")
    parts: list[str] = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                raise AgentError("PATH_TRAVERSAL_DENIED", f"Path traverses above root: {raw}")
            parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def _content_bytes(content: str | bytes) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


def _extract_text(content: bytes, media_type: str | None) -> str | None:
    try:
        match media_type:
            case "application/pdf":
                return _clean_extracted_text(_extract_pdf_text(content))
            case "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                return _clean_extracted_text(_extract_docx_text(content))
            case "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                return _clean_extracted_text(_extract_pptx_text(content))
            case "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                return _clean_extracted_text(_extract_xlsx_text(content))
            case _:
                return None
    except (ElementTree.ParseError, KeyError, OSError, ValueError, zipfile.BadZipFile):
        return None


def _extract_docx_text(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = _xml_root(archive, "word/document.xml")
        paragraphs = _paragraph_texts(root)
        if paragraphs:
            return "\n\n".join(paragraphs)
        return "\n".join(_text_nodes(root))


def _extract_pptx_text(content: bytes) -> str:
    sections: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        slide_names = sorted(
            (name for name in archive.namelist() if _is_slide_xml(name)),
            key=_slide_sort_key,
        )
        for index, name in enumerate(slide_names, start=1):
            root = _xml_root(archive, name)
            text = "\n".join(_paragraph_texts(root)) or "\n".join(_text_nodes(root))
            if text.strip():
                sections.append(f"## Slide {index}\n\n{text.strip()}")
    return "\n\n".join(sections)


def _extract_xlsx_text(content: bytes) -> str:
    sections: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        sheet_names = sorted(
            (name for name in archive.namelist() if _is_sheet_xml(name)),
            key=_sheet_sort_key,
        )
        for index, name in enumerate(sheet_names, start=1):
            root = _xml_root(archive, name)
            rows = _xlsx_rows(root, shared_strings)
            if rows:
                sections.append(f"## Sheet {index}\n\n" + "\n".join(rows))
    return "\n\n".join(sections)


def _extract_pdf_text(content: bytes) -> str:
    lines: list[str] = []
    for match in _PDF_TJ_RE.finditer(content):
        decoded = _decode_pdf_literal(match.group(1)).strip()
        if decoded:
            lines.append(decoded)
    for match in _PDF_TJ_ARRAY_RE.finditer(content):
        parts = (
            _decode_pdf_literal(raw).strip()
            for raw in _pdf_literal_parts(match.group(1))
        )
        decoded = " ".join(
            part
            for part in parts
            if part
        )
        if decoded:
            lines.append(decoded)
    if lines:
        return "\n".join(lines)
    return _extract_printable_pdf_text(content)


def _xml_root(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    with archive.open(name) as handle:
        return ElementTree.fromstring(handle.read())


def _paragraph_texts(root: ElementTree.Element) -> list[str]:
    paragraphs: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) != "p":
            continue
        text = "".join(_text_nodes(element)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _text_nodes(root: ElementTree.Element) -> list[str]:
    return [
        element.text or ""
        for element in root.iter()
        if _local_name(element.tag) == "t" and (element.text or "").strip()
    ]


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _xml_root(archive, "xl/sharedStrings.xml")
    strings: list[str] = []
    for item in root:
        if _local_name(item.tag) == "si":
            strings.append("".join(_text_nodes(item)).strip())
    return strings


def _xlsx_rows(root: ElementTree.Element, shared_strings: list[str]) -> list[str]:
    rows: list[str] = []
    for row in root.iter():
        if _local_name(row.tag) != "row":
            continue
        values = [
            value
            for value in (_xlsx_cell_value(cell, shared_strings) for cell in row)
            if value
        ]
        if values:
            rows.append(" | ".join(values))
    return rows


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    if _local_name(cell.tag) != "c":
        return ""
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(_text_nodes(cell)).strip()
    value = _first_child_text(cell, "v")
    if cell_type == "s":
        try:
            return shared_strings[int(value)].strip()
        except (IndexError, TypeError, ValueError):
            return ""
    return (value or "").strip()


def _first_child_text(element: ElementTree.Element, local_name: str) -> str:
    for child in element:
        if _local_name(child.tag) == local_name:
            return child.text or ""
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_slide_xml(name: str) -> bool:
    return bool(re.fullmatch(r"ppt/slides/slide\d+\.xml", name))


def _slide_sort_key(name: str) -> int:
    return int(re.search(r"slide(\d+)\.xml$", name).group(1))  # type: ignore[union-attr]


def _is_sheet_xml(name: str) -> bool:
    return bool(re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))


def _sheet_sort_key(name: str) -> int:
    return int(re.search(r"sheet(\d+)\.xml$", name).group(1))  # type: ignore[union-attr]


def _decode_pdf_literal(raw: bytes) -> str:
    output = bytearray()
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != 0x5C:
            output.append(char)
            index += 1
            continue
        index += 1
        if index >= len(raw):
            break
        escaped = raw[index]
        if escaped in b"nrtbf":
            output.append(_PDF_ESCAPE_BYTES[escaped])
            index += 1
            continue
        if 48 <= escaped <= 55:
            octal = bytes([escaped])
            index += 1
            for _ in range(2):
                if index < len(raw) and 48 <= raw[index] <= 55:
                    octal += bytes([raw[index]])
                    index += 1
                else:
                    break
            output.append(int(octal, 8))
            continue
        output.append(escaped)
        index += 1
    return bytes(output).decode("utf-8", errors="replace")


def _pdf_literal_parts(raw: bytes) -> Iterable[bytes]:
    index = 0
    while index < len(raw):
        if raw[index] != 0x28:
            index += 1
            continue
        index += 1
        start = index
        escaped = False
        while index < len(raw):
            char = raw[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if char == 0x5C:
                escaped = True
                index += 1
                continue
            if char == 0x29:
                yield raw[start:index]
                index += 1
                break
            index += 1


def _extract_printable_pdf_text(content: bytes) -> str:
    decoded = content.decode("latin-1", errors="ignore")
    lines: list[str] = []
    for chunk in _PRINTABLE_RE.findall(decoded):
        compact = " ".join(chunk.split())
        if _looks_like_pdf_syntax(compact):
            continue
        if re.search(r"[A-Za-z]{3}", compact):
            lines.append(compact)
    return "\n".join(lines[:100])


def _looks_like_pdf_syntax(value: str) -> bool:
    markers = ("%PDF", " obj", "endobj", "stream", "endstream", "xref", "trailer", "%%EOF")
    return any(marker in value for marker in markers)


def _clean_extracted_text(text: str | None) -> str | None:
    if text is None:
        return None
    lines = [" ".join(line.split()) for line in text.replace("\x00", "").splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    return cleaned or None


def _bounded_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_CONVERTED_TEXT_CHARS:
        return text, False
    return text[:MAX_CONVERTED_TEXT_CHARS].rstrip(), True


def _converted_output_path(source_path: str) -> str:
    normalized = _normalize_workspace_path(source_path)
    parts = [part for part in normalized.lstrip("/").split("/") if part and part != ".."]
    return "/converted/" + "/".join(parts) + ".md"


def _conversion_markdown(
    *,
    source: AgentWorkspaceFile,
    text: str,
    truncated: bool,
) -> str:
    lines = [
        "# Converted Workspace File",
        "",
        f"- Source path: `{source.path}`",
        f"- Source media type: `{source.media_type or 'unknown'}`",
        f"- Source size: `{source.size} bytes`",
        f"- Converter: `{CONVERTER_NAME}`",
        "",
        "## Extracted Text",
        "",
        text,
    ]
    if truncated:
        lines.extend(
            [
                "",
                f"[Converted text truncated at {MAX_CONVERTED_TEXT_CHARS} characters.]",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
