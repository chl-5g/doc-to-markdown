"""Tests for ExcelConverter: .xlsx/.xls conversion."""
import tempfile
from pathlib import Path

from openpyxl import Workbook

from doc2md.excel_converter import ExcelConverter


def _make_xlsx(path: Path, sheets: dict[str, list[list]]) -> None:
    wb = Workbook()
    first = True
    for name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = name
            first = False
        else:
            ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    wb.save(path)


def test_convert_single_sheet():
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx = Path(tmpdir) / 'test.xlsx'
        _make_xlsx(xlsx, {
            'Data': [['Name', 'Age'], ['Alice', 30], ['Bob', 25]],
        })

        result = ExcelConverter().convert(str(xlsx))

        assert 'Data' in result.content
        assert 'Name' in result.content
        assert 'Alice' in result.content
        assert 'Bob' in result.content
        assert '|' in result.content
        assert result.metadata['sheets'] == ['Data']


def test_convert_multi_sheet():
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx = Path(tmpdir) / 'multi.xlsx'
        _make_xlsx(xlsx, {
            'Sheet1': [['A', 'B'], [1, 2]],
            'Sheet2': [['X', 'Y'], [10, 20]],
        })

        result = ExcelConverter().convert(str(xlsx))

        assert 'Sheet1' in result.content
        assert 'Sheet2' in result.content
        assert 'X' in result.content
        assert result.metadata['sheets'] == ['Sheet1', 'Sheet2']


def test_convert_empty_sheet():
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx = Path(tmpdir) / 'empty.xlsx'
        _make_xlsx(xlsx, {'Empty': []})

        result = ExcelConverter().convert(str(xlsx))

        assert 'Empty' in result.content
        assert 'empty sheet' in result.content.lower()
