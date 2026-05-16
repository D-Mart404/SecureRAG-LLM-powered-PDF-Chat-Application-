"""
SecureRAG — LangSmith tracing setup.

Enables LangSmith observability for all LangChain calls (retrieval,
reranking, LLM generation) when LANGCHAIN_TRACING_V2=true is set in .env.

Usage:
    import langsmith_setup  # import before any langchain code
    # or just ensure .env has LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root so this works whether run from repo root or backend/
_root = Path(__file__).resolve().parent
for candidate in [_root / ".env", _root.parent / ".env"]:
    if candidate.is_file():
        load_dotenv(candidate)
        break

_tracing = os.getenv("LANGCHAIN_TRACING_V2", "").lower() in ("1", "true", "yes")
_api_key = os.getenv("LANGCHAIN_API_KEY", "")
_project = os.getenv("LANGCHAIN_PROJECT", "SecureRAG")

if _tracing and _api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = _api_key
    os.environ["LANGCHAIN_PROJECT"] = _project
    print(f"[LangSmith] Tracing enabled → project: {_project}")
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    if not _api_key:
        print("[LangSmith] LANGCHAIN_API_KEY not set — tracing disabled.")