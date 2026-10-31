import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.cache.store import clear_answer_cache
from app.db.models import Chunk, Escalation, PolicyDocument, User
from app.db.session import get_db
from app.ingestion.indexer import sync_document


router = APIRouter(prefix="/admin", tags=["admin"])
upload_folder = Path("/app/data/uploads")


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    effective_date: date | None = Form(default=None),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Upload a PDF or DOCX document.")
    data = await file.read(15 * 1024 * 1024 + 1)
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Maximum upload size is 15 MB.")
    name = Path(file.filename or ("policy" + suffix)).name
    result = await db.execute(select(PolicyDocument).where(PolicyDocument.name == name).order_by(PolicyDocument.version.desc()))
    document = result.scalars().first()
    if document is None:
        document = PolicyDocument(name=name, file_hash="", version=1, effective_date=effective_date, is_active=True)
        db.add(document)
        await db.flush()
    elif effective_date:
        document.effective_date = effective_date
    upload_folder.mkdir(parents=True, exist_ok=True)
    file_path = upload_folder / (str(document.id) + suffix)
    file_path.write_bytes(data)
    await db.commit()
    try:
        indexed = await sync_document(document.id, str(file_path))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="The document could not be indexed. Check that it is a readable PDF or DOCX.") from exc
    await clear_answer_cache()
    await db.refresh(document)
    return {"id": str(document.id), "name": name, "version": document.version, "effective_date": document.effective_date, **indexed}


@router.get("/documents")
async def list_documents(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PolicyDocument).order_by(PolicyDocument.name))
    return [{"id": str(doc.id), "name": doc.name, "version": doc.version, "effective_date": doc.effective_date, "active": doc.is_active, "uploaded_at": doc.uploaded_at} for doc in result.scalars()]


@router.delete("/documents/{document_id}")
async def delete_document(document_id: uuid.UUID, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    document = await db.get(PolicyDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    document.is_active = False
    result = await db.execute(select(Chunk).where(Chunk.doc_id == document_id))
    for chunk in result.scalars():
        chunk.is_active = False
    await db.commit()
    await clear_answer_cache()
    return {"status": "deleted"}


class EscalationReply(BaseModel):
    reply: str = Field(min_length=1, max_length=5000)


@router.get("/escalations")
async def list_escalations(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Escalation).order_by(Escalation.created_at.desc()))
    return [{"id": str(item.id), "user_email": item.user_email, "question": item.question, "bot_answer": item.bot_answer, "status": item.status, "hr_reply": item.hr_reply, "created_at": item.created_at} for item in result.scalars()]


@router.post("/escalations/{escalation_id}/reply")
async def reply_to_escalation(escalation_id: uuid.UUID, body: EscalationReply, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    item = await db.get(Escalation, escalation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Escalation not found.")
    item.hr_reply = body.reply
    item.status = "resolved"
    item.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": item.status, "hr_reply": item.hr_reply}
