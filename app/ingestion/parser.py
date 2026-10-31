import re
from pathlib import Path
from statistics import median

import pymupdf
from docx import Document as WordDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from langchain_core.documents import Document


def table_to_markdown(rows):
    if not rows:
        return ""

    lines = []
    for row in rows:
        cells = [str(cell or "").replace("|", r"\|").replace("\n", "<br>") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")

    if len(lines) == 1:
        return lines[0]

    divider = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    return "\n".join([lines[0], divider] + lines[1:])


def is_heading(text, font_size=0, body_font_size=0, bold=False):
    text = text.strip()

    if not text or len(text) > 120:
        return False
    if text.endswith((".", "?", "!", ";")):
        return False

    numbered = re.match(r"^\s*(\d+(\.\d+)*[.)]?|[A-Z][.)])\s+\S", text)
    large = body_font_size and font_size >= body_font_size + 1.5

    return bool(numbered or bold or large)


def add_document(documents, parts, document_name, section, page):
    text = "\n".join(part for part in parts if part.strip()).strip()

    if text:
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "document": document_name,
                    "section": section,
                    "page": page,
                },
            )
        )


def extract_pdf(path):
    documents = []
    document_name = path.name
    sections = []

    with pymupdf.open(path) as pdf:
        for page in pdf:
            page_data = page.get_text("dict")
            for block in page_data["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if span["text"].strip():
                            sections.append(span["size"])

        body_font_size = median(sections) if sections else 0
        current_section = "General"

        for page_number, page in enumerate(pdf, start=1):
            page_data = page.get_text("dict")
            page_parts = []

            tables = page.find_tables().tables
            table_areas = [table.bbox for table in tables]
            tables_written = set()

            for block in page_data["blocks"]:
                for line in block.get("lines", []):
                    spans = line["spans"]
                    text = "".join(span["text"] for span in spans).strip()

                    if not text:
                        continue

                    line_box = line["bbox"]
                    center_x = (line_box[0] + line_box[2]) / 2
                    center_y = (line_box[1] + line_box[3]) / 2
                    inside_table = any(
                        area[0] <= center_x <= area[2]
                        and area[1] <= center_y <= area[3]
                        for area in table_areas
                    )

                    if inside_table:
                        # FIX: write the table here, at the place where it sits on the page,
                        # the first time we reach one of its lines. Before, every table was
                        # added at the end of the page and got the LAST heading of the page.
                        for index, area in enumerate(table_areas):
                            if (
                                area[0] <= center_x <= area[2]
                                and area[1] <= center_y <= area[3]
                            ):
                                if index not in tables_written:
                                    markdown = table_to_markdown(tables[index].extract())
                                    if markdown:
                                        page_parts.append(markdown)
                                    tables_written.add(index)
                                break
                        continue

                    font_size = max(span["size"] for span in spans)
                    bold = any(
                        "bold" in span["font"].lower()
                        or bool(span["flags"] & 16)
                        for span in spans
                    )

                    if is_heading(text, font_size, body_font_size, bold):
                        add_document(
                            documents,
                            page_parts,
                            document_name,
                            current_section,
                            page_number,
                        )
                        page_parts = []
                        current_section = text
                    else:
                        page_parts.append(text)

            # Safety net: any table that was not reached above is still added.
            for index, table in enumerate(tables):
                if index in tables_written:
                    continue
                markdown = table_to_markdown(table.extract())
                if markdown:
                    page_parts.append(markdown)

            add_document(
                documents,
                page_parts,
                document_name,
                current_section,
                page_number,
            )

    return documents


def extract_docx(path):
    documents = []
    document_name = path.name
    current_section = "General"
    section_parts = []

    word_file = WordDocument(path)

    for item in word_file.iter_inner_content():
        if isinstance(item, Paragraph):
            text = item.text.strip()
            style = item.style.name.lower()

            bold = bool(item.runs) and all(
                run.bold for run in item.runs if run.text.strip()
            )
            numbered = re.match(r"^\s*(\d+(\.\d+)*[.)]?|[A-Z][.)])\s+\S", text)

            if text and (
                style.startswith("heading")
                or style == "title"
                or numbered
                or (bold and len(text) <= 120 and not text.endswith((".", "?", "!", ";")))
            ):
                add_document(
                    documents,
                    section_parts,
                    document_name,
                    current_section,
                    None,
                )
                section_parts = []
                current_section = text
            elif text:
                section_parts.append(text)

        elif isinstance(item, Table):
            rows = [[cell.text for cell in row.cells] for row in item.rows]
            markdown = table_to_markdown(rows)
            if markdown:
                section_parts.append(markdown)

    add_document(
        documents,
        section_parts,
        document_name,
        current_section,
        None,
    )

    return documents


def extract_sections(file_path):
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Document not found: {path}")

    if path.suffix.lower() == ".pdf":
        return extract_pdf(path)

    if path.suffix.lower() == ".docx":
        return extract_docx(path)

    raise ValueError("Only digital PDF and DOCX files are supported.")