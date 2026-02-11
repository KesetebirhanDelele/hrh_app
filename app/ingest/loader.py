"""Extract text and tables from PDF and DOCX files."""

from __future__ import annotations

from pathlib import Path
from typing import List, TypedDict

import pdfplumber
from docx import Document as DocxDocument


class Snippet(TypedDict):
    locator: str
    text: str
    type: str  # "text" | "table"


def _table_to_markdown(table_data: list[list[str | None]]) -> str:
    """Convert a 2-D list of cell values into a markdown table string."""
    if not table_data or not table_data[0]:
        return ""

    def _cell(val: str | None) -> str:
        if val is None:
            return ""
        return val.replace("|", "\\|").replace("\n", " ").strip()

    rows: list[str] = []
    # Header row
    header = [_cell(c) for c in table_data[0]]
    rows.append("| " + " | ".join(header) + " |")
    rows.append("| " + " | ".join("---" for _ in header) + " |")
    # Data rows
    for row in table_data[1:]:
        cells = [_cell(c) for c in row]
        # Pad or truncate to match header width
        while len(cells) < len(header):
            cells.append("")
        rows.append("| " + " | ".join(cells[: len(header)]) + " |")

    return "\n".join(rows)


def extract_pdf(file_path: str | Path) -> List[Snippet]:
    """Extract text and tables from a PDF file, page by page.

    Returns a list of Snippet dicts with locator, text, and type fields.
    """
    file_path = Path(file_path)
    snippets: list[Snippet] = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            locator_prefix = f"p. {page_num}"

            # Extract tables and convert to markdown
            tables = page.extract_tables()

            if tables:
                for table_idx, table_data in enumerate(tables):
                    md = _table_to_markdown(table_data)
                    if md.strip():
                        label = f"Table on {locator_prefix}"
                        if len(tables) > 1:
                            label = f"Table {table_idx + 1} on {locator_prefix}"
                        snippets.append(
                            Snippet(locator=label, text=md, type="table")
                        )

            # Extract page text (tables may appear duplicated in text,
            # but the LLM benefits from having both structured and
            # narrative context).
            text = page.extract_text() or ""

            text = text.strip()
            if text:
                snippets.append(
                    Snippet(locator=locator_prefix, text=text, type="text")
                )

    return snippets


def extract_docx(file_path: str | Path) -> List[Snippet]:
    """Extract text and tables from a DOCX file.

    Returns a list of Snippet dicts. Paragraphs are grouped into page-like
    chunks, and tables are converted to markdown.
    """
    file_path = Path(file_path)
    doc = DocxDocument(str(file_path))
    snippets: list[Snippet] = []

    # Track position for locators
    para_buffer: list[str] = []
    element_index = 0

    # Iterate through document body elements in order to preserve
    # the interleaving of paragraphs and tables.
    for element in doc.element.body:
        tag = element.tag.split("}")[-1]  # strip namespace

        if tag == "p":
            # Paragraph element
            from docx.oxml.text.paragraph import CT_P

            if isinstance(element, CT_P):
                para_text = element.text or ""
                # Also gather text from runs for richer extraction
                runs_text = "".join(
                    node.text or ""
                    for node in element.iter()
                    if node.text
                )
                text = runs_text.strip() if runs_text.strip() else para_text.strip()
                if text:
                    para_buffer.append(text)

        elif tag == "tbl":
            # Flush paragraph buffer before the table
            if para_buffer:
                element_index += 1
                snippets.append(
                    Snippet(
                        locator=f"Section {element_index}",
                        text="\n".join(para_buffer),
                        type="text",
                    )
                )
                para_buffer = []

            # Extract table
            from docx.table import Table as DocxTable

            tbl = DocxTable(element, doc)
            table_data: list[list[str]] = []
            for row in tbl.rows:
                table_data.append([cell.text.strip() for cell in row.cells])

            md = _table_to_markdown(table_data)
            if md.strip():
                element_index += 1
                snippets.append(
                    Snippet(
                        locator=f"Table in section {element_index}",
                        text=md,
                        type="table",
                    )
                )

    # Flush remaining paragraphs
    if para_buffer:
        element_index += 1
        snippets.append(
            Snippet(
                locator=f"Section {element_index}",
                text="\n".join(para_buffer),
                type="text",
            )
        )

    return snippets
