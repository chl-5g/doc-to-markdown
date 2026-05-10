"""Tests for WordConverter: .docx and .doc support."""
import tempfile
import zipfile
from pathlib import Path

from doc2md.word_converter import WordConverter


MINIMAL_DOCX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Hello World</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Section One</w:t></w:r></w:p>
    <w:p><w:r><w:t>This is a paragraph with some content.</w:t></w:r></w:p>
  </w:body>
</w:document>"""

DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOCX_WORD_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>"""


def _make_docx(path: Path) -> None:
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', DOCX_CONTENT_TYPES)
        z.writestr('_rels/.rels', DOCX_RELS)
        z.writestr('word/_rels/document.xml.rels', DOCX_WORD_RELS)
        z.writestr('word/document.xml', MINIMAL_DOCX_XML)


def test_convert_docx_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        docx = Path(tmpdir) / 'test.docx'
        _make_docx(docx)

        result = WordConverter().convert(str(docx))

        assert result.source_format == 'docx'
        assert 'Hello World' in result.content
        assert 'Section One' in result.content
        assert 'paragraph' in result.content


def test_convert_docx_empty():
    empty_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body></w:body>
</w:document>"""

    with tempfile.TemporaryDirectory() as tmpdir:
        docx = Path(tmpdir) / 'empty.docx'
        with zipfile.ZipFile(docx, 'w') as z:
            z.writestr('[Content_Types].xml', DOCX_CONTENT_TYPES)
            z.writestr('_rels/.rels', DOCX_RELS)
            z.writestr('word/_rels/document.xml.rels', DOCX_WORD_RELS)
            z.writestr('word/document.xml', empty_xml)

        result = WordConverter().convert(str(docx))
        assert result.source_format == 'docx'


def test_convert_save_to_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        docx = Path(tmpdir) / 'test.docx'
        _make_docx(docx)

        result = WordConverter().convert(str(docx))
        out = Path(tmpdir) / 'out.md'
        result.save(str(out))

        assert out.exists()
        content = out.read_text()
        assert 'Hello World' in content
