"""Database layer: MongoDB-backed user store plus chat/session audit logs."""
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

import config  # noqa: F401 — loads .env via config side effect


def create_user(username: str, password_hash: str) -> bool:
    """Create a user in MongoDB."""
    try:
        db = get_db()
        if db is None:
            return False

        db.users.create_index("username", unique=True)
        db.users.insert_one({"username": username, "password": password_hash})
        return True
    except DuplicateKeyError:
        return False
    except PyMongoError:
        return False


def get_user_hash(username: str) -> str | None:
    """Look up a user password hash from MongoDB."""
    try:
        db = get_db()
        if db is None:
            return None

        user = db.users.find_one({"username": username})
        if user:
            return user.get("password")
    except PyMongoError:
        return None

    return None


# ── MongoDB (optional) ────────────────────────────────────────────────────────
_client: MongoClient | None = None


def get_client() -> MongoClient | None:
    global _client
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return None
    if _client is None:
        try:
            _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        except Exception:
            return None
    return _client


def get_db() -> Database[Any] | None:
    c = get_client()
    if c is None:
        return None
    name = os.getenv("MONGODB_DB", "securerag")
    return c[name]


def ping_mongo() -> bool:
    try:
        c = get_client()
        if c is None:
            return False
        c.admin.command("ping")
        return True
    except PyMongoError:
        return False


def _serialize_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def log_query(
    username: str,
    question: str,
    answer: str,
    chat_id: str | None = None,
    chat_no: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a single chat turn with session metadata."""
    try:
        db = get_db()
        if db is None:
            return
        db.audit_logs.insert_one(
            {
                "user": username,
                "chat_id": chat_id,
                "chat_no": chat_no,
                "question": question[:500],
                "answer": answer,
                "timestamp": datetime.now(timezone.utc),
                "metadata": metadata or {},
            }
        )
    except PyMongoError:
        return


def get_user_history(username: str) -> list[dict[str, Any]]:
    """Fetch grouped per-chat history for a user."""
    try:
        db = get_db()
        if db is None:
            return []
        cursor = db.audit_logs.find({"user": username}).sort([("timestamp", 1), ("_id", 1)])
        sessions: dict[str, dict[str, Any]] = {}
        order: list[str] = []

        for doc in cursor:
            chat_id = str(doc.get("chat_id") or doc.get("_id"))
            timestamp = _serialize_timestamp(doc.get("timestamp"))
            session = sessions.get(chat_id)
            if session is None:
                session = {
                    "chat_id": chat_id,
                    "chat_no": doc.get("chat_no"),
                    "messages": [],
                    "first_question": doc.get("question", ""),
                    "message_count": 0,
                    "last_updated": timestamp,
                    "updated_at": timestamp,
                }
                sessions[chat_id] = session
                order.append(chat_id)

            message = {
                "question": doc.get("question", ""),
                "answer": doc.get("answer", ""),
                "timestamp": timestamp,
                "metadata": doc.get("metadata", {}) or {},
                "logs": (doc.get("metadata", {}) or {}).get("logs", {}),
                "citations": (doc.get("metadata", {}) or {}).get("citations", []),
            }
            session["messages"].append(message)
            session["message_count"] = len(session["messages"])
            session["last_updated"] = timestamp
            session["updated_at"] = timestamp
            if session.get("chat_no") is None and doc.get("chat_no") is not None:
                session["chat_no"] = doc.get("chat_no")
            if not session.get("first_question") and message["question"]:
                session["first_question"] = message["question"]

        grouped = [sessions[chat_id] for chat_id in order]
        # Sort by chat_no descending so the newest chat is at the top
        grouped.sort(key=lambda x: x.get("chat_no") or 0, reverse=True)
        return grouped
    except PyMongoError:
        return []


def get_chat_messages(username: str, chat_id: str, n_pairs: int | None = None) -> list[dict[str, Any]]:
    """Fetch chronological messages for one chat session."""
    try:
        db = get_db()
        if db is None:
            return []

        query: dict[str, Any] = {"user": username, "chat_id": chat_id}
        cursor = db.audit_logs.find(query).sort([("timestamp", 1), ("_id", 1)])
        docs = list(cursor)
        if n_pairs is not None:
            docs = docs[-n_pairs:]

        messages: list[dict[str, Any]] = []
        for doc in docs:
            messages.append({"role": "user", "content": doc.get("question", "")})
            messages.append({"role": "assistant", "content": doc.get("answer", "")})
        return messages
    except PyMongoError:
        return []


def get_chat_no(username: str, chat_id: str) -> int:
    """Return an existing chat number for a session or allocate the next one."""
    try:
        db = get_db()
        if db is None:
            return 1

        existing = db.audit_logs.find_one({"user": username, "chat_id": chat_id, "chat_no": {"$ne": None}})
        if existing and existing.get("chat_no") is not None:
            try:
                return int(existing.get("chat_no"))
            except (TypeError, ValueError):
                pass

        distinct_chat_ids = db.audit_logs.distinct("chat_id", {"user": username})
        used_chat_ids = [value for value in distinct_chat_ids if value]
        return len(used_chat_ids) + 1
    except PyMongoError:
        return 1


def get_recent_history(username: str, chat_id: str | None = None, n_pairs: int = 3) -> list[dict]:
    """
    Fetch recent chat messages as LangChain-style messages.
    If chat_id is supplied, return that session; otherwise return the newest
    session for the user to preserve backwards compatibility.

    Returns list of dicts: [{"role": "user"|"assistant", "content": str}, ...]
    ordered oldest → newest (ready to pass to LangChain MessagesPlaceholder).
    """
    try:
        if chat_id:
            return get_chat_messages(username, chat_id, n_pairs=n_pairs)

        sessions = get_user_history(username)
        if not sessions:
            return []

        newest = sessions[0]
        messages: list[dict[str, Any]] = []
        for item in newest.get("messages", [])[-n_pairs:]:
            messages.append({"role": "user", "content": item.get("question", "")})
            messages.append({"role": "assistant", "content": item.get("answer", "")})
        return messages
    except PyMongoError:
        return []


def clear_user_history(username: str) -> bool:
    """Wipe chat history for a specific user from MongoDB."""
    try:
        db = get_db()
        if db is None:
            return False
        db.audit_logs.delete_many({"user": username})
        return True
    except PyMongoError:
        return False


def clear_all_history() -> bool:
    """Wipe the entire audit_logs collection."""
    try:
        db = get_db()
        if db is None:
            return False
        db.audit_logs.delete_many({})
        return True
    except PyMongoError:
        return False