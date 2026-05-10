"""Tests for PdfConverter: text-layer extraction and OCR pipeline."""
import tempfile
from pathlib import Path

import fitz

from doc2md.pdf_converter import (
    PdfConverter,
    _clean_text,
    _images_to_pdf,
    _preprocess_pdf_pages,
)


def _make_text_pdf(path: Path, pages: list[str]) -> None:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


def _make_heading_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Big Title", fontsize=24)
    page.insert_text((72, 120), "Normal paragraph text goes here with enough content.", fontsize=12)
    page.insert_text((72, 160), "Sub Section", fontsize=16)
    page.insert_text((72, 200), "More body text right here for testing purposes.", fontsize=12)
    doc.save(str(path))
    doc.close()


def test_extract_text_layer():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf = Path(tmpdir) / 'test.pdf'
        # >= 50 chars to stay on pymupdf path, not trigger OCR
        _make_text_pdf(pdf, [
            'This is a PDF with a proper text layer that has enough '
            'characters to pass the minimum text length threshold.'
        ])

        converter = PdfConverter()
        result = converter.convert(str(pdf))

        assert result.source_format == 'pdf'
        assert result.metadata['engine'] == 'pymupdf'
        assert 'proper text layer' in result.content


def test_extract_with_headings():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf = Path(tmpdir) / 'headings.pdf'
        _make_heading_pdf(pdf)

        converter = PdfConverter()
        result = converter.convert(str(pdf))

        assert 'Big Title' in result.content
        assert 'Sub Section' in result.content
        assert 'Normal paragraph' in result.content
        assert 'More body text' in result.content


def test_clean_text_filters_garbled():
    # Realistic OCR noise: Chinese text with garbled character sequences
    result = _clean_text('这是一段正常的中文文本\n丂丄丂丄丰亐倷伒偀\n继续正常文本')
    # jieba segments garbled chars individually -> low valid/total ratio -> filtered
    assert '正常的中文文本' in result
    assert '继续正常文本' in result


def test_clean_text_preserves_blank_lines():
    result = _clean_text('line one\n\nline two')
    assert '\n\n' in result


def test_convert_save():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf = Path(tmpdir) / 'test.pdf'
        _make_text_pdf(pdf, [
            'Save test content that needs to be long enough for the text '
            'layer detection threshold so it does not trigger OCR path.'
        ])

        converter = PdfConverter()
        result = converter.convert(str(pdf))
        out = Path(tmpdir) / 'out.md'
        result.save(str(out))

        assert out.exists()
        assert 'Save test content' in out.read_text()
        assert result.metadata['engine'] == 'pymupdf'
