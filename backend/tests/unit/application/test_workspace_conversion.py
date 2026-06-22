import io
import zipfile

import pytest

from aithru_agent.application.workspace_conversion import convert_workspace_file
from aithru_agent.persistence.memory import InMemoryAgentStore


PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.asyncio
async def test_converts_docx_to_managed_markdown_and_preserves_original() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    content = _zip_bytes(
        {
            "word/document.xml": """
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                  <w:body>
                    <w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p>
                    <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>
                  </w:body>
                </w:document>
                """,
        }
    )
    source = await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/source.docx",
        content=content,
        media_type=DOCX_MEDIA_TYPE,
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/source.docx",
    )

    assert result.status == "converted"
    assert result.converter == "builtin_document_text"
    assert result.source_path == "/uploads/source.docx"
    assert result.source_size == len(content)
    assert result.source_content_hash == source.content_hash
    assert result.output_path == "/converted/uploads/source.docx.md"
    assert result.output_media_type == "text/markdown"
    assert result.output_file is not None
    assert result.output_file.path == "/converted/uploads/source.docx.md"

    converted = await store.read_workspace_file(workspace.id, result.output_path)
    original = await store.read_workspace_file(workspace.id, "/uploads/source.docx")
    assert original.content == content
    assert converted.media_type == "text/markdown"
    assert isinstance(converted.content, str)
    assert "Source path: `/uploads/source.docx`" in converted.content
    assert f"Source media type: `{DOCX_MEDIA_TYPE}`" in converted.content
    assert "Hello DOCX" in converted.content
    assert "Second paragraph" in converted.content
    assert sorted(file.path for file in await store.list_workspace_files(workspace.id)) == [
        "/converted/uploads/source.docx.md",
        "/uploads/source.docx",
    ]


@pytest.mark.asyncio
async def test_converts_pptx_slides_in_order() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    content = _zip_bytes(
        {
            "ppt/slides/slide2.xml": """
                <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
                  <p:cSld><p:spTree><p:sp><p:txBody>
                    <a:p><a:r><a:t>Second slide</a:t></a:r></a:p>
                  </p:txBody></p:sp></p:spTree></p:cSld>
                </p:sld>
                """,
            "ppt/slides/slide1.xml": """
                <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
                  <p:cSld><p:spTree><p:sp><p:txBody>
                    <a:p><a:r><a:t>First slide</a:t></a:r></a:p>
                  </p:txBody></p:sp></p:spTree></p:cSld>
                </p:sld>
                """,
        }
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/deck.pptx",
        content=content,
        media_type=PPTX_MEDIA_TYPE,
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/deck.pptx",
    )

    converted = await store.read_workspace_file(workspace.id, result.output_path or "")
    assert result.status == "converted"
    assert isinstance(converted.content, str)
    assert converted.content.index("Slide 1") < converted.content.index("Slide 2")
    assert "First slide" in converted.content
    assert "Second slide" in converted.content


@pytest.mark.asyncio
async def test_converts_xlsx_rows_with_shared_and_inline_strings() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    content = _zip_bytes(
        {
            "xl/sharedStrings.xml": """
                <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <si><t>Quarter</t></si>
                  <si><t>Revenue</t></si>
                </sst>
                """,
            "xl/worksheets/sheet1.xml": """
                <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <sheetData>
                    <row r="1">
                      <c r="A1" t="s"><v>0</v></c>
                      <c r="B1" t="s"><v>1</v></c>
                    </row>
                    <row r="2">
                      <c r="A2" t="inlineStr"><is><t>Q1</t></is></c>
                      <c r="B2"><v>42</v></c>
                    </row>
                  </sheetData>
                </worksheet>
                """,
        }
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/workbook.xlsx",
        content=content,
        media_type=XLSX_MEDIA_TYPE,
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/workbook.xlsx",
    )

    converted = await store.read_workspace_file(workspace.id, result.output_path or "")
    assert result.status == "converted"
    assert isinstance(converted.content, str)
    assert "Sheet 1" in converted.content
    assert "Quarter | Revenue" in converted.content
    assert "Q1 | 42" in converted.content


@pytest.mark.asyncio
async def test_converts_simple_pdf_text_operators() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    content = b"%PDF-1.4\nBT\n/F1 12 Tf\n(Hello PDF) Tj\n[(Second) 120 (line)] TJ\nET\n%%EOF"
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/report.pdf",
        content=content,
        media_type=PDF_MEDIA_TYPE,
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/report.pdf",
    )

    converted = await store.read_workspace_file(workspace.id, result.output_path or "")
    assert result.status == "converted"
    assert isinstance(converted.content, str)
    assert "Hello PDF" in converted.content
    assert "Second line" in converted.content


@pytest.mark.asyncio
async def test_invalid_printable_pdf_fails_without_writing_output() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/fake.pdf",
        content=b"This is plain printable text, not a real PDF document.",
        media_type=PDF_MEDIA_TYPE,
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/fake.pdf",
    )

    assert result.status == "failed"
    assert result.output_path is None
    assert result.output_file is None
    assert result.reason == "Could not extract text from workspace file."
    assert [file.path for file in await store.list_workspace_files(workspace.id)] == [
        "/uploads/fake.pdf",
    ]


@pytest.mark.asyncio
async def test_empty_pdf_fails_without_writing_output() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/empty.pdf",
        content=b"",
        media_type=PDF_MEDIA_TYPE,
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/empty.pdf",
    )

    assert result.status == "failed"
    assert result.output_path is None
    assert result.output_file is None
    assert result.reason == "Could not extract text from workspace file."
    assert [file.path for file in await store.list_workspace_files(workspace.id)] == [
        "/uploads/empty.pdf",
    ]


@pytest.mark.asyncio
async def test_skips_model_readable_text_without_writing_output() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/notes.md",
        content="# Notes\n",
        media_type="text/markdown",
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/notes.md",
    )

    assert result.status == "skipped"
    assert result.reason == "File is already model-readable."
    assert result.output_path is None
    assert [file.path for file in await store.list_workspace_files(workspace.id)] == [
        "/uploads/notes.md",
    ]


@pytest.mark.asyncio
async def test_returns_unsupported_for_non_document_media_without_writing_output() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/chart.png",
        content=b"image bytes",
        media_type="image/png",
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/chart.png",
    )

    assert result.status == "unsupported"
    assert result.reason == "Unsupported workspace file media type."
    assert result.output_path is None
    assert [file.path for file in await store.list_workspace_files(workspace.id)] == [
        "/uploads/chart.png",
    ]


@pytest.mark.asyncio
async def test_invalid_supported_file_fails_without_writing_empty_output() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/broken.docx",
        content=b"not a zip file",
        media_type=DOCX_MEDIA_TYPE,
    )

    result = await convert_workspace_file(
        store,
        workspace_id=workspace.id,
        path="/uploads/broken.docx",
    )

    assert result.status == "failed"
    assert result.output_path is None
    assert result.output_file is None
    assert result.reason == "Could not extract text from workspace file."
    assert [file.path for file in await store.list_workspace_files(workspace.id)] == [
        "/uploads/broken.docx",
    ]


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()
