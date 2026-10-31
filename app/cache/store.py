import json
from functools import lru_cache

from redis.asyncio import Redis

from app.config import CACHE_TTL, MEMORY_MESSAGES, MEMORY_TTL, REDIS_URL


@lru_cache
def get_redis():
    return Redis.from_url(REDIS_URL, decode_responses=True)


async def get_cached_answer(key):
    value = await get_redis().get("answer:" + key)
    return json.loads(value) if value else None


async def save_cached_answer(key, value):
    await get_redis().set("answer:" + key, json.dumps(value), ex=CACHE_TTL)


async def get_history(session_id):
    value = await get_redis().get("history:" + session_id)
    return json.loads(value) if value else []


async def save_history(session_id, history):
    history = history[-MEMORY_MESSAGES * 2:]
    await get_redis().set("history:" + session_id, json.dumps(history), ex=MEMORY_TTL)


async def clear_answer_cache():
    redis = get_redis()
    keys = [key async for key in redis.scan_iter("answer:*")]
    if keys:
        await redis.delete(*keys)
