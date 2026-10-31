from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_user
from app.db.models import Escalation, User
from app.db.session import get_db


router = APIRouter(prefix="/escalations", tags=["escalations"])


class EscalationRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    bot_answer: str = Field(min_length=1, max_length=5000)


@router.post("")
async def create_escalation(body: EscalationRequest, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    item = Escalation(user_email=user.email, question=body.question, bot_answer=body.bot_answer, status="open")
    db.add(item)
    await db.commit()
    return {"id": str(item.id), "status": item.status}


@router.get("")
async def my_escalations(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Escalation).where(Escalation.user_email == user.email).order_by(Escalation.created_at.desc()))
    return [{"id": str(item.id), "question": item.question, "status": item.status, "hr_reply": item.hr_reply, "created_at": item.created_at} for item in result.scalars()]
