from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.escalations import router as escalation_router
from app.db.session import get_db


app = FastAPI(title="PolicyBot")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(escalation_router)


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Database is unavailable.",
        ) from exc

    return {"status": "ok"}


@app.get("/")
async def home():
    from fastapi.responses import FileResponse

    return FileResponse("frontend/index.html")
