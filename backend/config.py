"""Environment-driven settings for SecureRAG backend."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

ROOT = Path(__file__).resolve().parent.parent

# --- Security Settings ---
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-use-openssl-rand")
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
DEMO_USERS_JSON = os.getenv(
    "DEMO_USERS_JSON",
    '{"admin":"admin123","analyst":"analyst123"}',
)

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# groq | ollama | local (Unsloth 4-bit base + PEFT from LORA_ADAPTER_DIR)
LLM_BACKEND = os.getenv("LLM_BACKEND", "groq").strip().lower()
LOCAL_BASE_MODEL = os.getenv("LOCAL_BASE_MODEL", "").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
MONGODB_VECTOR_COLLECTION = os.getenv("MONGODB_VECTOR_COLLECTION", "vectors")
MONGODB_VECTOR_INDEX = os.getenv("MONGODB_VECTOR_INDEX", "vector_index")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "").strip()

_ld_raw = os.getenv("LORA_ADAPTER_DIR")
if _ld_raw:
    _ldp = Path(_ld_raw).expanduser()
    LORA_ADAPTER_DIR = str(_ldp if _ldp.is_absolute() else (ROOT / _ldp))
else:
    LORA_ADAPTER_DIR = str(ROOT / "fine_tune_llama_3.2")

# --- Multimodal Vision Settings ---
# Llama 4 Scout — natively multimodal, available on Groq free tier
# Supports image + text in a single call via the standard OpenAI vision format.
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "meta-llama/llama-4-scout-17b-16e-instruct")
# Fallback: text-only model for chart insights when vision call fails
VISION_FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
# Maximum number of page images to analyze per query (cost/latency guardrail)
MAX_IMAGES_PER_QUERY = int(os.getenv("MAX_IMAGES_PER_QUERY", "3"))
# Local directory where extracted page images are persisted during this session
IMAGE_STORE_DIR = Path(
    os.getenv("IMAGE_STORE_DIR", str(Path(__file__).resolve().parent / "data" / "images"))
)
IMAGE_STORE_DIR.mkdir(parents=True, exist_ok=True)