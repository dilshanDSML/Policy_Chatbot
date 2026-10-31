import asyncio
import hashlib
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.db.models import Chunk, PolicyDocument
from app.db.session import SessionLocal
from app.ingestion.chunker import chunk_sections
from app.ingestion.embedder import embed_documents
from app.ingestion.hasher import hash_chunk
from app.ingestion.parser import extract_sections


logger = logging.getLogger(__name__)


def get_file_hash(file_path):
    with open(file_path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


async def sync_document(document_id: UUID, file_path: str):
    file_path = Path(file_path)
    current_file_hash = get_file_hash(file_path)

    async with SessionLocal() as session:
        document = await session.get(PolicyDocument, document_id)
        if document is None:
            raise ValueError("Document record was not found.")

        if document.file_hash == current_file_hash and document.is_active:
            logger.info("File is unchanged; skipping indexing.")
            return {"skipped": 0, "added": 0, "deactivated": 0}

        sections = await asyncio.to_thread(extract_sections, file_path)
        chunks = await asyncio.to_thread(chunk_sections, sections)

        chunks_by_hash = {}
        for chunk in chunks:
            chunks_by_hash.setdefault(
                hash_chunk(chunk.page_content),
                chunk,
            )

        result = await session.execute(
            select(Chunk).where(Chunk.doc_id == document_id)
        )
        old_chunks = result.scalars().all()
        old_by_hash = {chunk.chunk_hash: chunk for chunk in old_chunks}
        new_hashes = set(chunks_by_hash)

        deactivated = 0
        for old_chunk in old_chunks:
            if old_chunk.is_active and old_chunk.chunk_hash not in new_hashes:
                old_chunk.is_active = False
                deactivated += 1

        chunks_to_add = []
        skipped = 0

        for chunk_hash, chunk in chunks_by_hash.items():
            old_chunk = old_by_hash.get(chunk_hash)

            if old_chunk is not None:
                old_chunk.is_active = True
                skipped += 1
            else:
                chunks_to_add.append((chunk_hash, chunk))

        if chunks_to_add:
            texts = [chunk.page_content for _, chunk in chunks_to_add]
            embeddings = await asyncio.to_thread(embed_documents, texts)

            for (chunk_hash, chunk), embedding in zip(chunks_to_add, embeddings):
                session.add(
                    Chunk(
                        doc_id=document_id,
                        chunk_hash=chunk_hash,
                        text=chunk.page_content,
                        section=chunk.metadata.get("section"),
                        page=chunk.metadata.get("page"),
                        embedding=embedding,
                        tsv=func.to_tsvector("english", chunk.page_content),
                        is_active=True,
                    )
                )

        if document.file_hash:
            document.version += 1

        document.file_hash = current_file_hash
        document.is_active = True

        await session.commit()

        added = len(chunks_to_add)
        logger.info(
            "%s skipped, %s added, %s deactivated",
            skipped,
            added,
            deactivated,
        )

        return {
            "skipped": skipped,
            "added": added,
            "deactivated": deactivated,
        }