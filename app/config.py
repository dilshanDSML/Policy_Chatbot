import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://policybot:policybot@postgres:5432/policybot",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "policybot")
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "openai/gpt-oss-120b")
SMALL_MODEL = os.getenv("SMALL_MODEL", "openai/gpt-oss-20b")

if LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGCHAIN_TRACING_V2"] = str(LANGSMITH_TRACING).lower()

VECTOR_K = 5
KEYWORD_K = 5
FINAL_K = 3
SCORE_THRESHOLD = 0.5

CACHE_TTL = 300
MEMORY_TTL = 1800
MEMORY_MESSAGES = 6

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "2000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
MIN_SECTION_CHARS = int(os.getenv("MIN_SECTION_CHARS", "100"))
