"""Reading .xlsx and .docx with the standard library only.

This is how the source registry is built from the owner's spreadsheet, so a
mis-read here decides which sources exist. It had no tests.

The fixtures are real Office files assembled with zipfile, not mocks: the whole
point of this module is that it parses the actual XML those formats use, and a
mock of that XML would only test the mock.
"""

import os
import sys
import tempfile
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.office_reader import docx_to_text, xlsx_to_text

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RELNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
WNS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _xlsx(sheet_xml, shared=None, rels=None, sheet_name="Sheet1"):
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml",
                    f'<workbook {NS} {RELNS}><sheets>'
                    f'<sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>'
                    f'</sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/'
                    'package/2006/relationships"><Relationship Id="rId1" '
                    'Target="worksheets/sheet1.xml"/></Relationships>')
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        if shared is not None:
            zf.writestr("xl/sharedStrings.xml", shared)
        if rels is not None:
            zf.writestr("xl/worksheets/_rels/sheet1.xml.rels", rels)
    return path


def _sheet(rows_xml):
    return f'<worksheet {NS}><sheetData>{rows_xml}</sheetData></worksheet>'


def _inline(ref, text):
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


# --- cells --------------------------------------------------------------------

def test_inline_strings_are_read():
    path = _xlsx(_sheet(f'<row>{_inline("A1","BIS")}{_inline("B1","regulator")}</row>'))
    try:
        assert "BIS | regulator" in xlsx_to_text(path)
    finally:
        os.unlink(path)


def test_shared_strings_are_resolved():
    """Excel stores repeated text once and references it by index. Reading the
    index literally would fill the registry with numbers."""
    shared = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
              '2006/main"><si><t>Bank for Intl. Settlements</t></si>'
              '<si><t>regulator</t></si></sst>')
    path = _xlsx(_sheet('<row><c r="A1" t="s"><v>0</v></c>'
                        '<c r="B1" t="s"><v>1</v></c></row>'), shared=shared)
    try:
        assert "Bank for Intl. Settlements | regulator" in xlsx_to_text(path)
    finally:
        os.unlink(path)


def test_an_out_of_range_shared_index_does_not_crash():
    shared = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
              '2006/main"><si><t>only one</t></si></sst>')
    path = _xlsx(_sheet('<row><c r="A1" t="s"><v>99</v></c></row>'), shared=shared)
    try:
        xlsx_to_text(path)        # must not raise
    finally:
        os.unlink(path)


def test_the_sheet_name_is_reported():
    path = _xlsx(_sheet(f'<row>{_inline("A1","x")}</row>'), sheet_name="Sources")
    try:
        assert "SHEET: Sources" in xlsx_to_text(path)
    finally:
        os.unlink(path)


# --- hyperlinks ---------------------------------------------------------------

def test_a_hyperlink_target_is_recovered():
    """A cell displaying "Homepage" with the URL behind it would otherwise reach
    the registry as a dead label with no address."""
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Id="rId1" '
            'Target="https://bis.org" TargetMode="External"/></Relationships>')
    sheet = (f'<worksheet {NS} {RELNS}><sheetData>'
             f'<row>{_inline("A1","Homepage")}</row></sheetData>'
             f'<hyperlinks><hyperlink ref="A1" r:id="rId1"/></hyperlinks>'
             f'</worksheet>')
    path = _xlsx(sheet, rels=rels)
    try:
        assert "Homepage <https://bis.org>" in xlsx_to_text(path)
    finally:
        os.unlink(path)


def test_a_url_already_shown_is_not_repeated():
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Id="rId1" '
            'Target="https://bis.org" TargetMode="External"/></Relationships>')
    sheet = (f'<worksheet {NS} {RELNS}><sheetData>'
             f'<row>{_inline("A1","https://bis.org")}</row></sheetData>'
             f'<hyperlinks><hyperlink ref="A1" r:id="rId1"/></hyperlinks>'
             f'</worksheet>')
    path = _xlsx(sheet, rels=rels)
    try:
        assert xlsx_to_text(path).count("https://bis.org") == 1
    finally:
        os.unlink(path)


# --- shape --------------------------------------------------------------------

def test_trailing_empty_cells_are_dropped_but_inner_ones_kept():
    """An empty column in the middle is a missing value and shifts every later
    field if it is dropped."""
    path = _xlsx(_sheet(f'<row>{_inline("A1","a")}<c r="B1"/>{_inline("C1","c")}'
                        f'<c r="D1"/></row>'))
    try:
        assert "a |  | c" in xlsx_to_text(path)
    finally:
        os.unlink(path)


def test_a_wholly_empty_row_is_skipped():
    path = _xlsx(_sheet(f'<row>{_inline("A1","a")}</row><row><c r="A2"/></row>'))
    try:
        assert len([ln for ln in xlsx_to_text(path).splitlines()
                    if ln and not ln.startswith("=")]) == 1
    finally:
        os.unlink(path)


def test_a_runaway_workbook_is_truncated():
    rows = "".join(f'<row>{_inline(f"A{i}", f"row{i}")}</row>' for i in range(50))
    path = _xlsx(_sheet(rows))
    try:
        out = xlsx_to_text(path, max_rows=10)
        assert "truncated at 10 rows" in out
        assert "row20" not in out
    finally:
        os.unlink(path)


def test_newlines_inside_a_cell_do_not_break_the_row():
    """Rows are the record separator; a newline in a cell would split one record
    into two."""
    path = _xlsx(_sheet(f'<row>{_inline("A1","two<", )}</row>'.replace("two<", "line\none")))
    try:
        body = [ln for ln in xlsx_to_text(path).splitlines() if not ln.startswith("=")]
        assert len([ln for ln in body if ln]) == 1
    finally:
        os.unlink(path)


# --- docx ---------------------------------------------------------------------

def test_docx_paragraphs_are_read_in_order():
    fd, path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml",
                    f'<document {WNS}><w:body>'
                    f'<w:p><w:r><w:t>First line</w:t></w:r></w:p>'
                    f'<w:p><w:r><w:t>Second </w:t></w:r>'
                    f'<w:r><w:t>line</w:t></w:r></w:p>'
                    f'</w:body></document>')
    try:
        out = docx_to_text(path)
        assert "First line" in out
        assert "Second line" in out, "runs within a paragraph must join"
        assert out.index("First") < out.index("Second")
    finally:
        os.unlink(path)


def test_an_unreadable_file_raises_rather_than_returning_nothing():
    """Silently returning "" would build an empty registry and look like an empty
    spreadsheet."""
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    with open(path, "w") as fh:
        fh.write("this is not a zip file")
    try:
        with pytest.raises(Exception):
            xlsx_to_text(path)
    finally:
        os.unlink(path)
