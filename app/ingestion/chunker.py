from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHUNK_OVERLAP, CHUNK_SIZE, MIN_SECTION_CHARS


def combine_sections(first, second):
    metadata = dict(first.metadata)

    first_section = first.metadata.get("section", "General")
    second_section = second.metadata.get("section", "General")
    metadata["section"] = f"{first_section} / {second_section}"

    return Document(
        page_content=first.page_content + "\n\n" + second.page_content,
        metadata=metadata,
    )


def merge_short_sections(sections):
    merged = []
    index = 0

    while index < len(sections):
        section = sections[index]

        while (
            len(section.page_content) < MIN_SECTION_CHARS
            and index + 1 < len(sections)
            and section.metadata.get("document")
            == sections[index + 1].metadata.get("document")
            and section.metadata.get("page")
            == sections[index + 1].metadata.get("page")
        ):
            section = combine_sections(section, sections[index + 1])
            index += 1

        merged.append(section)
        index += 1

    return merged


def chunk_sections(sections):
    sections = merge_short_sections(sections)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    return splitter.split_documents(sections)