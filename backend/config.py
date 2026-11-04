import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aegissupport_dev.db")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))
GROQ_MAX_CONCURRENT_REQUESTS = int(
    os.getenv("GROQ_MAX_CONCURRENT_REQUESTS", "8")
)
DETERMINISTIC_INTENT_ROUTING = os.getenv(
    "DETERMINISTIC_INTENT_ROUTING", "true"
).lower() in {"1", "true", "yes", "on"}
RAG_CACHE_TTL_SECONDS = int(os.getenv("RAG_CACHE_TTL_SECONDS", "300"))
RAG_CACHE_MAX_ENTRIES = int(os.getenv("RAG_CACHE_MAX_ENTRIES", "512"))
