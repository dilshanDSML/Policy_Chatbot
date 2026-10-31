import hashlib
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import require_user
from app.cache.store import get_cached_answer, get_history, get_redis, save_cached_answer, save_history
from app.config import FINAL_K
from app.db.models import User
from app.llm.bot import answer_question, is_policy_question, rewrite_question
from app.retrieval.retriever import retrieve_documents


router = APIRouter(tags=["chat"])
valid_strategies = {"vector_only", "hybrid", "hybrid_rerank"}


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    session_id: str | None = None
    retrieval_config: str = "hybrid_rerank"
    include_contexts: bool = False


@router.post("/ask")
async def ask(body: AskRequest, user: User = Depends(require_user)):
    if body.retrieval_config not in valid_strategies:
        raise HTTPException(status_code=400, detail="Unknown retrieval configuration.")
    redis = get_redis()
    count = await redis.incr("rate:" + str(user.id))
    if count == 1:
        await redis.expire("rate:" + str(user.id), 60)
    if count > 30:
        raise HTTPException(status_code=429, detail="Please wait a minute before asking more questions.")

    session_id = body.session_id or str(uuid.uuid4())
    try:
        uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id must be a UUID.") from exc

    start_time = time.perf_counter()
    history_key = str(user.id) + ":" + session_id
    history = await get_history(history_key)
    cache_key = hashlib.sha256(f"{body.retrieval_config}:{body.question.lower().strip()}".encode()).hexdigest()
    cached = await get_cached_answer(cache_key) if not history else None
    if cached:
        cached["cached"] = True
        cached["session_id"] = session_id
        cached["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        if not body.include_contexts:
            cached.pop("contexts", None)
        history.extend([{"role": "user", "content": body.question}, {"role": "assistant", "content": cached["answer"]}])
        await save_history(history_key, history)
        return cached

    search_query = await rewrite_question(body.question, history)
    if not await is_policy_question(search_query):
        answer = "I can help with company workplace policies. Please ask a question related to leave, travel, IT security, conduct, or another company policy."
        result = {"answer": answer, "sources": [], "contexts": [], "refused": True}
    else:
        documents = await retrieve_documents(search_query, body.retrieval_config)
        # CHANGE 1: keep only FINAL_K documents, so the model reads exactly the same text
        # that is returned as "contexts" (and judged by the eval).
        documents = documents[:FINAL_K]
        if not documents:
            answer = "I could not find an answer in the current policy documents. Would you like me to escalate this to HR?"
        else:
            answer = await answer_question(body.question, documents, history)
        contexts = [document.page_content for document in documents]
        sources = [
            {"document": document.metadata.get("document"), "section": document.metadata.get("section"), "page": document.metadata.get("page")}
            for document in documents
        ]
        # CHANGE 2: also count "I could not find it in the documents" answers as refused.
        # Before, "refused" was True only when no documents came back, so a not-found answer
        # built from 3 unrelated documents was reported as refused = False.
        not_found = "could not find" in answer.lower()
        result = {"answer": answer, "sources": sources, "contexts": contexts, "refused": (not bool(documents)) or not_found}

    if not history:
        await save_cached_answer(cache_key, result)
    history.extend([{"role": "user", "content": body.question}, {"role": "assistant", "content": result["answer"]}])
    await save_history(history_key, history)
    result["cached"] = False
    result["session_id"] = session_id
    result["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
    if not body.include_contexts:
        result.pop("contexts", None)
    return result