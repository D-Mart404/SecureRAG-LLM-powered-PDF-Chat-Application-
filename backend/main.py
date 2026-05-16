"""SecureRAG FastAPI: JWT auth, sanitization, upload, Q&A, summarize."""
import json
import logging
import os
import sys
from time import perf_counter
from uuid import uuid4
import uvicorn
from typing import Annotated, Any

# Ultimate fix for Windows CP1252 charmap errors: Force UTF-8 for all console output
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding='utf-8')

# ── Pipeline logging — shows retrieval, rerank, vision, and context logs ──────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
# Silence noisy 3rd-party loggers that aren't useful for debugging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("langchain_core").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)


from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="SecureRAG API", version="1.0.0")

origins = [
    "http://localhost:8501",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "https://genai-rag-application.streamlit.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


oauth2 = OAuth2PasswordBearer(tokenUrl="/login")

@app.get("/ping")
def ping():
    """Ultra-lightweight endpoint for UptimeRobot/Keep-alive."""
    return {"status": "alive"}

def get_pwd_context():
    from passlib.context import CryptContext
    return CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginData(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class Query(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    chat_id: str | None = None
    chat_history: list[dict[str, Any]] = Field(default_factory=list)


class SummarizeBody(BaseModel):
    focus: str = Field(default="", max_length=500)
    chat_id: str | None = None


def users_map() -> dict[str, str]:
    from config import DEMO_USERS_JSON
    return json.loads(DEMO_USERS_JSON)


@app.post("/register")
def register(data: LoginData):
    from database import get_user_hash, create_user
    from auth import create_token
    # Check if user already exists
    if get_user_hash(data.username) or data.username in users_map():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Hash password and create
    pwd_context = get_pwd_context()
    hashed = pwd_context.hash(data.password)
    print(hashed)
    success = create_user(data.username, hashed)
    print(success)
    if not success:
        raise HTTPException(status_code=500, detail="Database error during registration")
    
    return {
        "token": create_token(data.username),
        "token_type": "bearer",
        "user": {"username": data.username},
    }


@app.post("/login")
def login(data: LoginData):
    from database import get_user_hash
    from auth import create_token
    db_hash = get_user_hash(data.username)
    # Check environmental dummy users as fallback
    if not db_hash:
        users = users_map()
        if data.username in users:
            # Check if it's already a hash or plain text
            stored = users[data.username]
            is_match = False
            pwd_context = get_pwd_context()
            try:
                # Try as hash first
                if pwd_context.identify(stored):
                    is_match = pwd_context.verify(data.password, stored)
                else:
                    is_match = (stored == data.password)
            except Exception:
                is_match = (stored == data.password)
            
            if is_match:
                return {"token": create_token(data.username), "token_type": "bearer"}
        
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    pwd_context = get_pwd_context()
    if not pwd_context.verify(data.password, db_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    return {"token": create_token(data.username), "token_type": "bearer"}


def current_user(token: Annotated[str, Depends(oauth2)]) -> str:
    from auth import verify_token
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


@app.post("/upload")
async def upload_pdf(
    user: Annotated[str, Depends(current_user)],
    file: UploadFile = File(...),
):
    name = file.filename or "upload.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    from ingest import ingest_pdf_bytes
    raw = await file.read()
    try:
        n, parser_name = ingest_pdf_bytes(raw, name, user)
    except ValueError as e:
        import traceback
        with open("MAIN_TRACE.txt", "w", encoding="utf-8") as f:
            f.write("VALUE_ERROR:\n" + traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        import traceback
        with open("MAIN_TRACE.txt", "w", encoding="utf-8") as f:
            f.write("GENERAL_EXCEPTION:\n" + traceback.format_exc())
        raise

    # CRITICAL: Clear the cached BM25+chain for this user so the next query
    # rebuilds the retriever from the freshly uploaded documents.
    # Without this, BM25 keeps searching its stale in-memory corpus and returns
    # completely unrelated chunks (e.g. ESG page instead of EBITDA table).
    from rag_pipeline import invalidate_rag_cache
    invalidate_rag_cache()

    return {"chunks_added": n, "filename": name, "user": user, "parser": parser_name}


@app.post("/query")
def query(q: Query, user: Annotated[str, Depends(current_user)]):
    import langsmith_setup  # noqa: F401
    from rag_pipeline import multimodal_rag_query
    from security import sanitize_input
    from database import get_chat_no, log_query
    from rag_pipeline import EMBEDDING_MODEL_NAME
    
    started_at = perf_counter()
    chat_id = q.chat_id or str(uuid4())
    chat_no = get_chat_no(user, chat_id)
    clean = sanitize_input(q.question)
    if not clean.strip():
        raise HTTPException(status_code=400, detail="Empty question after sanitization")
        
    # Build chat history from MongoDB — survives backend restarts + browser refreshes.
    # Frontend session_state is RAM-only; DB history is permanent.
    from database import get_recent_history
    history_msgs = q.chat_history or get_recent_history(user, chat_id=chat_id, n_pairs=3)

    # ── Multimodal RAG Pipeline ──────────────────────────────────────────────
    # This runs the full VisDoM pipeline:
    #   Textual retrieval → Page image identification → Visual analysis
    #   → Evidence aggregation → Three-step prompted generation
    result = multimodal_rag_query(user, clean, history_msgs)

    ans = result["answer"]

    logs = {
        "retrieved_chunks": [
            {
                "text": item.get("snippet", ""),
                "page": item.get("page"),
                "score": item.get("score"),
            }
            for item in result.get("text_sources", [])
        ],
        "embedding_model": EMBEDDING_MODEL_NAME,
        "vision_processing": "enabled" if result.get("visual_sources") else "disabled",
        "processing_time_ms": int((perf_counter() - started_at) * 1000),
        "thinking_steps": [
            "Rewriting query...",
            "Retrieving top-k chunks...",
            "Reranking...",
            "Generating answer...",
        ],
    }

    citations = result.get("source_pages", [])

    log_query(user, clean, ans, chat_id=chat_id, chat_no=chat_no, metadata={"logs": logs, "citations": citations})
    return {
        "answer": ans,
        "chat_id": chat_id,
        "chat_no": chat_no,
        "citations": citations,
        "logs": logs,
        "sources": result["text_sources"],
        "visual_sources": result["visual_sources"],
        "source_pages": result["source_pages"],
        "user": user,
    }


@app.post("/summarize")
def summarize(body: SummarizeBody, user: Annotated[str, Depends(current_user)]):
    import langsmith_setup  # noqa: F401
    from rag_pipeline import get_summarize_chain
    from security import sanitize_input
    from database import get_chat_messages
    from database import get_chat_no
    from database import log_query
    from llm_factory import get_chat_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    if body.chat_id:
        chat_no = get_chat_no(user, body.chat_id)
        messages = get_chat_messages(user, body.chat_id)
        transcript = "\n".join(
            f"{item['role'].upper()}: {item['content']}"
            for item in messages
            if item.get("content", "").strip()
        )
        llm = get_chat_llm(0.0)
        prompt = [
            SystemMessage(content="You summarize chat conversations clearly and concisely. Keep the summary grounded in the chat transcript."),
            HumanMessage(content=f"Summarize this chat session:\n\n{transcript}" if transcript else "Summarize this empty chat session."),
        ]
        response = llm.invoke(prompt)
        ans = response.content if hasattr(response, "content") else str(response)
        log_query(user, f"SUMMARIZE_CHAT:{body.chat_id}", ans, chat_id=body.chat_id, chat_no=chat_no, metadata={"type": "summary"})
        return {"summary": ans, "chat_id": body.chat_id, "chat_no": chat_no, "user": user}

    focus = sanitize_input(body.focus) or "main themes and important facts"
    out = get_summarize_chain(user).invoke({"input": focus})
    ans = str(out.get("answer", ""))
    log_query(user, "SUMMARIZE:" + focus[:200], ans, metadata={"type": "document_summary"})
    return {"summary": ans, "chat_id": body.chat_id, "user": user}
@app.get("/history")
def get_history(user: Annotated[str, Depends(current_user)]):
    from database import get_user_history
    history = get_user_history(user)
    return history

@app.delete("/history")
def delete_history(user: Annotated[str, Depends(current_user)]):
    from database import clear_user_history
    success = clear_user_history(user)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear history from database")
    return {"message": "History cleared successfully", "user": user}

@app.get("/health")
def health():
    from database import ping_mongo
    from config import LLM_BACKEND
    return {"status": "ok", "mongo": ping_mongo(), "llm_backend": LLM_BACKEND}

@app.get("/")
def read_root():
    return {"message": "SecureRAG Backend is running on Hugging Face"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
