"""Read .xlsx / .docx with the standard library only.

Ported from the predecessor repo (antier-intelligence-agent). No pandas, no openpyxl:
these are configuration files read once per run, and a zero-dependency reader keeps
CLAUDE.md rule 2 honest.

Recovers hyperlink targets. Excel stores a link's URL outside the cell, so a cell
reading "Homepage" with a link behind it would otherwise extract as a dead label --
and SOURCE_POLICY.md requires a working URL per source.

    from src.ingestion.office_reader import xlsx_to_text, docx_to_text
"""

import os
import re
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

CELL_REF = re.compile(r"^([A-Z]+)([0-9]+)$")



def docx_to_text(path):
    """Paragraph text from a .docx. Table cells arrive via the same <w:p> walk."""
    zf = zipfile.ZipFile(path)
    if "word/document.xml" not in zf.namelist():
        return ""
    root = ET.fromstring(zf.read("word/document.xml"))
    lines = []
    for para in root.iter(W + "p"):
        text = "".join(node.text or "" for node in para.iter(W + "t"))
        if text.strip():
            lines.append(text.strip())
    return "\n".join(lines)


def _shared_strings(zf):
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(S + "t")) for si in root.iter(S + "si")]


def _sheet_paths(zf):
    """Ordered {sheet name: zip path}, resolved through workbook rels."""
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_xml = zf.read("xl/_rels/workbook.xml.rels").decode("utf8", "replace")
    rels = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels_xml))
    sheets = {}
    for sheet in workbook.iter(S + "sheet"):
        target = rels.get(sheet.attrib.get(R_ID), "")
        if target:
            sheets[sheet.attrib["name"]] = "xl/" + target.lstrip("/").replace("xl/", "")
    return sheets


def _hyperlink_map(zf, sheet_path):
    """{cell ref -> URL} for links stored as relationship targets.

    Excel keeps a hyperlink's URL outside the cell: the cell holds display text
    ("Homepage") and a <hyperlink> element points at a target in the sheet's .rels.
    Reading cell values alone silently drops those URLs, which matters because §3
    Pass 2 searches by entity and every event needs a working link.
    """
    rels_path = sheet_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if rels_path not in zf.namelist():
        return {}
    rels = dict(
        re.findall(
            r'Id="([^"]+)"[^>]*Target="([^"]+)"',
            zf.read(rels_path).decode("utf8", "replace"),
        )
    )
    links = {}
    root = ET.fromstring(zf.read(sheet_path))
    for node in root.iter(S + "hyperlink"):
        ref = node.attrib.get("ref", "")
        target = rels.get(node.attrib.get(R_ID, ""), "")
        if ref and target.startswith("http"):
            # A ref can be a range (A1:A9); anchor on its first cell.
            links[ref.split(":")[0]] = target
    return links


def xlsx_to_text(path, max_rows=5000):
    """Every sheet as pipe-delimited rows. max_rows guards a runaway workbook."""
    zf = zipfile.ZipFile(path)
    shared = _shared_strings(zf)
    out = []
    for name, sheet_path in _sheet_paths(zf).items():
        if sheet_path not in zf.namelist():
            continue
        out.append("\n===== SHEET: %s =====" % name)
        links = _hyperlink_map(zf, sheet_path)
        root = ET.fromstring(zf.read(sheet_path))
        for row_index, row in enumerate(root.iter(S + "row")):
            if row_index >= max_rows:
                out.append("  ... [truncated at %d rows]" % max_rows)
                break
            cells = []
            for cell in row.iter(S + "c"):
                value_node = cell.find(S + "v")
                inline_node = cell.find(S + "is")
                value = ""
                if value_node is not None and value_node.text is not None:
                    value = value_node.text
                    if cell.attrib.get("t") == "s":
                        try:
                            value = shared[int(value)]
                        except (ValueError, IndexError):
                            pass
                elif inline_node is not None:
                    value = "".join(t.text or "" for t in inline_node.iter(S + "t"))
                text = value.replace("\n", " ").strip()
                # Recover a hyperlink target the display text does not already show,
                # so "Homepage" becomes "Homepage <https://...>" rather than a dead label.
                url = links.get(cell.attrib.get("r", ""))
                if url and url not in text:
                    text = ("%s <%s>" % (text, url)).strip()
                cells.append(text)
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                out.append(" | ".join(cells))
    return "\n".join(out)
